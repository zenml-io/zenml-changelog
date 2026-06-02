#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = [
#     "pydantic>=2",
# ]
# ///
from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import List, Sequence, TypedDict

from pydantic import BaseModel, ConfigDict, StrictBool, StrictStr, ValidationError, model_validator

DEFAULT_CHANGELOG_WORKFLOW_RESULT_FILE = Path("changelog_workflow_result.json")
CHANGELOG_WORKFLOW_RESULT_ENV = "CHANGELOG_WORKFLOW_RESULT"
GITHUB_OUTPUT_ENV = "GITHUB_OUTPUT"
NEEDS_ATTENTION_HEADER = "The following PRs had empty or insufficient descriptions and need manual review:"
GITHUB_MULTILINE_OUTPUT_FIELDS = (
    "markdown_file",
    "breaking_changes",
    "needs_attention",
    "source_windows",
)
ALLOWED_MARKDOWN_FILES = frozenset(
    {
        "gitbook-release-notes/server-sdk.md",
        "gitbook-release-notes/pro-control-plane.md",
    }
)


class NeedsAttentionItem(TypedDict):
    number: str
    title: str
    url: str


class ChangelogWorkflowResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    has_changes: StrictBool
    markdown_file: StrictStr
    breaking_changes: StrictStr
    needs_attention: StrictStr
    source_windows: StrictStr

    @model_validator(mode="after")
    def require_changed_artifacts(self) -> "ChangelogWorkflowResult":
        if self.markdown_file:
            if any(ord(char) < 32 or ord(char) == 127 for char in self.markdown_file):
                raise ValueError("markdown_file must not contain control characters")
            if self.markdown_file not in ALLOWED_MARKDOWN_FILES:
                raise ValueError("markdown_file must be a known release-notes target")

        if self.has_changes:
            if not self.markdown_file.strip():
                raise ValueError("markdown_file is required when has_changes is true")
            if not self.source_windows.strip():
                raise ValueError("source_windows is required when has_changes is true")
        return self


def get_changelog_workflow_result_path() -> Path:
    return Path(os.environ.get(CHANGELOG_WORKFLOW_RESULT_ENV, DEFAULT_CHANGELOG_WORKFLOW_RESULT_FILE))


def clear_changelog_workflow_result(path: Path) -> None:
    try:
        path.unlink()
    except FileNotFoundError:
        return


def write_changelog_workflow_result(
    result: ChangelogWorkflowResult,
    path: Path | None = None,
) -> None:
    result_path = path or get_changelog_workflow_result_path()
    result_path.parent.mkdir(parents=True, exist_ok=True)
    result_path.write_text(
        json.dumps(result.model_dump(), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def read_changelog_workflow_result(path: Path | None = None) -> ChangelogWorkflowResult:
    result_path = path or get_changelog_workflow_result_path()
    try:
        raw = result_path.read_text(encoding="utf-8")
    except FileNotFoundError as exc:
        raise RuntimeError(f"Changelog workflow result file not found: {result_path}") from exc

    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Invalid changelog workflow result JSON in {result_path}: {exc}") from exc

    if not isinstance(payload, dict):
        raise RuntimeError(f"Invalid changelog workflow result in {result_path}: expected object")

    try:
        return ChangelogWorkflowResult.model_validate(payload)
    except ValidationError as exc:
        raise RuntimeError(f"Invalid changelog workflow result in {result_path}: {exc}") from exc


def _github_output_delimiter(name: str, value_lines: Sequence[str]) -> str:
    base = f"ZENML_CHANGELOG_OUTPUT_{name.upper()}"
    value_line_set = set(value_lines)
    delimiter = base
    suffix = 1
    while delimiter in value_line_set:
        delimiter = f"{base}_{suffix}"
        suffix += 1
    return delimiter


def _append_github_scalar_output(lines: List[str], name: str, value: str) -> None:
    lines.append(f"{name}={value}")


def _append_github_multiline_output(lines: List[str], name: str, value: str) -> None:
    value_lines = value.splitlines()
    delimiter = _github_output_delimiter(name, value_lines)
    lines.append(f"{name}<<{delimiter}")
    lines.extend(value_lines)
    lines.append(delimiter)


def write_changelog_github_outputs(
    result: ChangelogWorkflowResult,
    output_path: Path,
) -> None:
    lines: List[str] = []
    _append_github_scalar_output(lines, "has_changes", "true" if result.has_changes else "false")
    for field_name in GITHUB_MULTILINE_OUTPUT_FIELDS:
        _append_github_multiline_output(lines, field_name, getattr(result, field_name))
    with output_path.open("a", encoding="utf-8") as output_file:
        output_file.write("\n".join(lines) + "\n")


def require_env(name: str) -> str:
    value = os.environ.get(name)
    if value is None:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value


def run_write_github_outputs_mode() -> None:
    output_path = require_env(GITHUB_OUTPUT_ENV)
    result = read_changelog_workflow_result()
    write_changelog_github_outputs(result, Path(output_path))


def format_breaking_changes_output(
    bullets: List[str],
    *,
    is_major_bump: bool,
) -> str:
    cleaned = [bullet.strip() for bullet in bullets if bullet.strip()]
    if cleaned:
        return "\n".join(f"- {bullet}" for bullet in cleaned)
    if is_major_bump:
        return "- Major version bump detected; manual review recommended"
    return ""


def format_needs_attention_output(needs_attention: List[NeedsAttentionItem]) -> str:
    if not needs_attention:
        return ""
    lines = [NEEDS_ATTENTION_HEADER]
    for pr in needs_attention:
        if pr["url"]:
            lines.append(f"- PR #{pr['number']}: {pr['title']} ({pr['url']})")
        else:
            lines.append(f"- {pr['title']}")
    return "\n".join(lines)


def cli(argv: Sequence[str] | None = None) -> None:
    args = list(sys.argv[1:] if argv is None else argv)
    if args == ["write-github-outputs"]:
        run_write_github_outputs_mode()
        return
    raise SystemExit("Usage: workflow_result.py write-github-outputs")


if __name__ == "__main__":
    cli()
