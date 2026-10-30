"""Exercise config-entry integration with the real frontend."""

from homeassistant.components import frontend
from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.favicon.const import CONF_ICON_COLOR, CONF_ICON_PATH, CONF_TITLE, DOMAIN

pytestmark = pytest.mark.integration


async def test_config_entry_options_and_removal(favicon_frontend: HomeAssistant) -> None:
    """Install, edit and remove through the public flow and entry managers.

    Args:
        favicon_frontend (HomeAssistant): Real frontend with local icon files.
    """
    hass = favicon_frontend
    original_icons = frontend.MANIFEST_JSON["icons"].copy()
    flow = await hass.config_entries.flow.async_init(DOMAIN, context={"source": "user"})
    assert flow["type"] is FlowResultType.FORM
    result = await hass.config_entries.flow.async_configure(
        flow["flow_id"],
        {
            CONF_TITLE: "First home",
            CONF_ICON_PATH: "/local/favicons/",
            CONF_ICON_COLOR: [18, 52, 86],
        },
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    await hass.async_block_till_done()
    entry = result["result"]
    assert entry.state is ConfigEntryState.LOADED
    original_runtime_data = entry.runtime_data
    assert entry.data[CONF_ICON_COLOR] == "#123456"
    assert frontend.MANIFEST_JSON["name"] == "First home"

    options = await hass.config_entries.options.async_init(entry.entry_id)
    assert options["type"] is FlowResultType.FORM
    changed = await hass.config_entries.options.async_configure(
        options["flow_id"],
        {
            CONF_TITLE: "Updated home",
            CONF_ICON_PATH: "/local/favicons/",
            CONF_ICON_COLOR: [255, 0, 0],
        },
    )
    assert changed["type"] is FlowResultType.CREATE_ENTRY
    await hass.async_block_till_done()
    assert entry.runtime_data is not original_runtime_data
    assert not original_runtime_data.active
    assert entry.runtime_data.active
    assert entry.data[CONF_TITLE] == "Updated home"
    assert entry.data[CONF_ICON_COLOR] == "#ff0000"
    assert entry.state is ConfigEntryState.LOADED
    assert frontend.MANIFEST_JSON["short_name"] == "Updated home"

    assert await hass.config_entries.async_remove(entry.entry_id)
    await hass.async_block_till_done()
    assert not hasattr(entry, "runtime_data")
    assert not hass.config_entries.async_entries(DOMAIN)
    assert frontend.MANIFEST_JSON["name"] == "Home Assistant"
    assert frontend.MANIFEST_JSON["icons"] == original_icons


@pytest.mark.parametrize("path", ["/config/www/favicons", "https://example.com/icons", ""])
async def test_invalid_path_can_be_corrected(favicon_frontend: HomeAssistant, path: str) -> None:
    """Keep failed input in the form and allow a corrected submission.

    Args:
        favicon_frontend (HomeAssistant): Real frontend with local icon files.
        path (str): Unsupported icon path submitted by the user.
    """
    hass = favicon_frontend
    flow = await hass.config_entries.flow.async_init(DOMAIN, context={"source": "user"})
    settings = {CONF_TITLE: "My home", CONF_ICON_PATH: path, CONF_ICON_COLOR: [1, 2, 3]}
    result = await hass.config_entries.flow.async_configure(flow["flow_id"], settings)
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "bad_path"}
    assert not hass.config_entries.async_entries(DOMAIN)
    settings[CONF_ICON_PATH] = "/local/favicons/"
    result = await hass.config_entries.flow.async_configure(flow["flow_id"], settings)
    assert result["type"] is FlowResultType.CREATE_ENTRY
    await hass.async_block_till_done()
    assert result["result"].state is ConfigEntryState.LOADED


async def test_single_instance(favicon_frontend: HomeAssistant) -> None:
    """Reject a second integration without modifying the existing entry.

    Args:
        favicon_frontend (HomeAssistant): Real frontend with local icon files.
    """
    hass = favicon_frontend
    entry = MockConfigEntry(domain=DOMAIN, data={CONF_TITLE: "Existing home"})
    entry.add_to_hass(hass)
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": "user"})
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "single_instance_allowed"
    assert entry.data[CONF_TITLE] == "Existing home"
