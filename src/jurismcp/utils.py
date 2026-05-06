import logging
from contextlib import asynccontextmanager
from typing import TYPE_CHECKING

from patchright.async_api import async_playwright

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator

    from patchright.async_api import BrowserContext

_LOGGER = logging.getLogger(__name__)


@asynccontextmanager
async def browser_factory(
    headless: bool = True,
) -> "AsyncGenerator[BrowserContext, None]":
    """Standard browser factory using patchright (Chromium). Used for STF and TST."""
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(
            headless=headless,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
            ],
        )
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/137.0.0.0 Safari/537.36",
            viewport={"width": 1920, "height": 1080},
            locale="pt-BR",
        )
        try:
            yield context
        finally:
            await context.close()
            await browser.close()
