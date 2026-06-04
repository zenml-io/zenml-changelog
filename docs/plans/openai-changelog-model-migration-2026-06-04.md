# OpenAI Changelog Model Migration: Plan

## Goal

Migrate the changelog automation from Anthropic Claude Sonnet 4.5 to OpenAI models without degrading dashboard changelog entries, GitBook release notes, breaking-change summaries, workflow outputs, or consumed-source replay prevention.

The key model question is empirical: `gpt-5.4-mini` is not automatically too weak, and `gpt-5.5` is not automatically necessary. We should test a mini model, a stronger model, and a high-quality ceiling model against the current Claude output, then choose the cheapest option that preserves quality and contracts.

## Background

### Current automation seams

- `.github/workflows/process-release.yml:3-16` triggers the automation from `repository_dispatch` release events or manual `workflow_dispatch` inputs.
- `.github/workflows/process-release.yml:43-58` runs `uv run scripts/update_changelog.py` with release metadata, GitHub credentials, `ANTHROPIC_API_KEY`, and `CHANGELOG_WORKFLOW_RESULT`.
- `scripts/update_changelog.py:1211-1248` initializes the script, requires `SOURCE_REPO`, `RELEASE_TAG`, `GITHUB_TOKEN`, and `ANTHROPIC_API_KEY`, then constructs Anthropic and GitHub clients.
- `scripts/update_changelog.py:92-131` defines `REPO_CONFIG`, the main extension seam that maps trigger repositories to output markdown files, audiences, source repos, branch defaults, tag prefixes, and release-link behavior.
- `scripts/source_windows.py:42-71` defines the source-window result types used to collect release-note PRs and breaking-change PRs across configured source repositories.
- `scripts/update_changelog.py:539-557` wires concrete GitHub functions into `source_windows.collect_multi_source_prs`, giving the source-window logic a testable seam.
- `scripts/consumed_sources.py:241-315` prevents replay by checking and recording consumed release windows and PRs only after successful artifact generation.

### Current LLM call sites and contracts

- `scripts/update_changelog.py:171-232` defines the Pydantic output models: `ChangelogCopy`, `GroupedChangelogEntry`, `GroupedChangelogOutput`, `BreakingChangesOutput`, and `MarkdownSection`.
- `scripts/update_changelog.py:611-676` generates grouped dashboard changelog entries with `anthropic_client.beta.messages.parse(...)`, `model="claude-sonnet-4-5-20250929"`, Anthropic structured outputs, `temperature=0`, and `output_format=GroupedChangelogOutput`.
- `scripts/update_changelog.py:683-743` generates breaking-change bullets as `BreakingChangesOutput`.
- `scripts/update_changelog.py:805-862` generates the GitBook release-note body as `MarkdownSection`.
- `scripts/update_changelog.py:871-967` still contains an older full-section markdown generator, but the current main path assembles header, breaking section, body, and footer separately.
- `scripts/update_changelog.py:989-1180` is the key semantic safety layer: it rejects ambiguous, unknown, duplicated, or missing PR assignments and retries grouped generation up to three times with feedback before any repository artifacts are written.
- `scripts/update_changelog.py:1344-1391` writes `changelog.json`, validates it, renders markdown, updates consumed-source state, and writes the structured workflow result.

The important boundary is: the model produces semantic content only. It should not own source-window metadata, release-note headers, image tags, footers, workflow outputs, GitHub multiline formatting, `.image_state`, or `.consumed_sources_state`.

### Existing test and CI guardrails

- `tests/test_update_changelog_grouped_retry.py:53-117` tests semantic grouped-output validation: duplicate PR assignment, invented PR numbers, missing PR numbers, and valid grouped conversion.
- `tests/test_update_changelog_grouped_retry.py:129-264` tests manual semantic retries and the fail-before-writing behavior when grouped generation cannot be made valid.
- `tests/test_update_changelog_main.py:61-164` uses fake Anthropic/GitHub clients and monkeypatched LLM helpers to test the main workflow without live API calls.
- `tests/test_update_changelog_workflow_result.py:26-279` tests the deterministic workflow-result model, JSON round trips, GitHub multiline outputs, exact formatting contracts, and fail-closed behavior.
- `.github/workflows/process-release.yml:68-74` validates `changelog.json` against `changelog_schema/announcement-schema.json` after generation.
- `scripts/run_pytest.py` currently includes `anthropic` in its inline dependency list; OpenAI SDK support would need to be added where tests/scripts require it.

