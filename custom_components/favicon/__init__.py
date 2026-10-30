"""Initialize hass-favicon."""

from collections.abc import Callable, MutableMapping
from html import escape
import json
import logging
from pathlib import Path
import re
from typing import Any

from aiohttp import web
from aiohttp.web_urldispatcher import ResourceRoute, UrlMappingMatchInfo
from homeassistant.components import frontend
from homeassistant.config_entries import ConfigEntry, ConfigType
from homeassistant.core import HomeAssistant
from homeassistant.helpers import config_validation as cv

from .const import CONF_ICON_COLOR, CONF_ICON_PATH, CONF_KEYS, CONF_TITLE, DOMAIN

_LOGGER: logging.Logger = logging.getLogger(__name__)

RE_APPLE = r"^favicon-apple-"
RE_ICON = r"^favicon-(\d+x\d+)\..+"

CONFIG_SCHEMA: Callable[[dict], dict] = cv.empty_config_schema(DOMAIN)


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Initialize hass-favicon and apply YAML settings when present.

    Args:
        hass (HomeAssistant): Home Assistant instance.
        config (ConfigType): Loaded Home Assistant configuration.

    Returns:
        bool: Whether setup succeeded.
    """
    if not hass.data.get(DOMAIN):
        hass.data.setdefault(DOMAIN, {})

    if not hass.data[DOMAIN].get("resolve"):
        hass.data[DOMAIN]["resolve"] = frontend.IndexView.resolve
    if not hass.data[DOMAIN].get("manifest_icons"):
        hass.data[DOMAIN]["manifest_icons"] = frontend.MANIFEST_JSON["icons"].copy()
    _LOGGER.debug("[async_setup] resolve: %s", hass.data[DOMAIN]["resolve"])
    _LOGGER.debug("[async_setup] manifest_icons: %s", hass.data[DOMAIN]["manifest_icons"])

    conf = config.get(DOMAIN)
    if not conf:
        return True
    for key in CONF_KEYS:
        if key in hass.data[DOMAIN]:
            del hass.data[DOMAIN][key]
    hass.data[DOMAIN].update(conf)
    return await apply_hooks(hass, dict(conf))


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up from a config entry.

    Args:
        hass (HomeAssistant): Home Assistant instance.
        entry (ConfigEntry): Entry containing the favicon settings.

    Returns:
        bool: Whether setup succeeded.
    """
    _LOGGER.debug("[async_setup_entry] entry.data: %s", entry.data)
    if not hass.data.get(DOMAIN):
        hass.data.setdefault(DOMAIN, {})
    entry.async_on_unload(entry.add_update_listener(_update_listener))
    await _update_listener(hass, entry)
    return True


