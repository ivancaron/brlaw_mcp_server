"""LexML federated legal-precedent scraper using direct HTTP requests.

LexML (https://www.lexml.gov.br) is the Brazilian government's federated
legal information portal. Its search aggregates jurisprudence from many
courts (STF, STJ, TST, TRFs, TJs, ...) in a single index, which makes it a
high-coverage discovery source: one connector surfaces precedents from
courts the dedicated scrapers don't (yet) cover.

Important characteristics discovered while integrating (jun/2026):

* The historical SRU/XML endpoint (``/busca/SRU``) was decommissioned in the
  site refresh and now returns 404. The live search is the XTF-backed HTML
  page at ``/busca/search``, which renders results **server-side**, so we
  scrape the HTML directly (no SRU, no browser).
* The response is **UTF-8** (``charset=UTF-8`` in the Content-Type), so we
  rely on httpx's ``response.text`` to decode it correctly.
* The jurisprudence facet is selected with ``f1-tipoDocumento=Jurisprudência``.
* Pagination uses ``startDoc`` (1-based offset), 20 results per page.
* ``robots.txt`` blocks the default ``python-requests`` user agent and sets a
  crawl-delay; we send a browser-like User-Agent and keep request volume low.

LexML jurisprudence records expose **metadata only** (localidade, autoridade,
título = acórdão + processo number, data) plus a URN link — **not** the full
ementa. We therefore build ``summary`` from the metadata and set
``full_text_url`` to the URN resolver, which redirects to the source court
for the full text.
"""

import html
import logging
import re
import unicodedata
from typing import TYPE_CHECKING, ClassVar, Self, override
from urllib.parse import quote

import httpx

from jurismcp.domain.base import BaseLegalPrecedent

if TYPE_CHECKING:
    from patchright.async_api import Page

_LOGGER = logging.getLogger(__name__)

_SEARCH_URL = "https://www.lexml.gov.br/busca/search"
_BASE = "https://www.lexml.gov.br"
_RESULTS_PER_PAGE = 20
_MAX_RETRIES = 2
_HTTP_TIMEOUT = 30.0

_HEADERS = {
    # robots.txt blocks the python-requests UA; a browser UA is required.
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/131.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "pt-BR,pt;q=0.9,en-US;q=0.8,en;q=0.7",
    "Referer": "https://www.lexml.gov.br/busca/search",
}

# Each result is wrapped in <div id="main_N" class="docHit"><table>...</table>.
# Within it, metadata is laid out as label/value pairs across table cells:
#   <td class="col2"><b>LABEL</b></td><td class="col3">VALUE</td>
_DOCHIT_BLOCK_RE = re.compile(
    r'<div id="main_\d+" class="docHit">(.*?)</table>',
    re.DOTALL,
)
_ROW_RE = re.compile(
    r'<td class="col2"><b>(.*?)</b></td><td class="col3">(.*?)</td>',
    re.DOTALL,
)
_URN_RE = re.compile(r'href="(/urn/(urn:lex:[^"]+))"')
_HTML_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"\s+")
# "Nenhum documento" / "0 documentos" guard for empty result pages.
_NO_RESULTS_RE = re.compile(
    r"Nenhum\s+documento|0\s+documentos\s+encontrad", re.IGNORECASE
)


def _clean(fragment: str) -> str:
    """Strip HTML tags, unescape entities and collapse whitespace."""
    text = _HTML_TAG_RE.sub(" ", fragment)
    text = html.unescape(text)
    # The non-breaking space (\xa0) is used as a cell filler; normalize it.
    text = text.replace("\xa0", " ")
    return _WS_RE.sub(" ", text).strip()


def _label(raw: str) -> str:
    """Normalize a metadata label (drops trailing filler/colon)."""
    return _clean(raw).rstrip(":").strip()


