"""STJ legal precedent scraper using direct HTTP requests.

Uses processo.stj.jus.br/SCON/pesquisar.jsp which is NOT behind
Cloudflare Turnstile (unlike scon.stj.jus.br). The response is
HTML with ISO-8859-1 encoding containing textarea elements with
the ementa text.
"""

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

_SEARCH_URL = "https://processo.stj.jus.br/SCON/pesquisar.jsp"
_RESULTS_PER_PAGE = 10
_MAX_RETRIES = 2
_HTTP_TIMEOUT = 30.0
_ENCODING = "iso-8859-1"

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/131.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "pt-BR,pt;q=0.9,en-US;q=0.8,en;q=0.7",
    "Content-Type": "application/x-www-form-urlencoded",
    "Origin": "https://processo.stj.jus.br",
    "Referer": "https://processo.stj.jus.br/SCON/",
}

# --- Patterns for the SCON result template (refreshed by STJ ~2025-2026) -----
#
# Each acordao on the SCON result page is wrapped in
#     <div class="row itemlistadocumentos p-2">...</div>
# The block contains, in order:
#   - process number inside <a href="/SCON/jurisprudencia/doc.jsp?...">REsp&nbsp;NNN</a>
#   - class (ACORDAO etc.) in <div class="small">(CLASSE)</div>
#   - relator in <div>Ministro/Ministra NAME</div>
#   - DJe date in <div>DJe DD/MM/AAAA</div>
#   - decision date in <div>Decisao: DD/MM/AAAA</div>
#   - optional indicators (IAC, repetitivo) in <div class="indicaIAC">
#   - summary ementa in <div class="clsResumoEmenta"> (with highlight markup)
#   - full ementa in <div class="clsEmentaCompleta">...</div> (preferred)
#
# Legacy fallback (older template, may still appear on edge cases):
#   - <a name="DOCN"></a> markers + <div class="documento"> blocks
#   - <textarea id="textSemformatacao\d+"> for the ementa
#   - inteiro_teor('/SCON/GetInteiroTeorDoAcordao?num_registro=...&dt_publicacao=...')

_ITEM_BLOCK_SPLIT = re.compile(
    r'(?=<div\s+class="row\s+itemlistadocumentos)',
)
_ITEM_BLOCK_START = re.compile(
    r'^<div\s+class="row\s+itemlistadocumentos',
)
_PROCESSO_RE = re.compile(
    r'<h4>\s*Processo\s*</h4>\s*<div>\s*<a[^>]*href="([^"]*)"[^>]*>([^<]+)</a>',
    re.DOTALL,
)
_CLASSE_RE = re.compile(r'<div\s+class="small">\(([^)]+)\)</div>')
_RELATOR_RE = re.compile(r'<div>\s*(Ministr[oa][^<]+?)\s*</div>')
_DJE_RE = re.compile(r'<div>\s*(DJe[^<]+?)\s*</div>')
_DECISAO_RE = re.compile(r'<div>\s*(Decis\w*:[^<]+?)\s*</div>')
_INDICADORES_RE = re.compile(
    r'<div\s+class="(?:indicaIAC|indicaRepetitivo|indicaAfetacao)[^"]*">'
    r'\s*([^<]+?)\s*</div>',
)
_EMENTA_COMPLETA_RE = re.compile(
    r'<div\s+class="clsEmentaCompleta"[^>]*>\s*(.*?)\s*</div>',
    re.DOTALL,
)
_EMENTA_RESUMO_RE = re.compile(
    r'<div\s+class="clsResumoEmenta"[^>]*>\s*(.*?)\s*</div>',
    re.DOTALL,
)
_HIGHLIGHT_RE = re.compile(
    r'<span\s+class=(?:"highlightBrs"|highlightBrs)[^>]*>(.*?)</span>',
    re.DOTALL,
)
_HTML_TAG_RE = re.compile(r'<[^>]+>')
_HTML_COMMENT_RE = re.compile(r'<!--.*?-->', re.DOTALL)
_NUM_DOCS_RE = re.compile(r'<span\s+class="numDocs">\s*([\d\.,]+)\s*ac[oó]rd[aã]os')