async def async_remove_entry(hass: HomeAssistant, _: ConfigEntry) -> bool:
    """Restore the original frontend when removing the entry.

    Args:
        hass (HomeAssistant): Home Assistant instance.

    Returns:
        bool: Whether the original frontend was restored.
    """
    return remove_hooks(hass)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry.

    Args:
        hass (HomeAssistant): Home Assistant instance.
        entry (ConfigEntry): Entry being unloaded.

    Returns:
        bool: Whether unloading succeeded.
    """
    _LOGGER.info("Unloading: %s", entry.data)
    return True


async def _update_listener(hass: HomeAssistant, config_entry: ConfigEntry) -> None:
    """Apply updated config-entry settings.

    Args:
        hass (HomeAssistant): Home Assistant instance.
        config_entry (ConfigEntry): Entry containing the updated settings.
    """
    conf = config_entry.options
    for key in CONF_KEYS:
        if key in hass.data[DOMAIN]:
            del hass.data[DOMAIN][key]
    hass.data[DOMAIN].update(conf)
    await apply_hooks(hass, dict(config_entry.data))


def find_icons(hass: HomeAssistant, path_str: str) -> MutableMapping:
    """Find icons in a local folder.

    Args:
        hass (HomeAssistant): Home Assistant instance.
        path_str (str): Frontend path under /local/ to search.

    Returns:
        MutableMapping: Discovered icon paths and manifest entries.
    """
    icons: MutableMapping = {}
    manifest: list = []
    if not path_str or not path_str.startswith("/local/"):
        _LOGGER.error("Invalid Path: %s", path_str)
        return icons
    path: Path = Path(path_str)
    localpath_str: str = "www" + path_str[len("/local") :]
    localpath: Path = Path(hass.config.path(localpath_str))
    _LOGGER.info("Looking for icons in: %s", localpath)

    for fn in localpath.iterdir():
        if fn.name == "favicon.ico":
            icons["favicon"] = path / fn.name
            _LOGGER.info("Found favicon: %s", icons["favicon"])

        if re.search(RE_APPLE, fn.name):
            icons["apple"] = path / fn.name
            _LOGGER.info("Found apple icon: %s", icons["apple"])

        icon = re.search(RE_ICON, fn.name)
        if icon:
            manifest.append(
                {
                    "src": path / fn.name,
                    "sizes": icon.group(1),
                    "type": "image/png",
                }
            )
            _LOGGER.info("Found icon: %s", path / fn.name)

    if manifest:
        icons["manifest"] = manifest
    _LOGGER.debug("[find_icons] icons: %s", icons)
    return icons


async def apply_hooks(hass: HomeAssistant, config_data: MutableMapping[str, Any]) -> bool:
    """Apply frontend response and manifest customizations.

    Args:
        hass (HomeAssistant): Home Assistant instance.
        config_data (MutableMapping[str, Any]): Favicon settings to apply.

    Returns:
        bool: Whether the customizations were applied.
    """
    icons = await hass.loop.run_in_executor(
        None, find_icons, hass, config_data.get(CONF_ICON_PATH, None)
    )
    _LOGGER.debug("[apply_hooks] icons: %s", icons)
    title = config_data.get(CONF_TITLE, None)
    launch_icon_color = config_data.get(CONF_ICON_COLOR, None)
    data = hass.data.get(DOMAIN, {})

    def customize_html(text: str) -> str:
        """Apply the configured branding to rendered HTML.

        Args:
            text (str): Original frontend HTML.

        Returns:
            str: Branded frontend HTML.
        """
        _LOGGER.debug("[customize_html] original text: %s", text)
        if "favicon" in icons:
            text = text.replace("/static/icons/favicon.ico", str(icons["favicon"]))
        if "apple" in icons:
            text = text.replace("/static/icons/favicon-apple-180x180.png", str(icons["apple"]))
        if title:
            title_json = json.dumps(title).replace("<", r"\u003c")
            text = text.replace(
                "<title>Home Assistant</title>", f"<title>{escape(title)}</title>"
            )
            text = text.replace(
                "<body>",
                f"""
                <body>
                    <script type="module">
                        const title = {title_json};
                        customElements.whenDefined('ha-sidebar').then(() => {{
                            const Sidebar = customElements.get('ha-sidebar');
                            const updated = Sidebar.prototype.updated;
                            Sidebar.prototype.updated = function(changedProperties) {{
                                updated.bind(this)(changedProperties);
                                this.shadowRoot.querySelector(".title").textContent = title;
                            }};
                        }});

                        window.setInterval(() => {{
                            if(document.title !== title &&
                               !document.title.endsWith(" – " + title) &&
                               !document.title.endsWith(" - " + title) &&
                               document.title.endsWith("Home Assistant")) {{
                                document.title = document.title.replace(/Home Assistant$/, () => title);
                            }}
                        }}, 1000);
                    </script>
                """,  # noqa: E501
            )

        if launch_icon_color:
            # Regex to match hex color codes (e.g., #18bcf2, #123ABC)
            hex_color_pattern = r"#(?:[0-9a-fA-F]{6})"

            text = re.sub(
                r'(<link rel="mask-icon" href="/static/icons/mask-icon\.svg" color=")'
                + hex_color_pattern
                + r'(">)',
                rf"\1{launch_icon_color}\2",
                text,
            )
            text = re.sub(
                rf'(<path fill="){hex_color_pattern}(")',
                rf"\1{launch_icon_color}\2",
                text,
                count=1,  # Only replace the first occurrence
            )

        return text

    async def resolve(
        self: frontend.IndexView, request: web.Request
    ) -> tuple[UrlMappingMatchInfo | None, set[str]]:
        """Wrap only successful frontend routes without changing template caches.

        Args:
            self (frontend.IndexView): Frontend resource being resolved.
            request (web.Request): Incoming HTTP request.

        Returns:
            tuple[UrlMappingMatchInfo | None, set[str]]: Route and allowed methods.
        """
        match_info, allowed_methods = await data["resolve"](self, request)
        if match_info is None or self.hass is not hass:
            return match_info, allowed_methods

        async def handle(request: web.Request) -> web.StreamResponse:
            """Customize a successful HTML response from the original handler.

            Args:
                request (web.Request): Incoming HTTP request.

            Returns:
                web.StreamResponse: Original response with optional HTML branding.
            """
            response = await match_info.handler(request)
            if (
                isinstance(response, web.Response)
                and response.status == 200
                and response.content_type == "text/html"
                and response.text is not None
            ):
                response.text = customize_html(response.text)
            return response

        route = ResourceRoute(
            match_info.route.method,
            handle,
            match_info.route.resource,
            expect_handler=match_info.route.handle_expect_header,
        )
        return UrlMappingMatchInfo(match_info, route), allowed_methods

    frontend.IndexView.resolve = resolve  # type: ignore[method-assign]

    if "manifest" in icons:
        frontend.add_manifest_json_key("icons", icons["manifest"])
    else:
        frontend.add_manifest_json_key("icons", data["manifest_icons"].copy())

    if title:
        frontend.add_manifest_json_key("name", title)
        frontend.add_manifest_json_key("short_name", title)
    else:
        frontend.add_manifest_json_key("name", "Home Assistant")
        frontend.add_manifest_json_key("short_name", "Assistant")

    return True


def remove_hooks(hass: HomeAssistant) -> bool:
    """Restore the original frontend routing and manifest.

    Args:
        hass (HomeAssistant): Home Assistant instance.

    Returns:
        bool: Whether the original frontend was restored.
    """
    data = hass.data[DOMAIN]
    frontend.IndexView.resolve = data["resolve"]  # type: ignore[method-assign]
    frontend.add_manifest_json_key("icons", data["manifest_icons"].copy())
    frontend.add_manifest_json_key("name", "Home Assistant")
    frontend.add_manifest_json_key("short_name", "Assistant")
    return True
