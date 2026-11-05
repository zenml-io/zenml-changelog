#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = [
#     "pydantic>=2",
# ]
# ///
"""Compatibility page: reading its tables, adding release rows, and redrawing the matrix.

The page itself is the source of truth. People and the release automation edit two
tables, "Breaking points" and "Release by release"; the client/server matrix is always
derived from them, so it is never edited by hand and is redrawn on every update.
"""
from __future__ import annotations

import re
import sys
from enum import Enum
from pathlib import Path
from typing import List, Optional, Sequence, Tuple

from pydantic import BaseModel, ConfigDict

try:
    from scripts.changelog_llm_outputs import CompatibilityStatus
except ModuleNotFoundError:  # pragma: no cover - direct `uv run scripts/changelog_compatibility.py`
    from changelog_llm_outputs import CompatibilityStatus  # type: ignore[no-redef]

COMPATIBILITY_PAGE = Path("gitbook-release-notes/compatibility.md")
MATRIX_HEADING = "## Client and server matrix"
BREAKING_POINTS_HEADING = "## Breaking points"
RELEASES_HEADING = "## Release by release"
NO_KNOWN_IMPACT = "None known."
EMPTY_CELL = "–"

MATRIX_INTRO = (
    "Rows are the client version: the `zenml` package your team runs, including the one in "
    "your snapshot images. Columns are the server version. Versions are grouped by minor "
    "release (0.98 covers 0.98.0, 0.98.1, and so on). ✅ works. ⚠️ works, except for the "
    "listed breaking points. – the client is newer than the server, which is not supported."
)
OLDER_ERAS_NOTE = (
    "Each hard break starts a new era. A client and a server from different eras do not "
    "work together: upgrade both at the same time."
)

Series = Tuple[int, int]

_CELL_SEPARATOR = re.compile(r"(?<!\\)\|")
_VERSION = re.compile(r"^v?(\d+)\.(\d+)(?:\.\d+)?$")
_UPGRADE_IMPACT_HEADING = re.compile(r"^#{1,6}\s*upgrade impact\b.*$", flags=re.IGNORECASE | re.MULTILINE)


class BreakingPointKind(str, Enum):
    HARD_BREAK = "Hard break"
    EXCEPTION = "Exception"


_ID_PREFIX = {BreakingPointKind.HARD_BREAK: "H", BreakingPointKind.EXCEPTION: "E"}


class BreakingPoint(BaseModel):
    """A release from which clients older than `since` lose some or all functionality."""

    model_config = ConfigDict(frozen=True)

    id: str
    since: str
    kind: BreakingPointKind
    description: str

    @property
    def series(self) -> Series:
        return series_of(self.since)


class ReleaseCompatibility(BaseModel):
    """What one release means for existing clients, as written to the page."""

    model_config = ConfigDict(frozen=True)

    version: str
    status: CompatibilityStatus
    server_impact: str
    client_upgrade_notes: str
    breaking_point_description: str = ""


class CompatibilityUpdate(BaseModel):
    model_config = ConfigDict(frozen=True)

    page: str
    release: ReleaseCompatibility
    new_breaking_point: Optional[BreakingPoint] = None


def series_of(version: str) -> Series:
    match = _VERSION.match(version.strip())
    if not match:
        raise ValueError(f"Not a release version: {version!r}")
    return int(match.group(1)), int(match.group(2))


def format_series(series: Series) -> str:
    return f"{series[0]}.{series[1]}"


def upgrade_impact_section(pr_body: str) -> str:
    """Return the text under the PR description's "Upgrade impact" heading, or ''."""
    match = _UPGRADE_IMPACT_HEADING.search(pr_body or "")
    if not match:
        return ""
    rest = pr_body[match.end():]
    next_heading = re.search(r"^#{1,6}\s", rest, flags=re.MULTILINE)
    return (rest[: next_heading.start()] if next_heading else rest).strip()


def format_breaking_points(points: Sequence[BreakingPoint]) -> str:
    if not points:
        return "- none"
    return "\n".join(
        f"- {point.id} since {point.since} ({point.kind.value}): {point.description}" for point in points
    )


def _section_bounds(page: str, heading: str) -> Tuple[int, int]:
    """Return the start and end offsets of the body under `heading`."""
    match = re.search(rf"^{re.escape(heading)}[ \t]*$", page, flags=re.MULTILINE)
    if not match:
        raise ValueError(f"Compatibility page is missing the '{heading}' section")
    body_start = match.end() + 1
    next_heading = re.search(r"^## ", page[body_start:], flags=re.MULTILINE)
    body_end = body_start + next_heading.start() if next_heading else len(page)
    return body_start, body_end


