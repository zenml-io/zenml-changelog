from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts import sync_zenml_github_release_notes as sync
from scripts import update_changelog as uc


def valid_sync_meta_body(
    source_repo: str = "zenml-io/zenml",
    release_tag: str = "0.85.0",
    markdown_file: str = "gitbook-release-notes/server-sdk.md",
    extra_lines: str = "",
) -> str:
    extra = f"{extra_lines}\n" if extra_lines else ""
    return f"""<!--
{sync.START_SYNC_META_SENTINEL}
source_repo={source_repo}
release_tag={release_tag}
markdown_file={markdown_file}
{extra}{sync.END_SYNC_META_SENTINEL}
-->

Automated release notes update.
"""


def test_extract_release_section_matches_update_changelog_header_and_footer() -> None:
    header = uc.render_release_header(
        release_tag="0.85.0",
        published_at="2026-06-02T10:11:12Z",
        image_number=7,
        source_repo="zenml-io/zenml",
    )
    footer = uc.render_release_footer(
        source_repo="zenml-io/zenml",
        release_url="https://github.com/zenml-io/zenml/releases/tag/0.85.0",
    )
    markdown = (
        "# Server SDK\n\n"
        f"{header}"
        "<!-- generated bookkeeping comment -->\n"
        "### Highlights\n\n"
        "ZenML now keeps release notes safer.\n\n"
        "#### Details\n\n"
        "Nested headings remain part of the release.\n\n"
        f"{footer}\n\n"
        "## 0.84.0 (2026-05-01)\n\nOlder content.\n"
    )

    extracted = sync.extract_release_section_from_server_sdk(markdown, "0.85.0")

    assert "### Highlights" in extracted
    assert "#### Details" in extracted
    assert "ZenML now keeps release notes safer." in extracted
    assert "Nested headings remain part of the release." in extracted
    assert "See what's new and improved" not in extracted
    assert "<img" not in extracted
    assert "<!--" not in extracted
    assert "View full release on GitHub" not in extracted
    assert "***" not in extracted
    assert "Older content" not in extracted


def test_extract_release_section_stops_at_separator() -> None:
    markdown = """## 1.2.3 (2026-06-02)

Release body.

***

This is after the separator.
"""

    extracted = sync.extract_release_section_from_server_sdk(markdown, "1.2.3")

    assert extracted == "Release body."


def test_extract_release_section_stops_at_next_release_heading_not_subheadings() -> None:
    markdown = """## 1.2.3 (2026-06-02)

### Kept subsection

Keep this subsection.

#### Also kept

Keep this deeper subsection.

## 1.2.2 (2026-05-01)

Do not include older release.
"""

    extracted = sync.extract_release_section_from_server_sdk(markdown, "1.2.3")

    assert "### Kept subsection" in extracted
    assert "#### Also kept" in extracted
    assert "Do not include older release" not in extracted


def test_extract_release_section_missing_heading_fails_clearly() -> None:
    with pytest.raises(RuntimeError, match="Release heading not found"):
        sync.extract_release_section_from_server_sdk("## 1.2.2 (2026-05-01)\n", "1.2.3")


def test_extract_release_section_empty_tag_fails_clearly() -> None:
    with pytest.raises(ValueError, match="release_tag must be a non-empty string"):
        sync.extract_release_section_from_server_sdk("## 1.2.3 (2026-06-02)\n", "  ")


def test_upsert_inserts_managed_block_before_whats_changed() -> None:
    updated = sync.upsert_prepended_block(
        existing_body="Intro text.\n\n## What's Changed\n\n* Existing release item\n",
        new_block="GitBook release notes.",
        tag="1.2.3",
    )

    assert updated.index("GitBook release notes.") < updated.index("## What's Changed")
    assert updated.startswith("Intro text.")
    assert updated.endswith("* Existing release item\n")


def test_upsert_prepends_when_whats_changed_is_absent() -> None:
    updated = sync.upsert_prepended_block(
        existing_body="Existing release body.",
        new_block="GitBook release notes.",
        tag="1.2.3",
    )

    assert updated.startswith("<!-- ZENML_GITBOOK_RELEASE_NOTES_START tag=1.2.3 -->")
    assert "GitBook release notes.\n<!-- ZENML_GITBOOK_RELEASE_NOTES_END tag=1.2.3 -->\n\nExisting release body." in updated


def test_upsert_replaces_same_tag_managed_block() -> None:
    existing = """<!-- ZENML_GITBOOK_RELEASE_NOTES_START tag=1.2.3 -->
Old managed notes.
<!-- ZENML_GITBOOK_RELEASE_NOTES_END tag=1.2.3 -->

## What's Changed

* Existing release item
"""

    updated = sync.upsert_prepended_block(
        existing_body=existing,
        new_block="New managed notes.",
        tag="1.2.3",
    )

    assert "New managed notes." in updated
    assert "Old managed notes." not in updated
    assert updated.count("ZENML_GITBOOK_RELEASE_NOTES_START tag=1.2.3") == 1


def test_upsert_preserves_other_tag_managed_blocks() -> None:
    other_tag_block = """<!-- ZENML_GITBOOK_RELEASE_NOTES_START tag=1.2.2 -->
Older managed notes.
<!-- ZENML_GITBOOK_RELEASE_NOTES_END tag=1.2.2 -->"""
    existing = f"{other_tag_block}\n\n## What's Changed\n\n* Existing release item\n"

    updated = sync.upsert_prepended_block(
        existing_body=existing,
        new_block="New managed notes.",
        tag="1.2.3",
    )

    assert "Older managed notes." in updated
    assert "New managed notes." in updated
    assert updated.count("ZENML_GITBOOK_RELEASE_NOTES_START tag=") == 2


