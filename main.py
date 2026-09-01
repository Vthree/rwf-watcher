"""
RWF sidecar: poll Raider.io, notify Telegram + Discord on kill / new best.

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
from models import GUILDS, RAID_SLUG, boss_list
from notify import fanout
from rio import RioClient, RioError
from state import load as load_state
from state import load_tw
from state import save as save_state
from state import save_tw
from tw import coalesce_tw, diff_tw, tw_region_max
from watcher import coalesce_snapshot, diff_snapshot, fingerprint

logging.basicConfig(
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger("rwf")
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)

VERSION = "1.2.3"


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
    dests = load_dests(feed="rwf")
    tw_dests = load_dests(feed="tw")
    logger.info(
        "rwf-watcher %s raid=%s guilds=%s poll=%ss dry_run=%s dest_tg=%s dest_dc=%s tw_tg=%s tw_dc=%s",
        VERSION,
        RAID_SLUG,
        ",".join(g.name for g in GUILDS),
        interval,
        dry_run,
        dests.get("telegram") or [],
        dests.get("discord") or [],
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

        prev = load_state()
        if prev is None:
            logger.info("no prior state; first poll will seed and stay silent")
        else:
            logger.info("loaded state fp=%s", fingerprint(prev))
        tw_prev = load_tw()
        if tw_prev is None:
            logger.info("no prior TW state; first TW poll will seed and stay silent")
        else:
            logger.info("loaded TW state region_max=%s", tw_prev.region_max)

        while True:
            try:
                curr = client.fetch_snapshot(bosses)
                tick = diff_snapshot(prev, curr, bosses, GUILDS)
                msg = tick.message()
                if tick.silent or not msg:
                    logger.info("silent fp=%s world_ulatek=%s", tick.fingerprint, curr.world_ulatek)
                else:
                    logger.info("notify %s chars fp=%s body=%r", len(msg), tick.fingerprint, msg)
                    dests = load_dests(feed="rwf")
                    fanout(
                        msg,
                        telegram_token=tg_token,
                        discord_token=dc_token,
                        telegram_chat_ids=dests.get("telegram") or [],
                        discord_channel_ids=dests.get("discord") or [],
                        dry_run=dry_run,
                    )
                stored = coalesce_snapshot(prev, curr)
                save_state(stored)
                prev = stored
            except Exception:
                logger.exception("poll failed")
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
