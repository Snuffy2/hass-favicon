"""Regression tests for Home Assistant setup and form contracts."""

import html
import json
from pathlib import Path
import re
from types import SimpleNamespace
from unittest.mock import patch

from homeassistant.components import frontend
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.helpers.data_entry_flow import FlowManagerIndexView
from jinja2 import Template
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry
import yaml

from custom_components.favicon import (
    CONFIG_SCHEMA,
    async_remove_entry,
    async_setup,
    async_setup_entry,
    async_unload_entry,
    find_icons,
    remove_hooks,
)
from custom_components.favicon.config_flow import FaviconConfigFlow
from custom_components.favicon.const import CONF_ICON_COLOR, CONF_ICON_PATH, CONF_TITLE, DOMAIN


def _create_icon_files(directory: Path, filenames: tuple[str, ...]) -> None:
    """Create the local files needed by icon discovery tests.

    Args:
        directory (Path): Directory in the Home Assistant configuration path.
        filenames (tuple[str, ...]): Icon filenames to create.
    """
    directory.mkdir(parents=True, exist_ok=True)
    for filename in filenames:
        (directory / filename).touch()


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


def test_yaml_schema_accepts_sample_configuration() -> None:
    """Validate the supported YAML keys while permitting other HA sections."""
    sample_path = Path(__file__).parents[1] / "test" / "configuration.yaml"
    configuration = yaml.safe_load(sample_path.read_text(encoding="utf-8"))

    assert CONFIG_SCHEMA(configuration) == configuration