### Prior art and warnings

- `docs/plans/structured-update-changelog-output-2026-06-02.md:4-7` planned the separation between deterministic workflow metadata and semantic LLM-generated changelog content.
- `docs/plans/structured-update-changelog-output-2026-06-02.md:47-55` calls out exact multiline-output contracts: `breaking_changes` remains bullets-only, `needs_attention` includes its header plus PR bullets, and `source_windows` is marker-free body text.
- `docs/reviews/critique-structured-update-changelog-output-2026-06-02.md:7-15` warned that these exact string contracts are easy to under-specify and need explicit tests.
- `README.md:45-48` documents the current implemented flow: `update_changelog.py` writes `changelog_workflow_result.json`, `workflow_result.py` publishes GitHub Actions outputs, and grouped changelog entries are generated via Anthropic structured outputs.

### OpenAI facts verified during planning

As of June 4, 2026, the official OpenAI docs support the following planning assumptions:

- The Responses API supports structured parsing with Pydantic models using `client.responses.parse(..., text_format=<PydanticModel>)`, with parsed output available as `response.output_parsed`.
- OpenAI Structured Outputs should be used instead of prompt-only JSON for this migration.
- OpenAI Structured Outputs require all fields to be required and objects to set `additionalProperties: false`; the current Pydantic list defaults need a compatibility pass.
- The model pages list `gpt-5.4-mini`, `gpt-5.4`, and `gpt-5.5` as supporting Structured Outputs and the Responses endpoint.
- Current listed standard prices are: `gpt-5.4-mini` at $0.75 / 1M input tokens and $4.50 / 1M output tokens, `gpt-5.4` at $2.50 input and $15 output, and `gpt-5.5` at $5 input and $30 output.
- Model names, SDK syntax, and pricing are live product facts; verify them again from official docs immediately before implementation.

## Approach

Use a targeted provider migration, not a broad rewrite.

The current release automation already has good safety rails. The provider-specific part is narrow: Anthropic imports, Anthropic client initialization, Anthropic retry exception classes, and the five `anthropic_client.beta.messages.parse(...)` calls. The safest plan is to put a thin structured-output provider layer at that seam, keep Anthropic as the production default, add OpenAI support behind configuration, and run OpenAI side-by-side before cutover.

Concrete story:

1. The rest of the script keeps asking for `GroupedChangelogOutput`, `BreakingChangesOutput`, or `MarkdownSection`.
2. A small provider wrapper decides whether that request goes to Anthropic or OpenAI.
3. The existing semantic validators still act like the lock on the door: if a model assigns PR `#101` twice and forgets `#103`, no repository artifact is written.
4. The evaluation harness runs on copied historical inputs, not live release state, so it cannot accidentally mark source windows consumed.
5. Only after offline evaluation, and optionally a manual or CI shadow comparison, do we switch production to OpenAI.

### Model choice

Evaluate these candidates:

| Candidate | Role | Expected use |
| --- | --- | --- |
| `claude-sonnet-4-5-20250929` | Champion baseline | Keep as rollback until OpenAI proves itself |
| `gpt-5.4-mini` | Main cost/latency challenger | Preferred if it passes hard gates and human review |
| `gpt-5.4` | Quality challenger | Use globally or only for release-note body if mini is too thin |
| `gpt-5.5` | Quality ceiling | Use only if the quality gain justifies cost |

Working hypothesis: `gpt-5.4-mini` may be strong enough for grouped dashboard entries, breaking-change bullets, and possibly first-pass summarization. The release-note prose is the riskiest call site because it needs editorial judgment: it must preserve OSS vs Pro tone, avoid implementation noise, include PR links only when appropriate, and produce readable GitBook structure. A likely routing to test is: cheaper model for extracting/grouping/summarizing PR themes, stronger model such as `gpt-5.4` or `gpt-5.5` for final GitBook release-note prose. If mini passes hard structure checks but produces thinner release notes, route `llm_generate_release_notes_body(...)` and the older `llm_generate_markdown_section(...)` helper to the stronger model.

