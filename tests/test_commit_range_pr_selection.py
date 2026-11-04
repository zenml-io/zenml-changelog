from __future__ import annotations

import sys
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from github import UnknownObjectException

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts import update_changelog as uc

ZENML = "zenml-io/zenml"
DASHBOARD = "zenml-io/zenml-dashboard"
LABELS = ["release-notes", *uc.BREAKING_CHANGE_LABELS]


@dataclass
class FakePR:
    number: int
    labels: list[str] = field(default_factory=list)
    base_ref: str = "develop"
    title: str | None = None
    merged: bool = True
    merge_commit_sha: str | None = None

    def __post_init__(self) -> None:
        self.title = self.title or f"PR {self.number}"
        self.merge_commit_sha = self.merge_commit_sha or f"sha-{self.number}"
        self.html_url = f"https://github.com/{ZENML}/pull/{self.number}"
        self.user = SimpleNamespace(login="dev")
        self.body = f"Body for PR {self.number}"
        self.base = SimpleNamespace(ref=self.base_ref)
        # Ordered by number so results sort deterministically by merge time.
        merged_at = datetime(2026, 10, 20, tzinfo=timezone.utc) + timedelta(minutes=self.number)
        self.merged_at = merged_at if self.merged else None
        self.labels = [SimpleNamespace(name=name) for name in self.labels]


class FakeCommit:
    def __init__(self, sha: str, pulls: list[FakePR]) -> None:
        self.sha = sha
        self._pulls = pulls

    def get_pulls(self) -> list[FakePR]:
        return self._pulls


def squash_commit(pr: FakePR, *also_in: FakePR) -> FakeCommit:
    """A squash-merge commit; GitHub also lists open or later PRs that contain it."""
    return FakeCommit(pr.merge_commit_sha, [pr, *also_in])


class FakeRepo:
    def __init__(self, name: str, prs: list[FakePR], commits: list[FakeCommit]) -> None:
        self.full_name = name
        self.prs = {pr.number: pr for pr in prs}
        self.commits = commits
        self.compared: list[tuple[str, str]] = []

    def compare(self, base: str, head: str) -> SimpleNamespace:
        self.compared.append((base, head))
        return SimpleNamespace(commits=self.commits)

    def get_pull(self, number: int) -> FakePR:
        if number not in self.prs:
            raise UnknownObjectException(404, {"message": "Not Found"}, {})
        return self.prs[number]

    def get_release(self, tag: str) -> SimpleNamespace:
        return SimpleNamespace(
            published_at=datetime(2026, 11, 4, 5, 40, tzinfo=timezone.utc),
            created_at=None,
        )


class FakeGithub:
    def __init__(self, *repos: FakeRepo) -> None:
        self.repos = {repo.full_name: repo for repo in repos}
        self.queries: list[str] = []

    def get_repo(self, name: str) -> FakeRepo:
        return self.repos[name]

    def search_issues(self, query: str) -> list[SimpleNamespace]:
        self.queries.append(query)
        repo = next(repo for name, repo in self.repos.items() if f"repo:{name} " in query)
        return [
            SimpleNamespace(number=pr.number)
            for pr in repo.prs.values()
            if pr.merged and any(f'label:"{label.name}"' in query for label in pr.labels)
        ]


def window(
    previous_tag: str | None = "0.98.0",
    current_tag: str = "0.98.1",
    repo: str = ZENML,
    base_branch: str = "develop",
) -> uc.SourceReleaseWindow:
    return uc.SourceReleaseWindow(
        source_repo=repo,
        base_branch=base_branch,
        previous_tag=previous_tag,
        current_tag=current_tag,
        is_primary=repo == ZENML,
    )


def numbers(prs: list[dict[str, Any]]) -> list[int]:
    return [pr["number"] for pr in prs]


