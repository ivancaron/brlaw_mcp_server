"""Cloudflare Turnstile challenge detection and resolution.

Adapted from the Turnstile-Solver technique (Theyka/Turnstile-Solver).
Designed to work with camoufox (Firefox anti-detect browser) which avoids
CDP-based detection that blocks Chromium automation.
"""

import asyncio
import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from patchright.async_api import Page

_LOGGER = logging.getLogger(__name__)

_CHALLENGE_TITLE_KEYWORDS = ("moment", "momento", "just a")
_TURNSTILE_IFRAME_URL_FRAGMENT = "challenges.cloudflare.com"
_MAX_SOLVE_ATTEMPTS = 20
_ATTEMPT_INTERVAL_SECONDS = 2.0
_CHECKBOX_X_OFFSET = 30
_POST_CLICK_WAIT_SECONDS = 3.0
_INITIAL_WAIT_SECONDS = 3.0


async def is_cloudflare_challenge(page: "Page") -> bool:
    """Detect whether the current page is a Cloudflare challenge."""
    title = (await page.title()).lower()
    return any(kw in title for kw in _CHALLENGE_TITLE_KEYWORDS)


async def solve_cloudflare_challenge(
    page: "Page",
    *,
    timeout_seconds: float = 90.0,
) -> bool:
    """Attempt to solve the Cloudflare Turnstile challenge on the current page.

    Uses two detection methods:
    1. Check if the page title changes (leaves the challenge page)
    2. Check if the cf-turnstile-response hidden input gets a value

    Returns True if the challenge was solved, False on timeout.
    """
    _LOGGER.info("Attempting to solve Cloudflare Turnstile challenge")

    # Wait for the Turnstile widget to fully render
    await asyncio.sleep(_INITIAL_WAIT_SECONDS)

    deadline = asyncio.get_event_loop().time() + timeout_seconds

    for attempt in range(1, _MAX_SOLVE_ATTEMPTS + 1):
        if asyncio.get_event_loop().time() >= deadline:
            _LOGGER.warning("Timeout reached while solving Cloudflare challenge")
            return False

        # Check resolution via title change
        if not await is_cloudflare_challenge(page):
            _LOGGER.info(
                "Cloudflare challenge resolved (title changed) after %d attempt(s)",
                attempt - 1,
            )
            return True

        # Check resolution via turnstile response token
        if await _has_turnstile_response(page):
            _LOGGER.info(
                "Cloudflare challenge resolved (token received) after %d attempt(s)",
                attempt - 1,
            )
            # Wait for redirect to complete
            await asyncio.sleep(2.0)
            return True

        turnstile_frame = _find_turnstile_frame(page)
        if turnstile_frame is None:
            _LOGGER.debug(
                "Turnstile iframe not found yet (attempt %d/%d)",
                attempt,
                _MAX_SOLVE_ATTEMPTS,
            )
            await asyncio.sleep(_ATTEMPT_INTERVAL_SECONDS)
            continue

        frame_element = await turnstile_frame.frame_element()
        bounding_box = await frame_element.bounding_box()

        if bounding_box is None:
            _LOGGER.debug("Could not get bounding box for Turnstile iframe")
            await asyncio.sleep(_ATTEMPT_INTERVAL_SECONDS)
            continue

        # Click the checkbox: offset from left edge, vertically centered
        click_x = bounding_box["x"] + _CHECKBOX_X_OFFSET
        click_y = bounding_box["y"] + bounding_box["height"] / 2

        _LOGGER.info(
            "Clicking Turnstile checkbox at (%.0f, %.0f) — attempt %d/%d",
            click_x,
            click_y,
            attempt,
            _MAX_SOLVE_ATTEMPTS,
        )

        await page.mouse.click(click_x, click_y)
        await asyncio.sleep(_POST_CLICK_WAIT_SECONDS)

        # Check if resolved after click
        if not await is_cloudflare_challenge(page):
            _LOGGER.info(
                "Cloudflare challenge solved on attempt %d", attempt
            )
            return True

        if await _has_turnstile_response(page):
            _LOGGER.info(
                "Cloudflare challenge token received on attempt %d", attempt
            )
            await asyncio.sleep(2.0)
            return True

    _LOGGER.warning(
        "Failed to solve Cloudflare challenge after %d attempts", _MAX_SOLVE_ATTEMPTS
    )
    return False


async def _has_turnstile_response(page: "Page") -> bool:
    """Check if the Turnstile response token has been set."""
    try:
        value = await page.input_value(
            "[name=cf-turnstile-response]", timeout=1000
        )
        return bool(value)
    except Exception:
        return False


def _find_turnstile_frame(page: "Page"):
    """Find the Turnstile challenge iframe among the page frames."""
    for frame in page.frames:
        if _TURNSTILE_IFRAME_URL_FRAGMENT in (frame.url or ""):
            return frame
    return None
