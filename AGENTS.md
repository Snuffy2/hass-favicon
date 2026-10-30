# AGENTS

## Purpose

- Provide clear, repository-specific instructions for autonomous agents working in this repository.

## General Guidelines

- Follow Home Assistant developer documentation: https://developers.home-assistant.io/docs/.
- Be concise and explain coding steps briefly when making changes.
- For non-trivial edits, provide a short plan. For small, low-risk edits, implement and include a one-line summary.
- Focus on a single conceptual change at a time when public APIs or multiple modules are affected.
- Maintain project style and Python 3.14+ compatibility. Target the Home Assistant versions supported by this integration.
- If deviating from these guidelines, explain which guideline and why.

## Agent permissions and virtual environments

- Use the repository's existing virtual environment at `./.venv` when available.
- Run repository tooling through `./.venv/bin/...`.
- Installing packages from repository manifests into `./.venv` is allowed when needed for requested validation.

## Home Assistant integration hygiene

- When changing config, options, or other UI-visible strings, update `translations/*.json` as needed.
- When changing installation or configuration steps, update `README.md` and `hacs.json` as needed.

## Project structure

- Integration code is in `custom_components/favicon/`.
- Tests are in `tests/`; shared test fixtures are in `tests/conftest.py`.
- `README.md` is the primary user documentation.
- Keep constants in the integration's `const.py` and follow the existing module layout.

## Coding standards

- Add type annotations, including return types, to new or changed functions and classes.
- Use `Any` only when appropriate and avoid `cast` unless necessary.
- Do not use `assert` in production code.
- Follow existing docstring and formatting conventions; Python docstrings use Google style.
- Preserve useful comments, keep imports at the top, and correct comments made obsolete by changes.
- Prefer root-cause fixes and keep changes focused.
- Catch specific exceptions rather than broad `Exception`, unless an established pattern justifies it.
- Use Home Assistant's logging framework and include useful context in logs.

## Local tooling

- Project metadata and tool settings are in `pyproject.toml`; dependencies are managed with `uv`.
- Use `prek` for configured formatting and lint checks: `./.venv/bin/prek run -a`.
- Run tests with `./.venv/bin/python -m pytest`.
- Follow the applicable repository and user instructions when choosing validation; report checks that could not be run.

## Testing

- Use pytest and the existing pytest Home Assistant fixtures and helpers.
- Put tests under `tests/`, extending the corresponding existing test module where practical.
- Add or update tests for meaningful behavior changes, including relevant failure paths.
- Avoid tests that only mirror implementation details or duplicate existing coverage.
- For documentation, declarative configuration, and small workflow changes, use proportionate validation such as configured linters or focused checks.

## Git and pull requests

- Use `main` as the primary branch.
- Do not commit, push, or open a pull request unless explicitly requested.
- Keep feature branches tracking their same-named `origin` branch.
- Follow repository PR templates and describe the actual changes and validation accurately.

## Network and CI

- Obtain authorization before network operations that are not needed for explicitly requested publishing or validation.
- GitHub Actions are used for CI; keep workflow changes consistent with existing conventions.
