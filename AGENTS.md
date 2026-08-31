# AGENTS.md — rwf-watcher

Sidecar for WoW RWF notices (Echo / Liquid / Method, 《烈毒之淵》 Mythic).

**Not** grok-bot-core. Do not add Hermes, web search, or LINE Push.

## Do

- Raider.io **API only** (`access_key` from env). No WCL / PullCount HTML.
- Kill = rankings `encountersDefeated` ∪ live raid-progress `isDefeated`.
- New best = first undefeated boss live `progress_display` (lower remaining HP or later phase).
- Never use ranking `bestPercent` or `boss=latest` for kills.
- Hidden HP: no percent alerts; still report kills.
- Fingerprint without timestamps. First poll seeds state, stays silent.
- `pulls` → 嘗試次數. Do not send `[SILENT]` to chats.
- Ula'tek `世界首殺` only if previous state had no world ulatek.

## Don't

- Commit `RIO_ACCESS_KEY`.
- Hand-edit telegram/discord/line grok bots for this feature.
- Notify LINE (Push quota).
