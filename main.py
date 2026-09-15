"""
TW sidecar: v1 rankings every poll for kills; v2 progressRace (cached) for
best % / pulls — same board as /zone/race/latest?region=4. RIO union.
World RWF (Echo / Liquid / Method) is not polled.

Not part of grok-bot-core. No LLM. LINE is intentionally omitted.
"""

from __future__ import annotations

import logging
import os
import sys
import time

from control import start_control_server
from destinations import load as load_dests
from env_utils import env_secret
from models import RAID_SLUG, boss_list
from notify import fanout
from rio import RioClient, RioError
from state import load_tw
from state import save_tw
from tw import coalesce_tw, diff_tw, merge_tw_snapshots, tw_region_max
from wcl import WclClient, WclV2Client

logging.basicConfig(
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger("rwf")
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)

VERSION = "1.6.1"


def _int_env(name: str, default: int) -> int:
    raw = env_secret(name)
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def main() -> int:
    rio_key = env_secret("RIO_ACCESS_KEY", "RAIDERIO_ACCESS_KEY", "RIO_API_KEY")
    wcl_key = env_secret("WCL_API_KEY", "WARCRAFTLOGS_API_KEY")
    wcl_id = env_secret("WCL_CLIENT_ID")
    wcl_sec = env_secret("WCL_CLIENT_SECRET")
    tg_token = env_secret("TELEGRAM_BOT_TOKEN", "TELEGRAM_TOKEN")
    dc_token = env_secret("DISCORD_BOT_TOKEN", "DISCORD_TOKEN")
    dry_run = env_secret("RWF_DRY_RUN").lower() in {"1", "true", "yes", "on"}
    once = env_secret("RWF_ONCE").lower() in {"1", "true", "yes", "on"}
    interval = max(30, _int_env("RWF_POLL_SECONDS", 30))

    if not rio_key:
        logger.error("RIO_ACCESS_KEY missing")
        return 1
    if not wcl_id or not wcl_sec:
        logger.warning("WCL_CLIENT_ID/SECRET missing; progressRace off")
    if not wcl_key:
        logger.warning("WCL_API_KEY missing; v1 rankings fallback off")

    start_control_server()
    tw_dests = load_dests(feed="tw")
    logger.info(
        "rwf-watcher %s raid=%s poll=%ss dry_run=%s world_rwf=off wcl_v2=%s wcl_v1=%s tw_tg=%s tw_dc=%s",
        VERSION,
        RAID_SLUG,
        interval,
        dry_run,
        bool(wcl_id and wcl_sec),
        bool(wcl_key),
        tw_dests.get("telegram") or [],
        tw_dests.get("discord") or [],
    )

    client = RioClient(rio_key)
    wcl = WclClient(wcl_key) if wcl_key else None
    wcl2 = WclV2Client(wcl_id, wcl_sec, race_ttl=_int_env("WCL_RACE_TTL_SECONDS", 480)) if (wcl_id and wcl_sec) else None
    try:
        try:
            bosses = client.static_bosses()
        except RioError as e:
            logger.warning("static-data failed (%s); fallback bosses", e)
            bosses = boss_list()
        logger.info("bosses: %s", ", ".join(f"{b.index}:{b.slug}" for b in bosses))

        tw_prev = load_tw()
        if tw_prev is None:
            logger.info("no prior TW state; first TW poll will seed and stay silent")
        else:
            logger.info("loaded TW state region_max=%s", tw_prev.region_max)

        while True:
            try:
                rio_snap = None
                try:
                    rio_snap = client.fetch_tw_snapshot(bosses)
                except Exception:
                    logger.exception("rio tw snapshot failed")
                race_snap = None
                if wcl2 is not None:
                    try:
                        race_snap = wcl2.fetch_tw_race(bosses)
                    except Exception:
                        logger.exception("wcl v2 progressRace failed")
                wcl_snap = None
                if wcl is not None:
                    try:
                        wcl_snap = wcl.fetch_tw_kills(bosses)
                    except Exception:
                        logger.exception("wcl v1 rankings failed")
                if rio_snap is None and wcl_snap is None and race_snap is None:
                    raise RuntimeError("no TW snapshot from RIO or WCL")
                tw_curr = merge_tw_snapshots(merge_tw_snapshots(rio_snap, wcl_snap), race_snap)
                tw_tick = diff_tw(tw_prev, tw_curr, bosses)
                tw_msg = tw_tick.message()
                if tw_tick.silent or not tw_msg:
                    logger.info(
                        "tw silent region_max=%s",
                        tw_region_max(tw_curr),
                    )
                else:
                    logger.info("tw notify %s chars", len(tw_msg))
                    tw_dests = load_dests(feed="tw")
                    fanout(
                        tw_msg,
                        telegram_token=tg_token,
                        discord_token=dc_token,
                        telegram_chat_ids=tw_dests.get("telegram") or [],
                        discord_channel_ids=tw_dests.get("discord") or [],
                        dry_run=dry_run,
                    )
                tw_stored = coalesce_tw(tw_prev, tw_curr)
                save_tw(tw_stored)
                tw_prev = tw_stored
            except Exception:
                logger.exception("tw poll failed")
            if once:
                return 0
            time.sleep(interval)
    finally:
        client.close()
        if wcl is not None:
            wcl.close()
        if wcl2 is not None:
            wcl2.close()


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        sys.exit(0)