def test_upsert_is_idempotent_for_same_block_and_tag() -> None:
    once = sync.upsert_prepended_block(
        existing_body="## What's Changed\n\n* Existing release item\n",
        new_block="Managed notes.",
        tag="1.2.3",
    )
    twice = sync.upsert_prepended_block(
        existing_body=once,
        new_block="Managed notes.",
        tag="1.2.3",
    )

    assert once == twice


def test_parse_sync_metadata_happy_path_with_unknown_extra_key() -> None:
    metadata = sync.parse_sync_metadata_from_pr_body(
        valid_sync_meta_body(extra_lines="future_key=future value")
    )

    assert metadata == sync.SyncMetadata(
        source_repo="zenml-io/zenml",
        release_tag="0.85.0",
        markdown_file="gitbook-release-notes/server-sdk.md",
    )


def test_parse_sync_metadata_accepts_crlf_and_trims_values() -> None:
    body = valid_sync_meta_body(
        source_repo=" zenml-io/zenml ",
        release_tag=" 0.85.0 ",
        markdown_file=" gitbook-release-notes/server-sdk.md ",
    ).replace("\n", "\r\n")

    metadata = sync.parse_sync_metadata_from_pr_body(body)

    assert metadata.source_repo == "zenml-io/zenml"
    assert metadata.release_tag == "0.85.0"
    assert metadata.markdown_file == "gitbook-release-notes/server-sdk.md"


def test_parse_sync_metadata_does_not_count_end_sentinel_as_second_start() -> None:
    metadata = sync.parse_sync_metadata_from_pr_body(valid_sync_meta_body())

    assert metadata.release_tag == "0.85.0"


@pytest.mark.parametrize(
    ("body", "error_match"),
    [
        ("No metadata here.", "block not found"),
        (
            f"<!--\n{sync.START_SYNC_META_SENTINEL}\nsource_repo=zenml-io/zenml\n",
            "missing its end sentinel",
        ),
        (
            f"""<!--
{sync.START_SYNC_META_SENTINEL}
source_repo=zenml-io/zenml
release_tag=0.85.0
{sync.END_SYNC_META_SENTINEL}
-->""",
            "markdown_file",
        ),
        (
            f"""<!--
{sync.START_SYNC_META_SENTINEL}
source_repo=zenml-io/zenml
source_repo=zenml-io/zenml-cloud-api
release_tag=0.85.0
markdown_file=gitbook-release-notes/server-sdk.md
{sync.END_SYNC_META_SENTINEL}
-->""",
            "Duplicate sync metadata key: source_repo",
        ),
        (
            f"""<!--
{sync.START_SYNC_META_SENTINEL}
source_repo=zenml-io/zenml
release_tag=
markdown_file=gitbook-release-notes/server-sdk.md
{sync.END_SYNC_META_SENTINEL}
-->""",
            "release_tag.*must not be empty",
        ),
        (
            valid_sync_meta_body() + "\n" + valid_sync_meta_body(release_tag="0.85.1"),
            "found multiple",
        ),
        (
            valid_sync_meta_body(markdown_file="gitbook-release-notes/pro-control-plane.md"),
            "Refusing OSS sync",
        ),
    ],
)
def test_parse_sync_metadata_fails_closed_on_broken_required_data(
    body: str,
    error_match: str,
) -> None:
    with pytest.raises(RuntimeError, match=error_match):
        sync.parse_sync_metadata_from_pr_body(body)


def test_should_sync_oss_release_notes_only_for_zenml_repo() -> None:
    assert sync.should_sync_oss_release_notes(
        sync.SyncMetadata(
            source_repo="zenml-io/zenml",
            release_tag="0.85.0",
            markdown_file="gitbook-release-notes/server-sdk.md",
        )
    )
    assert not sync.should_sync_oss_release_notes(
        sync.SyncMetadata(
            source_repo="zenml-io/zenml-cloud-api",
            release_tag="0.13.15",
            markdown_file="gitbook-release-notes/pro-control-plane.md",
        )
    )


def test_parser_mode_writes_github_outputs(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    output_path = tmp_path / "github-output.txt"
    monkeypatch.setenv("PR_BODY", valid_sync_meta_body())
    monkeypatch.setenv("GITHUB_OUTPUT", str(output_path))

    sync.run_parse_sync_metadata_mode()

    assert output_path.read_text(encoding="utf-8") == (
        "source_repo=zenml-io/zenml\n"
        "release_tag=0.85.0\n"
        "markdown_file=gitbook-release-notes/server-sdk.md\n"
        "should_sync=true\n"
    )


def test_cli_dispatches_parse_sync_meta_mode(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    output_path = tmp_path / "github-output.txt"
    monkeypatch.setenv("PR_BODY", valid_sync_meta_body())
    monkeypatch.setenv("GITHUB_OUTPUT", str(output_path))

    sync.cli(["parse-sync-meta"])

    assert "should_sync=true\n" in output_path.read_text(encoding="utf-8")


def test_parser_mode_writes_should_sync_false_for_non_oss_source(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    output_path = tmp_path / "github-output.txt"
    monkeypatch.setenv(
        "PR_BODY",
        valid_sync_meta_body(
            source_repo="zenml-io/zenml-cloud-api",
            release_tag="0.13.15",
            markdown_file="gitbook-release-notes/pro-control-plane.md",
        ),
    )
    monkeypatch.setenv("GITHUB_OUTPUT", str(output_path))

    sync.run_parse_sync_metadata_mode()

    assert "should_sync=false\n" in output_path.read_text(encoding="utf-8")
