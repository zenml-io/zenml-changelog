#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path
from typing import Iterable, Final

PRODUCTION_ARTIFACT_RELATIVE_PATHS: Final = frozenset(
    {
        "changelog.json",
        ".image_state",
        ".consumed_sources_state",
        "gitbook-release-notes/server-sdk.md",
        "gitbook-release-notes/pro-control-plane.md",
    }
)


def production_artifact_paths(repo_root: Path) -> set[Path]:
    """Return the known production artifact paths for this repository."""
    return {(repo_root / relative_path).resolve() for relative_path in PRODUCTION_ARTIFACT_RELATIVE_PATHS}


def is_production_artifact_path(path: Path, *, repo_root: Path) -> bool:
    """Return whether a path is a production changelog/release-note artifact."""
    resolved = path.resolve()
    gitbook_dir = (repo_root / "gitbook-release-notes").resolve()
    return resolved in production_artifact_paths(repo_root) or (
        resolved.is_relative_to(gitbook_dir) and resolved.suffix == ".md"
    )


def unsafe_relative_artifact_path_reason(
    path: Path,
    *,
    repo_root: Path,
    extra_production_relative_paths: Iterable[str] = (),
) -> str | None:
    """Explain why a configured relative output path is unsafe, if it is.

    This is used for non-production review artifacts such as shadow comments.
    Those files must be simple repo-relative paths and must not point at known
    production artifacts.
    """
    if path.is_absolute():
        return "absolute paths are not allowed"
    if ".." in path.parts:
        return "parent-directory traversal is not allowed"
    if path.parts and path.parts[0] == "gitbook-release-notes":
        return "release-note markdown paths are production artifacts"

    production_relative_paths = {
        *PRODUCTION_ARTIFACT_RELATIVE_PATHS,
        *extra_production_relative_paths,
    }
    if path.as_posix() in production_relative_paths:
        return "path is a production artifact"

    if is_production_artifact_path(repo_root / path, repo_root=repo_root):
        return "path is a production artifact"
    return None
