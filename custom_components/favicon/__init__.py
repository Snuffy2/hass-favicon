"""Initialize hass-favicon."""

from collections.abc import Awaitable, Callable, MutableMapping
from dataclasses import dataclass
from html import escape
import json
import logging
from pathlib import Path
import re
from typing import Any
from urllib.parse import quote

from aiohttp import web
from aiohttp.web_urldispatcher import ResourceRoute, UrlMappingMatchInfo
from homeassistant.components import frontend
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import config_validation as cv

from .const import CONF_ICON_COLOR, CONF_ICON_PATH, CONF_TITLE, DOMAIN

_LOGGER: logging.Logger = logging.getLogger(__name__)


@dataclass
class FaviconRuntimeData:
    """Original frontend state and guards for one loaded entry lifetime."""

    resolve: Callable[
        [frontend.IndexView, web.Request],
        Awaitable[tuple[UrlMappingMatchInfo | None, set[str]]],
    ]
    manifest_icons: list[dict[str, str]]
    manifest_names: dict[str, str]
    generation: int = 0
    active: bool = True


type FaviconConfigEntry = ConfigEntry[FaviconRuntimeData]


RE_APPLE = r"^favicon-apple-"
RE_ICON = r"^favicon-(\d+x\d+)\..+"

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)


async def async_setup_entry(hass: HomeAssistant, entry: FaviconConfigEntry) -> bool:
    """Set up from a config entry.

    Args:
        hass (HomeAssistant): Home Assistant instance.
        entry (FaviconConfigEntry): Entry containing the favicon settings.

    Returns:
        bool: Whether setup succeeded.
    """
    _LOGGER.debug("[async_setup_entry] entry.data: %s", entry.data)
    data = entry.runtime_data = FaviconRuntimeData(
        resolve=frontend.IndexView.resolve,
        manifest_icons=frontend.MANIFEST_JSON["icons"].copy(),
        manifest_names={key: frontend.MANIFEST_JSON[key] for key in ("name", "short_name")},
    )

    async def update_listener(hass: HomeAssistant, config_entry: FaviconConfigEntry) -> None:
        """Apply settings only while this entry lifetime remains active.

        Args:
            hass (HomeAssistant): Home Assistant instance.
            config_entry (FaviconConfigEntry): Entry containing updated settings.
        """
        if not data.active or getattr(config_entry, "runtime_data", None) is not data:
            return
        await apply_hooks(hass, config_entry, dict(config_entry.data))

    entry.async_on_unload(entry.add_update_listener(update_listener))
    await update_listener(hass, entry)
    return True


async def async_remove_entry(hass: HomeAssistant, entry: FaviconConfigEntry) -> bool:
    """Restore the original frontend when removing a loaded entry.

    Args:
        hass (HomeAssistant): Home Assistant instance.
        entry (FaviconConfigEntry): Entry being removed, possibly already unloaded.

    Returns:
        bool: Whether the original frontend was restored.
    """
    return remove_hooks(entry)


async def async_unload_entry(hass: HomeAssistant, entry: FaviconConfigEntry) -> bool:
    """Unload a config entry.

    Args:
        hass (HomeAssistant): Home Assistant instance.
        entry (FaviconConfigEntry): Entry being unloaded.

    Returns:
        bool: Whether unloading succeeded.
    """
    _LOGGER.info("Unloading: %s", entry.data)
    return remove_hooks(entry)


