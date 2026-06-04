from __future__ import annotations

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = REPO_ROOT / ".github" / "workflows" / "process-release.yml"


def test_process_release_workflow_wires_openai_shadow_comments() -> None:
    workflow = WORKFLOW.read_text(encoding="utf-8")

    assert "OPENAI_API_KEY: ${{ secrets.OPENAI_API_KEY }}" in workflow
    assert "CHANGELOG_LLM_PROVIDER: ${{ vars.CHANGELOG_LLM_PROVIDER || 'anthropic' }}" in workflow
    assert "CHANGELOG_LLM_MODEL: ${{ vars.CHANGELOG_LLM_MODEL || '' }}" in workflow
    assert 'CHANGELOG_OPENAI_SHADOW_MODE: "true"' in workflow
    assert "CHANGELOG_OPENAI_SHADOW_MODEL:" in workflow

    assert "id: create_widget_pr" in workflow
    assert "id: create_release_notes_pr" in workflow
    assert "steps.create_widget_pr.outputs.pull-request-number" in workflow
    assert "steps.create_release_notes_pr.outputs.pull-request-number" in workflow

    assert "zenml-changelog-openai-shadow-widget" in workflow
    assert "zenml-changelog-openai-shadow-release-notes" in workflow
    assert "peter-evans/find-comment@v3" in workflow
    assert "peter-evans/create-or-update-comment@v4" in workflow
    assert "openai-shadow-widget-comment.md" in workflow
    assert "openai-shadow-release-notes-comment.md" in workflow
    assert 'delimiter="$(uuidgen)"' in workflow