### API mapping

Use the OpenAI Responses API structured parsing path, not raw JSON mode and not a prompt-only schema instruction.

| Current Anthropic shape | OpenAI Responses shape |
| --- | --- |
| `model="claude-sonnet-4-5-20250929"` | `model=<configured OpenAI model>` |
| `messages=[{"role": "user", "content": prompt}]` | `input=[{"role": "user", "content": prompt}]` |
| `output_format=<PydanticModel>` | `text_format=<PydanticModel>` |
| `max_tokens=...` | `max_output_tokens=...` |
| `temperature=0` | `temperature=0` |
| Anthropic structured-output beta flag | no equivalent |
| no equivalent | `store=False` unless there is a deliberate need to retain responses |

Make reasoning effort and service tier configurable for OpenAI, but do not over-tune them before evaluation. For production release automation, omit `service_tier` or use default processing. Use Batch API only for larger offline evaluation runs; do not use Flex for production release dispatches because release automation should not depend on lower-priority capacity.

### Provider boundary

Add a small provider abstraction at the structured-output call seam. This can live inside `scripts/update_changelog.py` at first, or in a narrow new helper module if the implementation stays easy to test. Do not move broad changelog logic out of `update_changelog.py` just to make a framework.

The current tests monkeypatch symbols on the `update_changelog` module itself, including the provider constructor and LLM helper functions. Preserve that testing posture: either keep provider symbols patchable through `update_changelog.py`, or update the tests in the same work item so future maintainers are not left guessing which seam to patch.

The conceptual shape is simple:

- a provider value: `anthropic` or `openai`;
- a call-site value: grouped changelog, breaking changes, release-note body, etc.;
- a provider-aware `parse_structured_output(...)` helper that takes a prompt, a Pydantic output model type, token/temperature settings, and returns the parsed Pydantic instance.

Keep the public LLM generation functions in `scripts/update_changelog.py` unchanged. For example, `llm_generate_grouped_changelog_entries(...)` should still return `GroupedChangelogOutput`. Internally, it should build the same prompt and call the configured provider helper.

### Configuration

Start with minimal explicit configuration:

```text
CHANGELOG_LLM_PROVIDER=anthropic | openai
ANTHROPIC_API_KEY=<required for Anthropic provider>
OPENAI_API_KEY=<required for OpenAI provider>
CHANGELOG_LLM_MODEL=<optional global model override>
```

Default during migration: `CHANGELOG_LLM_PROVIDER=anthropic`.

Start evaluation with one global model for simplicity, but explicitly test per-call-site routing because the release-note prose may deserve a stronger model than PR grouping/summarization. Do not add a large override surface up front. If evaluation supports routing, add the smallest useful override surface, likely one global model plus one release-notes-prose override.

Also move LLM client initialization until after the script knows there is LLM work to do. Today the no-changes path still needs `ANTHROPIC_API_KEY`; after the migration, a no-changes run should be able to write a valid no-changes `ChangelogWorkflowResult` without any LLM key.

### Structured-output compatibility

Before trusting OpenAI structured outputs, make the current Pydantic output schemas compatible with OpenAI strict structured output constraints.

Likely changes:

- `ChangelogCopy.suggested_labels`: required list; prompt says return `[]` when none.
- `GroupedChangelogEntry.suggested_labels`: required list; prompt says return `[]` when none.
- `BreakingChangesOutput.bullets`: required list; empty list is valid.
- `MarkdownSection.content`: already required.

This is not a production data-shape change. It just changes the model-output contract from “provider may omit a list and Pydantic fills the default” to “provider must return an explicit empty list.”

The OpenAI wrapper should fail closed if:

- `response.output_parsed` is `None`;
- the response is a refusal;
- the response is incomplete because `max_output_tokens` was too low;
- the schema is rejected as invalid.

### Prompt handling