def find_icons(hass: HomeAssistant, path_str: str) -> MutableMapping[str, Any]:
    """Find icons in a local folder.

    Args:
        hass (HomeAssistant): Home Assistant instance.
        path_str (str): Frontend path under /local/ to search.

    Returns:
        MutableMapping[str, Any]: Discovered icon paths and manifest entries.
    """
    icons: dict[str, Any] = {}
    manifest: list[dict[str, Any]] = []
    if not path_str or not path_str.startswith("/local/") or ".." in path_str.split("/"):
        _LOGGER.error("Invalid Path: %s", path_str)
        return icons
    path: Path = Path(path_str)
    localpath_str: str = "www" + path_str[len("/local") :]
    localpath: Path = Path(hass.config.path(localpath_str))
    _LOGGER.info("Looking for icons in: %s", localpath)

    try:
        for fn in localpath.iterdir():
            apple = re.search(RE_APPLE, fn.name)
            icon = re.search(RE_ICON, fn.name)
            if fn.name != "favicon.ico" and not apple and not icon:
                continue
            try:
                icon_url = quote(str(path / fn.name), safe="/")
            except UnicodeEncodeError:
                _LOGGER.warning("Skipping icon with a non-UTF-8 filename: %r", fn.name)
                continue
            if fn.name == "favicon.ico":
                icons["favicon"] = icon_url
                _LOGGER.info("Found favicon: %s", icons["favicon"])

            if apple:
                icons["apple"] = icon_url
                _LOGGER.info("Found apple icon: %s", icons["apple"])

            if icon:
                manifest.append(
                    {
                        "src": icon_url,
                        "sizes": icon.group(1),
                        "type": "image/png",
                    }
                )
                _LOGGER.info("Found icon: %s", path / fn.name)
    except (OSError, ValueError) as err:
        _LOGGER.warning(
            "Unable to read favicon icon directory %s; check that it exists and is readable: %s",
            localpath,
            err,
        )
        return {}

    if manifest:
        icons["manifest"] = manifest
    _LOGGER.debug("[find_icons] icons: %s", icons)
    return icons


async def apply_hooks(
    hass: HomeAssistant, entry: FaviconConfigEntry, config_data: MutableMapping[str, Any]
) -> bool:
    """Apply frontend response and manifest customizations.

    Args:
        hass (HomeAssistant): Home Assistant instance.
        entry (FaviconConfigEntry): Loaded entry owning the frontend state.
        config_data (MutableMapping[str, Any]): Favicon settings to apply.

    Returns:
        bool: Whether the customizations were applied.
    """
    data = entry.runtime_data
    data.generation += 1
    generation = data.generation
    icons = await hass.loop.run_in_executor(
        None, find_icons, hass, config_data.get(CONF_ICON_PATH, None)
    )
    if not data.active or data.generation != generation:
        return True
    _LOGGER.debug("[apply_hooks] icons: %s", icons)
    title = config_data.get(CONF_TITLE, None)
    launch_icon_color = config_data.get(CONF_ICON_COLOR, None)

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
            text = text.replace("<title>Home Assistant</title>", f"<title>{escape(title)}</title>")
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
            escaped_color = escape(launch_icon_color)
            # Regex to match hex color codes (e.g., #18bcf2, #123ABC)
            hex_color_pattern = r"#(?:[0-9a-fA-F]{6})"

            text = re.sub(
                r'(<link rel="mask-icon" href="/static/icons/mask-icon\.svg" color=")'
                + hex_color_pattern
                + r'(">)',
                lambda match: f"{match[1]}{escaped_color}{match[2]}",
                text,
            )
            text = re.sub(
                rf'(<path fill="){hex_color_pattern}(")',
                lambda match: f"{match[1]}{escaped_color}{match[2]}",
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
        match_info, allowed_methods = await data.resolve(self, request)
        if match_info is None or self.hass is not hass:
            return match_info, allowed_methods

        resource = match_info.route.resource
        if resource is None:
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
            resource,
            expect_handler=match_info.route.handle_expect_header,
        )
        return UrlMappingMatchInfo(match_info, route), allowed_methods

    frontend.IndexView.resolve = resolve  # type: ignore[method-assign]

    if "manifest" in icons:
        frontend.add_manifest_json_key("icons", icons["manifest"])
    else:
        frontend.add_manifest_json_key("icons", data.manifest_icons.copy())

    if title:
        frontend.add_manifest_json_key("name", title)
        frontend.add_manifest_json_key("short_name", title)
    else:
        for key, value in data.manifest_names.items():
            frontend.add_manifest_json_key(key, value)

    return True


def remove_hooks(entry: FaviconConfigEntry) -> bool:
    """Restore the original frontend routing and manifest once per lifetime.

    Args:
        entry (FaviconConfigEntry): Entry whose hooks should be removed.

    Returns:
        bool: Whether the original frontend was restored.
    """
    data = getattr(entry, "runtime_data", None)
    if data is None or not data.active:
        return True
    data.active = False
    data.generation += 1
    frontend.IndexView.resolve = data.resolve  # type: ignore[method-assign]
    frontend.add_manifest_json_key("icons", data.manifest_icons.copy())
    for key, value in data.manifest_names.items():
        frontend.add_manifest_json_key(key, value)
    return True
