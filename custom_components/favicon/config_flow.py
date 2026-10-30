"""Config flow for hass-favicon."""

from __future__ import annotations

from collections.abc import MutableMapping
import logging
from typing import Any

from homeassistant.config_entries import ConfigEntry, ConfigFlow, ConfigFlowResult, OptionsFlow
from homeassistant.core import callback
from homeassistant.helpers import selector
import voluptuous as vol

from .const import (
    CONF_ICON_COLOR,
    CONF_ICON_PATH,
    CONF_TITLE,
    DEFAULT_ICON_COLOR,
    DEFAULT_ICON_PATH,
    DEFAULT_TITLE,
    DOMAIN,
)

_LOGGER: logging.Logger = logging.getLogger(__name__)


def rgb_list_to_hex(rgb: list[int]) -> str | None:
    """Convert an RGB list color to a hex string.

    Args:
        rgb (list[int]): Red, green, and blue channel values.

    Returns:
        str | None: Hex color, or None for invalid channels.
    """
    if len(rgb) != 3 or not all(0 <= x <= 255 for x in rgb):
        return None
    hex_str: str = ("{:02X}" * 3).format(rgb[0], rgb[1], rgb[2]).lower()
    if not hex_str.startswith("#"):
        hex_str = f"#{hex_str}"
    _LOGGER.debug("[rgb_list_to_hex] rgb: %s, hex: %s", rgb, hex_str)
    return hex_str


def hex_to_rgb_list(hex_str: str) -> list[int]:
    """Convert a hex color to RGB as a list.

    Args:
        hex_str (str): Six-digit hex color with an optional leading hash.

    Returns:
        list[int]: Red, green, and blue channel values.
    """
    hex_str = hex_str.lstrip("#").upper()
    rgb: list[int] = [int(hex_str[i : i + 2], 16) for i in (0, 2, 4)]
    _LOGGER.debug("[hex_to_rgb_list] hex: #%s, rgb: %s", hex_str, rgb)
    return rgb


def _get_schema(
    user_input: MutableMapping[str, Any] | None,
    default_dict: MutableMapping[str, Any] | None = None,
) -> vol.Schema:
    """Build the form schema using fallback defaults.

    Args:
        user_input (MutableMapping[str, Any] | None): Submitted values.
        default_dict (MutableMapping[str, Any] | None): Fallback values.

    Returns:
        vol.Schema: Schema for the favicon settings form.
    """
    if user_input is None:
        user_input = {}
    if default_dict is None:
        default_dict = {}

    def _get_default(key: str, fallback_default: Any | None = None) -> Any | None:
        """Get the default value for a key.

        Args:
            key (str): Setting to look up.
            fallback_default (Any | None): Value used when no default exists.

        Returns:
            Any | None: Submitted, configured, or fallback value.
        """
        default: Any | None = user_input.get(key)
        if default is None:
            default = default_dict.get(key, fallback_default)
        if default is None:
            default = fallback_default
        return default

    default_color: str | list[int] | None = _get_default(CONF_ICON_COLOR)
    if isinstance(default_color, str):
        default_color = hex_to_rgb_list(hex_str=default_color)
    return vol.Schema(
        {
            vol.Required(CONF_TITLE, default=_get_default(CONF_TITLE)): str,
            vol.Required(CONF_ICON_PATH, default=_get_default(CONF_ICON_PATH)): str,
            vol.Required(CONF_ICON_COLOR, default=default_color): selector.ColorRGBSelector(
                selector.ColorRGBSelectorConfig()
            ),
        },
    )


async def _convert_color_to_hex(user_input: MutableMapping[str, Any]) -> None:
    """Convert the submitted RGB color list to a hex string.

    Args:
        user_input (MutableMapping[str, Any]): Settings updated in place.
    """
    if isinstance(user_input[CONF_ICON_COLOR], list):
        color_hex = rgb_list_to_hex(rgb=user_input[CONF_ICON_COLOR])
        if color_hex:
            user_input[CONF_ICON_COLOR] = color_hex


async def validate_input(user_input: MutableMapping[str, Any], errors: dict[str, Any]) -> None:
    """Validate user input and normalize its color.

    Args:
        user_input (MutableMapping[str, Any]): Settings updated in place.
        errors (dict[str, Any]): Validation errors updated in place.
    """
    await _convert_color_to_hex(user_input)
    if not user_input.get(CONF_ICON_PATH, "").startswith("/local/"):
        errors["base"] = "bad_path"
        return


class FaviconConfigFlow(ConfigFlow, domain=DOMAIN):
    """Config Flow for hass-favicon integration."""

    VERSION = 1

    async def async_step_user(
        self, user_input: MutableMapping[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle the initial step.

        Args:
            user_input (MutableMapping[str, Any] | None): Submitted settings.

        Returns:
            ConfigFlowResult: Settings form, created entry, or abort result.
        """
        if self._async_current_entries():
            return self.async_abort(reason="single_instance_allowed")
        errors: dict[str, Any] = {}
        input_defaults: MutableMapping[str, Any] = {
            CONF_TITLE: DEFAULT_TITLE,
            CONF_ICON_PATH: DEFAULT_ICON_PATH,
            CONF_ICON_COLOR: DEFAULT_ICON_COLOR,
        }

        if user_input is not None:
            await validate_input(user_input, errors)

            _LOGGER.debug("[Config Flow async_step_user] user_input: %s", user_input)
            if not errors:
                return self.async_create_entry(title="favicon", data=user_input)

        return self.async_show_form(
            step_id="user",
            # Home Assistant aliases Voluptuous at runtime; older annotations need no ignore.
            data_schema=_get_schema(user_input=user_input, default_dict=input_defaults),  # type: ignore[arg-type, unused-ignore]
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(
        _: ConfigEntry,
    ) -> FaviconOptionsFlowHandler:
        """Create the options flow for hass-favicon.

        Returns:
            FaviconOptionsFlowHandler: Handler for editing favicon settings.
        """
        return FaviconOptionsFlowHandler()


class FaviconOptionsFlowHandler(OptionsFlow):
    """Config flow options for hass-favicon.

    Does not actually store these into Options but updates the Config instead.
    """

    async def async_step_init(
        self, user_input: MutableMapping[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Manage the options.

        Args:
            user_input (MutableMapping[str, Any] | None): Submitted settings.

        Returns:
            ConfigFlowResult: Settings form or completed options result.
        """
        errors: dict[str, Any] = {}
        if user_input is not None:
            await validate_input(user_input, errors)
            _LOGGER.debug("[Options async_step_init] user_input: %s", user_input)
            if not errors:
                self.hass.config_entries.async_update_entry(
                    self.config_entry, data=user_input, options=self.config_entry.options
                )
                await self.hass.config_entries.async_reload(self.config_entry.entry_id)
                return self.async_create_entry(title="", data={})
        return self.async_show_form(
            step_id="init",
            # Home Assistant aliases Voluptuous at runtime; older annotations need no ignore.
            data_schema=_get_schema(user_input=dict(self.config_entry.data)),  # type: ignore[arg-type, unused-ignore]
            errors=errors,
        )