def _split_cells(line: str) -> List[str]:
    return [cell.strip() for cell in _CELL_SEPARATOR.split(line.strip().strip("|"))]


def _is_separator_row(cells: Sequence[str]) -> bool:
    return all(cell and set(cell) <= set("-: ") for cell in cells)


def _table_rows(page: str, heading: str) -> List[List[str]]:
    """Return the data rows of the first table under `heading`, without its header."""
    start, end = _section_bounds(page, heading)
    rows = [
        _split_cells(line)
        for line in page[start:end].splitlines()
        if line.lstrip().startswith("|")
    ]
    data_rows = [cells for cells in rows if not _is_separator_row(cells)]
    return data_rows[1:]


def parse_breaking_points(page: str) -> List[BreakingPoint]:
    points: List[BreakingPoint] = []
    for cells in _table_rows(page, BREAKING_POINTS_HEADING):
        if len(cells) != 4:
            raise ValueError(f"Breaking points rows need 4 cells (ID, Since, Type, description): {cells}")
        point_id, since, kind, description = cells
        try:
            parsed_kind = BreakingPointKind(kind)
        except ValueError as exc:
            allowed = ", ".join(repr(k.value) for k in BreakingPointKind)
            raise ValueError(f"Breaking point {point_id} has type {kind!r}; expected one of {allowed}") from exc
        series_of(since)
        points.append(BreakingPoint(id=point_id, since=since, kind=parsed_kind, description=description))
    return points


def parse_release_versions(page: str) -> List[str]:
    versions = []
    for cells in _table_rows(page, RELEASES_HEADING):
        series_of(cells[0])
        versions.append(cells[0])
    duplicates = sorted({version for version in versions if versions.count(version) > 1})
    if duplicates:
        raise ValueError(f"Release by release lists these versions more than once: {', '.join(duplicates)}")
    return versions


def _split_into_eras(series: Sequence[Series], hard_breaks: Sequence[Series]) -> List[List[Series]]:
    eras: dict[int, List[Series]] = {}
    for current in sorted(series):
        era_index = sum(1 for hard_break in hard_breaks if hard_break <= current)
        eras.setdefault(era_index, []).append(current)
    return [eras[index] for index in sorted(eras)]


def _compact_ids(ids: Sequence[str]) -> str:
    """Collapse runs of consecutive IDs ("E2", "E3", "E4", "E6") into "E2–E4, E6".

    Cells would otherwise grow with every new exception and stretch the matrix.
    """
    numbered = sorted((int(re.sub(r"\D", "", point_id) or 0), point_id) for point_id in ids)
    runs: List[List[Tuple[int, str]]] = []
    for item in numbered:
        if runs and item[0] == runs[-1][-1][0] + 1:
            runs[-1].append(item)
        else:
            runs.append([item])
    return ", ".join(run[0][1] if len(run) == 1 else f"{run[0][1]}–{run[-1][1]}" for run in runs)


def _matrix_cell(client: Series, server: Series, exceptions: Sequence[BreakingPoint]) -> str:
    if client > server:
        return EMPTY_CELL
    applying = [point.id for point in exceptions if client < point.series <= server]
    return f"⚠️ {_compact_ids(applying)}" if applying else "✅"


def _render_era_table(era: Sequence[Series], exceptions: Sequence[BreakingPoint]) -> str:
    header = "| Client ↓ / Server → | " + " | ".join(format_series(server) for server in era) + " |"
    separator = "| --- " * (len(era) + 1) + "|"
    rows = [
        f"| **{format_series(client)}** | "
        + " | ".join(_matrix_cell(client, server, exceptions) for server in era)
        + " |"
        for client in era
    ]
    return "\n".join([header, separator, *rows])


def render_matrix(series: Sequence[Series], breaking_points: Sequence[BreakingPoint]) -> str:
    """Render the matrix section body: the current era open, older eras collapsed."""
    if not series:
        return MATRIX_INTRO + "\n"
    hard_breaks = sorted({point.series for point in breaking_points if point.kind is BreakingPointKind.HARD_BREAK})
    exceptions = [point for point in breaking_points if point.kind is BreakingPointKind.EXCEPTION]
    *older_eras, current_era = _split_into_eras(series, hard_breaks)

    parts = [MATRIX_INTRO]
    if older_eras:
        parts.append(OLDER_ERAS_NOTE)
    parts.append(f"**ZenML {format_series(current_era[0])} and later**")
    parts.append(_render_era_table(current_era, exceptions))
    for era in reversed(older_eras):
        parts.append(
            "<details>\n"
            f"<summary>ZenML {format_series(era[0])} to {format_series(era[-1])}</summary>\n\n"
            f"{_render_era_table(era, exceptions)}\n\n"
            "</details>"
        )
    return "\n\n".join(parts) + "\n"