Extract prompt construction into pure functions after, or alongside, the schema compatibility pass. Do not edit prompt strings in one step only to move them immediately in the next; keep this as one coherent change where possible. Do not rewrite prompts as part of the provider migration.

Suggested functions:

- `build_changelog_copy_prompt(...) -> str`
- `build_grouped_changelog_entries_prompt(...) -> str`
- `build_breaking_changes_prompt(...) -> str`
- `build_release_notes_body_prompt(...) -> str`
- `build_markdown_section_prompt(...) -> str`

The first comparison should preserve task wording as much as possible. If OpenAI performs poorly, then tune prompts as a follow-up so we can separate “model is weak” from “prompt transfer was sloppy.”

The only prompt clarifications that belong in the migration are boundary-preserving ones:

- return `[]` for empty list fields;
- release-note body must not include `##`, `<img>`, `Breaking Changes`, release links, or `***`;
- breaking-change bullets must not start with `-` or `*`;
- Pro outputs must not include PR links, raw URLs, or PR numbers when links are disabled.

### Additional validators

Keep `validate_grouped_changelog_output(...)` as the hard validator for dashboard grouping. Add two new validators for places currently guarded mostly by prompt wording.

Add `validate_release_notes_body_output(...)`:

Hard-fail if the generated body includes:

- a line starting with `## `;
- `<img`;
- a `Breaking Changes` heading;
- `[View full release on GitHub]`;
- a standalone `***` footer;
- missing PR links for OSS output when `include_pr_links=True` and body PRs exist;
- PR links, raw PR URLs, or PR numbers for Pro output when `include_pr_links=False`.

Warn, but do not hard-fail, if bugfix PRs exist and no `<details><summary>Fixed</summary>` block appears. Some small releases may read better without a details block.

Add `validate_breaking_changes_output(...)`:

Hard-fail if:

- bullets already start with `-` or `*`;
- OSS bullets omit PR links when links are required;
- Pro bullets include PR links, raw URLs, or PR numbers when links are disabled.

Warn, but do not hard-fail, if a breaking-change bullet lacks action language such as “rename”, “remove”, “update”, “migrate”, “configure”, “replace”, “requires”, or “no longer”.

### Evaluation harness

Add a non-production script: `scripts/evaluate_changelog_llms.py`.

It should have two modes:

1. `capture-fixture`: capture release inputs without calling an LLM.
2. `run-eval`: read fixtures and evaluate one or more provider/model combinations without writing repository artifacts.

Evaluation must never call `main()`, never call `mark_consumed_after_success(...)`, and never write `changelog.json`, GitBook markdown, `.image_state`, or `.consumed_sources_state`.

Use a gitignored output directory:

```text
eval-results/openai-migration/<timestamp>/
```

Each case/model directory should contain enough artifacts for review: generated grouped output, rendered release-note body/section, hard-gate results, cost/latency, errors if any, and a readable diff against Claude. The exact filenames are implementation detail.

Fixture inputs should include fields such as `fixture_id`, `source_repo`, `release_tag`, release metadata, `release_notes_prs`, `breaking_prs`, expected markdown target, and optional reference Claude outputs.

Minimum fixture suite:

- OSS small release where the model should avoid over-expanding a few PRs.
- OSS large/mixed release where grouping and release-note structure matter.
- OSS feature-heavy release where technical details must become user-facing value.
- Pro UI/API release where no PR links should appear.
- Pro organization/access-control release where Pro tone matters.
- Real or synthetic breaking-change release.
- Major bump with no breaking PRs, preserving existing fallback behavior.
- No-changes fixture proving no LLM client is required.
- Ambiguous bare PR-number fixture proving fail-fast behavior still prevents model calls.

Run each candidate at least twice with `temperature=0`. Low temperature is not a formal determinism guarantee, and repeated runs catch occasional instruction/schema drift.

### Automatic evaluation gates

Hard gates:

