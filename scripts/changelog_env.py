#!/usr/bin/env python3
from __future__ import annotations

import os
from collections.abc import Sequence


def env_value(name: str) -> str | None:
    """Return a stripped environment value, treating blanks as missing."""
    value = os.environ.get(name)
    if value is None:
        return None
    stripped = value.strip()
    return stripped or None


def require_env_values(names: Sequence[str]) -> dict[str, str]:
    """Read required environment values, treating blank strings as missing."""
    values: dict[str, str] = {}
    missing: list[str] = []
    for name in names:
        value = env_value(name)
        if value is None:
            missing.append(name)
        else:
            values[name] = value
    if missing:
        raise RuntimeError(f"Missing required environment variables: {', '.join(missing)}")
    return values
