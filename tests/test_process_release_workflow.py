from __future__ import annotations

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = REPO_ROOT / ".github" / "workflows" / "process-release.yml"


def test_process_release_workflow_defaults_to_routed_openai_without_shadow_comments() -> None:
    workflow = WORKFLOW.read_text(encoding="utf-8")

    assert "OPENAI_API_KEY: ${{ secrets.OPENAI_API_KEY }}" in workflow
    assert "ANTHROPIC_API_KEY: ${{ secrets.ANTHROPIC_API_KEY }}" in workflow
    assert "CHANGELOG_LLM_PROVIDER: ${{ vars.CHANGELOG_LLM_PROVIDER || 'openai' }}" in workflow
    assert "CHANGELOG_LLM_MODEL: ${{ vars.CHANGELOG_LLM_MODEL || '' }}" in workflow
    assert "CHANGELOG_LLM_MODEL_GROUPED: ${{ vars.CHANGELOG_LLM_MODEL_GROUPED || 'gpt-5.4' }}" in workflow
    assert "CHANGELOG_LLM_MODEL_BREAKING: ${{ vars.CHANGELOG_LLM_MODEL_BREAKING || 'gpt-5.4' }}" in workflow
    assert "CHANGELOG_LLM_MODEL_RELEASE_NOTES: ${{ vars.CHANGELOG_LLM_MODEL_RELEASE_NOTES || 'gpt-5.5' }}" in workflow

    assert "id: create_widget_pr" in workflow
    assert "id: create_release_notes_pr" in workflow
    assert "CHANGELOG_OPENAI_SHADOW" not in workflow
    assert "openai-shadow" not in workflow
    assert "find-comment" not in workflow
    assert "create-or-update-comment" not in workflow
    assert "issues: write" not in workflow
