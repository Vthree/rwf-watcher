# Changelog

## 1.1.0 — 2026-08-31

- Destinations are toggled per channel via `/rwfnotifi on|off` on the grok bots.
- HTTP control API on `PORT` (default 8080). Empty dest list = no send.
- Env `TELEGRAM_RWF_CHAT_ID` / `DISCORD_RWF_CHANNEL_ID` no longer auto-target a channel.

## 1.0.1 — 2026-08-31

- Railpack runtime Python 3.13.7 (3.12.8 mise attestations failed).
- Raider.io HTTP timeout 40s after a world-rankings read timeout.

## 1.0.0 — 2026-08-31

- Sidecar watcher for Echo / Liquid / Method on *The Venomous Abyss* Mythic.
- Telegram + Discord fan-out. LINE omitted.
- Raider.io API only. Kill = rankings ∪ live `isDefeated`. New best = first undefeated `progress_display`.
- Fingerprint without timestamps. First poll seeds state and stays silent.
