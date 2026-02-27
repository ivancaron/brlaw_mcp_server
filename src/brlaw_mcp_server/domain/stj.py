import contextlib
import logging
from typing import TYPE_CHECKING, Self, override

from patchright.async_api import TimeoutError

from brlaw_mcp_server.cloudflare import (
    is_cloudflare_challenge,
    solve_cloudflare_challenge,
)
from brlaw_mcp_server.domain.base import BaseLegalPrecedent

if TYPE_CHECKING:
    from patchright.async_api import Locator, Page

_LOGGER = logging.getLogger(__name__)

_MAX_RETRIES = 2
_NAV_TIMEOUT_MS = 30_000
_LOCATOR_TIMEOUT_MS = 30_000


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

    @classmethod
    async def _attempt_research(
        cls, browser: "Page", *, summary_search_prompt: str, desired_page: int
    ) -> "list[Self]":
        """Single attempt to perform research. May raise TimeoutError."""
        await browser.goto(
            "https://scon.stj.jus.br/SCON/", wait_until="domcontentloaded"
        )

        if await is_cloudflare_challenge(browser):
            _LOGGER.info("Cloudflare challenge detected on STJ, attempting to solve")
            solved = await solve_cloudflare_challenge(browser)
            if not solved:
                raise RuntimeError(
                    "Could not bypass Cloudflare challenge on STJ website"
                )
            _LOGGER.info("Cloudflare challenge solved successfully")

        # Wait for the actual page to be fully loaded and interactive
        await browser.wait_for_load_state("networkidle")
        await browser.wait_for_function(
            "() => document.readyState === 'complete'", timeout=_NAV_TIMEOUT_MS
        )
        _LOGGER.debug("STJ page fully loaded (readyState=complete)")

        adv_search_btn = browser.locator("#idMostrarPesquisaAvancada")
        await adv_search_btn.wait_for(state="visible", timeout=_LOCATOR_TIMEOUT_MS)
        await adv_search_btn.click()

        summary_input_locator = browser.locator("#ementa")
        await summary_input_locator.wait_for(state="visible", timeout=_LOCATOR_TIMEOUT_MS)
        await summary_input_locator.fill(summary_search_prompt)
        await summary_input_locator.press("Enter")

        await browser.locator("#corpopaginajurisprudencia").wait_for(
            state="visible", timeout=_NAV_TIMEOUT_MS
        )

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

    @override
    @classmethod
    async def research(
        cls, browser: "Page", *, summary_search_prompt: str, desired_page: int = 1
    ) -> "list[Self]":
        _LOGGER.info(
            "Starting research for legal precedents authored by the STJ with the summary search prompt %s",
            repr(summary_search_prompt),
        )

        last_error: Exception | None = None

        for attempt in range(1, _MAX_RETRIES + 1):
            try:
                return await cls._attempt_research(
                    browser,
                    summary_search_prompt=summary_search_prompt,
                    desired_page=desired_page,
                )
            except (TimeoutError, RuntimeError) as exc:
                last_error = exc
                _LOGGER.warning(
                    "STJ research attempt %d/%d failed: %s",
                    attempt,
                    _MAX_RETRIES,
                    exc,
                )
                if attempt < _MAX_RETRIES:
                    _LOGGER.info("Reloading STJ page for retry")
                    with contextlib.suppress(Exception):
                        await browser.goto(
                            "about:blank", wait_until="domcontentloaded"
                        )

        raise RuntimeError(
            f"STJ research failed after {_MAX_RETRIES} attempts"
        ) from last_error
