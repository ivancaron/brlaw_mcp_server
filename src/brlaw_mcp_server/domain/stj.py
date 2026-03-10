"""STJ legal precedent scraper using direct HTTP requests.

Uses processo.stj.jus.br/SCON/pesquisar.jsp which is NOT behind
Cloudflare Turnstile (unlike scon.stj.jus.br). The response is
HTML with ISO-8859-1 encoding containing textarea elements with
the ementa text.
"""

import logging
import re
import unicodedata
from typing import TYPE_CHECKING, Self, override
from urllib.parse import quote

import httpx

from brlaw_mcp_server.domain.base import BaseLegalPrecedent

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

# Regex to extract ementa text from textarea elements
_EMENTA_PATTERN = re.compile(
    r'<textarea[^>]*id="textSemformatacao\d+"[^>]*>(.*?)</textarea>',
    re.DOTALL,
)


class StjLegalPrecedent(BaseLegalPrecedent):
    """Model for a legal precedent from the Superior Tribunal de Justica (STJ)."""

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
        """Extract ementa texts from the HTML response."""
        matches = _EMENTA_PATTERN.findall(html)
        _LOGGER.debug("Found %d ementa(s) in response", len(matches))

        if not matches:
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

        return [
            cls(summary=text.strip())
            for text in matches
            if text.strip()
        ]

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
