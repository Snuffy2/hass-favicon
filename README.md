<picture>
  <source media="(prefers-color-scheme: dark)" srcset="custom_components/favicon/brand/dark_logo.png">
  <img src="custom_components/favicon/brand/logo.png" alt="Custom Favicon logo" width="379">
</picture>

# Favicon Changer

[![GitHub Downloads][downloads-shield]][releases]
[![GitHub Latest Downloads][downloads-latest-shield]][releases]
[![GitHub Release][releases-shield]][releases]
[![GitHub Release Date][release-date-shield]][releases]
[![GitHub Activity][commits-shield]][commits]
[![Coverage][coverage-shield]][coverage]
[![License][license-shield]](LICENSE)
[![hacs][hacsbadge]][hacs]

Customize the page title, favicon, app icons, and launch icon color of your Home Assistant instance.

![Example browser title and icon](https://user-images.githubusercontent.com/1299821/62975860-ad283a80-be1b-11e9-836a-d58a1732fb21.png)

## Installation

Use **HACS** on Home Assistant versions before 2026.11, or **Marketplace** on 2026.11 and later. [Marketplace replaces HACS and is built into Home Assistant](https://contributors.home-assistant.io/marketplace/), under Settings > Marketplace.

1. In HACS or Marketplace, add `https://github.com/Snuffy2/hass-favicon` as a custom repository.
2. Download `Favicon Changer (Snuffy2)` and restart Home Assistant.
3. Copy an icon set into `<your config dir>/www/favicons/`. Ready-to-use sets are included in [`icons/`](icons/): `dev`, `green`, `orange`, and `red`. If you created the `www` directory, restart Home Assistant before using its files.

Home Assistant serves files in `www` under `/local/`, so the frontend path for this example is `/local/favicons/`. You can also use your own icons, such as [Home Assistant iOS alternate icons](https://github.com/home-assistant/iOS/tree/main/icons/Alternates), or generate them with an icon generator.

## Configuration

Configuration is through the Home Assistant UI. Add **Favicon** from Settings > Devices & services, or use this shortcut:

[![Open your Home Assistant instance and install hass-favicon.](https://my.home-assistant.io/badges/brand.svg)](https://my.home-assistant.io/redirect/config_flow_start/?domain=favicon)

Enter the following settings and submit the form:

- **Page title**: The title used in the browser and Home Assistant sidebar. The default is `Home Assistant`.
- **Icon path**: The frontend directory containing the icons, such as `/local/favicons/`. It must begin with `/local/`, must not contain a `..` parent-directory segment, and should point to the directory, not an individual file.
- **Launch icon color**: The color of the Home Assistant logo shown while the frontend loads, and of the Safari pinned-tab icon. The default is `#18BCF2`.

Only one Favicon configuration is allowed. To change these settings later, open the integration's options. Refresh the page after saving; clear your browser cache if old icons remain.

![Favicon configuration](https://user-images.githubusercontent.com/1299821/65991117-1d068900-e48d-11e9-9002-f2253fafa190.gif)

## Icon filenames

The integration scans the configured directory for these filenames:

- `favicon.ico`: Browser tab and bookmark icon.
- `favicon-apple-<anything>.png`: Apple touch icon for a saved home-screen shortcut. If there are several, `favicon-apple-180x180.png` is used, otherwise the first in alphabetical order.
- `favicon-<width>x<height>.png`: App manifest icon, for example `favicon-192x192.png`. Other image formats such as `.webp` also work; the manifest lists each icon with the type matching its extension.

Files are recognized by their extension, not their contents. Matching files whose extension is not an image type, such as `favicon-192x192.png.bak`, are ignored.

![Example icons](https://user-images.githubusercontent.com/1299821/62975899-c29d6480-be1b-11e9-9b6b-9d160ef8b439.jpg)

## Troubleshooting

If icons do not appear, check that the icon path starts with `/local/`, that the corresponding directory under `www` exists and is readable, and that the filenames match the patterns above. If `www` was newly created, restart Home Assistant. Refresh the page and clear the browser cache if it still shows old icons. Check the Home Assistant logs for directory-reading warnings.

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for development setup, tests and pull request guidance.

## Attribution

This project continues the now-deprecated [hass-favicon](https://github.com/thomasloven/hass-favicon) integration originally created by [thomasloven](https://github.com/thomasloven). Thank you, thomasloven, for creating the original integration and sharing it with the Home Assistant community.

The logo and icon were created by [MelchMwoan](https://github.com/MelchMwoan). Thank you for contributing the project's branding.

[downloads-shield]: https://img.shields.io/github/downloads/Snuffy2/hass-favicon/total?style=for-the-badge&label=total%20downloads
[downloads-latest-shield]: https://img.shields.io/github/downloads-pre/Snuffy2/hass-favicon/latest/total?style=for-the-badge
[releases]: https://github.com/Snuffy2/hass-favicon/releases
[releases-shield]: https://img.shields.io/github/release/Snuffy2/hass-favicon.svg?style=for-the-badge
[release-date-shield]: https://img.shields.io/github/release-date/Snuffy2/hass-favicon?style=for-the-badge
[commits]: https://github.com/Snuffy2/hass-favicon/commits/main
[commits-shield]: https://img.shields.io/github/last-commit/Snuffy2/hass-favicon?style=for-the-badge
[license-shield]: https://img.shields.io/github/license/Snuffy2/hass-favicon?color=blue&style=for-the-badge
[hacsbadge]: https://img.shields.io/badge/HACS-Custom-orange.svg?style=for-the-badge
[hacs]: https://hacs.xyz
[coverage]: https://htmlpreview.github.io/?https://github.com/Snuffy2/hass-favicon/blob/python-coverage-comment-action-data/htmlcov/index.html
[coverage-shield]: https://img.shields.io/endpoint?url=https%3A%2F%2Fraw.githubusercontent.com%2FSnuffy2%2Fhass-favicon%2Fpython-coverage-comment-action-data%2Fendpoint.json&style=for-the-badge