- API call succeeds.
- Structured parse succeeds.
- Pydantic model validation succeeds.
- No OpenAI refusal.
- No incomplete response caused by `max_output_tokens`.
- `GroupedChangelogOutput.entries` length is 1–3.
- Every input PR appears exactly once.
- No invented, missing, duplicated, or ambiguous PR assignments.
- Grouped entry titles are `<=60` characters.
- Labels are within the existing schema vocabulary.
- `changelog.json` schema validates after rendering.
- Release-note body validator passes.
- Breaking-change validator passes.
- Evaluation writes only under the eval output directory.
- No LLM calls are made for no-changes and ambiguous-PR fixtures.

Soft review rubric, scored by humans from 1 to 5:

- dashboard grouping quality;
- dashboard title quality;
- dashboard description usefulness;
- label correctness;
- OSS vs Pro tone;
- release-note structure;
- release-note completeness;
- noise avoidance;
- breaking-change actionability;
- missing important user-facing changes;
- invented claims.

Promotion threshold:

- 100% hard-gate pass rate across fixtures and repeated runs;
- average human score at least 4/5;
- no score below 3 on critical cases;
- no invented claims or PR references;
- no more manual editing than the current Claude baseline.

Do not use an LLM judge as the final promotion gate. A model grader can triage diffs, but the final decision should be human because the product risk is editorial trust.

### Cost and latency

Record token usage, latency, model, provider, reasoning effort, and estimated cost for every call.

Use this estimate:

```text
estimated_cost =
  input_tokens / 1_000_000 * input_price_per_million
  +
  output_tokens / 1_000_000 * output_price_per_million
```

Production volume is low, so do not save a few cents by accepting worse release notes. If one release used roughly 40K input tokens and 5K output tokens, the listed current prices put a run in the cents range even for stronger models. The real cost of a bad model is reviewer time and loss of trust.

### Retry and errors

Keep the existing idea: transient provider/API failures retry, authentication/configuration failures fail immediately, semantic grouped-output failures go through the existing three-attempt feedback loop.

Prefer `OpenAI(max_retries=0)` plus the repo’s explicit Tenacity retries, so the retry story stays visible and does not stack SDK retries on top of Tenacity retries.

Retry:

- connection errors;
- timeouts;
- rate limits;
- provider/internal server errors;
- structured parse/Pydantic validation failures caused by model output.

Do not retry:

- missing or invalid API keys;
- permission errors;
- invalid schema / unsupported parameter errors;
- model refusal;
- content-filter incomplete responses;
- ambiguous input PR-number failures.

If `max_output_tokens` causes an incomplete response, either retry once with a higher cap for that call site or fail with a clear message telling the maintainer which cap to raise. Do not write artifacts after incomplete structured output.

### Shadow comparison and cutover

After offline evaluation passes, compare OpenAI against Claude on one or two real release inputs before cutover. The default comparison path should be a locally triggered evaluation harness run using captured historical release inputs. The harness should support a pre-built fixture set of roughly four to five representative versions and produce side-by-side outputs for Anthropic and OpenAI.

A lightweight comparison UI is desirable: generate a small static HTML page that shows side-by-side outputs for dashboard entries, breaking-change bullets, and release-note prose. The UI may support blind review as an optional local mode, but PR-facing shadow output should be labeled with the provider and model names used.

For production shadow mode, prefer dual output surfaced as PR comments or linked artifacts on the PRs that the workflow already opens. PR comments should explicitly name the provider/model used for each output, for example the Anthropic baseline model and the OpenAI candidate model. The OpenAI shadow output should be visible to reviewers but should not modify `changelog.json`, GitBook markdown, `.image_state`, or `.consumed_sources_state`.

If CI shadow mode is implemented, it needs its own seam: a fenced code path that calls the second provider, writes comparison artifacts or PR comments only, and never writes production artifacts. Workflow YAML alone is not enough.

Cut over only after evaluation plus at least one or two real-release comparisons are accepted. Keep Anthropic rollback support for at least the first few successful OpenAI production releases.

Rollback should be simple:

```text
CHANGELOG_LLM_PROVIDER=anthropic
```

Prefer fail-closed behavior over automatic fallback for semantic grouped-output failures. If OpenAI cannot assign PRs correctly after retries, that is a quality problem, not a transient outage.

### Privacy and vendor approval

