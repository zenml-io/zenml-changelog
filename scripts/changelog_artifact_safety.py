#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path
from typing import Final

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