async def test_custom_title_is_rendered_safely_and_unload_restores_frontend(
    hass: HomeAssistant, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Escape custom title output and restore cached frontend state on unload.

    Args:
        hass (HomeAssistant): Home Assistant test instance.
        monkeypatch (pytest.MonkeyPatch): Fixture for replacing frontend interfaces.
    """
    index_view = frontend.IndexView(None, hass)
    monkeypatch.setattr(
        hass,
        "http",
        SimpleNamespace(
            app=SimpleNamespace(router=SimpleNamespace(resources=lambda: [index_view]))
        ),
    )
    monkeypatch.setattr(
        frontend.IndexView,
        "get_template",
        lambda _self: Template(
            '<html><head><title>Home Assistant</title><link rel="icon" '
            'href="/static/icons/favicon.ico"><link rel="apple-touch-icon" '
            'href="/static/icons/favicon-apple-180x180.png"><link rel="mask-icon" '
            'href="/static/icons/mask-icon.svg" color="#18bcf2"></head>'
            '<body><svg><path fill="#18bcf2"></path></svg></body></html>'
        ),
    )
    original_get_template = frontend.IndexView.get_template
    yaml_icon_directory = Path(hass.config.path("www/yaml-favicons"))
    await hass.async_add_executor_job(
        _create_icon_files,
        yaml_icon_directory,
        ("favicon.ico", "favicon-apple-180x180.png", "favicon-192x192.png"),
    )
    title = 'Lab "quoted"\n</script><img src=x onerror=alert(1)>'
    config = {
        DOMAIN: {
            CONF_TITLE: title,
            CONF_ICON_PATH: "/local/yaml-favicons/",
            CONF_ICON_COLOR: "#ff0000",
        }
    }

    assert await async_setup(hass, config) is True
    rendered = index_view.get_template().render()

    assert f"<title>{html.escape(title)}</title>" in rendered
    serialized_title = re.search(r"const title = (.+);", rendered)
    assert serialized_title is not None
    assert json.loads(serialized_title.group(1)) == title
    assert "</script><img" not in rendered
    assert 'querySelector(".title").textContent = title' in rendered
    assert 'querySelector(".title").innerHTML' not in rendered
    assert 'href="/static/icons/mask-icon.svg" color="#ff0000"' in rendered
    assert '<path fill="#ff0000">' in rendered
    assert 'href="/local/yaml-favicons/favicon.ico"' in rendered
    assert 'href="/local/yaml-favicons/favicon-apple-180x180.png"' in rendered

    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            CONF_TITLE: "Entry title",
            CONF_ICON_PATH: "/local/entry-icons/",
            CONF_ICON_COLOR: "#00ff00",
        },
    )
    assert await async_setup_entry(hass, entry) is True
    entry_rendered = index_view.get_template().render()
    assert "<title>Entry title</title>" in entry_rendered
    assert 'color="#00ff00"' in entry_rendered

    for view in hass.http.app.router.resources():
        if isinstance(view, frontend.IndexView):
            view._template_cache = Template("cached custom page")
    assert await async_unload_entry(hass, entry) is True
    assert all(
        view._template_cache is None
        for view in hass.http.app.router.resources()
        if isinstance(view, frontend.IndexView)
    )
    assert frontend.MANIFEST_JSON["icons"] == [
        {
            "src": "/local/yaml-favicons/favicon-192x192.png",
            "sizes": "192x192",
            "type": "image/png",
        }
    ]
    assert frontend.MANIFEST_JSON["name"] == title
    assert frontend.MANIFEST_JSON["short_name"] == title
    yaml_rendered = index_view.get_template().render()
    assert f"<title>{html.escape(title)}</title>" in yaml_rendered
    assert 'color="#ff0000"' in yaml_rendered
    assert 'href="/local/yaml-favicons/favicon.ico"' in yaml_rendered
    assert await async_remove_entry(hass, entry) is True
    assert frontend.MANIFEST_JSON["name"] == title
    assert await async_remove_entry(hass, entry) is True
    remove_hooks(hass)
    assert frontend.IndexView.get_template is original_get_template


async def test_icon_urls_encode_reserved_filesystem_characters(
    hass: HomeAssistant, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Encode special filesystem characters in emitted icon and manifest URLs.

    Args:
        hass (HomeAssistant): Home Assistant test instance.
        monkeypatch (pytest.MonkeyPatch): Fixture for replacing the frontend template.
    """
    path_str = "/local/favicons#2"
    icon_directory = Path(hass.config.path("www/favicons#2"))
    filenames = (
        "favicon.ico",
        'favicon-apple-180x180 #? ".png',
        'favicon-192x192.png #? ".png',
    )
    await hass.async_add_executor_job(_create_icon_files, icon_directory, filenames)

    monkeypatch.setattr(
        frontend.IndexView,
        "get_template",
        lambda _self: Template(
            '<html><head><link rel="icon" href="/static/icons/favicon.ico">'
            '<link rel="apple-touch-icon" '
            'href="/static/icons/favicon-apple-180x180.png"></head><body></body></html>'
        ),
    )
    icons = find_icons(hass, path_str)
    favicon_url = "/local/favicons%232/favicon.ico"
    apple_url = "/local/favicons%232/favicon-apple-180x180%20%23%3F%20%22.png"
    manifest_url = "/local/favicons%232/favicon-192x192.png%20%23%3F%20%22.png"
    assert icons["favicon"] == favicon_url
    assert icons["apple"] == apple_url
    assert icons["manifest"] == [{"src": manifest_url, "sizes": "192x192", "type": "image/png"}]

    assert await async_setup(hass, {DOMAIN: {CONF_ICON_PATH: path_str}}) is True
    rendered = frontend.IndexView(None, hass).get_template().render()
    assert f'href="{favicon_url}"' in rendered
    assert f'href="{apple_url}"' in rendered
    assert frontend.MANIFEST_JSON["icons"] == icons["manifest"]
    remove_hooks(hass)


async def test_entry_unload_restores_defaults_without_yaml(hass: HomeAssistant) -> None:
    """Restore the default frontend when an entry has no YAML configuration.

    Args:
        hass (HomeAssistant): Home Assistant test instance.
    """
    original_manifest_icons = frontend.MANIFEST_JSON["icons"].copy()
    await async_setup(hass, {})
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_TITLE: "Entry only", CONF_ICON_PATH: "/local/missing-icons/"},
    )
    with patch("custom_components.favicon.apply_hooks", autospec=True, return_value=True):
        assert await async_setup_entry(hass, entry) is True
    assert await async_unload_entry(hass, entry) is True
    assert frontend.MANIFEST_JSON["icons"] == original_manifest_icons
    assert frontend.MANIFEST_JSON["name"] == "Home Assistant"
    assert frontend.MANIFEST_JSON["short_name"] == "Assistant"
    assert await async_remove_entry(hass, entry) is True
    assert frontend.MANIFEST_JSON["name"] == "Home Assistant"


