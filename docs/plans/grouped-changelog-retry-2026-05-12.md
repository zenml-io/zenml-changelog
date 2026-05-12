# Grouped Changelog Retry: Plan

## Goal
Make the release automation recover when Anthropic returns a structurally valid but semantically invalid grouped changelog response — for example, assigning the same PR to two changelog groups.

The workflow should ask for a corrected grouping and continue if a later attempt is valid. It should fail only after targeted semantic retries are exhausted.

## Background
The failed GitHub Actions run for `zenml-io/zenml` release `0.94.4` crashed in `Run changelog update script` because `build_grouped_changelog_entries()` raised:

```text
RuntimeError: PR #4803 appears in more than one grouped changelog entry
```

The important sequence is:

1. `.github/workflows/process-release.yml:52` runs `uv run scripts/update_changelog.py | tee changelog_output.txt` under `set -euo pipefail`.
2. `main()` chooses `grouping_prs`, then calls `llm_generate_grouped_changelog_entries()` once (`scripts/update_changelog.py:1173`).
3. `build_grouped_changelog_entries()` validates and converts the LLM output (`scripts/update_changelog.py:975`).
4. If semantic validation raises, the script exits nonzero before writing `changelog.json`, updating GitBook markdown, or creating PR artifacts.

The existing Tenacity retry on `llm_generate_grouped_changelog_entries()` handles API, rate-limit, and Pydantic structured-output failures (`scripts/update_changelog.py:610`). It does not handle semantic mistakes discovered after the LLM call, such as duplicate, missing, or invented PR numbers.

Prior design treated LLM/schema failures as manual-rerun failures (`design/plan.md:775`). This incident is different: the environment was healthy, the response parsed, and the error was a recoverable sorting mistake.

## Approach
Add a small retry boundary around exactly this unit of work:

```text
call grouped LLM helper
  → validate grouped PR assignment
  → convert to changelog entries
```

Do not retry the whole script and do not add workflow-level retries. The fix belongs inside `scripts/update_changelog.py`, before any repository files are written.

### Recommended behavior

- First attempt uses the existing grouped-changelog prompt.
- If semantic validation fails, retry grouped generation with compact feedback:
  - validation errors, e.g. `PR #4803 appears in more than one grouped changelog entry`;
  - a compact invalid grouping summary, e.g. group titles plus PR-number lists.
- Use **3 semantic attempts total**.
- If a later attempt succeeds, continue normally: write `changelog.json`, update markdown, validate schema, and let the workflow create the widget/GitBook PRs.
- If all attempts fail, raise an actionable error that includes all attempt summaries.

The existing Tenacity retry remains responsible for transient Anthropic/API/structured-output problems. The new semantic retry is responsible only for parsed output that assigns PR numbers incorrectly.

This means the worst case is nested retries: 3 semantic attempts, each of which may use the existing 5-attempt Tenacity policy if Anthropic/API calls are flaky. That is acceptable for this release workflow because semantic failures should be rare, manual reruns are more expensive, and the retry boundary is before repository file writes.

## Work Items

### 1. Add a semantic grouping error type
In `scripts/update_changelog.py`, add a dedicated exception such as `GroupedChangelogSemanticError`.

Use this only for recoverable grouped-output mistakes:

- unknown PR number;
- duplicate PR assignment;
- omitted PR number.

Do **not** make generic `RuntimeError` retryable. The script also uses `RuntimeError` for hard failures like missing env vars, unconfigured repos, missing release tags, and missing Anthropic client.

### 2. Split semantic validation into a testable helper
Add a helper such as:

```text
validate_grouped_changelog_output(grouped_output, prs)
```

The helper should be called at the top of `build_grouped_changelog_entries()` (`scripts/update_changelog.py:975`). This makes it the single semantic-validation gate for every caller of that conversion function.

Move the current inline semantic checks out of `build_grouped_changelog_entries()` and into the helper. In particular, replace the existing `RuntimeError` sites for unknown, duplicate, and unassigned PR numbers (`scripts/update_changelog.py:990`, `scripts/update_changelog.py:994`, `scripts/update_changelog.py:1002`) with `GroupedChangelogSemanticError` raised by the helper.

The helper should collect all semantic errors for one attempt rather than stopping at the first error. It should then raise one `GroupedChangelogSemanticError` containing:

- all compact human-readable details;
- a compact invalid grouping summary suitable for retry feedback.

Keep conversion behavior unchanged after validation passes: same output shape, ID assignment, label mapping, slug generation, and audience behavior.

### 3. Let the grouped LLM helper accept retry feedback
Extend `llm_generate_grouped_changelog_entries()` (`scripts/update_changelog.py:615`) with an optional `retry_feedback` argument.

