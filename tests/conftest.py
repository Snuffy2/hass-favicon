"""Isolated frontend and icon files for integration and browser tests."""

from collections.abc import AsyncGenerator
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch

from homeassistant.components import frontend
from homeassistant.core import HomeAssistant
from homeassistant.setup import async_setup_component
from PIL import Image
import pytest


@pytest.fixture
def hass_config_dir(tmp_path: Path) -> str:
    """Use a writable, isolated Home Assistant configuration directory.

    Args:
        tmp_path (Path): Temporary directory for this test.

    Returns:
        str: Home Assistant configuration directory.
    """
    icon_dir = tmp_path / "www/favicons"
    icon_dir.mkdir(parents=True)
    (tmp_path / "www/empty").mkdir()
    image = Image.new("RGB", (192, 192), "red")
    image.save(icon_dir / "favicon.ico", sizes=[(32, 32)])
    image.save(icon_dir / "favicon-apple-180x180.png")
    image.save(icon_dir / "favicon-192x192.png")
    (icon_dir / "ignored.txt").write_text("Not an icon", encoding="utf-8")
    return str(tmp_path)


@pytest.fixture
async def favicon_frontend(
    hass: HomeAssistant, enable_custom_integrations: None
) -> AsyncGenerator[HomeAssistant]:
    """Start the real frontend with local icons and restore its global hooks.

    Args:
        hass (HomeAssistant): Home Assistant test instance.
        enable_custom_integrations (None): Enable loading this custom integration.

    Yields:
        HomeAssistant: Instance with a real frontend and isolated icon files.
    """
    original_template = frontend.IndexView.get_template
    manifest = deepcopy(frontend.MANIFEST_JSON.manifest)
    with patch("homeassistant.components.onboarding.async_is_onboarded", return_value=True):
        try:
            assert await async_setup_component(hass, "frontend", {})
            await hass.async_block_till_done()
            yield hass
        finally:
            frontend.IndexView.get_template = original_template
            frontend.MANIFEST_JSON.manifest.clear()
            frontend.MANIFEST_JSON.manifest.update(manifest)
            frontend.MANIFEST_JSON._serialize()
            frontend._async_render_index_cached.cache_clear()
