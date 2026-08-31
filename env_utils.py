"""Strip BOM / zero-width junk from secrets."""

from __future__ import annotations

import os

_INVISIBLE = (
    "\ufeff",
    "\u200b",
    "\u200c",
    "\u200d",
    "\u00a0",
)


def clean_secret(val: str | None) -> str:
    if val is None:
        return ""
    s = str(val)
    for ch in _INVISIBLE:
        s = s.replace(ch, "")
    return s.strip().strip('"').strip("'").strip()


def env_secret(*keys: str, default: str = "") -> str:
    for key in keys:
        if key in os.environ:
            cleaned = clean_secret(os.environ.get(key))
            if cleaned:
                return cleaned
        for env_key, env_val in os.environ.items():
            if env_key.upper() == key.upper():
                cleaned = clean_secret(env_val)
                if cleaned:
                    return cleaned
    return default