On the first attempt, keep the prompt effectively unchanged. On retries, append a clearly marked correction block:

```text
Previous grouped output failed validation.

Validation feedback:
- PR #4803 appeared in more than one group.

Previous invalid grouping:
- Group A: [4803, 4804]
- Group B: [4803, 4810]

Generate the grouped changelog entries again. Every PR number from the input list must appear exactly once. Do not invent, duplicate, or omit PR numbers.
```

Keep the existing Tenacity decorator unchanged.

### 4. Add a targeted grouped-generation orchestrator
Add a new function such as:

```text
generate_valid_grouped_changelog_entries(prs, source_repo, published_at, starting_id, max_attempts=3)
```

Its job:

1. call `llm_generate_grouped_changelog_entries()`;
2. call `build_grouped_changelog_entries()`;
3. catch only `GroupedChangelogSemanticError`;
4. build retry feedback from the validation error;
5. retry until a valid grouping is produced or attempts are exhausted.

On exhausted retries, raise a final error like:

```text
Grouped changelog generation failed semantic validation after 3 attempts.

Attempt 1:
- PR #4803 appears in more than one grouped changelog entry.

Attempt 2:
- PR #4810 was not assigned to any grouped changelog entry.

Attempt 3:
- Group references unknown PR #9999.

No changelog.json, markdown, or .image_state updates were written.
```

### 5. Replace the direct call in `main()`
Replace the current direct sequence in `main()` (`scripts/update_changelog.py:1173`):

```text
llm_generate_grouped_changelog_entries(...)
build_grouped_changelog_entries(...)
```

with the new orchestrator.

Everything downstream should stay the same:

- print created grouped entries;
- sort and prepend `new_entries`;
- write and validate `changelog.json`;
- rotate image state;
- render and insert markdown;
- print workflow markers.

### 6. Add focused tests
Create `tests/test_update_changelog_grouped_retry.py`.

Use pure fixtures and monkeypatching; do not call GitHub or Anthropic.

Cover:

1. duplicate PR numbers raise `GroupedChangelogSemanticError`;
2. unknown PR numbers raise `GroupedChangelogSemanticError`;
3. missing PR numbers raise `GroupedChangelogSemanticError`;
4. valid grouped output preserves existing conversion behavior: IDs, labels, slugs, audience, schema-shaped entry dicts;
5. semantic retry succeeds on the second attempt and passes non-empty retry feedback;
6. retry exhaustion fails after 3 attempts and includes all attempt summaries;
7. non-semantic errors, such as `RuntimeError("Anthropic client not initialized")`, are not swallowed or converted into semantic retry failures.

Recommended local command:

```bash
uv run --with pytest pytest tests/test_update_changelog_grouped_retry.py
```

### 7. Update documentation
Update the failure-policy table around `design/plan.md:775` so it distinguishes recoverable semantic grouping failures from hard LLM/configuration failures.

Add a row equivalent to:

```text
Semantically invalid grouped changelog output → retry grouped generation/conversion up to 3 attempts with validation feedback; fail only after exhaustion.
```

## Expected GitHub Actions Behavior

No workflow YAML changes are required for the core fix. On a successful semantic retry, the existing `Run changelog update script` step exits `0` with semantic-attempt log lines, then downstream validation, patch creation, artifact upload, and PR creation proceed normally. On exhausted semantic retries, the step exits nonzero before `changelog.json`, markdown, or `.image_state` are written, and before workflow patch artifacts or PRs are created.

## Non-goals

- Do not retry the entire workflow or all of `main()`.
- Do not change `changelog.json` schema.
- Do not change GitBook markdown generation.
- Do not change GitHub PR discovery.
- Do not catch all `RuntimeError`s.
- Do not suppress final schema validation failures.

## Decisions

- Semantic grouped-output retries: **3 attempts total**.
- Per-attempt validation: **collect all semantic errors**, then raise one semantic error.
- Validator location: **top of `build_grouped_changelog_entries()`**, so that function keeps enforcing its own input contract.
- Final failure: include **all invalid attempt summaries**.
- Retry prompt: include **compact validation feedback plus compact invalid grouping**, not full generated descriptions.

## Open Questions
None blocking.

## References
- Failed run: https://github.com/zenml-io/zenml-changelog/actions/runs/25743692814/job/75600937566
- Duplicate PR in failed grouping: https://github.com/zenml-io/zenml/pull/4803
- Existing grouped LLM helper: `scripts/update_changelog.py:615`
- Existing semantic validator/converter: `scripts/update_changelog.py:975`
- Current orchestration seam: `scripts/update_changelog.py:1173`
- Workflow script step: `.github/workflows/process-release.yml:52`
- Historical failure policy: `design/plan.md:775`
