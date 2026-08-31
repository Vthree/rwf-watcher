"""Persist snapshot JSON on a volume. No timestamps in the fingerprint."""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path

from models import Snapshot
from watcher import snapshot_from_json, snapshot_to_json

logger = logging.getLogger("rwf.state")


def default_path() -> Path:
    raw = os.environ.get("RWF_STATE_PATH") or os.environ.get("STATE_PATH")
    if raw:
        return Path(raw)
    if Path("/data").is_dir():
        return Path("/data/rwf-state.json")
    return Path("data/rwf-state.json")


def load(path: Path | None = None) -> Snapshot | None:
    p = path or default_path()
    if not p.is_file():
        return None
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        logger.warning("state load failed %s: %s", p, e)
        return None
    return snapshot_from_json(data)


def save(snapshot: Snapshot, path: Path | None = None) -> None:
    p = path or default_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(p.suffix + ".tmp")
    tmp.write_text(
        json.dumps(snapshot_to_json(snapshot), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    tmp.replace(p)
