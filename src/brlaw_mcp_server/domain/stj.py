import logging
from typing import TYPE_CHECKING, Self, override

from patchright.async_api import TimeoutError

from brlaw_mcp_server.cloudflare import is_cloudflare_challenge, solve_cloudflare_challenge
from brlaw_mcp_server.domain.base import BaseLegalPrecedent

if TYPE_CHECKING:
    from patchright.async_api import Locator, Page

_LOGGER = logging.getLogger(__name__)


class StjLegalPrecedent(BaseLegalPrecedent):
    """Model for a legal precedent from the Superior Tribunal de Justiça (STJ)."""

    @staticmethod
    async def _get_raw_summary_locators(browser: "Page") -> "list[Locator]":
        """Get the locators of the raw summaries shown on the current page."""
        raw_summary_locators = await browser.locator(
            "textarea[id^=textSemformatacao]"
        ).all()

        _LOGGER.debug(
            "Found %d raw summary locators on the current page",
            len(raw_summary_locators),
        )

        if len(raw_summary_locators) == 0:
            try:
                error_message = await browser.locator("div.erroMensagem").text_content()
            except TimeoutError as e:
                raise RuntimeError(
                    "Unexpected behavior from the requested service"
                ) from e

            if (
                error_message is not None
                and "Nenhum documento encontrado!" in error_message
            ):
                _LOGGER.info(
                    "No legal precedents found",
                )
                return []

        return raw_summary_locators

    @override
    @classmethod
    async def research(
        cls, browser: "Page", *, summary_search_prompt: str, desired_page: int = 1
    ) -> "list[Self]":
        _LOGGER.info(
            "Starting research for legal precedents authored by the STJ with the summary search prompt %s",
            repr(summary_search_prompt),
        )

        await browser.goto("https://scon.stj.jus.br/SCON/")

        if await is_cloudflare_challenge(browser):
            _LOGGER.info("Cloudflare challenge detected on STJ, attempting to solve")
            solved = await solve_cloudflare_challenge(browser)
            if not solved:
                raise RuntimeError(
                    "Could not bypass Cloudflare challenge on STJ website"
                )
            _LOGGER.info("Cloudflare challenge solved successfully")

        await browser.locator("#idMostrarPesquisaAvancada").click()

        summary_input_locator = browser.locator("#ementa")
        await summary_input_locator.fill(summary_search_prompt)
        await summary_input_locator.press("Enter")

        await browser.locator("#corpopaginajurisprudencia").wait_for(state="visible")

        raw_summary_locators = await cls._get_raw_summary_locators(browser)

        current_page = 1
        while current_page != desired_page:
            next_page_anchor_locators = await browser.locator(
                "a.iconeProximaPagina"
            ).all()
            await next_page_anchor_locators[0].click()
            await browser.wait_for_event("load")  # pyright: ignore[reportUnknownMemberType]
            raw_summary_locators = await cls._get_raw_summary_locators(browser)

            current_page += 1

        return [
            cls(summary=text)
            for locator in raw_summary_locators
            if (text := await locator.text_content()) is not None
        ]