The migration changes which vendor receives PR titles and bodies, including private-source-repo PR text when private release sources are involved. This is not just a code change. The migration PR should explicitly note that private ZenML PR content may be sent to OpenAI when `CHANGELOG_LLM_PROVIDER=openai`.

## Work Items

### Item 1 — Confirm vendor approval and OpenAI facts

**Goal:** Decide whether private-source PR content may be sent to OpenAI, and lock implementation against current official OpenAI docs.

**Done when:**

- OpenAI use for private PR content is recorded as approved for this migration.
- Official docs confirm the Responses API structured parsing call shape.
- Current model IDs, snapshots, context limits, and pricing are recorded.
- Exception classes and SDK retry defaults are checked.
- The plan or implementation notes identify the chosen initial candidate matrix.

**Key files:**

- `docs/plans/openai-changelog-model-migration-2026-06-04.md`
- OpenAI model docs: https://developers.openai.com/api/docs/models
- OpenAI Structured Outputs docs: https://developers.openai.com/api/docs/guides/structured-outputs
- OpenAI Responses API docs: https://developers.openai.com/api/reference/responses
- OpenAI Python SDK docs: https://developers.openai.com/api/docs/libraries
- OpenAI pricing docs: https://developers.openai.com/api/docs/pricing

**Dependencies:** none.

**Size:** Small.

### Item 2 — Add a thin structured-output provider seam

**Goal:** Isolate Anthropic and OpenAI SDK code behind one fakeable boundary while keeping the existing changelog generation functions stable.

**Done when:**

- Provider-specific SDK calls live behind a narrow helper, either inside `scripts/update_changelog.py` or in a small helper module.
- `scripts/update_changelog.py` no longer calls Anthropic directly from each LLM helper.
- Current monkeypatch seams are preserved or deliberately updated in tests in the same change.
- `llm_generate_changelog_copy(...)`, `llm_generate_grouped_changelog_entries(...)`, `llm_generate_breaking_changes_bullets(...)`, `llm_generate_release_notes_body(...)`, and `llm_generate_markdown_section(...)` keep their public return shapes.
- Anthropic remains the default provider during migration.
- No-changes runs do not require an LLM API key, with a dedicated test proving that env validation and global client initialization happen after the no-work branch.

**Key files:**

- `scripts/update_changelog.py:611-676`
- `scripts/update_changelog.py:683-743`
- `scripts/update_changelog.py:805-862`
- `scripts/update_changelog.py:871-967`
- `scripts/update_changelog.py:1211-1248`
- `tests/test_update_changelog_main.py:61-164`

**Dependencies:** Item 1 for current OpenAI SDK details.

**Size:** Medium.

### Item 3 — Make model-output schemas and prompts OpenAI-compatible

**Goal:** Preserve the existing Pydantic output models while making them suitable for OpenAI strict Structured Outputs, and make the smallest prompt clarifications needed for that schema.

**Done when:**

- Optional/default list fields used by LLM output models are changed to required explicit lists where needed.
- Prompt text, ideally via extracted prompt builders, tells models to return `[]` when a list has no values.
- Existing grouped-output tests still pass.
- OpenAI schema generation does not fail because of optional fields or additional properties.

**Key files:**

- `scripts/update_changelog.py:171-232`
- `tests/test_update_changelog_grouped_retry.py:15-117`

**Dependencies:** Item 1.

**Size:** Small/Medium.

### Item 4 — Extract prompt builders without tuning prompts

**Goal:** Make side-by-side evaluation fair by preserving prompt wording while making prompts reusable by the provider wrapper and evaluation harness.

**Done when:**

- Prompt construction is available through pure functions.
- The provider migration does not rewrite the prompts except for explicit empty-list and deterministic-boundary clarifications.
- Tests or snapshots cover the most important prompt invariants where practical.

**Key files:**

- `scripts/update_changelog.py:570-967`

**Dependencies:** Items 2 and 3 can be done together if that avoids editing prompt strings twice.

**Size:** Medium.

### Item 5 — Add output validators for release-note body and breaking bullets