# Legacy patterns (old template)
_LEGACY_EMENTA_PATTERN = re.compile(
    r'<textarea[^>]*id="textSemformatacao\d+"[^>]*>(.*?)</textarea>',
    re.DOTALL,
)
_LEGACY_DOC_BLOCK_SPLIT = re.compile(r'<a name="DOC\d+"></a>', re.DOTALL)
_LEGACY_INTEIRO_TEOR_PATTERN = re.compile(
    r"GetInteiroTeorDoAcordao\?num_registro=(\d+)&(?:amp;)?dt_publicacao=([\d/]+)"
)
_STJ_BASE = "https://processo.stj.jus.br"


def _clean_html_inline(fragment: str) -> str:
    """Remove inline HTML markup from an ementa fragment.

    The SCON ementa contains <br>, <span class=highlightBrs> (search term
    highlights) and may include comments. We strip everything except the
    plain text content and collapse whitespace."""
    # Strip comments first (they can contain misleading content like "Campo TEMA")
    text = _HTML_COMMENT_RE.sub(" ", fragment)
    # Unwrap highlight spans, keeping their text
    text = _HIGHLIGHT_RE.sub(lambda m: m.group(1), text)
    # Replace <br> with newline
    text = re.sub(r"<br\s*/?>", "\n", text, flags=re.IGNORECASE)
    # Strip remaining tags
    text = _HTML_TAG_RE.sub("", text)
    # Decode HTML entities the cheap way (covers the common cases in SCON)
    text = (
        text.replace("&nbsp;", " ")
            .replace("&amp;", "&")
            .replace("&lt;", "<")
            .replace("&gt;", ">")
            .replace("&quot;", '"')
            .replace("&#39;", "'")
    )
    # Collapse multi-space (but preserve newlines from <br>)
    text = re.sub(r"[ \t]+", " ", text)
    # Trim spaces around newlines
    text = re.sub(r"\s*\n\s*", "\n", text)
    return text.strip()


