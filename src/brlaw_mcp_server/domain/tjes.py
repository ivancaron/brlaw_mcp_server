"""TJES legal precedent scraper using direct HTTP requests.

Uses the REST API at sistemas.tjes.jus.br/consulta-jurisprudencia/api/search
which returns JSON with ementa, processo, magistrado, orgao_julgador, etc.

The API is a simple GET endpoint with no authentication or anti-bot protection,
making HTTP direct the most efficient approach (no browser needed).

Default core is 'pje2g' (2o grau PJe — acordaos colegiados), which is the
most relevant for jurisprudence research.
"""

import logging
import re
from typing import TYPE_CHECKING, Self, override

import httpx

from brlaw_mcp_server.domain.base import BaseLegalPrecedent

if TYPE_CHECKING:
    from patchright.async_api import Page

_LOGGER = logging.getLogger(__name__)

_SEARCH_URL = "https://sistemas.tjes.jus.br/consulta-jurisprudencia/api/search"
_RESULTS_PER_PAGE = 10
_MAX_RETRIES = 2
_HTTP_TIMEOUT = 30.0

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/131.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "pt-BR,pt;q=0.9,en-US;q=0.8,en;q=0.7",
    "Referer": "https://sistemas.tjes.jus.br/consulta-jurisprudencia/",
}

# HTML tag pattern for cleaning ementa text
_HTML_TAG_PATTERN = re.compile(r"<[^>]+>")
_WHITESPACE_PATTERN = re.compile(r"\s+")

# Pattern to detect winning dissent (voto vencedor por divergência) and extract the
# original rapporteur's name from the acórdão text. The TJES API indexes such
# decisions by the winner (redator), not the original relator, so we parse the
# composition line to recover the actual rapporteur.
_VOTO_VENCEDOR_PATTERN = re.compile(r"VOTO\s+VENCEDOR", re.IGNORECASE)
_RELATOR_ORIGINAL_PATTERN = re.compile(
    # Captures the name after "Relator:" in the composition line, ignoring
    # case and whitespace variations. Stops at common delimiters.
    r"Relator\s*:\s*Desembargador(?:\(a\))?\s+([A-ZÁÉÍÓÚÂÊÔÃÕÇ][^\n/]+?)(?:\s{2,}|\s*/|\s*\n|\s*Sess[ãa]o)",
    re.IGNORECASE,
)


def _clean_text(text: str) -> str:
    """Remove HTML tags and normalize whitespace from text."""
    text = _HTML_TAG_PATTERN.sub(" ", text)
    text = _WHITESPACE_PATTERN.sub(" ", text)
    return text.strip()


def _detect_winning_dissent(
    acordao_text: str, magistrado_api: str
) -> tuple[str | None, bool]:
    """Detect if the decision was rendered by a winning dissent.

    The TJES API returns the redator (winning rapporteur) in the `magistrado`
    field, regardless of whether the case was originally assigned to a different
    relator who lost the vote. We inspect the acórdão text to detect this and
    recover the original rapporteur's name.

    Returns:
        (relator_original_name, divergencia_vencedora_flag)
        - relator_original_name: name when different from magistrado_api, else None
        - divergencia_vencedora_flag: True when the decision is a winning dissent
    """
    if not acordao_text or "VOTO VENCEDOR" not in acordao_text.upper():
        return None, False

    match = _RELATOR_ORIGINAL_PATTERN.search(acordao_text)
    if not match:
        return None, False

    relator_orig = re.sub(r"\s+", " ", match.group(1)).strip().rstrip(",.")
    # Compare uppercased and stripped to detect divergence
    if relator_orig.upper() != magistrado_api.strip().upper():
        return relator_orig, True

    return None, False


