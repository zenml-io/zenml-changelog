from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from pydantic import BaseModel, Field

CONSUMED_SOURCE_STATE_FILE = Path(".consumed_sources_state")


class ConsumedPR(BaseModel):
    source_repo: str
    number: int
    first_consumed_by_release_tag: str
    first_consumed_at: str
    previous_tag: Optional[str] = None
    current_tag: Optional[str] = None
    # Legacy compatibility only. New writes use structured previous/current tags.
    source_window: Optional[str] = None
    origin: str = "automation"


class ConsumedWindow(BaseModel):
    source_repo: str
    previous_tag: Optional[str] = None
    current_tag: str
    consumed_by_release_tag: str
    consumed_at: str
    pr_keys: List[str] = Field(default_factory=list)
    origin: str = "automation"


class ConsumedTargetState(BaseModel):
    trigger_repo: str
    markdown_file: str
    consumed_windows: List[ConsumedWindow] = Field(default_factory=list)
    consumed_prs: Dict[str, ConsumedPR] = Field(default_factory=dict)


class ConsumedSourceState(BaseModel):
    version: int = 1
    updated_at: Optional[str] = None
    # Narrow manual seed, not a complete historical bootstrap. Future successful
    # automation runs build this ledger forward one finalized window at a time.
    bootstrap_note: Optional[str] = None
    targets: Dict[str, ConsumedTargetState] = Field(default_factory=dict)


def _model_dump(model: BaseModel) -> Dict[str, Any]:
    if hasattr(model, "model_dump"):
        return model.model_dump(exclude_none=True)
    return model.dict(exclude_none=True)  # type: ignore[attr-defined]


def _validate_consumed_source_state(payload: Dict[str, Any]) -> ConsumedSourceState:
    if hasattr(ConsumedSourceState, "model_validate"):
        return ConsumedSourceState.model_validate(payload)
    return ConsumedSourceState.parse_obj(payload)  # type: ignore[attr-defined]


def target_state_key(trigger_repo: str, markdown_file: str) -> str:
    return f"{trigger_repo}::{markdown_file}"


def format_source_window(previous_tag: Optional[str], current_tag: str) -> str:
    return f"{previous_tag or 'start'} -> {current_tag}"


def make_pr_key(repo_name: str, number: int) -> str:
    return f"{repo_name}#{number}"


def parse_pr_key(key: str) -> Tuple[str, int]:
    try:
        repo_name, number_text = key.rsplit("#", 1)
        return repo_name, int(number_text)
    except ValueError as error:
        raise RuntimeError(f"Invalid consumed PR key {key!r}; expected '<repo>#<number>'") from error


def pr_key_from_dict(pr: Dict[str, Any]) -> str:
    return make_pr_key(str(pr.get("repo", "")), int(pr["number"]))


def _parse_legacy_source_window(source_window: Optional[str]) -> Tuple[Optional[str], Optional[str]]:
    if not source_window or " -> " not in source_window:
        return None, None
    previous_tag, current_tag = source_window.split(" -> ", 1)
    return (None if previous_tag == "start" else previous_tag), current_tag


def _ensure_pr_window_tags(
    consumed_pr: ConsumedPR,
    previous_tag: Optional[str],
    current_tag: str,
) -> None:
    if consumed_pr.current_tag is None:
        legacy_previous, legacy_current = _parse_legacy_source_window(consumed_pr.source_window)
        consumed_pr.previous_tag = legacy_previous
        consumed_pr.current_tag = legacy_current

    if consumed_pr.current_tag is None:
        consumed_pr.previous_tag = previous_tag
        consumed_pr.current_tag = current_tag

    if consumed_pr.previous_tag != previous_tag or consumed_pr.current_tag != current_tag:
        raise RuntimeError(
            "Consumed PR window tags conflict with its containing consumed window: "
            f"PR says {format_source_window(consumed_pr.previous_tag, consumed_pr.current_tag)}, "
            f"window says {format_source_window(previous_tag, current_tag)}"
        )

    consumed_pr.source_window = None


def reconcile_consumed_source_state(state: ConsumedSourceState) -> ConsumedSourceState:
    """Normalize duplicated consumed-window/PR facts after reading state.

    The canonical PR provenance is structured ``previous_tag``/``current_tag``.
    ``source_window`` is accepted only as legacy input and is cleared on write.

    A consumed window is finalized: once its ``source_repo`` + previous/current
    tags are in the ledger, future runs skip that whole window before PR search.
    Late-added labels inside a finalized window are intentionally ignored rather
    than re-opening already-published release notes.
    """
    for target_key, target_state in state.targets.items():
        for consumed_window in target_state.consumed_windows:
            normalized_pr_keys: List[str] = []
            for raw_key in consumed_window.pr_keys:
                repo_name, number = parse_pr_key(raw_key)
                normalized_key = make_pr_key(repo_name, number)
                if repo_name != consumed_window.source_repo:
                    raise RuntimeError(
                        f"Consumed state target {target_key} has window "
                        f"{format_source_window(consumed_window.previous_tag, consumed_window.current_tag)} "
                        f"for {consumed_window.source_repo}, but window PR key {raw_key!r} "
                        f"belongs to {repo_name}"
                    )

                existing = target_state.consumed_prs.get(normalized_key)
                if existing is None:
                    target_state.consumed_prs[normalized_key] = ConsumedPR(
                        source_repo=repo_name,
                        number=number,
                        first_consumed_by_release_tag=consumed_window.consumed_by_release_tag,
                        first_consumed_at=consumed_window.consumed_at,
                        previous_tag=consumed_window.previous_tag,
                        current_tag=consumed_window.current_tag,
                        origin=consumed_window.origin,
                    )
                else:
                    _ensure_pr_window_tags(
                        existing,
                        previous_tag=consumed_window.previous_tag,
                        current_tag=consumed_window.current_tag,
                    )
                    if existing.source_repo != repo_name or existing.number != number:
                        raise RuntimeError(
                            f"Consumed state target {target_key} has conflicting facts for "
                            f"{normalized_key}: record says {existing.source_repo}#{existing.number}"
                        )
                normalized_pr_keys.append(normalized_key)

            consumed_window.pr_keys = sorted(set(normalized_pr_keys))

        for key, consumed_pr in target_state.consumed_prs.items():
            repo_name, number = parse_pr_key(key)
            if consumed_pr.current_tag is None:
                legacy_previous, legacy_current = _parse_legacy_source_window(consumed_pr.source_window)
                consumed_pr.previous_tag = legacy_previous
                consumed_pr.current_tag = legacy_current
            if consumed_pr.current_tag is None:
                raise RuntimeError(
                    f"Consumed state target {target_key} has standalone consumed_prs key {key!r} "
                    "without structured previous_tag/current_tag"
                )
            if consumed_pr.source_repo != repo_name or consumed_pr.number != number:
                raise RuntimeError(
                    f"Consumed state target {target_key} has consumed_prs key {key!r} "
                    f"but record says {consumed_pr.source_repo}#{consumed_pr.number}"
                )
            consumed_pr.source_window = None

    return state


