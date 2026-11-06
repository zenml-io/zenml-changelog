from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts import changelog_compatibility as compat
from scripts.changelog_llm_outputs import CompatibilityStatus

PAGE = """---
description: Test page.
---

# Compatibility

Intro text.

## Client and server matrix

Stale matrix that the redraw replaces.

## Breaking points

| ID | Since | Type | What breaks for older clients |
| --- | --- | --- | --- |
| E1 | 0.92.0 | Exception | Reading step inputs fails. |
| H1 | 0.90.0 | Hard break | Old clients stop working. |

## Release by release

| Release | Status | Server impact on existing clients | Client upgrade notes |
| --- | --- | --- | --- |
| 0.92.0 | ⚠️ Exceptions (E1) | Step inputs changed. | – |
| 0.91.0 | ✅ Compatible | None known. | – |
| 0.90.0 | ❌ Hard break (H1) | Not compatible with earlier clients. | – |
| 0.85.0 | ✅ Compatible | None known. | – |
"""


def release(version: str, status: CompatibilityStatus, description: str = "") -> compat.ReleaseCompatibility:
    return compat.ReleaseCompatibility(
        version=version,
        status=status,
        server_impact="Server impact text.",
        client_upgrade_notes="",
        breaking_point_description=description,
    )


def matrix_section(page: str) -> str:
    start, end = compat._section_bounds(page, compat.MATRIX_HEADING)
    return page[start:end]


def test_committed_page_parses() -> None:
    page = (REPO_ROOT / compat.COMPATIBILITY_PAGE).read_text(encoding="utf-8")

    versions = compat.parse_release_versions(page)
    points = compat.parse_breaking_points(page)

    assert versions
    assert {point.since for point in points} <= set(versions)
    compat.redraw_matrix(page)


def test_redraw_follows_breaking_points_and_eras() -> None:
    matrix = matrix_section(compat.redraw_matrix(PAGE))

    assert "Stale matrix" not in matrix
    assert "**ZenML 0.90 and later**" in matrix
    assert "| **0.90** | ✅ | ✅ | ⚠️ E1 |" in matrix
    assert "| **0.92** | – | – | ✅ |" in matrix
    assert "<summary>ZenML 0.85 to 0.85</summary>" in matrix


def test_redraw_keeps_the_rest_of_the_page() -> None:
    redrawn = compat.redraw_matrix(PAGE)

    assert redrawn.startswith(PAGE[: PAGE.index("## Client and server matrix")])
    assert redrawn.endswith(PAGE[PAGE.index("## Breaking points"):])
    assert compat.redraw_matrix(redrawn) == redrawn


def test_compatible_release_adds_a_row_and_a_matrix_column() -> None:
    update = compat.add_release(PAGE, release("0.93.0", CompatibilityStatus.COMPATIBLE))

    assert update.new_breaking_point is None
    rows = compat._table_rows(update.page, compat.RELEASES_HEADING)
    assert rows[0] == ["0.93.0", "✅ Compatible", "Server impact text.", "–"]
    assert "| **0.90** | ✅ | ✅ | ⚠️ E1 | ⚠️ E1 |" in update.page


def test_adding_a_listed_release_changes_nothing() -> None:
    update = compat.add_release(PAGE, release("0.92.0", CompatibilityStatus.BREAKING, "Ignored."))

    assert update.page == PAGE
    assert update.release is None
    assert update.new_breaking_point is None


def test_release_with_exceptions_adds_the_next_exception() -> None:
    update = compat.add_release(
        PAGE,
        release("0.93.0", CompatibilityStatus.EXCEPTIONS, "Listing runs per pipeline fails."),
    )

    assert update.new_breaking_point is not None
    assert update.new_breaking_point.id == "E2"
    assert compat._table_rows(update.page, compat.BREAKING_POINTS_HEADING)[0] == [
        "E2",
        "0.93.0",
        "Exception",
        "Listing runs per pipeline fails.",
    ]
    assert compat._table_rows(update.page, compat.RELEASES_HEADING)[0][1] == "⚠️ Exceptions (E2)"
    assert "| **0.90** | ✅ | ✅ | ⚠️ E1 | ⚠️ E1–E2 |" in update.page


def test_hard_break_starts_a_new_era() -> None:
    update = compat.add_release(PAGE, release("1.0.0", CompatibilityStatus.BREAKING, "Old clients stop working."))
    matrix = matrix_section(update.page)

    assert update.new_breaking_point is not None
    assert update.new_breaking_point.id == "H2"
    assert "**ZenML 1.0 and later**" in matrix
    assert "<summary>ZenML 0.90 to 0.92</summary>" in matrix
    assert compat._table_rows(update.page, compat.RELEASES_HEADING)[0][1] == "❌ Hard break (H2)"


def test_cell_text_stays_inside_one_table_cell() -> None:
    update = compat.add_release(
        PAGE,
        compat.ReleaseCompatibility(
            version="0.93.0",
            status=CompatibilityStatus.COMPATIBLE,
            server_impact="First line\nsecond | line",
            client_upgrade_notes="  ",
        ),
    )

    row = compat._table_rows(update.page, compat.RELEASES_HEADING)[0]
    assert row == ["0.93.0", "✅ Compatible", "First line second \\| line", "–"]


def test_unknown_breaking_point_type_is_rejected() -> None:
    page = PAGE.replace("| Hard break |", "| Soft break |")

    with pytest.raises(ValueError, match="Soft break"):
        compat.parse_breaking_points(page)


def test_duplicate_release_rows_are_rejected() -> None:
    page = PAGE.replace("| 0.91.0 |", "| 0.92.0 |")

    with pytest.raises(ValueError, match="more than once"):
        compat.parse_release_versions(page)


def test_upgrade_impact_section_is_read_until_the_next_heading() -> None:
    body = "## Describe changes\nStuff.\n\n## Upgrade impact\nRe-create snapshots.\n\n## Pre-requisites\n- [x] done"

    assert compat.upgrade_impact_section(body) == "Re-create snapshots."
    assert compat.upgrade_impact_section("No such section.") == ""


def test_matrix_cells_collapse_consecutive_exception_ids() -> None:
    assert compat._compact_ids(["E4", "E2", "E3", "E6", "E9", "E8"]) == "E2–E4, E6, E8–E9"
    assert compat._compact_ids(["E5"]) == "E5"


def test_upgrade_impact_section_ignores_the_template_placeholder() -> None:
    template = "## Upgrade impact\n<!--- Required when this PR changes ... -->\n\n## Pre-requisites"
    filled = "## Upgrade impact\n<!--- Required when ... -->\nOlder clients can't list runs.\n\n## Pre-requisites"

    assert compat.upgrade_impact_section(template) == ""
    assert compat.upgrade_impact_section(filled) == "Older clients can't list runs."


def test_duplicate_breaking_point_ids_are_rejected() -> None:
    page = PAGE.replace("| H1 | 0.90.0 |", "| E1 | 0.90.0 |")

    with pytest.raises(ValueError, match="IDs more than once: E1"):
        compat.parse_breaking_points(page)


def test_status_referring_to_an_unknown_breaking_point_is_rejected() -> None:
    page = PAGE.replace("| 0.91.0 | ✅ Compatible |", "| 0.91.0 | ⚠️ Exceptions (E7) |")

    with pytest.raises(ValueError, match="Release 0.91.0 refers to unknown breaking points: E7"):
        compat.redraw_matrix(page)
