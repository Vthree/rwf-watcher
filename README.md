# rwf-watcher

Taiwan Mythic progress notifier for *The Venomous Abyss*（《烈毒之淵》）. Kills from **Warcraft Logs** (union Raider.io). World RWF polling is **off**.

Independent sidecar. **Not** part of `grok-bot-core`. No LLM. LINE is omitted (Push quota).

Toggle Taiwan overall-progress kills from the grok bot already in that chat:

```text
/twnotifi on
/twnotifi off
```

Every 30 seconds it polls the [Raider.io API](https://raider.io) `region=tw` and sends **only to channels that are on**.

Taiwan feed: **no named guilds**. From **六王**, notify the first 3 kills of that boss (`台服首殺` only for place 1). Last boss also posts TW-lead best `%`. First poll seeds and stays silent.

Quiet otherwise. `[SILENT]` is never posted to chat.

## Behaviour

| Rule | Detail |
|------|--------|
| Kills | Union of `/raiding/raid-rankings` `encountersDefeated` and `/live-tracking/guild/raid-progress` `isDefeated`. Never uses `boss=latest` to decide a kill. |
| New best | `/live-tracking/guild/boss-progress` for the first still-alive boss, using `progress_display`. Ranking `bestPercent` is ignored. |
| Hidden HP | Liquid-style hidden percents: no HP alerts, **kills still fire**. |
| World first | Last boss Ula'tek may say `世界首殺` only if previous state had no world ulatek kill. |
| Fingerprint | Kills + best display. **No timestamps.** |
| Copy | Best starts with `!best`. Kill is `{guild} 擊殺 尾王 …（8/8）` then `嘗試次數 N`. `pulls` → **嘗試次數** (never 「拉」). No URL. |
| Taiwan | Kills: WCL TW Mythic ∪ RIO. From 六王: first 3 kills (`台服首殺` on place 1 only). 尾王: + TW-lead `!best`. |

## Env

| Variable | Required | Notes |
|----------|----------|--------|
| `RIO_ACCESS_KEY` | yes | Also accepts `RAIDERIO_ACCESS_KEY` / `RIO_API_KEY` |
| `WCL_CLIENT_ID` | yes (TW race) | WCL v2 OAuth client id. Never commit. |
| `WCL_CLIENT_SECRET` | yes (TW race) | WCL v2 OAuth secret. Never commit. |
| `WCL_API_KEY` | fallback | v1 public key if v2 is down. Never commit. |
| `TELEGRAM_BOT_TOKEN` | for TG send | Same token as telegram-grok-bot |
| `DISCORD_BOT_TOKEN` | for DC send | Same token as discord-grok-bot |
| `RWF_CONTROL_TOKEN` | yes | Shared with grok bots so `/twnotifi` can toggle dests |
| `PORT` | no | Control HTTP (default 8080) |
| `RWF_POLL_SECONDS` | no | Default `30` |
| `RWF_STATE_PATH` | no | Default `/data/rwf-state.json` on Railway |
| `RWF_DRY_RUN` | no | Log only |
| `RWF_ONCE` | no | One poll then exit |

## Local

```text
python tests_offline.py
python main.py
```

First poll **seeds state and stays silent** so current 7/8 progress is not dumped into chat.

## Railway

Same project as the grok bots. Volume mounted at `/data` for the fingerprint. Tokens are copied as env vars — **do not commit the Raider.io key**.
