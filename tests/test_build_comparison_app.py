from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts import build_comparison_app as builder


def make_result(
    fixture: str,
    model: str,
    *,
    status: str = "pass",
    entries: list[dict] | None = None,
    body: str = "",
    bullets: list[str] | None = None,
) -> dict:
    return {
        "fixture_id": fixture,
        "display_name": model,
        "candidate_id": "cand-" + model.lower().replace(" ", "-"),
        "hard_gate_status": status,
        "generated_grouped_entries": entries,
        "release_notes_body": body,
        "breaking_bullets": bullets or [],
    }


ENTRY_A = {
    "title": "Faster starts",
    "labels": ["feature"],
    "description": "Templates help.",
    "id": 1,
    "slug": "faster-starts",
    "audience": "oss",
}


# ---------------------------------------------------------------- extract_content


def test_extract_release_notes_returns_body() -> None:
    result = make_result("f", "Claude baseline", body="#### Hi\n\ntext")
    assert builder.extract_content(result, builder.TYPE_RELEASE_NOTES) == "#### Hi\n\ntext"


def test_extract_release_notes_blank_returns_none() -> None:
    result = make_result("f", "Claude baseline", body="   \n  ")
    assert builder.extract_content(result, builder.TYPE_RELEASE_NOTES) is None


def test_extract_changelog_json_keeps_only_title_labels_description() -> None:
    result = make_result("f", "Claude baseline", entries=[ENTRY_A])
    out = builder.extract_content(result, builder.TYPE_CHANGELOG_JSON)
    assert out == [{"title": "Faster starts", "labels": ["feature"], "description": "Templates help."}]


def test_extract_breaking_returns_bullets() -> None:
    result = make_result("f", "Claude baseline", bullets=["Do X before upgrade."])
    assert builder.extract_content(result, builder.TYPE_BREAKING) == ["Do X before upgrade."]


def test_extract_missing_content_returns_none() -> None:
    result = make_result("f", "Claude baseline")
    assert builder.extract_content(result, builder.TYPE_CHANGELOG_JSON) is None
    assert builder.extract_content(result, builder.TYPE_BREAKING) is None
    assert builder.extract_content(result, builder.TYPE_RELEASE_NOTES) is None


# ---------------------------------------------------------------- build_comparison_pool


def test_pool_pairs_two_models_for_each_type() -> None:
    results = [
        make_result("f1", "Claude baseline", body="A body", entries=[ENTRY_A]),
        make_result("f1", "OpenAI 5.4", body="B body", entries=[{**ENTRY_A, "title": "Other"}]),
    ]
    pool = builder.build_comparison_pool(results, {"f1": []})
    types = sorted({item["type"] for item in pool})
    assert types == sorted([builder.TYPE_RELEASE_NOTES, builder.TYPE_CHANGELOG_JSON])
    notes = next(item for item in pool if item["type"] == builder.TYPE_RELEASE_NOTES)
    assert {notes["a"]["model"], notes["b"]["model"]} == {"Claude baseline", "OpenAI 5.4"}
    assert {notes["a"]["content"], notes["b"]["content"]} == {"A body", "B body"}


def test_pool_excludes_failing_results() -> None:
    results = [
        make_result("f1", "Claude baseline", body="A body"),
        make_result("f1", "OpenAI 5.4", body="B body", status="fail"),
    ]
    assert builder.build_comparison_pool(results, {"f1": []}) == []


def test_pool_excludes_identical_content_pairs() -> None:
    results = [
        make_result("f1", "Claude baseline", body="same words"),
        make_result("f1", "OpenAI 5.4", body="same words"),
    ]
    notes = [
        item
        for item in builder.build_comparison_pool(results, {"f1": []})
        if item["type"] == builder.TYPE_RELEASE_NOTES
    ]
    assert notes == []


def test_pool_attaches_source_prs() -> None:
    prs = [{"number": 101, "title": "Add templates", "url": "u", "repo": "zenml-io/zenml"}]
    results = [
        make_result("f1", "Claude baseline", body="A"),
        make_result("f1", "OpenAI 5.4", body="B"),
    ]
    pool = builder.build_comparison_pool(results, {"f1": prs})
    assert pool[0]["source_prs"] == prs


