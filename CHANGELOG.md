# Changelog

## 1.1.6 — 2026-08-31

- Kill notice also includes `嘗試次數 N` when pullCount is known (live ulatek after 8/8, else last stored ulatek pulls).

## 1.1.5 — 2026-08-31

- Kill line puts the guild name first: `Echo 擊殺 尾王 Ula'tek（8/8）` (` 世界首殺` still appended when applicable).

## 1.1.4 — 2026-08-31

- Ula'tek `%` notices only when a tracked guild takes the **world lead** among Echo / Liquid / Method (lower remaining than the current leader). Personal bests behind the leader stay silent.

## 1.1.3 — 2026-08-31

- Poll interval default 30s (`RWF_POLL_SECONDS=30`).

## 1.1.2 — 2026-08-31

- Best notice starts with `!best` and no longer includes the Raider.io URL.

## 1.1.1 — 2026-08-31

- Notices only for last boss **Ula'tek**: new best HP and kill (incl. 世界首殺). Bosses 1–7 stay silent.

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
