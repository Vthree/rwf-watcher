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
    telegram_chat_id: str,
    discord_token: str,
    discord_channel_id: str,
    dry_run: bool = False,
) -> None:
    if not should_send(text):
        logger.info("skip send: empty or SILENT")
        return
    if dry_run:
        logger.info("DRY_RUN would send %s chars", len(text))
        return
    errors: list[str] = []
    if telegram_token and telegram_chat_id:
        try:
            send_telegram(telegram_token, telegram_chat_id, text)
            logger.info("telegram sent chat=%s chars=%s", telegram_chat_id, len(text))
        except Exception as e:
            errors.append(f"telegram: {e}")
            logger.exception("telegram send failed")
    else:
        logger.warning("telegram not configured")
    if discord_token and discord_channel_id:
        try:
            send_discord(discord_token, discord_channel_id, text)
            logger.info("discord sent channel=%s chars=%s", discord_channel_id, len(text))
        except Exception as e:
            errors.append(f"discord: {e}")
            logger.exception("discord send failed")
    else:
        logger.warning("discord not configured")
    if errors and len(errors) == 2:
        raise RuntimeError("; ".join(errors))
