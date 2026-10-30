"""End-to-end HTTP coverage using Home Assistant's real frontend and APIs."""

from unittest.mock import patch

from aiohttp.test_utils import TestClient
from homeassistant.core import HomeAssistant
import pytest
from pytest_homeassistant_custom_component.typing import ClientSessionGenerator

from custom_components.favicon.const import DOMAIN

pytestmark = pytest.mark.e2e


async def configure_favicon(client: TestClient, title: str = "My home") -> str:
    """Configure the integration through the same HTTP API as the UI.

    Args:
        client (TestClient): Authenticated Home Assistant HTTP client.
        title (str): Desired page title.

    Returns:
        str: Created config entry identifier.
    """
    response = await client.post("/api/config/config_entries/flow", json={"handler": DOMAIN})
    assert response.status == 200
    form = await response.json()
    assert form["type"] == "form"
    response = await client.post(
        f"/api/config/config_entries/flow/{form['flow_id']}",
        json={"title": title, "icon_path": "/local/favicons/", "launch_icon_color": [18, 52, 86]},
    )
    assert response.status == 200
    result = await response.json()
    assert result["type"] == "create_entry"
    return result["result"]["entry_id"]


async def test_configure_and_serve_assets(
    favicon_frontend: HomeAssistant, hass_client: ClientSessionGenerator
) -> None:
    """Serve customized HTML, manifest and downloadable icons after UI setup.

    Args:
        favicon_frontend (HomeAssistant): Real frontend with local icon files.
        hass_client (ClientSessionGenerator): Authenticated HTTP client factory.
    """
    client = await hass_client()
    response = await client.get("/")
    assert "<title>Home Assistant</title>" in await response.text()
    await configure_favicon(client)
    await favicon_frontend.async_block_till_done()

    response = await client.get("/")
    assert response.status == 200
    html = await response.text()
    assert "<title>My home</title>" in html
    assert "/local/favicons/favicon.ico" in html
    assert "/local/favicons/favicon-apple-180x180.png" in html
    assert 'color="#123456"' in html

    response = await client.get("/manifest.json")
    assert response.status == 200
    manifest = await response.json()
    assert manifest["name"] == manifest["short_name"] == "My home"
    assert manifest["icons"] == [
        {"src": "/local/favicons/favicon-192x192.png", "sizes": "192x192", "type": "image/png"}
    ]
    for path in (
        "/local/favicons/favicon.ico",
        "/local/favicons/favicon-apple-180x180.png",
        manifest["icons"][0]["src"],
    ):
        response = await client.get(path)
        assert response.status == 200
        assert response.content_type.startswith("image/")
        assert await response.read()


async def test_empty_icon_directory_keeps_default_icons(
    favicon_frontend: HomeAssistant, hass_client: ClientSessionGenerator
) -> None:
    """Allow a title-only customization with an existing empty icon directory.

    Args:
        favicon_frontend (HomeAssistant): Real frontend with local icon files.
        hass_client (ClientSessionGenerator): Authenticated HTTP client factory.
    """
    client = await hass_client()
    response = await client.get("/manifest.json")
    default_icons = (await response.json())["icons"]
    response = await client.post("/api/config/config_entries/flow", json={"handler": DOMAIN})
    flow = await response.json()
    response = await client.post(
        f"/api/config/config_entries/flow/{flow['flow_id']}",
        json={"title": "Title only", "icon_path": "/local/empty/", "launch_icon_color": [0, 0, 0]},
    )
    assert response.status == 200
    assert (await response.json())["type"] == "create_entry"
    await favicon_frontend.async_block_till_done()
    response = await client.get("/")
    html = await response.text()
    assert "<title>Title only</title>" in html
    assert "/static/icons/favicon.ico" in html
    response = await client.get("/manifest.json")
    assert (await response.json())["icons"] == default_icons


async def test_options_and_removal_update_served_page(
    favicon_frontend: HomeAssistant, hass_client: ClientSessionGenerator
) -> None:
    """Refresh a previously served page after changing and removing settings.

    Args:
        favicon_frontend (HomeAssistant): Real frontend with local icon files.
        hass_client (ClientSessionGenerator): Authenticated HTTP client factory.
    """
    client = await hass_client()
    response = await client.get("/")
    original_html = await response.text()
    entry_id = await configure_favicon(client)
    await favicon_frontend.async_block_till_done()
    response = await client.get("/")
    assert "<title>My home</title>" in await response.text()

    response = await client.post(
        "/api/config/config_entries/options/flow", json={"handler": entry_id}
    )
    assert response.status == 200
    flow = await response.json()
    response = await client.post(
        f"/api/config/config_entries/options/flow/{flow['flow_id']}",
        json={"title": "New home", "icon_path": "/local/empty/", "launch_icon_color": [0, 0, 0]},
    )
    assert response.status == 200
    assert (await response.json())["type"] == "create_entry"
    await favicon_frontend.async_block_till_done()
    response = await client.get("/")
    html = await response.text()
    assert "<title>New home</title>" in html
    assert "/static/icons/favicon.ico" in html
    assert 'color="#000000"' in html
    assert html.count("customElements.whenDefined('ha-sidebar')") == 1

    response = await client.delete(f"/api/config/config_entries/entry/{entry_id}")
    assert response.status == 200
    await favicon_frontend.async_block_till_done()
    response = await client.get("/")
    html = await response.text()
    assert "<title>Home Assistant</title>" in html
    assert "/static/icons/favicon.ico" in html
    assert "New home" not in html
    assert html == original_html


async def test_frontend_preserves_redirects_and_errors(
    favicon_frontend: HomeAssistant, hass_client: ClientSessionGenerator
) -> None:
    """Keep frontend redirects and routing failures intact while branding is active.

    Args:
        favicon_frontend (HomeAssistant): Real frontend with local icon files.
        hass_client (ClientSessionGenerator): Authenticated HTTP client factory.
    """
    client = await hass_client()
    await configure_favicon(client)
    await favicon_frontend.async_block_till_done()
    response = await client.get("/not-a-panel")
    assert response.status == 404
    response = await client.post("/")
    assert response.status == 405
    with patch("homeassistant.components.onboarding.async_is_onboarded", return_value=False):
        response = await client.get("/", allow_redirects=False)
    assert response.status == 302
    assert response.headers["Location"] == "/onboarding.html"
