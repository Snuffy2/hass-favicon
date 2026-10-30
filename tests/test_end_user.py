"""Chromium acceptance tests against the served Home Assistant page."""

from collections.abc import AsyncGenerator
import json
import re

from homeassistant.core import HomeAssistant
from playwright.async_api import Page, async_playwright, expect
import pytest
from pytest_homeassistant_custom_component.typing import ClientSessionGenerator

from tests.test_e2e import configure_favicon

pytestmark = [pytest.mark.end_user, pytest.mark.timeout(60)]


@pytest.fixture
async def browser_page(socket_enabled: None) -> AsyncGenerator[Page]:
    """Open an isolated Chromium page and close all browser resources afterward.

    Args:
        socket_enabled (None): Allow browser communication with the local server.

    Yields:
        Page: Fresh page in a disposable browser context.
    """
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch()
        try:
            context = await browser.new_context()
            page = await context.new_page()
            page.set_default_timeout(10000)
            yield page
        finally:
            await browser.close()


async def test_browser_title_icons_and_navigation(
    favicon_frontend: HomeAssistant,
    hass_client: ClientSessionGenerator,
    hass_access_token: str,
    browser_page: Page,
) -> None:
    """Display custom metadata and preserve the title after frontend navigation.

    Args:
        favicon_frontend (HomeAssistant): Real frontend with local icon files.
        hass_client (ClientSessionGenerator): Authenticated HTTP client factory.
        hass_access_token (str): Access token for the isolated test user.
        browser_page (Page): Isolated Chromium page.
    """
    client = await hass_client()
    title = 'Family "home" & </script><img src=x onerror=alert(1)>'
    await configure_favicon(client, title)
    await favicon_frontend.async_block_till_done()
    tokens = {
        "hassUrl": str(client.make_url("/")).rstrip("/"),
        "access_token": hass_access_token,
        "token_type": "Bearer",
        "expires": 4102444800000,
        "expires_in": 3600,
        "refresh_token": "test-only",
        "clientId": str(client.make_url("/")),
    }
    await browser_page.add_init_script(
        f"localStorage.setItem('hassTokens', {json.dumps(json.dumps(tokens))})"
    )
    response = await browser_page.goto(str(client.make_url("/")))
    assert response is not None and response.status == 200
    await expect(browser_page).to_have_title(re.compile(re.escape(title) + "$"))
    await expect(browser_page.locator('link[rel="icon"]')).to_have_attribute(
        "href", "/local/favicons/favicon.ico"
    )
    await expect(browser_page.locator('link[rel="apple-touch-icon"]')).to_have_attribute(
        "href", "/local/favicons/favicon-apple-180x180.png"
    )
    await expect(browser_page.locator('link[rel="mask-icon"]')).to_have_attribute(
        "color", "#123456"
    )

    await expect(browser_page.locator("ha-sidebar .title")).to_have_text(title)
    await expect(browser_page.locator("ha-sidebar .title img")).to_have_count(0)
    await browser_page.get_by_role("link", name="Settings", exact=True).click()
    await expect(browser_page).to_have_title(re.compile("Settings.*" + re.escape(title) + "$"))

    await browser_page.reload()
    await expect(browser_page.locator("ha-sidebar .title")).to_have_text(title)
    await expect(browser_page).to_have_title(re.compile("Settings.*" + re.escape(title) + "$"))
