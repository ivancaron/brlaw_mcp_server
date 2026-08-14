"""Jurisprudencias.ai multi-court legal-precedent client (opt-in, token-gated).

Jurisprudencias.ai (https://jurisprudencias.ai) exposes a documented REST API
over a large index of Brazilian court decisions. Unlike the other sources in
this package, it is **not** a scrape of an official portal: it is a paid
third-party aggregator with an authenticated API. It is therefore wired as an
**additional, opt-in source** — it only activates when the environment variable
``JURISPRUDENCIAS_AI_TOKEN`` is set. Without a token the tool raises a clear
error and the remaining sources keep working untouched.

Why it earns a place beside LexML: it covers state courts and administrative
tribunals the dedicated scrapers don't reach in depth — TJSP, TJRS, TJMG, TJPR,
TJSC, TJRJ, TJCE, TJGO, TJMA, TJMT, plus TRF3/TRF4 and **CARF** (fiscal). It
does NOT cover the TJES (use the dedicated ``TjesLegalPrecedentsRequest`` tool
for the home court). Use this for persuasive, out-of-state breadth and for CARF
in tax matters.

Integration quirks discovered while testing the free tier (jul/2026), each
handled below:

* **Auth**: every endpoint requires ``Authorization: Bearer jur_...``; 401
  otherwise. The token is read from ``JURISPRUDENCIAS_AI_TOKEN``.
* **WAF blocks non-browser User-Agents** (Python's default UA got 403), so we
  send a browser-like UA — same tactic as the LexML/TJES clients.
* **WAF rejects accented queries** with a 400 HTML page. The ``q`` parameter is
  normalized to ASCII (accents stripped) before the request; the provider's
  search is accent-insensitive, so recall is unaffected. Spaces are fine.
* **Pagination is 0-indexed** (``page=0`` is the first page, 10 per page), while
  this package's interface is 1-based; we map ``desired_page - 1``.

The response body is clean UTF-8 (``httpx.Response.json()`` decodes it
correctly); no encoding repair is needed. (Apparent mojibake when eyeballing the
JSON is a cp1252 console artifact, not the payload.)

The official decision URL returned by the API (deep-link into the source
tribunal, e.g. e-SAJ for TJSP) is placed in ``full_text_url``, mirroring the
other clients.
"""

import logging
import os
import unicodedata
from typing import TYPE_CHECKING, Any, ClassVar, Self, override

import httpx

from jurismcp.domain.base import BaseLegalPrecedent

if TYPE_CHECKING:
    from patchright.async_api import Page

_LOGGER = logging.getLogger(__name__)

_TOKEN_ENV = "JURISPRUDENCIAS_AI_TOKEN"  # noqa: S105 — env var name, not a secret
_BASE_URL = "https://jurisprudencias.ai/api/v1"
_ISO_DATE_LEN = 10  # length of a "yyyy-mm-dd" prefix
_MAX_RETRIES = 2
_HTTP_TIMEOUT = 40.0

_HEADERS = {
    # The edge WAF blocks non-browser User-Agents (403); a browser UA is required.
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/131.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json",
    "Accept-Language": "pt-BR,pt;q=0.9,en-US;q=0.8,en;q=0.7",
}

# Known court ids (from GET /courts, jul/2026). Used to validate the `court`
# argument early with a helpful message instead of a raw API 404/422. The list
# may grow on the provider side; unknown ids are still forwarded to the API,
# which is the source of truth — we only warn.
_KNOWN_COURTS: frozenset[str] = frozenset({
    "stf", "stj", "tst", "trf3", "trf4", "carf",
    "tjce", "tjgo", "tjma", "tjmg", "tjmt", "tjpr",
    "tjrj", "tjrs", "tjsc", "tjsp",
})

_HTTP_UNAUTHORIZED = 401
_HTTP_FORBIDDEN = 403


def _ascii_query(prompt: str) -> str:
    """Strip accents so the WAF doesn't reject the query with a 400.

    Live testing showed accented/spaced queries hitting an HTML 400 page at the
    edge. Folding to ASCII (``tráfico`` -> ``trafico``) sidesteps it while the
    provider's own search remains accent-insensitive.
    """
    decomposed = unicodedata.normalize("NFKD", prompt)
    ascii_only = decomposed.encode("ascii", "ignore").decode("ascii")
    return " ".join(ascii_only.split()).strip()


def _format_date(raw: str) -> str:
    """Best-effort DD/MM/YYYY formatting; pass through unknown formats."""
    if not raw:
        return ""
    head = raw[:_ISO_DATE_LEN]
    if len(head) == _ISO_DATE_LEN and head[4] == "-" and head[7] == "-":  # ISO
        year, month, day = head.split("-")
        return f"{day}/{month}/{year}"
    return raw  # already BR-formatted (trial_date) or unknown