def test_pr_merged_after_the_release_branch_cut_is_left_for_the_next_release() -> None:
    in_release = FakePR(5399, ["release-notes"])
    unlabeled = FakePR(5400, ["no-release-notes"])
    # Merged into develop after release/0.98.1 was cut but before the release was
    # published, so its commit is not in 0.98.0...0.98.1.
    merged_after_cut = FakePR(5397, ["release-notes"])
    repo = FakeRepo(
        ZENML,
        prs=[in_release, unlabeled, merged_after_cut],
        commits=[squash_commit(in_release), squash_commit(unlabeled)],
    )
    gh = FakeGithub(repo)

    prs = uc.list_window_prs(gh, window(), LABELS)

    assert numbers(prs) == [5399]
    assert repo.compared == [("0.98.0", "0.98.1")]
    assert gh.queries == []


def test_backport_is_listed_as_its_original_pr_when_only_the_backport_is_in_range() -> None:
    original = FakePR(5405, ["release-notes"], title="Add version 0.98.0 to legacy docs")
    backport = FakePR(
        5407,
        ["backport"],
        base_ref="release/0.98.1",
        title="Add version 0.98.0 to legacy docs (#5405)",
    )
    repo = FakeRepo(ZENML, prs=[original, backport], commits=[squash_commit(backport)])

    prs = uc.list_window_prs(FakeGithub(repo), window(), LABELS)

    assert numbers(prs) == [5405]
    assert prs[0]["title"] == "Add version 0.98.0 to legacy docs"
    assert prs[0]["url"].endswith("/pull/5405")
    assert prs[0]["labels"] == ["release-notes", "backport"]


def test_backport_and_original_in_the_same_range_are_listed_once() -> None:
    original = FakePR(5405, ["release-notes"])
    backport = FakePR(5407, base_ref="release/0.98.1", title="PR 5405 (#5405)")
    repo = FakeRepo(
        ZENML,
        prs=[original, backport],
        commits=[squash_commit(original), squash_commit(backport)],
    )

    prs = uc.list_window_prs(FakeGithub(repo), window(), LABELS)

    assert numbers(prs) == [5405]


def test_backport_label_counts_for_the_original_pr() -> None:
    original = FakePR(5405)
    backport = FakePR(5407, ["release-notes"], base_ref="release/0.98.1", title="PR 5405 (#5405)")
    repo = FakeRepo(ZENML, prs=[original, backport], commits=[squash_commit(backport)])

    prs = uc.list_window_prs(FakeGithub(repo), window(), LABELS)

    assert numbers(prs) == [5405]


@pytest.mark.parametrize(
    "referenced_pr",
    [
        None,  # e.g. the reference is an issue number, not a PR
        FakePR(4000, merged=False),
        FakePR(4000, base_ref="main"),
    ],
)
def test_release_branch_pr_without_a_merged_base_branch_original_is_kept(
    referenced_pr: FakePR | None,
) -> None:
    release_only = FakePR(5407, ["release-notes"], base_ref="release/0.98.1", title="Hotfix (#4000)")
    prs_in_repo = [release_only] + ([referenced_pr] if referenced_pr else [])
    repo = FakeRepo(ZENML, prs=prs_in_repo, commits=[squash_commit(release_only)])

    prs = uc.list_window_prs(FakeGithub(repo), window(), LABELS)

    assert numbers(prs) == [5407]


def test_base_branch_pr_with_a_trailing_pr_reference_is_not_remapped() -> None:
    follow_up = FakePR(5410, ["release-notes"], title="Follow up on the step cache fix (#5300)")
    repo = FakeRepo(ZENML, prs=[follow_up, FakePR(5300)], commits=[squash_commit(follow_up)])

    prs = uc.list_window_prs(FakeGithub(repo), window(), LABELS)

    assert numbers(prs) == [5410]


