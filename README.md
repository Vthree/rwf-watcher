# rwf-watcher

WoW Race to World First notifier for **Echo / Liquid / Method** on *The Venomous Abyss* Mythic（《烈毒之淵》）.

Independent sidecar. **Not** part of `grok-bot-core`. No LLM. LINE is omitted (Push quota).

Toggle a channel from the grok bot already in that chat:

```text
/rwfnotifi on
/rwfnotifi off
```

(`!rwfnotifi` on Discord also works. Alias `/rwfnotify`.)

Every 30 seconds it polls the [Raider.io API](https://raider.io) and sends **only to channels that are on**, and **only for last boss Ula'tek**:

- a tracked guild **kills Ula'tek**, or
- live `progress_display` on Ula'tek is a new **world lead** among Echo / Liquid / Method (strictly better than the current leader). Personal bests that do not take the lead stay silent.

Bosses 1–7 are tracked internally so kills are not missed, but they never post.

Quiet otherwise. `[SILENT]` is never posted to chat.

## Behaviour

| Rule | Detail |
|------|--------|
| Kills | Union of `/raiding/raid-rankings` `encountersDefeated` and `/live-tracking/guild/raid-progress` `isDefeated`. Never uses `boss=latest` to decide a kill. |
| New best | `/live-tracking/guild/boss-progress` for the first still-alive boss, using `progress_display`. Ranking `bestPercent` is ignored. |
| Hidden HP | Liquid-style hidden percents: no HP alerts, **kills still fire**. |
| World first | Last boss Ula'tek may say `世界首殺` only if previous state had no world ulatek kill. |
| Fingerprint | Kills + best display. **No timestamps.** |
| Copy | Best starts with `!best`. `pulls` → **嘗試次數** (never 「拉」). No URL. |

## Env

| Variable | Required | Notes |
|----------|----------|--------|
| `RIO_ACCESS_KEY` | yes | Also accepts `RAIDERIO_ACCESS_KEY` / `RIO_API_KEY` |
| `TELEGRAM_BOT_TOKEN` | for TG send | Same token as telegram-grok-bot |
| `DISCORD_BOT_TOKEN` | for DC send | Same token as discord-grok-bot |
| `RWF_CONTROL_TOKEN` | yes | Shared with grok bots so `/rwfnotifi` can toggle dests |
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
