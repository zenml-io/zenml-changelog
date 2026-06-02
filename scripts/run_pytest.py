#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = [
#     # Keep this list broad enough for import-time dependencies of tested scripts,
#     # especially scripts/update_changelog.py.
#     "pytest",
#     "requests",
#     "PyGithub",
#     "anthropic",
#     "jsonschema",
#     "pydantic",
#     "python-slugify",
#     "tenacity",
# ]
# ///
from __future__ import annotations

import subprocess
import sys
from collections.abc import Sequence


def main(argv: Sequence[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if not args:
        args = ["-q"]
    return subprocess.call([sys.executable, "-m", "pytest", *args])


if __name__ == "__main__":
    raise SystemExit(main())
