import logging
import re
from typing import TYPE_CHECKING, Any, Self, override
from urllib.parse import quote_plus

from brlaw_mcp_server.domain.base import BaseLegalPrecedent

if TYPE_CHECKING:
    from patchright.async_api import Page

_LOGGER = logging.getLogger(__name__)

_BASE_URL = "https://sistemas.tjes.jus.br/consulta-jurisprudencia"
_API_URL = f"{_BASE_URL}/api/search"
_PER_PAGE = 20
_MIN_EMENTA_LENGTH = 30
_MAX_QUOTED_TERMS_WITH_AND = 2

_FETCH_JS = """async ([url, retryUrl]) => {
    let resp = await fetch(url);
    if (resp.status === 403 && retryUrl) {
        resp = await fetch(retryUrl);
    }
    if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
    return await resp.json();
}"""


def _sanitize_query(query: str) -> tuple[str, str | None]:
    """Sanitize a query to avoid TJES WAF blocks.

    Returns (primary_query, fallback_query_or_none).
    The WAF blocks queries with 3+ quoted terms combined with AND.
    """
    quoted_terms = re.findall(r'"[^"]*"', query)

    if len(quoted_terms) <= _MAX_QUOTED_TERMS_WITH_AND:
        return query, None

    _LOGGER.warning(
        "TJES query has %d quoted terms (max %d with AND). Building fallback.",
        len(quoted_terms),
        _MAX_QUOTED_TERMS_WITH_AND,
    )

    # Fallback: remove all quotes so WAF doesn't block
    fallback = re.sub(r'"([^"]*)"', r'\1', query)
    return query, fallback


class TjesLegalPrecedent(BaseLegalPrecedent):
    """Model for a legal precedent from the Tribunal de Justiça do Espírito Santo (TJES)."""

    @staticmethod
    def _build_summary(doc: dict[str, Any]) -> str:  # pyright: ignore[reportExplicitAny]
        """Build a rich summary string from an API document."""
        parts: list[str] = []

        nr_processo: str = doc.get("nr_processo", "")  # pyright: ignore[reportAny]
        classe: str = doc.get("classe_judicial", "")  # pyright: ignore[reportAny]
        magistrado: str = doc.get("magistrado", "")  # pyright: ignore[reportAny]
        orgao: str = doc.get("orgao_julgador", "")  # pyright: ignore[reportAny]
        dt: str = doc.get("dt_juntada", "")  # pyright: ignore[reportAny]
        assunto: str = doc.get("assunto_principal", "")  # pyright: ignore[reportAny]

        if nr_processo:
            header = f"PROCESSO: {nr_processo}"
            if classe:
                header += f" — {classe}"
            parts.append(header)
        if magistrado:
            parts.append(f"RELATOR(A): {magistrado}")
        if orgao:
            parts.append(f"ÓRGÃO JULGADOR: {orgao}")
        if dt:
            parts.append(f"DATA: {dt[:10]}")
        if assunto:
            parts.append(f"ASSUNTO: {assunto}")

        ementa: str = doc.get("ementa", "")  # pyright: ignore[reportAny]
        if len(ementa.strip()) > _MIN_EMENTA_LENGTH:
            parts.append(f"\nEMENTA:\n{ementa.strip()}")
        else:
            acordao: str = doc.get("acordao") or doc.get("inteiro_teor") or ""
            if acordao.strip():
                parts.append(f"\nINTEIRO TEOR:\n{acordao.strip()}")

        return "\n".join(parts)

    @override
    @classmethod
    async def research(
        cls, browser: "Page", *, summary_search_prompt: str, desired_page: int = 1
    ) -> "list[Self]":
        _LOGGER.info(
            "Starting research for legal precedents authored by the TJES with the summary search prompt %s",
            repr(summary_search_prompt),
        )

        await browser.goto(f"{_BASE_URL}/", wait_until="networkidle")

        primary_query, fallback_query = _sanitize_query(summary_search_prompt)

        primary_url = (
            f"{_API_URL}?core=pje2g"
            f"&q={quote_plus(primary_query)}"
            f"&page={desired_page}"
            f"&per_page={_PER_PAGE}"
        )

        fallback_url: str | None = None
        if fallback_query:
            fallback_url = (
                f"{_API_URL}?core=pje2g"
                f"&q={quote_plus(fallback_query)}"
                f"&page={desired_page}"
                f"&per_page={_PER_PAGE}"
            )

        _LOGGER.debug("Fetching TJES API: %s", primary_url)
        if fallback_url:
            _LOGGER.debug("Fallback URL prepared: %s", fallback_url)

        try:
            result: dict[str, Any] = await browser.evaluate(  # pyright: ignore[reportExplicitAny, reportAny]
                _FETCH_JS, [primary_url, fallback_url]
            )
        except Exception as exc:
            _LOGGER.error("TJES API request failed: %s", exc)
            return []

        docs: list[dict[str, Any]] = result.get("docs", [])  # pyright: ignore[reportExplicitAny, reportAny]
        total: int = result.get("total", 0)  # pyright: ignore[reportAny]

        _LOGGER.info(
            "TJES API returned %d documents (total: %s) for page %d",
            len(docs),
            total,
            desired_page,
        )

        if not docs:
            return []

        precedents: list[Self] = []
        for doc in docs:
            summary = cls._build_summary(doc)
            if summary.strip():
                precedents.append(cls(summary=summary))

        _LOGGER.info("Built %d legal precedents from TJES results", len(precedents))

        return precedents
