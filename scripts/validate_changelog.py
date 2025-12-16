# /// script
# requires-python = ">=3.10"
# dependencies = ["jsonschema"]
# ///
"""Validate changelog.json against the announcement schema.

Used by pre-commit hook and can be run standalone.
"""

import json
import sys
from pathlib import Path

from jsonschema import Draft7Validator


def main() -> int:
    repo_root = Path(__file__).parent.parent
    changelog_path = repo_root / "changelog.json"
    schema_path = repo_root / "changelog_schema" / "announcement-schema.json"

    with open(changelog_path) as f:
        data = json.load(f)

    with open(schema_path) as f:
        schema = json.load(f)

    validator = Draft7Validator(schema)
    errors = list(validator.iter_errors(data))

    if errors:
        print("Changelog validation failed:")
        for error in errors:
            print(f"  - {error.message}")
            if error.path:
                print(f"    at: {list(error.path)}")
        return 1

    print("Changelog validation passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