def read_consumed_source_state(path: Path = CONSUMED_SOURCE_STATE_FILE) -> ConsumedSourceState:
    if not path.exists():
        return ConsumedSourceState()

    raw = path.read_text().strip()
    if not raw:
        return ConsumedSourceState()

    try:
        loaded = json.loads(raw)
    except json.JSONDecodeError as error:
        raise RuntimeError(f"Invalid JSON in consumed source state file {path}: {error}") from error

    if not isinstance(loaded, dict):
        raise RuntimeError(f"Consumed source state file {path} must contain a JSON object")

    try:
        return reconcile_consumed_source_state(_validate_consumed_source_state(loaded))
    except Exception as error:
        raise RuntimeError(f"Invalid consumed source state file {path}: {error}") from error


def write_consumed_source_state(
    state: ConsumedSourceState,
    path: Path = CONSUMED_SOURCE_STATE_FILE,
) -> None:
    state.updated_at = datetime.now(timezone.utc).isoformat()
    path.write_text(json.dumps(_model_dump(state), indent=2, sort_keys=True) + "\n")


def get_consumed_target_state(
    state: ConsumedSourceState,
    trigger_repo: str,
    markdown_file: str,
) -> Optional[ConsumedTargetState]:
    return state.targets.get(target_state_key(trigger_repo, markdown_file))


def get_or_create_consumed_target_state(
    state: ConsumedSourceState,
    trigger_repo: str,
    markdown_file: str,
) -> ConsumedTargetState:
    key = target_state_key(trigger_repo, markdown_file)
    if key not in state.targets:
        state.targets[key] = ConsumedTargetState(
            trigger_repo=trigger_repo,
            markdown_file=markdown_file,
        )
    return state.targets[key]


def find_consumed_window(
    target_state: Optional[ConsumedTargetState],
    source_repo: str,
    previous_tag: Optional[str],
    current_tag: str,
) -> Optional[ConsumedWindow]:
    if target_state is None:
        return None
    for consumed_window in target_state.consumed_windows:
        if (
            consumed_window.source_repo == source_repo
            and consumed_window.previous_tag == previous_tag
            and consumed_window.current_tag == current_tag
        ):
            return consumed_window
    return None


def is_pr_consumed(target_state: Optional[ConsumedTargetState], key: str) -> bool:
    return bool(target_state and key in target_state.consumed_prs)


def mark_consumed_after_success(
    state: ConsumedSourceState,
    trigger_repo: str,
    markdown_file: str,
    trigger_release_tag: str,
    collection: Any,
    now: datetime,
) -> ConsumedSourceState:
    target_state = get_or_create_consumed_target_state(state, trigger_repo, markdown_file)
    consumed_at = now.astimezone(timezone.utc).isoformat()

    for source_collection in collection.included_windows:
        window = source_collection.window
        window_pr_keys = sorted(
            {
                pr_key_from_dict(pr)
                for pr in source_collection.release_notes_prs + source_collection.breaking_prs
            }
        )

        if find_consumed_window(
            target_state=target_state,
            source_repo=window.source_repo,
            previous_tag=window.previous_tag,
            current_tag=window.current_tag,
        ) is None:
            target_state.consumed_windows.append(
                ConsumedWindow(
                    source_repo=window.source_repo,
                    previous_tag=window.previous_tag,
                    current_tag=window.current_tag,
                    consumed_by_release_tag=trigger_release_tag,
                    consumed_at=consumed_at,
                    pr_keys=window_pr_keys,
                )
            )

        for key in window_pr_keys:
            if key in target_state.consumed_prs:
                continue
            repo_name, number = parse_pr_key(key)
            target_state.consumed_prs[key] = ConsumedPR(
                source_repo=repo_name,
                number=number,
                first_consumed_by_release_tag=trigger_release_tag,
                first_consumed_at=consumed_at,
                previous_tag=window.previous_tag,
                current_tag=window.current_tag,
            )

    state.targets[target_state_key(trigger_repo, markdown_file)] = target_state
    state.updated_at = consumed_at
    return state