async def test_entry_unload_unregisters_update_listener(hass: HomeAssistant) -> None:
    """Remove the update listener when Home Assistant processes entry unload.

    Args:
        hass (HomeAssistant): Home Assistant test instance.
    """
    entry = MockConfigEntry(domain=DOMAIN, data={CONF_TITLE: "Test home"})
    entry.add_to_hass(hass)

    assert await async_setup(hass, {}) is True
    with patch("custom_components.favicon.apply_hooks", autospec=True, return_value=True):
        assert await async_setup_entry(hass, entry) is True
    assert len(entry.update_listeners) == 1

    assert await async_unload_entry(hass, entry) is True
    await entry._async_process_on_unload(hass)
    assert entry.update_listeners == []


async def test_entry_setup_and_update(hass: HomeAssistant) -> None:
    """Return setup success while the registered update callback returns None.

    Args:
        hass (HomeAssistant): Home Assistant test instance.
    """
    entry = MockConfigEntry(domain=DOMAIN, data={CONF_TITLE: "Test home"})
    entry.add_to_hass(hass)
    with patch("custom_components.favicon.apply_hooks", autospec=True, return_value=True) as apply:
        assert await async_setup_entry(hass, entry) is True
        apply.assert_awaited_once_with(hass, dict(entry.data))
        listener = entry.update_listeners[0]
        assert await listener(hass, entry) is None

        updated_settings = {CONF_TITLE: "Updated home"}
        apply.reset_mock()
        assert hass.config_entries.async_update_entry(entry, data=updated_settings)
        await hass.async_block_till_done()
        apply.assert_awaited_once_with(hass, updated_settings)


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

    result = await flow.async_step_user(settings)
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"][CONF_ICON_COLOR] == "#ff0000"


async def test_options_flow(hass: HomeAssistant, enable_custom_integrations: None) -> None:
    """Open and save settings through HA's options flow manager.

    Args:
        hass (HomeAssistant): Home Assistant test instance.
        enable_custom_integrations (None): Enable loading the integration flow.
    """
    settings = {
        CONF_TITLE: "Test Home Assistant",
        CONF_ICON_PATH: "/local/favicons/",
        CONF_ICON_COLOR: "#18bcf2",
    }
    entry = MockConfigEntry(domain=DOMAIN, data=settings)
    entry.add_to_hass(hass)
    with patch("homeassistant.config_entries.async_process_deps_reqs"):
        result = await hass.config_entries.options.async_init(entry.entry_id)
    assert result["type"] is FlowResultType.FORM
    schema = result["data_schema"]
    assert schema is not None
    assert schema({})[CONF_ICON_COLOR] == [24, 188, 242]
    updated = {**settings, CONF_TITLE: "Updated Home Assistant", CONF_ICON_COLOR: [255, 0, 0]}
    with patch.object(hass.config_entries, "async_reload", return_value=True) as reload_entry:
        result = await hass.config_entries.options.async_configure(result["flow_id"], updated)
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert entry.data == {**updated, CONF_ICON_COLOR: "#ff0000"}
    assert entry.options == {}
    reload_entry.assert_awaited_once_with(entry.entry_id)


async def test_update_listener_cleanup(hass: HomeAssistant) -> None:
    """Remove update listeners on unload so reloads do not accumulate callbacks.

    Args:
        hass (HomeAssistant): Home Assistant test instance.
    """
    entry = MockConfigEntry(domain=DOMAIN, data={CONF_TITLE: "Test home"})
    entry.add_to_hass(hass)
    with patch("custom_components.favicon.apply_hooks", autospec=True, return_value=True) as apply:
        for _ in range(2):
            assert await async_setup_entry(hass, entry)
            assert len(entry.update_listeners) == 1
            await entry._async_process_on_unload(hass)
            assert not entry.update_listeners
        apply.reset_mock()
        hass.config_entries.async_update_entry(entry, data={CONF_TITLE: "Unloaded"})
        await hass.async_block_till_done()
        apply.assert_not_awaited()
