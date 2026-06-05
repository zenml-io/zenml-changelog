#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Build a self-contained offline blind-comparison web app from an eval run.

Reads one evaluation run's ``summary.json`` (produced by
``scripts/evaluate_changelog_llms.py``), turns passing model outputs into blind
A/B comparison pairs, and stamps everything — the comparison data plus a
vendored markdown renderer — into a single HTML file that opens with no server
and no network access.

The output is a build artifact and is expected to live under a gitignored path.
Model identities live in the embedded data but are never shown on screen; the
app shuffles left/right per reviewer at runtime and records which model each
side actually was, so results can be aggregated by model afterwards.
"""
from __future__ import annotations

import argparse
import itertools
import json
import random
import re
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from scripts.changelog_artifact_safety import is_production_artifact_path

REPO_ROOT = Path(__file__).resolve().parents[1]

APP_VERSION = 1

TYPE_RELEASE_NOTES = "release_notes"
TYPE_CHANGELOG_JSON = "changelog_json"
TYPE_BREAKING = "breaking_changes"

CONTENT_TYPES = (TYPE_RELEASE_NOTES, TYPE_CHANGELOG_JSON, TYPE_BREAKING)

TYPE_LABELS = {
    TYPE_RELEASE_NOTES: "Release notes",
    TYPE_CHANGELOG_JSON: "Changelog entries",
    TYPE_BREAKING: "Breaking-change notes",
}

TYPE_QUESTIONS = {
    TYPE_RELEASE_NOTES: "Which release notes would you rather ship?",
    TYPE_CHANGELOG_JSON: "Which set of dashboard entries is better?",
    TYPE_BREAKING: "Which breaking-change notes are more useful?",
}

DEFAULT_TARGET = 24
DEFAULT_SEED = 7

TEMPLATE_PATH = REPO_ROOT / "comparison_app" / "template.html"
MARKED_PATH = REPO_ROOT / "comparison_app" / "vendor" / "marked.min.js"
DEFAULT_FIXTURES_DIR = REPO_ROOT / "tests" / "fixtures" / "changelog-evals"

MARKED_PLACEHOLDER = "<!--__MARKED_JS__-->"
DATA_PLACEHOLDER = "<!--__APP_DATA__-->"


class ComparisonBuildError(RuntimeError):
    """Raised for builder configuration or input errors."""


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-") or "x"


def extract_content(result: dict, content_type: str) -> Any | None:
    """Return the comparable content of one model output, or None if empty.

    The three comparable shapes are: a release-notes markdown string, a list of
    {title, labels, description} dashboard entries, and a list of breaking-change
    bullet strings.
    """
    if content_type == TYPE_RELEASE_NOTES:
        body = (result.get("release_notes_body") or "").strip()
        return body or None
    if content_type == TYPE_CHANGELOG_JSON:
        entries = result.get("generated_grouped_entries") or []
        cleaned = [
            {
                "title": entry.get("title", ""),
                "labels": list(entry.get("labels", [])),
                "description": entry.get("description", ""),
            }
            for entry in entries
        ]
        return cleaned or None
    if content_type == TYPE_BREAKING:
        bullets = [bullet for bullet in (result.get("breaking_bullets") or []) if str(bullet).strip()]
        return bullets or None
    raise ComparisonBuildError(f"Unknown content type: {content_type!r}")


def build_comparison_pool(
    results: list[dict],
    source_prs_by_fixture: dict[str, list[dict]],
    content_types: tuple[str, ...] = CONTENT_TYPES,
    include_models: set[str] | None = None,
) -> list[dict]:
    """Build the full pool of blind comparison pairs from eval results.

    For every fixture and every output type, this forms all pairwise matchups of
    the models that both produced (different) non-empty content. Results whose
    hard gate failed are dropped — we never ask people to compare broken output.
    When ``include_models`` is given, only those display names are paired (used
    to keep synthetic test-double candidates out of a real comparison).
    """
    passing = [result for result in results if result.get("hard_gate_status") == "pass"]
    if include_models is not None:
        passing = [result for result in passing if result.get("display_name") in include_models]
    by_fixture: dict[str, list[dict]] = {}
    for result in passing:
        by_fixture.setdefault(result["fixture_id"], []).append(result)

    pool: list[dict] = []
    for fixture_id in sorted(by_fixture):
        fixture_results = by_fixture[fixture_id]
        source_prs = source_prs_by_fixture.get(fixture_id, [])
        for content_type in content_types:
            with_content: list[tuple[str, str, Any]] = []
            for result in fixture_results:
                content = extract_content(result, content_type)
                if content is not None:
                    with_content.append((result["display_name"], result.get("candidate_id", ""), content))
            with_content.sort(key=lambda triple: triple[0])
            for (model_a, cand_a, content_a), (model_b, cand_b, content_b) in itertools.combinations(
                with_content, 2
            ):
                if model_a == model_b or content_a == content_b:
                    continue
                pool.append(
                    {
                        "id": f"{fixture_id}__{content_type}__{_slug(model_a)}__vs__{_slug(model_b)}",
                        "type": content_type,
                        "type_label": TYPE_LABELS[content_type],
                        "question": TYPE_QUESTIONS[content_type],
                        "fixture": fixture_id,
                        "source_prs": source_prs,
                        "a": {"model": model_a, "candidate_id": cand_a, "content": content_a},
                        "b": {"model": model_b, "candidate_id": cand_b, "content": content_b},
                    }
                )
    return pool


def select_balanced(pool: list[dict], target: int, seed: int) -> list[dict]:
    """Pick ~target items, spread evenly across output types and model pairs.

    Selection is round-robin: cycle through output types, and within each type
    cycle through model pairs, taking one item each pass. A fixed seed makes the
    build reproducible. If target exceeds the pool, every item is returned.
    """
    rng = random.Random(seed)
    buckets: dict[tuple[str, tuple[str, str]], list[dict]] = {}
    for item in pool:
        pair_key = tuple(sorted((item["a"]["model"], item["b"]["model"])))
        buckets.setdefault((item["type"], pair_key), []).append(item)
    for key in buckets:
        rng.shuffle(buckets[key])

    types = sorted({key[0] for key in buckets})
    keys_by_type = {content_type: sorted(k for k in buckets if k[0] == content_type) for content_type in types}
    pair_pos = {content_type: 0 for content_type in types}

    selected: list[dict] = []
    remaining = sum(len(items) for items in buckets.values())
    type_pos = 0
    while len(selected) < target and remaining > 0:
        content_type = types[type_pos % len(types)]
        type_pos += 1
        keys = keys_by_type[content_type]
        if not keys:
            continue
        for _ in range(len(keys)):
            key = keys[pair_pos[content_type] % len(keys)]
            pair_pos[content_type] += 1
            if buckets[key]:
                selected.append(buckets[key].pop())
                remaining -= 1
                break
    return selected


def _embed_data_script(dataset: dict) -> str:
    payload = json.dumps(dataset, ensure_ascii=False, indent=2)
    # Stop any embedded "</script>" inside the data from closing the host tag.
    payload = payload.replace("</", "<\\/")
    return f"<script>window.BLIND_TEST = {payload};</script>"


def validate_comparison_output_path(output_path: Path, *, repo_root: Path = REPO_ROOT) -> Path:
    """Resolve and reject output paths that would overwrite production artifacts."""
    resolved = output_path if output_path.is_absolute() else repo_root / output_path
    resolved = resolved.resolve()
    if is_production_artifact_path(resolved, repo_root=repo_root):
        raise ComparisonBuildError(
            f"Refusing to write comparison app to production artifact path: {output_path}"
        )
    return resolved


def render_html(*, template: str, marked_js: str, dataset: dict) -> str:
    """Inline the markdown renderer and the comparison data into the template."""
    html = template.replace(MARKED_PLACEHOLDER, f"<script>{marked_js}</script>")
    html = html.replace(DATA_PLACEHOLDER, _embed_data_script(dataset))
    return html


def load_run_results(run_dir: Path) -> list[dict]:
    summary_path = run_dir / "summary.json"
    if not summary_path.exists():
        raise ComparisonBuildError(f"No summary.json found in run directory: {run_dir}")
    data = json.loads(summary_path.read_text(encoding="utf-8"))
    return data.get("results", [])


def _simplify_pr(pr: dict) -> dict:
    return {
        "number": pr.get("number"),
        "title": pr.get("title", ""),
        "url": pr.get("url", ""),
        "repo": pr.get("repo", ""),
    }


def load_fixture_meta(fixtures_dir: Path) -> dict[str, dict]:
    meta: dict[str, dict] = {}
    for path in sorted(fixtures_dir.glob("*.json")):
        fixture = json.loads(path.read_text(encoding="utf-8"))
        fixture_id = fixture.get("fixture_id")
        if not fixture_id:
            continue
        prs = [
            _simplify_pr(pr)
            for pr in [*fixture.get("release_notes_prs", []), *fixture.get("breaking_prs", [])]
        ]
        meta[fixture_id] = {
            "description": fixture.get("description", ""),
            "release_tag": fixture.get("release_tag", ""),
            "source_prs": prs,
        }
    return meta


def build_app(
    *,
    run_dir: Path,
    fixtures_dir: Path,
    output_path: Path,
    target: int = DEFAULT_TARGET,
    seed: int = DEFAULT_SEED,
    include_models: set[str] | None = None,
    template_path: Path = TEMPLATE_PATH,
    marked_path: Path = MARKED_PATH,
) -> dict:
    """Read an eval run, build a blind dataset, and write the single-file app."""
    output_path = validate_comparison_output_path(output_path)
    results = load_run_results(run_dir)
    fixture_meta = load_fixture_meta(fixtures_dir)
    prs_by_fixture = {fixture_id: info["source_prs"] for fixture_id, info in fixture_meta.items()}

    pool = build_comparison_pool(results, prs_by_fixture, include_models=include_models)
    if not pool:
        raise ComparisonBuildError(
            "No comparison pairs found — the run has no passing results with comparable content."
        )
    items = select_balanced(pool, target=target, seed=seed)
    for item in items:
        info = fixture_meta.get(item["fixture"], {})
        item["fixture_description"] = info.get("description", "")
        item["release_tag"] = info.get("release_tag", "")

    models = sorted({model for item in pool for model in (item["a"]["model"], item["b"]["model"])})
    run_id = json.loads((run_dir / "summary.json").read_text(encoding="utf-8")).get("run_id", run_dir.name)

    dataset = {
        "meta": {
            "run_id": run_id,
            "app_version": APP_VERSION,
            "target": target,
            "seed": seed,
            "item_count": len(items),
            "models": models,
        },
        "items": items,
    }

    template = template_path.read_text(encoding="utf-8")
    marked_js = marked_path.read_text(encoding="utf-8")
    html = render_html(template=template, marked_js=marked_js, dataset=dataset)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(html, encoding="utf-8")
    return dataset


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", type=Path, required=True, help="Eval run directory containing summary.json.")
    parser.add_argument("--fixtures-dir", type=Path, default=DEFAULT_FIXTURES_DIR)
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Output HTML path. Defaults to <run-dir>/blind-comparison.html.",
    )
    parser.add_argument("--target", type=int, default=DEFAULT_TARGET, help="How many comparisons to include.")
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED, help="Seed for reproducible balanced selection.")
    parser.add_argument(
        "--model",
        action="append",
        default=[],
        dest="models",
        help="Restrict to this model display name (repeatable). Omit to include every model in the run.",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    output = args.output or (args.run_dir / "blind-comparison.html")
    try:
        dataset = build_app(
            run_dir=args.run_dir,
            fixtures_dir=args.fixtures_dir,
            output_path=output,
            target=args.target,
            seed=args.seed,
            include_models=set(args.models) or None,
        )
    except ComparisonBuildError as error:
        print(f"error: {error}", file=sys.stderr)
        return 2
    print(f"Wrote blind comparison app to {output}")
    print(f"Items: {dataset['meta']['item_count']} | models: {', '.join(dataset['meta']['models'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
