# AGENTS.md — rwf-watcher

Sidecar for WoW RWF notices (Echo / Liquid / Method, 《烈毒之淵》 Mythic).

**Not** grok-bot-core. Do not add Hermes, web search, or LINE Push.

## Do

- Raider.io **API only** (`access_key` from env). No WCL / PullCount HTML.
- Kill = rankings `encountersDefeated` ∪ live raid-progress `isDefeated`.
- New best = first undefeated boss live `progress_display` (lower remaining HP or later phase). **Posted only for last boss Ula'tek.**
- Posted kills: **Ula'tek only**. Earlier bosses are still tracked in state, never sent.
- Never use ranking `bestPercent` or `boss=latest` for kills.
- Hidden HP: no percent alerts; still report kills.
- Fingerprint without timestamps. First poll seeds state, stays silent.
- Destinations: `/rwfnotifi on|off` in the grok bots writes `/data/rwf-destinations.json` via the control HTTP API. Empty list = no send.
- Best notice: first line `!best`, then guild / remaining / 嘗試次數. No URL.
- `pulls` → 嘗試次數. Do not send `[SILENT]` to chats.
- Ula'tek `世界首殺` only if previous state had no world ulatek.

## Don't

- Commit `RIO_ACCESS_KEY`.
- Hand-edit telegram/discord/line grok bots for this feature.
- Notify LINE (Push quota).