def test_pool_makes_all_pairs_for_three_models() -> None:
    results = [make_result("f1", model, body=f"body {model}") for model in ["Claude baseline", "OpenAI 5.4", "OpenAI 5.5"]]
    notes = [
        item
        for item in builder.build_comparison_pool(results, {"f1": []})
        if item["type"] == builder.TYPE_RELEASE_NOTES
    ]
    assert len(notes) == 3  # C(3, 2)
    for item in notes:
        assert item["a"]["model"] != item["b"]["model"]


def test_pool_includes_only_whitelisted_models() -> None:
    results = [
        make_result("f1", "Claude baseline", body="A body"),
        make_result("f1", "OpenAI 5.4", body="B body"),
        make_result("f1", "Fake OpenAI mini", body="C body"),
    ]
    pool = builder.build_comparison_pool(
        results, {"f1": []}, include_models={"Claude baseline", "OpenAI 5.4"}
    )
    notes = [item for item in pool if item["type"] == builder.TYPE_RELEASE_NOTES]
    assert len(notes) == 1
    assert {notes[0]["a"]["model"], notes[0]["b"]["model"]} == {"Claude baseline", "OpenAI 5.4"}


def test_pool_without_whitelist_keeps_all_models() -> None:
    results = [
        make_result("f1", "Claude baseline", body="A body"),
        make_result("f1", "OpenAI 5.4", body="B body"),
        make_result("f1", "Fake OpenAI mini", body="C body"),
    ]
    pool = builder.build_comparison_pool(results, {"f1": []})
    notes = [item for item in pool if item["type"] == builder.TYPE_RELEASE_NOTES]
    assert len(notes) == 3  # C(3, 2)


# ---------------------------------------------------------------- select_balanced


def _pool_of(content_type: str, count: int, tag: str = "") -> list[dict]:
    return [
        {
            "id": f"{content_type}-{tag}-{index}",
            "type": content_type,
            "a": {"model": "Claude baseline", "content": f"a{index}"},
            "b": {"model": "OpenAI 5.4", "content": f"b{index}"},
        }
        for index in range(count)
    ]


def test_select_balanced_respects_target() -> None:
    pool = _pool_of(builder.TYPE_RELEASE_NOTES, 10)
    assert len(builder.select_balanced(pool, target=4, seed=7)) == 4


def test_select_balanced_is_deterministic_for_seed() -> None:
    pool = _pool_of(builder.TYPE_RELEASE_NOTES, 10)
    first = [item["id"] for item in builder.select_balanced(pool, target=5, seed=7)]
    second = [item["id"] for item in builder.select_balanced(pool, target=5, seed=7)]
    assert first == second


def test_select_balanced_spreads_across_types() -> None:
    pool = _pool_of(builder.TYPE_RELEASE_NOTES, 10, "rn") + _pool_of(builder.TYPE_CHANGELOG_JSON, 10, "cj")
    chosen = builder.select_balanced(pool, target=4, seed=7)
    counts: dict[str, int] = {}
    for item in chosen:
        counts[item["type"]] = counts.get(item["type"], 0) + 1
    assert counts.get(builder.TYPE_RELEASE_NOTES) == 2
    assert counts.get(builder.TYPE_CHANGELOG_JSON) == 2


def test_select_balanced_target_larger_than_pool_returns_all() -> None:
    pool = _pool_of(builder.TYPE_RELEASE_NOTES, 3)
    assert len(builder.select_balanced(pool, target=99, seed=1)) == 3


# ---------------------------------------------------------------- render_html

TEMPLATE = "<html><head><!--__MARKED_JS__--></head><body><!--__APP_DATA__--></body></html>"


def test_render_html_embeds_dataset_and_marked() -> None:
    dataset = {"meta": {"run_id": "r1"}, "items": [{"id": "x"}]}
    out = builder.render_html(template=TEMPLATE, marked_js="MARKED_SOURCE", dataset=dataset)
    assert "MARKED_SOURCE" in out
    assert "r1" in out
    assert "BLIND_TEST" in out


