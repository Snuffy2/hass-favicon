# Contributing

Contributions to Favicon Changer are welcome. Keep changes focused and include
regression coverage when changing behavior.

## Reporting problems

Check existing issues before opening a report. Include your Home Assistant and
integration versions, steps to reproduce, expected and actual behavior, and
relevant logs. For icon problems, include the configured frontend path and icon
filenames. Remove credentials and other private information from logs and screenshots.

## Development setup

Use Python 3.14.2 or newer and uv 0.13.4 or newer, as required by `pyproject.toml`.
CI uses Python 3.14. Clone your fork, create a feature branch from `main`, and run
the commands below from the repository root.

The integration lives in `custom_components/favicon/`; tests live in `tests/`.
`pyproject.toml` contains dependency groups and tool settings, and `uv.lock`
records the resolved dependencies. Add test dependencies to the `pytest` group
and refresh the lockfile when changing dependencies. Keep the frontend test
assets aligned with the frontend version required by the locked Home Assistant
release.

## Tests

Install the locked test dependencies and the Chromium, Firefox and WebKit browsers, then run the suite:

```sh
uv sync --locked --group dev
./.venv/bin/python -m playwright install chromium firefox webkit
./.venv/bin/pytest
```

On Linux, use `./.venv/bin/python -m playwright install --with-deps chromium firefox webkit`
to install the browsers' system libraries too. The tests use an isolated temporary Home Assistant
configuration and generated icon files; no running Home Assistant is required.

The suite includes integration tests for configuration, options,
validation and removal; end-to-end HTTP tests for the configuration API, page,
manifest and icon downloads; and Chromium acceptance tests for the displayed
title, icon metadata, sidebar title, Settings navigation and page refresh. The
browser tests authenticate a temporary test user and navigate the real frontend;
configuration forms are covered through Home Assistant's flow managers and HTTP API.

Run one layer with `./.venv/bin/pytest -m integration`, `-m e2e`, or `-m end_user`.
To run without a browser installation, use `./.venv/bin/pytest -m 'not end_user'`.
CI installs Chromium and runs every layer.

## Code quality checks

After installing the `dev` group, run the repository checks:

```sh
./.venv/bin/prek run --all-files
```

The hooks in `prek.toml` check formatting, lint, types, docstrings, spelling and
workflow syntax. Some hooks apply fixes; inspect those changes and rerun checks
until they pass. Optional Git hooks can be installed with `./.venv/bin/prek install`.

Use type annotations and Google-style Python docstrings, consistent with the
existing code and configured checks.

## Pull requests

Open pull requests against `main`. Explain the problem, the resulting behavior,
and how the change was validated. Update affected documentation and include
screenshots when a visible change benefits from them.

Use a conventional PR title such as `fix: restore default icons after removal`
or `test: cover configuration validation`; CI validates the title. Run the
relevant tests and code quality checks before submitting, and mention any checks
you could not run. Keep generated reports, virtual environments and credentials
out of commits.
