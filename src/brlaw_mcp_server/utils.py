from contextlib import asynccontextmanager
from typing import TYPE_CHECKING

from patchright.async_api import async_playwright

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator

    from playwright.async_api import BrowserContext


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


@asynccontextmanager
async def stealth_browser_factory(
    headless: bool = True,
) -> "AsyncGenerator[BrowserContext, None]":
    """Stealth browser factory using camoufox (Firefox). Used for Cloudflare-protected sites."""
    from camoufox.async_api import AsyncCamoufox

    async with AsyncCamoufox(
        headless=headless,
        i_know_what_im_doing=True,
    ) as browser:
        context = await browser.new_context(ignore_https_errors=True)
        try:
            yield context
        finally:
            await context.close()
