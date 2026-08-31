"""Telegram + Discord outbound. Never send [SILENT]."""

from __future__ import annotations

import logging

import httpx

logger = logging.getLogger("rwf.notify")

_UA = "rwf-watcher/1.0"


def should_send(text: str | None) -> bool:
    if not text:
        return False
    stripped = text.strip()
    if not stripped or stripped == "[SILENT]":
        return False
    return True


def send_telegram(token: str, chat_id: str, text: str, timeout: float = 20.0) -> None:
    if not token or not chat_id:
        raise RuntimeError("telegram token/chat_id missing")
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    r = httpx.post(
        url,
        json={
            "chat_id": chat_id,
            "text": text,
            "disable_web_page_preview": False,
        },
        headers={"User-Agent": _UA},
        timeout=timeout,
    )
    if r.status_code >= 400:
        raise RuntimeError(f"telegram HTTP {r.status_code}: {r.text[:240]}")


def send_discord(token: str, channel_id: str, text: str, timeout: float = 20.0) -> None:
    if not token or not channel_id:
        raise RuntimeError("discord token/channel_id missing")
    url = f"https://discord.com/api/v10/channels/{channel_id}/messages"
    r = httpx.post(
        url,
        json={"content": text},
        headers={
            "Authorization": f"Bot {token}",
            "User-Agent": _UA,
            "Content-Type": "application/json",
        },
        timeout=timeout,
    )
    if r.status_code >= 400:
        raise RuntimeError(f"discord HTTP {r.status_code}: {r.text[:240]}")


def fanout(
    text: str,
    *,
    telegram_token: str,
    discord_token: str,
    telegram_chat_ids: list[str] | None = None,
    discord_channel_ids: list[str] | None = None,
    dry_run: bool = False,
) -> None:
    if not should_send(text):
        logger.info("skip send: empty or SILENT")
        return
    tg_ids = [x for x in (telegram_chat_ids or []) if x]
    dc_ids = [x for x in (discord_channel_ids or []) if x]
    if dry_run:
        logger.info(
            "DRY_RUN would send %s chars tg=%s dc=%s",
            len(text),
            tg_ids,
            dc_ids,
        )
        return
    if not tg_ids and not dc_ids:
        logger.info("no destinations; skip send")
        return
    errors: list[str] = []
    for chat_id in tg_ids:
        if not telegram_token:
            errors.append("telegram token missing")
            break
        try:
            send_telegram(telegram_token, chat_id, text)
            logger.info("telegram sent chat=%s chars=%s", chat_id, len(text))
        except Exception as e:
            errors.append(f"telegram {chat_id}: {e}")
            logger.exception("telegram send failed chat=%s", chat_id)
    for channel_id in dc_ids:
        if not discord_token:
            errors.append("discord token missing")
            break
        try:
            send_discord(discord_token, channel_id, text)
            logger.info("discord sent channel=%s chars=%s", channel_id, len(text))
        except Exception as e:
            errors.append(f"discord {channel_id}: {e}")
            logger.exception("discord send failed channel=%s", channel_id)
    if errors and len(errors) >= max(1, len(tg_ids) + len(dc_ids)):
        raise RuntimeError("; ".join(errors))
