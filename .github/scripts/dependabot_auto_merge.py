"""Authorize dependency updates before enabling Dependabot auto-merge."""

import argparse
from collections.abc import Sequence
from itertools import pairwise
import json
import os
from pathlib import Path
import re
import sys
from typing import Any, NoReturn

DEPENDABOT = "dependabot[bot]"
WEB_FLOW = "web-flow"


def _get(value: Any, *keys: str | int) -> Any:
    """Read a nested JSON value, returning None for missing or invalid paths.

    Args:
        value (Any): JSON value to inspect.
        keys (str | int): Object keys or list indexes to follow.

    Returns:
        Any: Nested value, or None if the path does not exist.
    """
    for key in keys:
        if isinstance(value, dict) and isinstance(key, str):
            value = value.get(key)
        elif isinstance(value, list) and isinstance(key, int) and 0 <= key < len(value):
            value = value[key]
        else:
            return None
    return value


def _refuse(message: str) -> NoReturn:
    """Reject an unauthorized update.

    Args:
        message (str): Reason the update cannot be authorized.

    Raises:
        ValueError: Always, with the refusal reason.
    """
    raise ValueError(f"Refusing auto-merge; {message}")


def _is_trusted_base_file(base_directory: Path, path: str) -> bool:
    """Check whether an existing file is lexically within the trusted checkout.

    Args:
        base_directory (Path): Trusted base checkout directory.
        path (str): File path from the pull request.

    Returns:
        bool: Whether the path names an existing file within the checkout.
    """
    # Normalize lexically, preserving the original check's treatment of symlinks.
    base = Path(os.path.abspath(base_directory))  # noqa: PTH100
    candidate = Path(os.path.abspath(base / path))  # noqa: PTH100
    return candidate != base and candidate.is_relative_to(base) and candidate.is_file()


def _assert_allowed_files(ecosystem: str, changed_files: list[str], base_directory: Path) -> None:
    """Check that the update changes only existing dependency files.

    Args:
        ecosystem (str): Dependency ecosystem being updated.
        changed_files (list[str]): Pull request file paths.
        base_directory (Path): Trusted base checkout directory.
    """
    if not changed_files:
        _refuse("the pull request has no changed files.")
    if ecosystem == "uv":
        if not _is_trusted_base_file(base_directory, "uv.lock"):
            _refuse("the trusted base does not use uv.")
        if changed_files != ["uv.lock"]:
            _refuse("uv updates must change only uv.lock.")
    elif ecosystem == "npm":
        if not all(
            _is_trusted_base_file(base_directory, path)
            for path in ("package.json", "package-lock.json")
        ):
            _refuse("the trusted base does not use npm.")
        if changed_files != ["package-lock.json"] and not (
            len(changed_files) == 2 and set(changed_files) == {"package.json", "package-lock.json"}
        ):
            _refuse("npm updates must change only package.json and package-lock.json.")
    elif not all(
        (
            re.fullmatch(r"\.github/workflows/[^/]+\.ya?ml", path)
            or re.search(r"(^|/)action\.ya?ml$", path)
        )
        and _is_trusted_base_file(base_directory, path)
        for path in changed_files
    ):
        _refuse("the update changes a file outside the trusted dependency scope.")


def _is_verified_dependabot_commit(commit: Any) -> bool:
    """Check the author, committer, and signature of a Dependabot commit.

    Args:
        commit (Any): Commit returned by the GitHub API.

    Returns:
        bool: Whether the commit has verified Dependabot provenance.
    """
    return (
        _get(commit, "author", "login") == DEPENDABOT
        and _get(commit, "committer", "login") == WEB_FLOW
        and _get(commit, "commit", "verification", "verified") is True
    )


