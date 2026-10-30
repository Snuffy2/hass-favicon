"""Regression tests for Home Assistant setup and form contracts."""

import asyncio
import html
import json
import logging
from pathlib import Path
import re
import threading
from unittest.mock import patch

from homeassistant.components import frontend
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.helpers.data_entry_flow import FlowManagerIndexView
from jinja2 import Template
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry
from pytest_homeassistant_custom_component.typing import ClientSessionGenerator

from custom_components.favicon import (
    apply_hooks,
    async_remove_entry,
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


async def test_stored_color_and_title_rendering_and_unload_restores_frontend(
    favicon_frontend: HomeAssistant,
    hass_client: ClientSessionGenerator,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Escape custom title and stored config-entry color, then restore on unload.

    The quote-bearing color exercises persisted entry data. The normal color selector
    accepts RGB channels, which the config flow converts to a hex string.

    Args:
        favicon_frontend (HomeAssistant): Real frontend with isolated icon files.
        hass_client (ClientSessionGenerator): Authenticated HTTP client factory.
        monkeypatch (pytest.MonkeyPatch): Fixture for replacing frontend interfaces.
    """
    hass = favicon_frontend
    client = await hass_client()
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
    original_names = {key: frontend.MANIFEST_JSON[key] for key in ("name", "short_name")}
    original_icons = frontend.MANIFEST_JSON["icons"].copy()
    icon_directory = Path(hass.config.path("www/custom-favicons"))
    await hass.async_add_executor_job(
        _create_icon_files,
        icon_directory,
        ("favicon.ico", "favicon-apple-180x180.png", "favicon-192x192.png"),
    )
    title = 'Lab "quoted"\n</script><img src=x onerror=alert(1)>'
    stored_color = '#ff0000" onload="alert(1)'
    escaped_color = "#ff0000&quot; onload=&quot;alert(1)"
    settings = {
        CONF_TITLE: title,
        CONF_ICON_PATH: "/local/custom-favicons/",
        CONF_ICON_COLOR: stored_color,
    }

    entry = MockConfigEntry(domain=DOMAIN, data=settings)
    entry.add_to_hass(hass)
    assert await async_setup_entry(hass, entry) is True
    rendered = await (await client.get("/")).text()

    assert f"<title>{html.escape(title)}</title>" in rendered
    serialized_title = re.search(r"const title = (.+);", rendered)
    assert serialized_title is not None
    assert json.loads(serialized_title.group(1)) == title
    assert "</script><img" not in rendered
    assert 'querySelector(".title").textContent = title' in rendered
    assert 'querySelector(".title").innerHTML' not in rendered
    assert f'href="/static/icons/mask-icon.svg" color="{escaped_color}"' in rendered
    assert f'<path fill="{escaped_color}">' in rendered
    assert f'color="{stored_color}"' not in rendered
    assert f'<path fill="{stored_color}">' not in rendered
    assert 'href="/local/custom-favicons/favicon.ico"' in rendered
    assert 'href="/local/custom-favicons/favicon-apple-180x180.png"' in rendered

    assert await async_unload_entry(hass, entry) is True
    assert frontend.MANIFEST_JSON["icons"] == original_icons
    assert {key: frontend.MANIFEST_JSON[key] for key in original_names} == original_names
    restored = await (await client.get("/")).text()
    assert "<title>Home Assistant</title>" in restored
    assert 'color="#18bcf2"' in restored
    assert 'href="/static/icons/favicon.ico"' in restored
    assert await async_remove_entry(hass, entry) is True
    assert await async_remove_entry(hass, entry) is True


async def test_icon_urls_encode_reserved_filesystem_characters(
    favicon_frontend: HomeAssistant,
    hass_client: ClientSessionGenerator,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Encode special filesystem characters in emitted icon and manifest URLs.

    Args:
        favicon_frontend (HomeAssistant): Real frontend with isolated icon files.
        hass_client (ClientSessionGenerator): Authenticated HTTP client factory.
        monkeypatch (pytest.MonkeyPatch): Fixture for replacing the frontend template.
    """
    hass = favicon_frontend
    client = await hass_client()
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

    entry = MockConfigEntry(domain=DOMAIN, data={CONF_ICON_PATH: path_str})
    assert await async_setup_entry(hass, entry) is True
    rendered = await (await client.get("/")).text()
    assert f'href="{favicon_url}"' in rendered
    assert f'href="{apple_url}"' in rendered
    assert frontend.MANIFEST_JSON["icons"] == icons["manifest"]
    remove_hooks(entry)


def test_malformed_icon_filename_does_not_block_valid_icons(
    hass: HomeAssistant, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """Skip filenames that cannot form UTF-8 URLs while discovering valid icons.

    Args:
        hass (HomeAssistant): Home Assistant test instance.
        monkeypatch (pytest.MonkeyPatch): Fixture for simulating directory entries.
        caplog (pytest.LogCaptureFixture): Captured warning logs.
    """
    filenames = [Path("favicon.ico"), Path("favicon-192x192.\udcff.png")]
    monkeypatch.setattr(Path, "iterdir", lambda _path: iter(filenames))
    assert find_icons(hass, "/local/favicons/") == {"favicon": "/local/favicons/favicon.ico"}
    assert any(
        record.name == "custom_components.favicon" and record.levelno == logging.WARNING
        for record in caplog.records
    )


async def test_entry_unload_restores_original_frontend(hass: HomeAssistant) -> None:
    """Restore the original frontend when a config entry unloads.

    Args:
        hass (HomeAssistant): Home Assistant test instance.
    """
    original_manifest_icons = frontend.MANIFEST_JSON["icons"].copy()
    original_names = {key: frontend.MANIFEST_JSON[key] for key in ("name", "short_name")}
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_TITLE: "Entry only", CONF_ICON_PATH: "/local/missing-icons/"},
    )
    with patch("custom_components.favicon.apply_hooks", autospec=True, return_value=True):
        assert await async_setup_entry(hass, entry) is True
    assert await async_unload_entry(hass, entry) is True
    assert frontend.MANIFEST_JSON["icons"] == original_manifest_icons
    assert {key: frontend.MANIFEST_JSON[key] for key in original_names} == original_names
    assert await async_remove_entry(hass, entry) is True
    assert {key: frontend.MANIFEST_JSON[key] for key in original_names} == original_names


async def test_remove_entry_without_runtime_data_is_safe(hass: HomeAssistant) -> None:
    """Leave the frontend alone when removing an entry that was never loaded.

    Args:
        hass (HomeAssistant): Home Assistant test instance.
    """
    original_resolve = frontend.IndexView.resolve
    original_manifest_icons = frontend.MANIFEST_JSON["icons"].copy()
    original_manifest_names = {key: frontend.MANIFEST_JSON[key] for key in ("name", "short_name")}
    entry = MockConfigEntry(domain=DOMAIN)

    assert await async_remove_entry(hass, entry) is True
    assert frontend.IndexView.resolve is original_resolve
    assert frontend.MANIFEST_JSON["icons"] == original_manifest_icons
    assert {
        key: frontend.MANIFEST_JSON[key] for key in original_manifest_names
    } == original_manifest_names


@pytest.mark.parametrize("reload_entry", [False, True])
async def test_queued_listener_ignores_unloaded_entry(
    hass: HomeAssistant, reload_entry: bool
) -> None:
    """Ignore a queued callback after its entry has unloaded.

    Args:
        hass (HomeAssistant): Home Assistant test instance.
        reload_entry (bool): Whether to reload before running the old callback.
    """
    entry = MockConfigEntry(domain=DOMAIN, data={CONF_TITLE: "Test home"})
    entry.add_to_hass(hass)

    with patch("custom_components.favicon.apply_hooks", autospec=True, return_value=True) as apply:
        assert await async_setup_entry(hass, entry) is True
        listener = entry.update_listeners[0]

        assert await async_unload_entry(hass, entry) is True
        await entry._async_process_on_unload(hass)
        if reload_entry:
            assert await async_setup_entry(hass, entry) is True
        apply.reset_mock()
        await listener(hass, entry)
        apply.assert_not_awaited()

    await entry._async_process_on_unload(hass)


async def test_unload_discards_in_flight_entry_icon_scan(
    hass: HomeAssistant,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Keep unload restoration after an entry scan that finishes late.

    Args:
        hass (HomeAssistant): Home Assistant test instance.
        monkeypatch (pytest.MonkeyPatch): Fixture for replacing icon discovery.
    """
    original_icons = frontend.MANIFEST_JSON["icons"].copy()
    original_names = {key: frontend.MANIFEST_JSON[key] for key in ("name", "short_name")}

    scan_started = asyncio.Event()
    release_scan = threading.Event()
    entry_icons = [
        {
            "src": "/local/entry-icons/favicon-192x192.png",
            "sizes": "192x192",
            "type": "image/png",
        }
    ]

    def blocked_entry_scan(scan_hass: HomeAssistant, path_str: str) -> dict[str, object]:
        if path_str != "/local/entry-icons/":
            return {}
        scan_hass.loop.call_soon_threadsafe(scan_started.set)
        if not release_scan.wait(timeout=5):
            raise TimeoutError("The test did not release the blocked icon scan")
        return {"manifest": entry_icons}

    monkeypatch.setattr("custom_components.favicon.find_icons", blocked_entry_scan)
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_TITLE: "Entry title", CONF_ICON_PATH: "/local/entry-icons/"},
    )
    setup_task = hass.async_create_task(async_setup_entry(hass, entry))
    try:
        await asyncio.wait_for(scan_started.wait(), timeout=5)
        assert await async_unload_entry(hass, entry) is True
    finally:
        release_scan.set()
    assert await asyncio.wait_for(setup_task, timeout=5) is True

    assert frontend.MANIFEST_JSON["icons"] == original_icons
    assert {key: frontend.MANIFEST_JSON[key] for key in original_names} == original_names


async def test_latest_overlapping_apply_wins(
    favicon_frontend: HomeAssistant,
    hass_client: ClientSessionGenerator,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Prevent an older icon scan from replacing a newer frontend update.

    Args:
        favicon_frontend (HomeAssistant): Real frontend with isolated icon files.
        hass_client (ClientSessionGenerator): Authenticated HTTP client factory.
        monkeypatch (pytest.MonkeyPatch): Fixture for replacing the template and icon scan.
    """
    hass = favicon_frontend
    client = await hass_client()
    monkeypatch.setattr(
        frontend.IndexView,
        "get_template",
        lambda _self: Template(
            "<html><head><title>Home Assistant</title></head><body></body></html>"
        ),
    )
    entry = MockConfigEntry(domain=DOMAIN)
    assert await async_setup_entry(hass, entry) is True
    old_scan_started = asyncio.Event()
    release_old_scan = threading.Event()
    old_icons = [{"src": "/local/old/favicon-192x192.png", "sizes": "192x192", "type": "image/png"}]
    latest_icons = [
        {
            "src": "/local/latest/favicon-192x192.png",
            "sizes": "192x192",
            "type": "image/png",
        }
    ]

    def overlapping_scan(scan_hass: HomeAssistant, path_str: str) -> dict[str, object]:
        if path_str == "/local/old/":
            scan_hass.loop.call_soon_threadsafe(old_scan_started.set)
            if not release_old_scan.wait(timeout=5):
                raise TimeoutError("The test did not release the older icon scan")
            return {"manifest": old_icons}
        return {"manifest": latest_icons}

    monkeypatch.setattr("custom_components.favicon.find_icons", overlapping_scan)
    old_task = hass.async_create_task(
        apply_hooks(hass, entry, {CONF_TITLE: "Old title", CONF_ICON_PATH: "/local/old/"})
    )
    try:
        await asyncio.wait_for(old_scan_started.wait(), timeout=5)
        assert (
            await apply_hooks(
                hass, entry, {CONF_TITLE: "Latest title", CONF_ICON_PATH: "/local/latest/"}
            )
            is True
        )
    finally:
        release_old_scan.set()
    assert await asyncio.wait_for(old_task, timeout=5) is True

    assert frontend.MANIFEST_JSON["icons"] == latest_icons
    assert frontend.MANIFEST_JSON["name"] == "Latest title"
    rendered = await (await client.get("/")).text()
    assert "<title>Latest title</title>" in rendered
    assert "Old title" not in rendered
    remove_hooks(entry)


@pytest.mark.parametrize("transition", ["update", "unload", "remove"])
async def test_in_flight_page_load_preserves_current_branding(
    favicon_frontend: HomeAssistant,
    hass_client: ClientSessionGenerator,
    monkeypatch: pytest.MonkeyPatch,
    transition: str,
) -> None:
    """Serve current branding after a settings change during an older request.

    Args:
        favicon_frontend (HomeAssistant): Real frontend with isolated icon files.
        hass_client (ClientSessionGenerator): Authenticated HTTP client factory.
        monkeypatch (pytest.MonkeyPatch): Fixture for replacing the template getter.
        transition (str): Entry transition while the original page is loading.
    """
    hass = favicon_frontend
    client = await hass_client()
    load_started = asyncio.Event()
    release_load = threading.Event()
    first_load = True
    load_lock = threading.Lock()
    source = "<html><head><title>Home Assistant</title></head><body></body></html>"

    def delayed_template(view: frontend.IndexView) -> Template:
        nonlocal first_load
        with load_lock:
            should_block = first_load
            first_load = False
        if should_block:
            hass.loop.call_soon_threadsafe(load_started.set)
            if not release_load.wait(timeout=5):
                raise TimeoutError("The test did not release the template load")
        template = view._template_cache
        if template is None:
            template = Template(source)
            view._template_cache = template
        return template

    monkeypatch.setattr(frontend.IndexView, "get_template", delayed_template)
    entry_title = "Entry title"
    entry = MockConfigEntry(domain=DOMAIN, data={CONF_TITLE: entry_title})
    assert await async_setup_entry(hass, entry) is True

    async def load_template() -> str:
        """Request rendered HTML through the real frontend route.

        Returns:
            str: Rendered page HTML.
        """
        return await (await client.get("/")).text()

    old_request = hass.async_create_task(load_template())
    try:
        await asyncio.wait_for(load_started.wait(), timeout=5)
        if transition == "update":
            assert await apply_hooks(hass, entry, {CONF_TITLE: "New title"}) is True
            expected_title = "New title"
        else:
            callback = async_unload_entry if transition == "unload" else async_remove_entry
            assert await callback(hass, entry) is True
            expected_title = "Home Assistant"
    finally:
        release_load.set()

    old_template = await asyncio.wait_for(old_request, timeout=5)
    assert f"<title>{entry_title}</title>" in old_template

    current_template = await load_template()
    assert f"<title>{expected_title}</title>" in current_template
    remove_hooks(entry)


async def test_development_frontend_serves_fresh_templates(
    favicon_frontend: HomeAssistant,
    hass_client: ClientSessionGenerator,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Keep development template reloads visible through the active hook.

    Args:
        favicon_frontend (HomeAssistant): Real frontend with isolated icon files.
        hass_client (ClientSessionGenerator): Authenticated HTTP client factory.
        monkeypatch (pytest.MonkeyPatch): Fixture for replacing the template getter.
    """
    hass = favicon_frontend
    client = await hass_client()
    calls = 0

    def changing_template(_view: frontend.IndexView) -> Template:
        nonlocal calls
        calls += 1
        return Template(f"<title>Template {calls}</title>")

    monkeypatch.setattr(frontend.IndexView, "get_template", changing_template)
    entry = MockConfigEntry(domain=DOMAIN)
    assert await async_setup_entry(hass, entry) is True

    index_view = next(
        view for view in hass.http.app.router.resources() if isinstance(view, frontend.IndexView)
    )
    monkeypatch.setattr(index_view, "repo_path", "/repo")
    first_page = await (await client.get("/")).text()
    second_page = await (await client.get("/")).text()

    assert first_page == "<title>Template 1</title>"
    assert second_page == "<title>Template 2</title>"
    remove_hooks(entry)


@pytest.mark.parametrize(
    "path", ["/local/missing-directory-for-warning-test/", "/local/invalid\x00/"]
)
def test_unreadable_icon_directory_warns_and_continues(
    hass: HomeAssistant, caplog: pytest.LogCaptureFixture, path: str
) -> None:
    """Return no icons and warn when the configured folder is unavailable.

    Args:
        hass (HomeAssistant): Home Assistant test instance.
        caplog (pytest.LogCaptureFixture): Captured warning logs.
        path (str): Missing or malformed icon directory.
    """
    with caplog.at_level(logging.WARNING, logger="custom_components.favicon"):
        assert find_icons(hass, path) == {}

    assert any(
        record.name == "custom_components.favicon"
        and record.levelno == logging.WARNING
        and Path(path).name in record.getMessage()
        for record in caplog.records
    )


async def test_entry_setup_and_update(hass: HomeAssistant) -> None:
    """Return setup success while the registered update callback returns None.

    Args:
        hass (HomeAssistant): Home Assistant test instance.
    """
    entry = MockConfigEntry(domain=DOMAIN, data={CONF_TITLE: "Test home"})
    entry.add_to_hass(hass)
    with patch("custom_components.favicon.apply_hooks", autospec=True, return_value=True) as apply:
        assert await async_setup_entry(hass, entry) is True
        apply.assert_awaited_once_with(hass, entry, dict(entry.data))
        listener = entry.update_listeners[0]
        assert await listener(hass, entry) is None

        updated_settings = {CONF_TITLE: "Updated home"}
        apply.reset_mock()
        assert hass.config_entries.async_update_entry(entry, data=updated_settings)
        await hass.async_block_till_done()
        apply.assert_awaited_once_with(hass, entry, updated_settings)


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