**Goal:** Turn the most important prompt-only formatting boundaries into code checks before production artifacts are written.

**Done when:**

- `validate_release_notes_body_output(...)` rejects duplicated deterministic headers, image tags, breaking-section headings, release footers, OSS missing links, and Pro forbidden links.
- `validate_breaking_changes_output(...)` rejects pre-bulleted strings and wrong link behavior.
- Style-sensitive checks, such as missing `Fixed` details blocks, are warnings rather than hard failures.
- Tests cover both validators.

**Key files:**

- `scripts/update_changelog.py:683-862`
- `scripts/workflow_result.py:157-179`
- `tests/test_update_changelog_workflow_result.py:113-150`
- New `tests/test_update_changelog_openai_validators.py`

**Dependencies:** Items 2 and 3.

**Size:** Medium.

### Item 6 — Add OpenAI provider support and provider tests

**Goal:** Enable OpenAI structured-output calls while preserving Anthropic behavior and offline tests.

**Done when:**

- OpenAI SDK dependency is added where imports require it.
- `OpenAIStructuredLLMClient` uses `responses.parse(...)`, `text_format=<PydanticModel>`, `max_output_tokens`, `temperature=0`, and `store=False`.
- Retry classification handles OpenAI errors without retrying auth/configuration failures.
- Tests use fake OpenAI response objects and make no network calls.
- Existing grouped retry, main-flow, workflow-result, and consumed-source tests still pass.

**Key files:**

- Optional new `scripts/llm_provider.py`
- `scripts/update_changelog.py`
- `scripts/run_pytest.py`
- New `tests/test_llm_provider.py`
- `tests/test_update_changelog_main.py`

**Dependencies:** Items 1–5.

**Size:** Medium/Large.

### Item 7 — Build the side-by-side evaluation harness

**Goal:** Answer “is mini good enough?” with real historical examples, automatic contract checks, human review, and cost/latency data.

**Done when:**

- `scripts/evaluate_changelog_llms.py` supports fixture capture and evaluation modes.
- Evaluation uses static fixtures and never mutates production artifacts or consumed-source state.
- Evaluation outputs side-by-side reports under a gitignored directory.
- Fixtures include OSS, Pro, small, large, breaking-change, no-changes, and ambiguous-PR cases.
- Automatic hard gates and human scoring forms are included in `summary.md` / per-case reports.

**Key files:**

- New `scripts/evaluate_changelog_llms.py`
- New `tests/test_evaluate_changelog_llms.py`
- `tests/fixtures/changelog-evals/` if committed fixtures are non-sensitive
- `.gitignore`
- `scripts/consumed_sources.py:241-315`
- `scripts/update_changelog.py:989-1180`

**Dependencies:** Items 2, 4, 5, and 6.

**Size:** Large.

### Item 8 — Run the model matrix and choose routing

**Goal:** Decide model routing from evidence, not assumption.

**Done when:**

- Claude baseline, `gpt-5.4-mini`, `gpt-5.4`, and `gpt-5.5` are evaluated across the fixture suite.
- Each candidate is run at least twice with `temperature=0`.
- Reports include hard-gate pass/fail, human scores, cost, latency, and diffs against Claude.
- The team chooses one default model or per-call-site routing.

**Key files:**

- `eval-results/openai-migration/<timestamp>/summary.md` (gitignored)
- `eval-results/openai-migration/<timestamp>/summary.json` (gitignored)
- `docs/plans/openai-changelog-model-migration-2026-06-04.md`

**Dependencies:** Item 7.

**Size:** Medium.

### Item 9 — Add workflow configuration and real-release comparison path

**Goal:** Allow OpenAI production runs after evaluation, and provide a low-complexity way to compare OpenAI and Claude on real release inputs before cutover.

**Done when:**