class TjesLegalPrecedent(BaseLegalPrecedent):
    """Model for a legal precedent from the Tribunal de Justica do Espirito Santo (TJES)."""

    @classmethod
    def _parse_results(cls, data: dict) -> list[Self]:
        """Extract legal precedents from the API JSON response.

        Each document in the response has fields including:
        - ementa: the summary text (may contain HTML)
        - nr_processo: case number in CNJ format
        - classe_judicial: type of judicial action
        - magistrado: judge/relator name
        - orgao_julgador: judging body (chamber/section)
        - dt_juntada: date of the decision
        - assunto_principal: main subject
        - acordao: full text of the decision (used to populate full_text field)
        """
        docs = data.get("docs", [])
        total = data.get("total", 0)
        _LOGGER.debug("TJES API returned %d doc(s) (total: %d)", len(docs), total)

        if not docs:
            _LOGGER.info("No legal precedents found for the given search")
            return []

        results: list[Self] = []
        for doc in docs:
            # Capture the full text of the decision (may be tens of thousands of chars).
            # The TJES REST API returns the complete acórdão in this field on the same
            # response as the summary, so we populate full_text without an extra request.
            acordao_raw = doc.get("acordao", "") or ""
            acordao_full = _clean_text(acordao_raw) if acordao_raw else ""

            ementa = doc.get("ementa", "")
            if not ementa or not ementa.strip():
                # Some decisions have "Voto servindo como ementa" or empty ementa.
                # Build a minimal summary from the acordao text (kept truncated for
                # the summary field, which is meant to be a short ementa).
                if acordao_full:
                    ementa = acordao_full[:2000]
                else:
                    continue

            ementa = _clean_text(ementa)
            if not ementa:
                continue

            # Enrich ementa with metadata for better context
            nr_processo = doc.get("nr_processo", "")
            classe = doc.get("classe_judicial", "")
            magistrado = doc.get("magistrado", "")
            orgao = doc.get("orgao_julgador", "")
            dt = doc.get("dt_juntada", "")

            # Build a rich summary with metadata header + ementa
            metadata_parts = []
            if nr_processo:
                metadata_parts.append(f"Processo: {nr_processo}")
            if classe:
                metadata_parts.append(f"Classe: {classe}")
            if magistrado:
                metadata_parts.append(f"Relator(a): {magistrado}")
            if orgao:
                metadata_parts.append(f"Orgao Julgador: {orgao}")
            if dt:
                # Format date from ISO to DD/MM/YYYY
                date_part = dt[:10] if len(dt) >= 10 else dt
                try:
                    year, month, day = date_part.split("-")
                    metadata_parts.append(f"Data: {day}/{month}/{year}")
                except (ValueError, IndexError):
                    metadata_parts.append(f"Data: {date_part}")

            if metadata_parts:
                metadata_header = " | ".join(metadata_parts)
                summary = f"[{metadata_header}]\n{ementa}"
            else:
                summary = ementa

            # Detect winning dissent: API returns the redator (winner) as
            # `magistrado`, but the original relator may differ. We parse the
            # acórdão text to recover this when it occurs.
            relator_original, divergencia_vencedora = _detect_winning_dissent(
                acordao_full, magistrado
            )

            results.append(
                cls(
                    summary=summary,
                    full_text=acordao_full or None,
                    relator_original=relator_original,
                    divergencia_vencedora=divergencia_vencedora,
                )
            )

        _LOGGER.info("Parsed %d legal precedent(s) from TJES", len(results))
        return results

    @override
    @classmethod
    async def research(
        cls,
        browser: "Page",  # pyright: ignore[reportUnusedParameter]
        *,
        summary_search_prompt: str,
        desired_page: int = 1,
    ) -> list[Self]:
        """Search TJES jurisprudence via direct HTTP GET.

        The browser parameter is accepted for interface compatibility
        but is NOT used. This implementation calls the TJES REST API
        directly, which is faster and more reliable than browser automation.
        """
        _LOGGER.info(
            "Starting HTTP research for TJES legal precedents: %s (page %d)",
            repr(summary_search_prompt),
            desired_page,
        )

        params = {
            "core": "pje2g",
            "q": summary_search_prompt,
            "page": str(desired_page),
            "per_page": str(_RESULTS_PER_PAGE),
        }

        last_error: Exception | None = None

        for attempt in range(1, _MAX_RETRIES + 1):
            try:
                async with httpx.AsyncClient(
                    timeout=_HTTP_TIMEOUT,
                    verify=False,  # noqa: S501 — TJES cert chain sometimes incomplete
                    follow_redirects=True,
                ) as client:
                    response = await client.get(
                        _SEARCH_URL,
                        headers=_HEADERS,
                        params=params,
                    )

                _LOGGER.debug(
                    "TJES API response: status=%d, length=%d",
                    response.status_code,
                    len(response.content),
                )

                _http_forbidden = 403
                if response.status_code == _http_forbidden:
                    raise RuntimeError(
                        "TJES API returned 403 Forbidden (possible WAF block)"
                    )

                response.raise_for_status()

                data = response.json()
                return cls._parse_results(data)

            except (httpx.HTTPError, RuntimeError) as exc:
                last_error = exc
                _LOGGER.warning(
                    "TJES HTTP research attempt %d/%d failed: %s",
                    attempt,
                    _MAX_RETRIES,
                    exc,
                )

        raise RuntimeError(
            f"TJES research failed after {_MAX_RETRIES} attempts"
        ) from last_error