def test_render_html_has_no_external_script_or_stylesheet() -> None:
    out = builder.render_html(template=TEMPLATE, marked_js="var x=1;", dataset={"meta": {}, "items": []})
    assert re.search(r"<script[^>]+\bsrc\s*=", out) is None
    assert re.search(r"<link[^>]+\bhref\s*=", out) is None


def test_template_sanitizes_rendered_markdown() -> None:
    template = (REPO_ROOT / "comparison_app" / "template.html").read_text(encoding="utf-8")

    assert "function sanitizeHtml" in template
    assert "sanitizeHtml(marked.parse" in template
    assert "sanitizeHtml(marked.parseInline" in template
    assert "script,style,iframe,object,embed" in template
    assert "name.indexOf('on') === 0" in template


def test_render_html_escapes_closing_script_tag_in_data() -> None:
    dataset = {"meta": {}, "items": [{"content": "</script><script>alert(1)</script>"}]}
    out = builder.render_html(template=TEMPLATE, marked_js="", dataset=dataset)
    assert "</script><script>alert(1)" not in out
    assert "<\\/script>" in out


def test_validate_output_path_rejects_production_artifacts() -> None:
    for unsafe in [
        Path("changelog.json"),
        Path(".image_state"),
        Path(".consumed_sources_state"),
        Path("gitbook-release-notes/server-sdk.md"),
        Path("gitbook-release-notes/other.md"),
    ]:
        with pytest.raises(builder.ComparisonBuildError, match="production artifact"):
            builder.validate_comparison_output_path(unsafe)


def test_validate_output_path_allows_eval_results_output() -> None:
    resolved = builder.validate_comparison_output_path(Path("eval-results/openai-migration/app.html"))
    assert resolved == (REPO_ROOT / "eval-results" / "openai-migration" / "app.html").resolve()


# ---------------------------------------------------------------- build_app (end to end)


def test_build_app_writes_self_contained_html(tmp_path: Path) -> None:
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    summary = {
        "run_id": "test-run",
        "results": [
            make_result("synthetic-oss-small", "Claude baseline", body="#### A\n\ntext", entries=[ENTRY_A]),
            make_result(
                "synthetic-oss-small",
                "OpenAI 5.4",
                body="#### B\n\nother text",
                entries=[{**ENTRY_A, "title": "Other"}],
            ),
        ],
    }
    (run_dir / "summary.json").write_text(json.dumps(summary), encoding="utf-8")

    fixtures_dir = tmp_path / "fixtures"
    fixtures_dir.mkdir()
    (fixtures_dir / "synthetic-oss-small.json").write_text(
        json.dumps(
            {
                "fixture_id": "synthetic-oss-small",
                "description": "Small OSS release.",
                "source_repo": "zenml-io/zenml",
                "release_tag": "0.91.0",
                "release_url": "https://example/0.91.0",
                "published_at": "2026-05-01T12:00:00Z",
                "release_notes_prs": [
                    {"number": 101, "title": "Add templates", "url": "u", "repo": "zenml-io/zenml"}
                ],
                "breaking_prs": [],
                "offline_candidates": [],
            }
        ),
        encoding="utf-8",
    )

    output_path = tmp_path / "app.html"
    dataset = builder.build_app(
        run_dir=run_dir,
        fixtures_dir=fixtures_dir,
        output_path=output_path,
        target=24,
        seed=7,
    )

    assert output_path.exists()
    html = output_path.read_text(encoding="utf-8")
    assert "BLIND_TEST" in html
    assert "Add templates" in html  # source PR surfaced for the show-source panel
    assert dataset["meta"]["run_id"] == "test-run"
    assert len(dataset["items"]) >= 1
    # offline guarantee holds for the real template too
    assert re.search(r"<script[^>]+\bsrc\s*=", html) is None
    assert re.search(r"<link[^>]+\bhref\s*=", html) is None
