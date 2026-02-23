import logging
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

        encoded_query = quote_plus(summary_search_prompt)
        api_url = (
            f"{_API_URL}?core=pje2g"
            f"&q={encoded_query}"
            f"&page={desired_page}"
            f"&per_page={_PER_PAGE}"
        )

        _LOGGER.debug("Fetching TJES API: %s", api_url)

        result: dict[str, Any] = await browser.evaluate(  # pyright: ignore[reportExplicitAny, reportAny]
            """async (url) => {
                const resp = await fetch(url);
                if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
                return await resp.json();
            }""",
            api_url,
        )

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
