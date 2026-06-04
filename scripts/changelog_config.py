#!/usr/bin/env python3
from __future__ import annotations

from typing import Any, Dict, List

REPO_CONFIG: Dict[str, Dict[str, Any]] = {
    "zenml-io/zenml": {
        "type": "oss",
        "markdown_file": "gitbook-release-notes/server-sdk.md",
        "audience": "oss",
        "include_release_link": True,
        "include_compatibility_note": False,
        "sources": [
            {
                "repo": "zenml-io/zenml",
                "default_branch": "develop",
                "github_tag_prefix": "",
            },
            {
                "repo": "zenml-io/zenml-dashboard",
                "default_branch": "staging",
                "github_tag_prefix": "v",
            },
        ],
    },
    "zenml-io/zenml-cloud-api": {
        "type": "pro",
        "markdown_file": "gitbook-release-notes/pro-control-plane.md",
        "audience": "pro",
        "include_release_link": False,
        "include_compatibility_note": False,
        "sources": [
            {
                "repo": "zenml-io/zenml-cloud-api",
                "default_branch": "develop",
                "github_tag_prefix": "",
            },
            {
                "repo": "zenml-io/zenml-cloud-ui",
                "default_branch": "staging",
                "github_tag_prefix": "",
            },
        ],
    },
}

def get_source_config(repo_name: str) -> Dict[str, Any]:
    for trigger_config in REPO_CONFIG.values():
        for source in trigger_config.get("sources", []):
            if source.get("repo") == repo_name:
                return source
    return {}

def with_prefix(repo_name: str, tag: str) -> str:
    config = get_source_config(repo_name)
    prefix = config.get("github_tag_prefix", "")
    if prefix and tag.startswith(prefix):
        return tag
    return f"{prefix}{tag}"

def strip_prefix(repo_name: str, tag: str) -> str:
    config = get_source_config(repo_name)
    prefix = config.get("github_tag_prefix", "")
    if prefix and tag.startswith(prefix):
        return tag[len(prefix) :]
    return tag

LABEL_MAPPING: Dict[str, str] = {
    "bug": "bugfix",
    "bugfix": "bugfix",
    "fix": "bugfix",
    "feature": "feature",
    "enhancement": "improvement",
    "improvement": "improvement",
    "deprecation": "deprecation",
    "breaking": "deprecation",
    "breaking-change": "deprecation",
    "breaking changes": "deprecation",
}

BREAKING_CHANGE_LABELS: List[str] = [
    "breaking-change",
    "breaking changes",
    "breaking",
]

PLACEHOLDER_LEARN_MORE_URL = "https://example.com/REPLACE-ME"

PLACEHOLDER_DOCS_URL = "https://docs.zenml.io/REPLACE-ME"