- `.github/workflows/process-release.yml` can pass `OPENAI_API_KEY`, `CHANGELOG_LLM_PROVIDER`, and the chosen model env var.
- Production default remains Anthropic until cutover.
- The evaluation harness can run against captured real release inputs and a pre-built set of roughly four to five historical versions.
- The harness can produce side-by-side Anthropic/OpenAI outputs, including a readable HTML comparison page; PR-facing output is labeled with provider/model names, while blind review can remain an optional local mode.
- If CI shadow mode is implemented, OpenAI shadow output is surfaced as PR comments or linked artifacts, and a separate fenced code path is tested to avoid production writes.
- Existing workflow outputs remain unchanged: `has_changes`, `markdown_file`, `breaking_changes`, `needs_attention`, and `source_windows`.
- Reviewer checklists continue to show source-window and LLM-output review points.

**Key files:**

- `.github/workflows/process-release.yml:43-58`
- `.github/workflows/process-release.yml:106-244`
- `scripts/workflow_result.py`
- `scripts/evaluate_changelog_llms.py`

**Dependencies:** Items 6–8.

**Size:** Small if using manual comparison; Medium/Large if building CI shadow mode.

### Item 10 — Cut over, monitor, and keep rollback

**Goal:** Move production to OpenAI only after evidence shows quality is preserved.

**Done when:**

- `CHANGELOG_LLM_PROVIDER=openai` is set for production in a separate PR.
- Anthropic rollback remains available for the first few successful OpenAI production releases.
- The first OpenAI release PRs receive explicit human review of grouped summaries, release-note body, breaking changes, and source-window behavior.
- After the rollback window, the team decides whether to keep or remove Anthropic support in a separate cleanup PR.

**Key files:**

- `.github/workflows/process-release.yml`
- `README.md`
- `AGENTS.md`
- `scripts/update_changelog.py`

**Dependencies:** Item 9.

**Size:** Small/Medium.

### Item 11 — Update docs and contributor guidance

**Goal:** Keep future operators and agents from accidentally weakening the migration safeguards.

**Done when:**

- `README.md` documents `OPENAI_API_KEY`, `CHANGELOG_LLM_PROVIDER`, the chosen model configuration, evaluation commands, and rollback.
- `AGENTS.md` tells future agents that unit tests must mock providers and live provider calls belong only in explicit evaluation runs.
- PR descriptions for migration/cutover mention the vendor change for private PR content.

**Key files:**

- `README.md`
- `AGENTS.md`
- `.github/workflows/process-release.yml`

**Dependencies:** Items 6–10.

**Size:** Small.

## Open Questions

- Should the first evaluated routing be mini-for-summarization plus `gpt-5.5` for final release-note prose, or mini plus `gpt-5.4` first with `gpt-5.5` as the ceiling? The evaluation matrix should include enough variants to answer this.
- Should evaluation fixtures be committed under `tests/fixtures/changelog-evals/`, or kept local because they include sensitive private PR content? OpenAI use is approved, but fixture commit policy still needs a repo/privacy decision.

## References

- `.github/workflows/process-release.yml`
- `scripts/update_changelog.py`
- `scripts/source_windows.py`
- `scripts/consumed_sources.py`
- `scripts/workflow_result.py`
- `tests/test_update_changelog_grouped_retry.py`
- `tests/test_update_changelog_main.py`
- `tests/test_update_changelog_workflow_result.py`
- `docs/plans/structured-update-changelog-output-2026-06-02.md`
- `docs/reviews/critique-structured-update-changelog-output-2026-06-02.md`
- OpenAI model docs: https://developers.openai.com/api/docs/models
- OpenAI `gpt-5.4-mini` model page: https://developers.openai.com/api/docs/models/gpt-5.4-mini
- OpenAI `gpt-5.4` model page: https://developers.openai.com/api/docs/models/gpt-5.4
- OpenAI `gpt-5.5` model page: https://developers.openai.com/api/docs/models/gpt-5.5
- OpenAI Structured Outputs docs: https://developers.openai.com/api/docs/guides/structured-outputs
- OpenAI Responses API docs: https://developers.openai.com/api/reference/responses
- OpenAI Python SDK docs: https://developers.openai.com/api/docs/libraries
- OpenAI pricing docs: https://developers.openai.com/api/docs/pricing
- OpenAI Batch API docs: https://developers.openai.com/api/docs/guides/batch
- OpenAI Flex processing docs: https://developers.openai.com/api/docs/guides/flex-processing
