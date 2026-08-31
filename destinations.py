"""Enabled Telegram chats / Discord channels. Command-toggled, persisted on volume."""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path

logger = logging.getLogger("rwf.dest")

PLATFORMS = ("discord", "telegram")


def default_path(feed: str = "rwf") -> Path:
    feed = (feed or "rwf").strip().lower()
    if feed == "tw":
        raw = os.environ.get("RWF_TW_DEST_PATH")
        if raw:
            return Path(raw)
        if Path("/data").is_dir():
            return Path("/data/tw-destinations.json")
        return Path("data/tw-destinations.json")
    raw = os.environ.get("RWF_DEST_PATH")
    if raw:
        return Path(raw)
    if Path("/data").is_dir():
        return Path("/data/rwf-destinations.json")
    return Path("data/rwf-destinations.json")


def _empty() -> dict[str, list[str]]:
    return {"discord": [], "telegram": []}


def load(path: Path | None = None, feed: str = "rwf") -> dict[str, list[str]]:
    p = path or default_path(feed)
    if not p.is_file():
        return _empty()
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        logger.warning("dest load failed %s: %s", p, e)
        return _empty()
    out = _empty()
    if not isinstance(data, dict):
        return out
    for plat in PLATFORMS:
        ids = []
        for item in data.get(plat) or []:
            s = str(item).strip()
            if s and s not in ids:
                ids.append(s)
        out[plat] = ids
    return out


def save(data: dict[str, list[str]], path: Path | None = None, feed: str = "rwf") -> None:
    p = path or default_path(feed)
    p.parent.mkdir(parents=True, exist_ok=True)
    payload = {plat: list(data.get(plat) or []) for plat in PLATFORMS}
    tmp = p.with_suffix(p.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp.replace(p)


def set_dest(
    platform: str,
    dest_id: str,
    enabled: bool,
    path: Path | None = None,
    feed: str = "rwf",
) -> dict:
    plat = (platform or "").strip().lower()
    if plat not in PLATFORMS:
        raise ValueError(f"platform must be discord or telegram, got {platform!r}")
    dest_id = str(dest_id).strip()
    if not dest_id:
        raise ValueError("id required")
    data = load(path, feed=feed)
    ids = list(data[plat])
    if enabled:
        if dest_id not in ids:
            ids.append(dest_id)
    else:
        ids = [x for x in ids if x != dest_id]
    data[plat] = ids
    save(data, path, feed=feed)
    logger.info(
        "%s %s dest feed=%s %s=%s now=%s",
        plat,
        "on" if enabled else "off",
        feed,
        dest_id,
        enabled,
        ids,
    )
    return {"platform": plat, "id": dest_id, "enabled": dest_id in ids, "ids": ids, "feed": feed}