def authorize_dependabot_update(
    *,
    event: dict[str, Any],
    changed_files: list[str],
    commits: list[dict[str, Any]],
    ancestry_proofs: list[dict[str, Any]] | None = None,
    trusted_base_directory: Path | None = None,
) -> str:
    """Authorize a Dependabot update with only verified Update branch merges.

    Args:
        event (dict[str, Any]): GitHub pull request event.
        changed_files (list[str]): Pull request file paths.
        commits (list[dict[str, Any]]): Pull request commits, in API order.
        ancestry_proofs (list[dict[str, Any]] | None): Base comparison results for merge parents.
        trusted_base_directory (Path | None): Trusted checkout, or the current directory.

    Returns:
        str: Authorized dependency ecosystem.
    """
    repository = event.get("repository")
    pull_request = event.get("pull_request")
    if (
        _get(repository, "full_name") != "Snuffy2/hass-favicon"
        or _get(pull_request, "user", "login") != DEPENDABOT
        or _get(pull_request, "head", "repo", "full_name") != _get(repository, "full_name")
        or _get(pull_request, "base", "ref") != _get(repository, "default_branch")
    ):
        _refuse("the pull request does not have the required Dependabot provenance.")

    head_ref = _get(pull_request, "head", "ref")
    ecosystems = {
        "dependabot/uv/": "uv",
        "dependabot/npm_and_yarn/": "npm",
        "dependabot/github_actions/": "github-actions",
    }
    ecosystem = next(
        (
            name
            for prefix, name in ecosystems.items()
            if isinstance(head_ref, str) and head_ref.startswith(prefix)
        ),
        None,
    )
    if ecosystem is None:
        _refuse(f"unsupported Dependabot branch: {head_ref}")

    if len(commits) == 1:
        if not _is_verified_dependabot_commit(commits[0]) or _get(commits[0], "sha") != _get(
            pull_request, "head", "sha"
        ):
            _refuse("the pull request does not have a verified Dependabot head commit.")
    else:
        if len(commits) < 2:
            _refuse("the pull request is not a GitHub Update branch merge.")
        if not _is_verified_dependabot_commit(commits[0]):
            _refuse("the pull request history does not begin with Dependabot.")
        for previous, commit in pairwise(commits):
            parents = _get(commit, "parents")
            if (
                _get(commit, "committer", "login") != WEB_FLOW
                or _get(commit, "commit", "verification", "verified") is not True
                or not isinstance(parents, list)
                or len(parents) != 2
                or _get(commit, "parents", 0, "sha") != _get(previous, "sha")
            ):
                _refuse("the pull request contains a non-Dependabot edit.")

        current_base = _get(pull_request, "base", "sha")
        proofs = ancestry_proofs if ancestry_proofs is not None else []
        if not isinstance(proofs, list) or len(proofs) != len(commits) - 1:
            _refuse("the merge-parent ancestry evidence is incomplete.")
        for commit, proof in zip(commits[1:], proofs, strict=True):
            second_parent = _get(commit, "parents", 1, "sha")
            ahead_by = _get(proof, "ahead_by")
            behind_by = _get(proof, "behind_by")
            if (
                not isinstance(second_parent, str)
                or _get(proof, "parent_sha") != second_parent
                or _get(proof, "base_sha") != current_base
                or _get(proof, "base_commit") != second_parent
                or _get(proof, "head_commit") != current_base
                or _get(proof, "merge_base_commit") != second_parent
                or _get(proof, "status") not in ("ahead", "identical")
                or isinstance(ahead_by, bool)
                or not isinstance(ahead_by, (int, float))
                or not ahead_by >= 0
                or ahead_by % 1 != 0
                or isinstance(behind_by, bool)
                or not isinstance(behind_by, (int, float))
                or behind_by != 0
            ):
                _refuse("a merge second parent is not proven to be on the current base.")
        latest = commits[-1]
        if (
            _get(latest, "sha") != _get(pull_request, "head", "sha")
            or _get(latest, "parents", 1, "sha") != current_base
        ):
            _refuse("the latest commit is not an update from the current base branch.")

    _assert_allowed_files(ecosystem, changed_files, trusted_base_directory or Path.cwd())
    return ecosystem


def main(argv: Sequence[str] | None = None) -> None:
    """Authorize the event and API responses supplied by the workflow.

    Args:
        argv (Sequence[str] | None): Command arguments, or process arguments when omitted.
    """
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("event", "changed_files", "commits", "ancestry_proofs"):
        parser.add_argument(name, type=Path)
    args = parser.parse_args(argv)
    commit_pages = json.loads(args.commits.read_text(encoding="utf-8"))
    authorize_dependabot_update(
        event=json.loads(args.event.read_text(encoding="utf-8")),
        changed_files=[
            line for line in args.changed_files.read_text(encoding="utf-8").split("\n") if line
        ],
        commits=[commit for page in commit_pages for commit in page],
        ancestry_proofs=json.loads(args.ancestry_proofs.read_text(encoding="utf-8")),
    )
    sys.stdout.write("Authorized dependency update files and commit history.\n")


if __name__ == "__main__":
    main()
