# AGENTS.md — rwf-watcher

**Handoff for other machines / Grok Build:** read [HANDOFF.md](HANDOFF.md) first.

Sidecar for WoW RWF notices (Echo / Liquid / Method, 《烈毒之淵》 Mythic) plus an independent **Taiwan** region feed.

**Not** grok-bot-core. Do not add Hermes, web search, or LINE Push.

## Do

- Raider.io **API only** (`access_key` from env). No WCL / PullCount HTML.
- Kill = rankings `encountersDefeated` ∪ live raid-progress `isDefeated`.
- New best posted only for last boss **Ula'tek**, and only when it is the **world lead among Echo/Liquid/Method** (strictly better than the previous leader's remaining HP / phase). A guild's personal best behind the leader is silent.
- Posted kills: **Ula'tek only**. Earlier bosses are still tracked in state, never sent. After 8/8, still read ulatek `pullCount` for the kill line.
- Never use ranking `bestPercent` or `boss=latest` for kills.
- Hidden HP: no percent alerts; still report kills.
- Fingerprint without timestamps. First poll seeds state, stays silent.
- Destinations: `/rwfnotifi on|off` in the grok bots writes `/data/rwf-destinations.json` via the control HTTP API. Empty list = no send.
- Best notice: first line `!best`, then guild / remaining / 嘗試次數. No URL.
- `pulls` → 嘗試次數. Do not send `[SILENT]` to chats.
- Ula'tek `世界首殺` only if previous state had no world ulatek.
- Kill line: `{guild} 擊殺 尾王 {name}（8/8）` then optional ` 世界首殺`, then `嘗試次數 N` when pullCount is known. Guild name before 擊殺.
- TW feed: no guild allowlist. Rankings `region=tw` only. Notify when overall max N/8 increases (3/8 → 4/8). **No bests.** First poll silent. `/twnotifi` writes `/data/tw-destinations.json`. Line: `台服 {guild} 擊殺 第N王 …（N/8）`.

## Don't

- Commit `RIO_ACCESS_KEY`.
- Edit grok-bot-core or LINE for this feature.
- Notify LINE (Push quota).
