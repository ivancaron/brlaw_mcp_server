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


def _clean_text(text: str) -> str:
    """Remove HTML tags and normalize whitespace from text."""
    text = _HTML_TAG_PATTERN.sub(" ", text)
    text = _WHITESPACE_PATTERN.sub(" ", text)
    return text.strip()


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
        - acordao: full text of the decision (not used here)
        """
        docs = data.get("docs", [])
        total = data.get("total", 0)
        _LOGGER.debug("TJES API returned %d doc(s) (total: %d)", len(docs), total)

        if not docs:
            _LOGGER.info("No legal precedents found for the given search")
            return []

        results: list[Self] = []
        for doc in docs:
            ementa = doc.get("ementa", "")
            if not ementa or not ementa.strip():
                # Some decisions have "Voto servindo como ementa" or empty ementa.
                # Try to build a minimal summary from the acordao text.
                acordao = doc.get("acordao", "")
                if acordao:
                    ementa = _clean_text(acordao)[:2000]
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

            results.append(cls(summary=summary))

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