def _replace_section_body(page: str, heading: str, body: str) -> str:
    start, end = _section_bounds(page, heading)
    trailing = "\n" if end < len(page) else ""
    return page[:start] + "\n" + body.strip() + "\n" + trailing + page[end:]


def redraw_matrix(page: str) -> str:
    """Rebuild the matrix from the page's breaking points and release rows."""
    series = sorted({series_of(version) for version in parse_release_versions(page)})
    return _replace_section_body(page, MATRIX_HEADING, render_matrix(series, parse_breaking_points(page)))


def _cell_text(text: str) -> str:
    """Make free text safe for a single markdown table cell."""
    flattened = " ".join(text.split()).replace("|", "\\|")
    return flattened or EMPTY_CELL


def _insert_first_row(page: str, heading: str, row: str) -> str:
    """Insert `row` as the first data row of the table under `heading` (newest first)."""
    start, end = _section_bounds(page, heading)
    lines = page[start:end].split("\n")
    for index, line in enumerate(lines):
        if line.lstrip().startswith("|") and _is_separator_row(_split_cells(line)):
            lines.insert(index + 1, row)
            return page[:start] + "\n".join(lines) + page[end:]
    raise ValueError(f"No table found under '{heading}'")


def _next_breaking_point_id(points: Sequence[BreakingPoint], kind: BreakingPointKind) -> str:
    prefix = _ID_PREFIX[kind]
    numbers = [int(point.id[len(prefix):]) for point in points if re.fullmatch(rf"{prefix}\d+", point.id)]
    return f"{prefix}{max(numbers, default=0) + 1}"


def _status_cell(status: CompatibilityStatus, point: Optional[BreakingPoint]) -> str:
    if status is CompatibilityStatus.COMPATIBLE or point is None:
        return "✅ Compatible"
    if status is CompatibilityStatus.EXCEPTIONS:
        return f"⚠️ Exceptions ({point.id})"
    return f"❌ Hard break ({point.id})"


def add_release(page: str, release: ReleaseCompatibility) -> CompatibilityUpdate:
    """Add a release row, plus a breaking point if needed, and redraw the matrix.

    Adding a release that is already listed changes nothing, so re-running the
    automation for the same tag never duplicates or overwrites a reviewed row.
    """
    if release.version in parse_release_versions(page):
        return CompatibilityUpdate(page=page, release=release)

    new_point: Optional[BreakingPoint] = None
    if release.status is not CompatibilityStatus.COMPATIBLE:
        kind = (
            BreakingPointKind.HARD_BREAK
            if release.status is CompatibilityStatus.BREAKING
            else BreakingPointKind.EXCEPTION
        )
        new_point = BreakingPoint(
            id=_next_breaking_point_id(parse_breaking_points(page), kind),
            since=release.version,
            kind=kind,
            description=_cell_text(release.breaking_point_description),
        )
        page = _insert_first_row(
            page,
            BREAKING_POINTS_HEADING,
            f"| {new_point.id} | {new_point.since} | {new_point.kind.value} | {new_point.description} |",
        )

    release_row = (
        f"| {release.version} | {_status_cell(release.status, new_point)} | "
        f"{_cell_text(release.server_impact)} | {_cell_text(release.client_upgrade_notes)} |"
    )
    page = _insert_first_row(page, RELEASES_HEADING, release_row)
    return CompatibilityUpdate(page=redraw_matrix(page), release=release, new_breaking_point=new_point)


def format_compatibility_summary(update: CompatibilityUpdate) -> str:
    """Summarize the update for the release-notes PR description."""
    release = update.release
    lines = [
        f"- **Status:** {_status_cell(release.status, update.new_breaking_point)}",
        f"- **Server impact on existing clients:** {_cell_text(release.server_impact)}",
        f"- **Client upgrade notes:** {_cell_text(release.client_upgrade_notes)}",
    ]
    if update.new_breaking_point:
        point = update.new_breaking_point
        lines.append(
            f"- **New breaking point {point.id}** ({point.kind.value.lower()} since {point.since}): "
            f"{point.description} The matrix was redrawn; check the new cells."
        )
    return "\n".join(lines)


def cli(argv: Sequence[str] | None = None) -> None:
    args = list(sys.argv[1:] if argv is None else argv)
    if args == ["redraw"]:
        COMPATIBILITY_PAGE.write_text(redraw_matrix(COMPATIBILITY_PAGE.read_text(encoding="utf-8")), encoding="utf-8")
        return
    raise SystemExit("Usage: changelog_compatibility.py redraw")


if __name__ == "__main__":
    cli()