class JurisprudenciasAiLegalPrecedent(BaseLegalPrecedent):
    """Model for a decision returned by the Jurisprudencias.ai multi-court API."""

    requires_browser: ClassVar[bool] = False  # direct HTTP GET (JSON REST API)

    @classmethod
    def _parse_results(cls, data: dict[str, Any], court_id: str) -> list[Self]:
        """Extract precedents from the API's ``{data, meta, links}`` payload."""
        docs = data.get("data", []) or []
        if not docs:
            _LOGGER.info("Jurisprudencias.ai returned no results")
            return []

        results: list[Self] = []
        for doc in docs:
            excerpt = doc.get("summary") or doc.get("excerpt") or ""
            if not excerpt.strip():
                continue

            processo = doc.get("process_number", "") or ""
            tipo = doc.get("process_type", "") or ""
            relator = doc.get("rapporteur", "") or ""
            orgao = doc.get("adjudicating_body", "") or ""
            pub = _format_date(doc.get("publication_date", "") or "")
            julg = _format_date(doc.get("trial_date", "") or "")
            url = doc.get("url") or None

            meta_parts: list[str] = []
            if processo:
                meta_parts.append(f"Processo: {processo}")
            if tipo:
                meta_parts.append(f"Classe: {tipo}")
            if relator:
                meta_parts.append(f"Relator(a): {relator}")
            if orgao:
                meta_parts.append(f"Orgao Julgador: {orgao}")
            if julg:
                meta_parts.append(f"Julgamento: {julg}")
            elif pub:
                meta_parts.append(f"Publicacao: {pub}")

            header = "[" + " | ".join(meta_parts) + "]\n" if meta_parts else ""
            summary = (header + excerpt).strip()

            results.append(
                cls(
                    summary=summary,
                    full_text_url=url,
                    court=(doc.get("court") or court_id).upper(),
                )
            )

        _LOGGER.info(
            "Parsed %d precedent(s) from Jurisprudencias.ai (%s)",
            len(results),
            court_id,
        )
        return results

    @override
    @classmethod
    async def research(
        cls,
        browser: "Page",  # interface compatibility; not used (HTTP, no browser)
        *,
        summary_search_prompt: str,
        desired_page: int = 1,
        court: str = "",
    ) -> list[Self]:
        """Search Jurisprudencias.ai via authenticated HTTP GET.

        :param court: court id (e.g. ``tjsp``, ``tjrs``, ``carf``). Forwarded by
            the dispatcher from the request model's ``court`` field.
        """
        token = os.environ.get(_TOKEN_ENV, "").strip()
        if not token:
            raise RuntimeError(
                "Fonte Jurisprudencias.ai nao configurada: defina a variavel de "
                f"ambiente {_TOKEN_ENV} com um token 'jur_...' (gerado em "
                "https://jurisprudencias.ai/api-tokens) para ativar esta fonte. "
                "As demais fontes (STF/STJ/TST/TJES/LexML) nao dependem dela."
            )

        court_id = (court or "").strip().lower()
        if not court_id:
            raise RuntimeError(
                "Informe o tribunal (campo 'court'). Ids disponiveis: "
                + ", ".join(sorted(_KNOWN_COURTS))
            )
        if court_id not in _KNOWN_COURTS:
            _LOGGER.warning(
                "Jurisprudencias.ai: court id %r nao esta na lista conhecida; "
                "encaminhando mesmo assim (a API valida).",
                court_id,
            )

        query = _ascii_query(summary_search_prompt)
        params = {
            "q": query,
            # API pagination is 0-indexed; our interface is 1-based.
            "page": str(max(desired_page - 1, 0)),
        }
        url = f"{_BASE_URL}/courts/{court_id}/decisions"
        headers = {**_HEADERS, "Authorization": f"Bearer {token}"}

        _LOGGER.info(
            "Jurisprudencias.ai research: court=%s q=%r page=%d",
            court_id,
            query,
            desired_page,
        )

        last_error: Exception | None = None
        for attempt in range(1, _MAX_RETRIES + 1):
            try:
                async with httpx.AsyncClient(
                    timeout=_HTTP_TIMEOUT,
                    follow_redirects=True,
                ) as client:
                    response = await client.get(url, headers=headers, params=params)

                if response.status_code == _HTTP_UNAUTHORIZED:
                    raise RuntimeError(
                        "Jurisprudencias.ai: token invalido ou ausente (401). "
                        f"Confira a variavel {_TOKEN_ENV}."
                    )
                if response.status_code == _HTTP_FORBIDDEN:
                    raise RuntimeError(
                        "Jurisprudencias.ai: acesso bloqueado (403) — possivel "
                        "bloqueio de WAF."
                    )

                response.raise_for_status()
                return cls._parse_results(response.json(), court_id)

            except (httpx.HTTPError, RuntimeError) as exc:
                last_error = exc
                _LOGGER.warning(
                    "Jurisprudencias.ai attempt %d/%d failed: %s",
                    attempt,
                    _MAX_RETRIES,
                    exc,
                )
                # Auth/config errors won't fix themselves on retry — fail fast.
                if isinstance(exc, RuntimeError):
                    raise

        raise RuntimeError(
            f"Jurisprudencias.ai research failed after {_MAX_RETRIES} attempts"
        ) from last_error
