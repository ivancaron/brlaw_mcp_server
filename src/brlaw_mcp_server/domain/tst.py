import contextlib
import logging
from typing import TYPE_CHECKING, Self, override

from patchright.async_api import TimeoutError
from pydantic import field_validator

from brlaw_mcp_server.domain.base import BaseLegalPrecedent

if TYPE_CHECKING:
    from patchright.async_api import Page

_LOGGER = logging.getLogger(__name__)


class TstLegalPrecedent(BaseLegalPrecedent):
    """Model for a legal precedent from the Tribunal Superior do Trabalho (TST)."""

    @field_validator("summary")
    @classmethod
    def _remove_style_elements_from_summary(cls, v: str) -> str:
        """Remove style elements from the summary.

        On the TST website, the summary is split into multiple elements. In some cases,
        there's a <style> element among the <p> elements. Its data is not relevant at all to
        the summary, so we need to filter it out."""

        if not v.startswith("<!--"):
            return v

        for char_idx, char in enumerate(v):
            if char == ">" and v[char_idx - 2 : char_idx + 1] == "-->":
                return v[char_idx + 1 :].strip()

        raise RuntimeError(
            "Could not find the end of the style element inside the summary"
        )

    @override
    @classmethod
    async def research(
        cls, browser: "Page", *, summary_search_prompt: str, desired_page: int = 1
    ) -> "list[Self]":
        _LOGGER.info(
            "Starting research for legal precedents authored by the TST with the summary search prompt %s",
            repr(summary_search_prompt),
        )

        await browser.goto("https://jurisprudencia.tst.jus.br/")

        with contextlib.suppress(TimeoutError):
            await (
                browser.locator("span[class^='jss']")
                .filter(has_text="Fechar")
                .click(timeout=1000)
            )

        locator_summary_input = browser.locator("#campoTxtEmenta")
        await locator_summary_input.fill(summary_search_prompt)
        await locator_summary_input.press("Enter")

        await browser.locator("circle").wait_for(state="hidden", timeout=1000 * 30)

        # Each result block is a `div[id^=celulaLeiaMaisAcordao]` and may contain
        # one or more `<a>` linking to the inteiro teor (PDF or HTML). We try to
        # extract such a link by looking for anchors carrying suggestive text
        # ("Inteiro Teor", "Acórdão") or hrefs ending in `.pdf` / containing
        # `icAcessoOriginal`. Falls back to None when the link cannot be found.
        result_locators = await browser.locator("div[id^=celulaLeiaMaisAcordao]").all()

        precedents: list[Self] = []
        for locator in result_locators:
            text = await locator.text_content()
            if text is None:
                continue

            full_text_url: str | None = None
            try:
                anchors = await locator.locator("a").all()
                for anchor in anchors:
                    href = await anchor.get_attribute("href")
                    label = (await anchor.text_content() or "").strip().lower()
                    if not href:
                        continue
                    is_inteiro_teor = (
                        "inteiro" in label
                        or "acórdão" in label
                        or "acordao" in label
                        or href.lower().endswith(".pdf")
                        or "icacessooriginal" in href.lower()
                        or "consultadocumento" in href.lower()
                    )
                    if is_inteiro_teor:
                        # Resolve to absolute URL when href is relative
                        if href.startswith("/"):
                            full_text_url = f"https://jurisprudencia.tst.jus.br{href}"
                        elif href.startswith("http"):
                            full_text_url = href
                        else:
                            full_text_url = f"https://jurisprudencia.tst.jus.br/{href}"
                        break
            except Exception:
                # Best-effort extraction; URL is optional and the test layout
                # of the TST jurisprudence page may change.
                _LOGGER.debug("Could not extract TST inteiro teor URL", exc_info=True)

            precedents.append(cls(summary=text, full_text_url=full_text_url))

        _LOGGER.info(
            "Found %d legal precedents (%d with inteiro teor URL)",
            len(precedents),
            sum(1 for p in precedents if p.full_text_url),
        )

        return precedents
