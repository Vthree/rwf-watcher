# AGENTS.md — rwf-watcher

**Handoff for other machines / Grok Build:** read [HANDOFF.md](HANDOFF.md) first.

Sidecar for WoW notices. **World RWF (Echo / Liquid / Method) polling is off.** Live feed is **Taiwan** region only.

**Not** grok-bot-core. Do not add Hermes, web search, or LINE Push.

## Do

- Raider.io **API only** (`access_key` from env). No WCL / PullCount HTML.
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
- TW feed: no guild allowlist. Rankings `region=tw` only. Notify when overall max N/8 increases (3/8 → 4/8). **No bests.** First poll silent. `/twnotifi` writes `/data/tw-destinations.json`. Line: `台服 {guild} 擊殺 四王 …（4/8） 台服首殺` (一王…七王; last boss 尾王).
- Do **not** resume Echo/Liquid/Method polling unless the owner asks. `/rwfnotifi` is removed from the grok bots.

## Don't

- Commit `RIO_ACCESS_KEY`.
- Edit grok-bot-core or LINE for this feature.
- Notify LINE (Push quota).
