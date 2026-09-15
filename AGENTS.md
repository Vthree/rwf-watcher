# AGENTS.md — rwf-watcher

**Handoff for other machines / Grok Build:** read [HANDOFF.md](HANDOFF.md) first.

Sidecar for WoW notices. **World RWF (Echo / Liquid / Method) polling is off.** Live feed is **Taiwan** region only.

**Not** grok-bot-core. Do not add Hermes, web search, or LINE Push.

## Do

- TW **kills** from WCL v1 rankings every poll (30s). TW **best %** from v2 progressRace (cached ~8 min, same as race page). Union RIO. No HTML. Never commit keys.
- Kill = rankings `encountersDefeated` ∪ live raid-progress `isDefeated`.
- New best posted only for last boss **Ula'tek**, world lead among Echo/Liquid/Method. Phase order from API `phase`: P1=1, P2=2, **I1=2.5**, P3=3, P4=4. Display uses `phase_label` (`I1` not `P2.5`). Later phase notifies even if `bestPercent` lags; same-phase remaining is gated by `bestPercent`.
- Posted kills: **Ula'tek only**. Earlier bosses are still tracked in state, never sent. After 8/8, still read ulatek `pullCount` for the kill line.
- Never use ranking `bestPercent` or `boss=latest` for kills.
- Hidden HP: no percent alerts; still report kills.
- Fingerprint without timestamps. First poll seeds state, stays silent.
- Destinations: `/twnotifi on|off` in the grok bots writes `/data/tw-destinations.json` via the control HTTP API. Empty list = no send.
- Best notice: first line `!best`, then guild / remaining / 嘗試次數. No URL.
- `pulls` → 嘗試次數. Do not send `[SILENT]` to chats.
- Ula'tek `世界首殺` only if previous state had no world ulatek.
- Kill line: `{guild} 擊殺 尾王 {name}（8/8）` then optional ` 世界首殺`, then `嘗試次數 N` when pullCount is known. Guild name before 擊殺.
- TW feed: no guild allowlist. Match guilds by **name**. Kills: v1 every 30s. Best %: v2 progressRace cache ~8 min. From **六王**, first 3 kills (`台服首殺` only place 1). Last boss TW-lead best. Bosses 1–5: no kill notices. First poll silent.
- Do **not** resume Echo/Liquid/Method polling unless the owner asks. `/rwfnotifi` is removed from the grok bots.

## Don't

- Commit `RIO_ACCESS_KEY`, `WCL_API_KEY`, `WCL_CLIENT_ID`, or `WCL_CLIENT_SECRET`.
- Edit grok-bot-core or LINE for this feature.
- Notify LINE (Push quota).