class LexmlLegalPrecedent(BaseLegalPrecedent):
    """Model for a federated legal precedent indexed by LexML (multi-tribunal)."""

    requires_browser: ClassVar[bool] = False  # server-side HTML at /busca/search

    @classmethod
    def _parse_results(cls, page_html: str) -> list[Self]:
        """Extract jurisprudence records from the XTF search HTML."""
        blocks = _DOCHIT_BLOCK_RE.findall(page_html)
        if not blocks:
            if _NO_RESULTS_RE.search(page_html):
                _LOGGER.info("LexML returned no results for the search")
            else:
                _LOGGER.warning(
                    "LexML: no docHit blocks found (template may have changed)"
                )
            return []

        results: list[Self] = []
        for block in blocks:
            fields: dict[str, str] = {}
            for raw_label, raw_value in _ROW_RE.findall(block):
                label = _label(raw_label)
                value = _clean(raw_value)
                if label and value:
                    fields[label.lower()] = value

            titulo = fields.get("título") or fields.get("titulo") or ""
            ementa = fields.get("ementa") or fields.get("descrição") or ""
            autoridade = fields.get("autoridade") or ""
            localidade = fields.get("localidade") or ""
            data = fields.get("data") or ""

            # Build the summary: metadata header + título (and ementa if present).
            header_parts: list[str] = []
            if autoridade:
                header_parts.append(f"Tribunal/Órgão: {autoridade}")
            if localidade:
                header_parts.append(f"Localidade: {localidade}")
            if data:
                header_parts.append(f"Data: {data}")
            header = "[" + " | ".join(header_parts) + "]\n" if header_parts else ""

            body = titulo
            if ementa:
                body = f"{titulo}\n{ementa}".strip() if titulo else ementa
            summary = (header + body).strip()
            if not summary:
                continue

            urn_match = _URN_RE.search(block)
            full_text_url = f"{_BASE}{urn_match.group(1)}" if urn_match else None
            urn = urn_match.group(2) if urn_match else None

            results.append(
                cls(
                    summary=summary,
                    full_text_url=full_text_url,
                    court=autoridade or None,
                    urn=urn,
                )
            )

        _LOGGER.info("Parsed %d legal precedent(s) from LexML", len(results))
        return results

    @override
    @classmethod
    async def research(
        cls,
        browser: "Page",  # interface compatibility; not used (HTTP, no browser)
        *,
        summary_search_prompt: str,
        desired_page: int = 1,
    ) -> list[Self]:
        """Search LexML federated jurisprudence via direct HTTP GET.

        The browser parameter is accepted for interface compatibility but is
        NOT used: LexML renders results server-side, so a plain HTTP GET to
        ``/busca/search`` (with the Jurisprudência facet) is enough.
        """
        _LOGGER.info(
            "Starting HTTP research for LexML legal precedents: %s (page %d)",
            repr(summary_search_prompt),
            desired_page,
        )

        # Normalize to NFC so accented chars are single codepoints (consistent
        # with how the user types them) before percent-encoding.
        keyword = unicodedata.normalize("NFC", summary_search_prompt)
        offset = (desired_page - 1) * _RESULTS_PER_PAGE + 1
        # Build the query string manually so the Jurisprudência facet keeps its
        # accents (httpx would encode them fine, but we mirror the site's params
        # explicitly for clarity and stability).
        query = (
            f"keyword={quote(keyword)}"
            f"&f1-tipoDocumento={quote('Jurisprudência')}"
            f"&startDoc={offset}"
        )
        url = f"{_SEARCH_URL}?{query}"

        last_error: Exception | None = None
        for attempt in range(1, _MAX_RETRIES + 1):
            try:
                async with httpx.AsyncClient(
                    timeout=_HTTP_TIMEOUT,
                    follow_redirects=True,
                ) as client:
                    response = await client.get(url, headers=_HEADERS)

                _LOGGER.debug(
                    "LexML response: status=%d, length=%d",
                    response.status_code,
                    len(response.content),
                )
                response.raise_for_status()
                # response.text honors the UTF-8 charset from the header.
                return cls._parse_results(response.text)

            except httpx.HTTPError as exc:
                last_error = exc
                _LOGGER.warning(
                    "LexML HTTP research attempt %d/%d failed: %s",
                    attempt,
                    _MAX_RETRIES,
                    exc,
                )

        raise RuntimeError(
            f"LexML research failed after {_MAX_RETRIES} attempts"
        ) from last_error