class StjLegalPrecedent(BaseLegalPrecedent):
    """Model for a legal precedent from the Superior Tribunal de Justica (STJ)."""

    requires_browser: ClassVar[bool] = False  # direct HTTP POST to SCON

    @staticmethod
    def _build_form_body(
        summary_search_prompt: str,
        desired_page: int,
    ) -> bytes:
        """Build URL-encoded form body in ISO-8859-1 for the SCON search.

        The SCON server expects ISO-8859-1 encoding (charset declared in
        its HTML ``<meta>`` and ``Content-Type`` response header). Sending
        accented characters as UTF-8 causes search mismatches.

        Input strings are normalized to NFC form to handle NFD input that
        may come from MCP protocol JSON. NFD combining characters (e.g.
        ``a`` + U+0303 for ``ã``) do not exist in ISO-8859-1 and would
        cause encoding errors.
        """
        # Normalize Unicode to NFC (composed form) so that accented
        # characters like ã (U+00E3) are single codepoints that map
        # cleanly to ISO-8859-1, instead of NFD decomposed sequences
        # (a + combining tilde) which cannot be encoded in ISO-8859-1.
        summary_search_prompt = unicodedata.normalize("NFC", summary_search_prompt)

        _LOGGER.debug(
            "Building form body — query: %s (len=%d, bytes=%s)",
            repr(summary_search_prompt),
            len(summary_search_prompt),
            summary_search_prompt.encode("utf-8").hex(),
        )

        offset = (desired_page - 1) * _RESULTS_PER_PAGE + 1
        params = {
            "b": "ACOR",
            "O": "RR",
            "ementa": summary_search_prompt,
            "acao": "pesquisar",
            "novaConsulta": "true" if desired_page == 1 else "false",
            "i": str(offset),
            "tipoPesquisa": "tipoPesquisaGenerica",
            "thesaurus": "JURIDICO",
            "p": "true",
            "tp": "T",
        }
        # Encode each value as ISO-8859-1 percent-encoded
        parts = []
        for key, value in params.items():
            try:
                encoded_value = quote(value, safe="", encoding=_ENCODING)
            except UnicodeEncodeError:
                # Fallback: strip diacritics for chars outside ISO-8859-1
                _LOGGER.warning(
                    "ISO-8859-1 encoding failed for key=%s, stripping diacritics",
                    key,
                )
                normalized = unicodedata.normalize("NFD", value)
                stripped = "".join(
                    c for c in normalized if unicodedata.category(c) != "Mn"
                )
                encoded_value = quote(stripped, safe="", encoding=_ENCODING)
            parts.append(f"{key}={encoded_value}")

        body = "&".join(parts).encode("ascii")
        _LOGGER.debug("Form body: %s", body[:200])
        return body

    @classmethod
    def _parse_ementas(cls, html: str) -> list[Self]:
        """Extract ementa texts and inteiro-teor URLs from the HTML response.

        The current SCON template (refreshed by STJ in 2025-2026) wraps each
        acordao in ``<div class="row itemlistadocumentos p-2">`` and exposes
        the full ementa inside ``<div class="clsEmentaCompleta">``. The
        process number is rendered as an anchor whose href points to the
        details page (``/SCON/jurisprudencia/doc.jsp?...``), which we use as
        ``full_text_url``.

        Falls back to the legacy template (``<a name="DOCN">`` markers +
        ``<textarea id="textSemformatacao\\d+">``) when the modern block is
        absent — useful for older fixtures or transitional templates."""
        # First, try the modern template (current SCON, post-2025)
        modern_results = cls._parse_modern_template(html)
        if modern_results:
            return modern_results

        # No modern blocks — handle "no results" / error before falling back
        if "Nenhum documento encontrado" in html:
            _LOGGER.info("No legal precedents found for the given search")
            return []

        if "erroMensagem" in html:
            error_match = re.search(
                r'<div class="erroMensagem">(.*?)</div>', html, re.DOTALL
            )
            error_text = error_match.group(1).strip() if error_match else "Unknown"
            _LOGGER.warning("SCON returned an error: %s", error_text)
            return []

        # Legacy template fallback
        return cls._parse_legacy_template(html)

    @classmethod
    def _parse_modern_template(cls, html: str) -> list[Self]:
        """Parse the current SCON template (``itemlistadocumentos`` blocks)."""
        blocks = _ITEM_BLOCK_SPLIT.split(html)
        results: list[Self] = []

        for block in blocks:
            if not _ITEM_BLOCK_START.match(block):
                continue

            # Prefer the full ementa; fall back to the resumo if absent
            ementa_match = _EMENTA_COMPLETA_RE.search(block)
            if not ementa_match:
                ementa_match = _EMENTA_RESUMO_RE.search(block)
            if not ementa_match:
                continue

            ementa_raw = ementa_match.group(1)
            ementa_text = _clean_html_inline(ementa_raw)
            if not ementa_text:
                continue

            # Metadata header
            metadata_parts: list[str] = []
            proc_m = _PROCESSO_RE.search(block)
            href = proc_m.group(1) if proc_m else None
            processo = (
                _clean_html_inline(proc_m.group(2)) if proc_m else None
            )
            classe_m = _CLASSE_RE.search(block)
            relator_m = _RELATOR_RE.search(block)
            dje_m = _DJE_RE.search(block)
            decisao_m = _DECISAO_RE.search(block)
            indicador_m = _INDICADORES_RE.search(block)

            if processo:
                cabec = f"Processo: {processo}"
                if classe_m:
                    cabec += f" | Classe: {classe_m.group(1).strip()}"
                metadata_parts.append(cabec)
            if relator_m:
                metadata_parts.append(f"Relator(a): {relator_m.group(1).strip()}")
            if decisao_m:
                metadata_parts.append(decisao_m.group(1).strip())
            if dje_m:
                metadata_parts.append(dje_m.group(1).strip())
            if indicador_m:
                metadata_parts.append(f"Indicador: {indicador_m.group(1).strip()}")

            header = (
                "[" + " | ".join(metadata_parts) + "]\n" if metadata_parts else ""
            )
            summary = header + ementa_text

            # full_text_url — uses the doc.jsp href, made absolute
            full_text_url: str | None = None
            if href:
                if href.startswith("http"):
                    full_text_url = href
                elif href.startswith("/"):
                    full_text_url = f"{_STJ_BASE}{href}"

            results.append(cls(summary=summary, full_text_url=full_text_url))

        _LOGGER.debug(
            "Modern template parsed %d result block(s); %d with inteiro-teor URL",
            len(results),
            sum(1 for r in results if r.full_text_url),
        )
        return results

    @classmethod
    def _parse_legacy_template(cls, html: str) -> list[Self]:
        """Parse the legacy SCON template (``<a name='DOCN'>`` + textareas).

        Kept as fallback for fixtures and transitional pages.  This is the
        original parser preserved verbatim for compatibility."""
        chunks = _LEGACY_DOC_BLOCK_SPLIT.split(html)[1:]

        if not chunks:
            # Plain ementa extraction when neither modern nor legacy markers exist
            matches = _LEGACY_EMENTA_PATTERN.findall(html)
            return [cls(summary=text.strip()) for text in matches if text.strip()]

        results: list[Self] = []
        for chunk in chunks:
            ementa_match = _LEGACY_EMENTA_PATTERN.search(chunk)
            if not ementa_match:
                continue
            ementa = ementa_match.group(1).strip()
            if not ementa:
                continue

            url_match = _LEGACY_INTEIRO_TEOR_PATTERN.search(chunk)
            full_text_url: str | None = None
            if url_match:
                num_registro, dt_publicacao = url_match.group(1), url_match.group(2)
                full_text_url = (
                    f"{_STJ_BASE}/SCON/GetInteiroTeorDoAcordao"
                    f"?num_registro={num_registro}&dt_publicacao={dt_publicacao}"
                )

            results.append(cls(summary=ementa, full_text_url=full_text_url))

        _LOGGER.debug(
            "Legacy template parsed %d result block(s); %d with inteiro-teor URL",
            len(results),
            sum(1 for r in results if r.full_text_url),
        )
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
        """Search STJ jurisprudence via direct HTTP POST.

        The browser parameter is accepted for interface compatibility
        but is NOT used. This implementation bypasses Cloudflare by
        posting directly to processo.stj.jus.br instead of scon.stj.jus.br.
        """
        _LOGGER.info(
            "Starting HTTP research for STJ legal precedents: %s (page %d) "
            "[len=%d, is_NFC=%s, utf8_hex=%s]",
            repr(summary_search_prompt),
            desired_page,
            len(summary_search_prompt),
            unicodedata.is_normalized("NFC", summary_search_prompt),
            summary_search_prompt.encode("utf-8").hex(),
        )

        form_body = cls._build_form_body(summary_search_prompt, desired_page)
        last_error: Exception | None = None

        for attempt in range(1, _MAX_RETRIES + 1):
            try:
                async with httpx.AsyncClient(
                    timeout=_HTTP_TIMEOUT,
                    verify=False,  # noqa: S501 — STJ cert chain sometimes incomplete
                    follow_redirects=True,
                ) as client:
                    response = await client.post(
                        _SEARCH_URL,
                        headers=_HEADERS,
                        content=form_body,
                    )

                _LOGGER.debug(
                    "SCON HTTP response: status=%d, length=%d",
                    response.status_code,
                    len(response.content),
                )

                _http_forbidden = 403
                if response.status_code == _http_forbidden:
                    raise RuntimeError(
                        "STJ SCON returned 403 Forbidden (Cloudflare block)"
                    )

                response.raise_for_status()

                html = response.content.decode(_ENCODING)
                return cls._parse_ementas(html)

            except (httpx.HTTPError, RuntimeError) as exc:
                last_error = exc
                _LOGGER.warning(
                    "STJ HTTP research attempt %d/%d failed: %s",
                    attempt,
                    _MAX_RETRIES,
                    exc,
                )

        raise RuntimeError(
            f"STJ research failed after {_MAX_RETRIES} attempts"
        ) from last_error
