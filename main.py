"""
TW sidecar: poll Raider.io Taiwan rankings, notify Telegram + Discord on
region-first kills. World RWF (Echo / Liquid / Method) is not polled.

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
from tw import coalesce_tw, diff_tw, tw_region_max

logging.basicConfig(
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger("rwf")
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)

VERSION = "1.3.0"


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
    tg_token = env_secret("TELEGRAM_BOT_TOKEN", "TELEGRAM_TOKEN")
    dc_token = env_secret("DISCORD_BOT_TOKEN", "DISCORD_TOKEN")
    dry_run = env_secret("RWF_DRY_RUN").lower() in {"1", "true", "yes", "on"}
    once = env_secret("RWF_ONCE").lower() in {"1", "true", "yes", "on"}
    interval = max(30, _int_env("RWF_POLL_SECONDS", 30))

    if not rio_key:
        logger.error("RIO_ACCESS_KEY missing")
        return 1

    start_control_server()
    tw_dests = load_dests(feed="tw")
    logger.info(
        "rwf-watcher %s raid=%s poll=%ss dry_run=%s world_rwf=off tw_tg=%s tw_dc=%s",
        VERSION,
        RAID_SLUG,
        interval,
        dry_run,
        tw_dests.get("telegram") or [],
        tw_dests.get("discord") or [],
    )

    client = RioClient(rio_key)
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
                tw_curr = client.fetch_tw_snapshot()
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


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        sys.exit(0)
