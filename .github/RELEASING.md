# Releasing hass-favicon

Release Please manages the release pull request, version tag, and GitHub
Release from conventional commits merged to `main`.

The release pull request updates all version sources together:

- `.release-please-manifest.json`
- `custom_components/favicon/const.py`
- `custom_components/favicon/manifest.json`

Review and merge the release pull request after its normal required checks
pass. The next `Release Please` workflow run creates the `v`-prefixed tag and
GitHub Release, then builds and uploads `hass-favicon.zip` for HACS. Release Please
does not create or maintain a changelog file in this repository.

If archive creation or upload fails after the GitHub Release exists, manually
run the `Release Please` workflow with that release's `vMAJOR.MINOR.PATCH` tag.
The recovery run checks out the existing tag, validates its version sources,
and rebuilds and replaces `hass-favicon.zip` without creating another release.

The `RELEASE_PLEASE_TOKEN`, `PREK_AUTOUPDATE_TOKEN`, and `PREK_AUTOFIX_TOKEN`
repository secrets support release and prek automation. Release, prek autoupdate, and Dependabot auto-merge are restricted to
`Snuffy2/hass-favicon`, allowing this maintained fork while skipping other forks.
