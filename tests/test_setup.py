"""Regression tests for Home Assistant setup and form contracts."""

from unittest.mock import patch

from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.helpers.data_entry_flow import FlowManagerIndexView
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.favicon import async_setup, async_setup_entry
from custom_components.favicon.config_flow import FaviconConfigFlow
from custom_components.favicon.const import CONF_ICON_COLOR, CONF_ICON_PATH, CONF_TITLE, DOMAIN


@pytest.mark.parametrize("configured", [False, True])
async def test_yaml_setup(hass: HomeAssistant, configured: bool) -> None:
    """Apply supplied YAML settings and leave an unconfigured frontend alone.

    Args:
        hass (HomeAssistant): Home Assistant test instance.
        configured (bool): Whether YAML settings are supplied.
    """
    settings = {CONF_ICON_PATH: "/local/favicons/", CONF_TITLE: "Test home"}
    config = {DOMAIN: settings} if configured else {}
    with patch("custom_components.favicon.apply_hooks", autospec=True, return_value=True) as apply:
        assert await async_setup(hass, config) is True
        if configured:
            apply.assert_awaited_once_with(hass, settings)
        else:
            apply.assert_not_awaited()


async def test_entry_setup_and_update(hass: HomeAssistant) -> None:
    """Return setup success while the registered update callback returns None.

    Args:
        hass (HomeAssistant): Home Assistant test instance.
    """
    entry = MockConfigEntry(domain=DOMAIN, data={CONF_TITLE: "Test home"})
    with patch("custom_components.favicon.apply_hooks", autospec=True, return_value=True) as apply:
        assert await async_setup_entry(hass, entry) is True
        apply.assert_awaited_once_with(hass, dict(entry.data))
        listener = entry.update_listeners[0]
        assert await listener(hass, entry) is None


async def test_user_form(hass: HomeAssistant) -> None:
    """Return a settings form whose schema accepts frontend selector values.

    Args:
        hass (HomeAssistant): Home Assistant test instance.
    """
    flow = FaviconConfigFlow()
    flow.hass = hass
    result = await flow.async_step_user()
    assert result["type"] is FlowResultType.FORM
    settings = {
        CONF_TITLE: "Test home",
        CONF_ICON_PATH: "/local/favicons/",
        CONF_ICON_COLOR: [255, 0, 0],
    }
    serialized = FlowManagerIndexView(hass.config_entries.flow)._prepare_result_json(result)
    assert {field["name"] for field in serialized["data_schema"]} == set(settings)
    schema = result["data_schema"]
    assert schema is not None
    assert schema(settings) == settings
