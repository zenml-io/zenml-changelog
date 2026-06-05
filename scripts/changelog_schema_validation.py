#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from jsonschema import Draft7Validator


def validate_changelog_data(changelog_data: Any, schema_path: Path) -> None:
    """Validate candidate changelog data against the announcement schema."""
    schema = json.loads(schema_path.read_text())
    validator = Draft7Validator(schema)
    validator.validate(changelog_data)


def validate_changelog(changelog_path: Path, schema_path: Path) -> None:
    changelog_data = json.loads(changelog_path.read_text())
    validate_changelog_data(changelog_data, schema_path)
    print(f"Validated changelog.json with {len(changelog_data)} entries.")
