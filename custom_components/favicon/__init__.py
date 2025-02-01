"""Initialize hass-favicon."""

from collections.abc import Callable, MutableMapping
import logging
from pathlib import Path
import re
from typing import Any

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
    """Initial hass-favicon setup."""
    if not hass.data.get(DOMAIN):
        hass.data.setdefault(DOMAIN, {})

    if not hass.data[DOMAIN].get("get_template"):
        hass.data[DOMAIN]["get_template"] = frontend.IndexView.get_template
    if not hass.data[DOMAIN].get("manifest_icons"):
        hass.data[DOMAIN]["manifest_icons"] = frontend.MANIFEST_JSON["icons"].copy()
    _LOGGER.debug("[async_setup] get_template: %s", hass.data[DOMAIN]["get_template"])
    _LOGGER.debug("[async_setup] manifest_icons: %s", hass.data[DOMAIN]["manifest_icons"])

    conf = config.get(DOMAIN)
    if not conf:
        return True
    for key in CONF_KEYS:
        if key in hass.data[DOMAIN]:
            del hass.data[DOMAIN][key]
    hass.data[DOMAIN].update(conf)
    return await apply_hooks(hass)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up from a config entry."""
    _LOGGER.debug("[async_setup_entry] entry.data: %s", entry.data)
    if not hass.data.get(DOMAIN):
        hass.data.setdefault(DOMAIN, {})
    entry.add_update_listener(_update_listener)
    return await _update_listener(hass, entry)


async def async_remove_entry(hass: HomeAssistant, _: ConfigEntry) -> bool:
    """Run before unload."""
    return remove_hooks(hass)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    _LOGGER.info("Unloading: %s", entry.data)
    return True


async def _update_listener(hass: HomeAssistant, config_entry: ConfigEntry) -> bool:
    conf = config_entry.options
    for key in CONF_KEYS:
        if key in hass.data[DOMAIN]:
            del hass.data[DOMAIN][key]
    hass.data[DOMAIN].update(conf)
    return await apply_hooks(hass, dict(config_entry.data))


def find_icons(hass: HomeAssistant, path_str: str) -> MutableMapping:
    """Find icons in folder."""

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
    """Apply hooks."""
    icons = await hass.loop.run_in_executor(
        None, find_icons, hass, config_data.get(CONF_ICON_PATH, None)
    )
    _LOGGER.debug("[apply_hooks] icons: %s", icons)
    title = config_data.get(CONF_TITLE, None)
    launch_icon_color = config_data.get(CONF_ICON_COLOR, None)
    data = hass.data.get(DOMAIN, {})

    def _get_template(self):
        tpl = data["get_template"](self)
        _LOGGER.debug("[get_template] tpl (%s): %s", type(tpl), tpl)
        render = tpl.render
        _LOGGER.debug("[get_template] render (%s): %s", type(render), render)

        def new_render(*args, **kwargs) -> str:
            text = render(*args, **kwargs)
            _LOGGER.debug("[new_render] original text: %s", text)
            if "favicon" in icons:
                text = text.replace("/static/icons/favicon.ico", str(icons["favicon"]))
            if "apple" in icons:
                text = text.replace("/static/icons/favicon-apple-180x180.png", str(icons["apple"]))
            if title:
                text = text.replace("<title>Home Assistant</title>", f"<title>{title}</title>")
                text = text.replace(
                    "<body>",
                    f"""
                    <body>
                        <script type="module">
                            customElements.whenDefined('ha-sidebar').then(() => {{
                                const Sidebar = customElements.get('ha-sidebar');
                                const updated = Sidebar.prototype.updated;
                                Sidebar.prototype.updated = function(changedProperties) {{
                                    updated.bind(this)(changedProperties);
                                    this.shadowRoot.querySelector(".title").innerHTML = "{title}";
                                }};
                            }});

                            window.setInterval(() => {{
                                if(!document.title.endsWith("- {title}") && document.title !== "{title}") {{
                                    document.title = document.title.replace(/Home Assistant/, "{title}");
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

        tpl.render = new_render
        return tpl

    frontend.IndexView.get_template = _get_template
    for view in hass.http.app.router.resources():
        if isinstance(view, frontend.IndexView):
            view._template_cache = None  # noqa: SLF001

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


def remove_hooks(hass) -> bool:
    """Remove hooks."""
    data = hass.data[DOMAIN]
    frontend.IndexView.get_template = data["get_template"]
    frontend.add_manifest_json_key("icons", data["manifest_icons"].copy())
    frontend.add_manifest_json_key("name", "Home Assistant")
    frontend.add_manifest_json_key("short_name", "Assistant")
    return True
