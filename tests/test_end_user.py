"""Chromium acceptance tests against the served Home Assistant page."""

from collections.abc import AsyncGenerator
import json
import re

from homeassistant.core import HomeAssistant
from playwright.async_api import Page, async_playwright, expect
import pytest
from pytest_homeassistant_custom_component.typing import ClientSessionGenerator

from tests.test_e2e import configure_favicon, launch_logo_svg

pytestmark = [pytest.mark.end_user, pytest.mark.timeout(60)]


@pytest.fixture(params=["chromium", "firefox", "webkit"])
async def browser_page(
    request: pytest.FixtureRequest, socket_enabled: None
) -> AsyncGenerator[Page]:
    """Open an isolated browser page and close all browser resources afterward.

    Args:
        request (pytest.FixtureRequest): Selected browser engine.
        socket_enabled (None): Allow browser communication with the local server.

    Yields:
        Page: Fresh page in a disposable browser context.
    """
    async with async_playwright() as playwright:
        browser = await getattr(playwright, request.param).launch()
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


async def test_browser_renders_recolored_launch_logo(
    favicon_frontend: HomeAssistant,
    hass_client: ClientSessionGenerator,
    browser_page: Page,
) -> None:
    """Render the served launch logo in the configured color.

    Args:
        favicon_frontend (HomeAssistant): Real frontend with local icon files.
        hass_client (ClientSessionGenerator): Authenticated HTTP client factory.
        browser_page (Page): Isolated browser page.
    """
    client = await hass_client()
    await configure_favicon(client)
    await favicon_frontend.async_block_till_done()
    html = await (await client.get("/")).text()
    match = re.search(r'<img class="ha-logo" src="([^"]+)"', html)
    assert match is not None and launch_logo_svg(html)

    await browser_page.set_content(f'<img id="logo" src="{match[1]}" width="120" height="120">')
    colors = await browser_page.evaluate(
        """async () => {
            const img = document.getElementById("logo");
            await img.decode();
            const canvas = document.createElement("canvas");
            canvas.width = canvas.height = 120;
            const context = canvas.getContext("2d");
            context.drawImage(img, 0, 0, 120, 120);
            const pixels = context.getImageData(0, 0, 120, 120).data;
            const near = (i, rgb) => rgb.every((value, c) => Math.abs(pixels[i + c] - value) <= 8);
            let custom = 0, original = 0;
            for (let i = 0; i < pixels.length; i += 4) {
                if (pixels[i + 3] < 250) continue;
                if (near(i, [0x12, 0x34, 0x56])) custom++;
                if (near(i, [0x18, 0xbc, 0xf2])) original++;
            }
            return {custom, original};
        }"""
    )
    assert colors["custom"] > 1000
    assert colors["original"] == 0