def test_commit_maps_to_the_pr_that_merged_it_not_open_or_later_prs() -> None:
    feature = FakePR(1104, ["release-notes"], base_ref="staging")
    still_open = FakePR(1200, ["release-notes"], base_ref="staging", merged=False)
    release_pr = FakePR(1109, ["release-notes"], base_ref="main", merge_commit_sha="merge-sha")
    repo = FakeRepo(
        DASHBOARD,
        prs=[feature, still_open, release_pr],
        commits=[squash_commit(feature, still_open, release_pr)],
    )

    prs = uc.list_window_prs(
        FakeGithub(repo),
        window("0.44.3", "0.44.4", repo=DASHBOARD, base_branch="staging"),
        LABELS,
    )

    assert numbers(prs) == [1104]


def test_commit_range_uses_prefixed_tags() -> None:
    feature = FakePR(1104, ["release-notes"], base_ref="staging")
    repo = FakeRepo(DASHBOARD, prs=[feature], commits=[squash_commit(feature)])

    uc.list_window_prs(
        FakeGithub(repo),
        window("0.44.3", "0.44.4", repo=DASHBOARD, base_branch="staging"),
        LABELS,
    )

    assert repo.compared == [("v0.44.3", "v0.44.4")]


def test_first_release_without_previous_tag_falls_back_to_merged_pr_search() -> None:
    feature = FakePR(1, ["release-notes"])
    breaking = FakePR(2, ["breaking-change"])
    repo = FakeRepo(ZENML, prs=[feature, breaking], commits=[])
    gh = FakeGithub(repo)

    prs = uc.list_window_prs(gh, window(previous_tag=None), LABELS)

    assert numbers(prs) == [1, 2]
    assert repo.compared == []
    assert gh.queries[0] == (
        f"repo:{ZENML} is:pr is:merged base:develop "
        'merged:2020-01-01T00:00:00Z..2026-11-04T05:40:00Z label:"release-notes"'
    )
    assert len(gh.queries) == len(LABELS)


def test_original_of_a_backport_consumed_by_an_earlier_release_is_filtered(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # 0.98.1 shipped the backport of #5405, so the ledger holds the original
    # number. 0.99.0's range contains #5405's own develop commit.
    original = FakePR(5405, ["release-notes"])
    new_feature = FakePR(5420, ["release-notes", "breaking-change"])
    zenml_repo = FakeRepo(
        ZENML,
        prs=[original, new_feature],
        commits=[squash_commit(original), squash_commit(new_feature)],
    )
    dashboard_repo = FakeRepo(DASHBOARD, prs=[], commits=[])
    gh = FakeGithub(zenml_repo, dashboard_repo)
    markdown_file = uc.REPO_CONFIG[ZENML]["markdown_file"]
    consumed_at = "2026-11-04T06:00:00+00:00"
    state = uc.ConsumedSourceState(
        targets={
            uc.target_state_key(ZENML, markdown_file): uc.ConsumedTargetState(
                trigger_repo=ZENML,
                markdown_file=markdown_file,
                consumed_prs={
                    f"{ZENML}#5405": uc.ConsumedPR(
                        source_repo=ZENML,
                        number=5405,
                        first_consumed_by_release_tag="0.98.1",
                        first_consumed_at=consumed_at,
                        previous_tag="0.98.0",
                        current_tag="0.98.1",
                    )
                },
            )
        }
    )
    monkeypatch.setattr(uc, "find_latest_release_tag", lambda gh, repo: "0.44.4")
    monkeypatch.setattr(
        uc,
        "find_previous_tag",
        lambda gh, repo, tag: {"0.99.0": "0.98.1", "0.44.4": "0.44.3"}[tag],
    )

    collection = uc.collect_multi_source_prs(
        gh=gh,
        trigger_repo=ZENML,
        trigger_release_tag="0.99.0",
        consumed_state=state,
    )

    assert numbers(collection.release_notes_prs) == [5420]
    assert numbers(collection.breaking_prs) == [5420]
    zenml_collection = collection.included_windows[0]
    assert zenml_collection.filtered_pr_keys == [f"{ZENML}#5405"]
    assert zenml_repo.compared == [("0.98.1", "0.99.0")]
    assert dashboard_repo.compared == [("v0.44.3", "v0.44.4")]
