# rwf-watcher

WoW Race to World First notifier for **Echo / Liquid / Method** on *The Venomous Abyss* Mythic（《烈毒之淵》）.

Independent sidecar. **Not** part of `grok-bot-core`. No LLM. LINE is omitted (Push quota).

Every 2 minutes it polls the [Raider.io API](https://raider.io) and sends **Telegram + Discord** only when:

- a tracked guild gets a **kill**, or
- live `progress_display` on the **first undefeated boss** is a strictly better remaining HP / later phase.

Quiet otherwise. `[SILENT]` is never posted to chat.

## Behaviour

| Rule | Detail |
|------|--------|
| Kills | Union of `/raiding/raid-rankings` `encountersDefeated` and `/live-tracking/guild/raid-progress` `isDefeated`. Never uses `boss=latest` to decide a kill. |
| New best | `/live-tracking/guild/boss-progress` for the first still-alive boss, using `progress_display`. Ranking `bestPercent` is ignored. |
| Hidden HP | Liquid-style hidden percents: no HP alerts, **kills still fire**. |
| World first | Last boss Ula'tek may say `世界首殺` only if previous state had no world ulatek kill. |
| Fingerprint | Kills + best display. **No timestamps.** |
| Copy | `pulls` → **嘗試次數** (never 「拉」). Notices in Traditional Chinese. |

Data attribution: notices include a [raider.io](https://raider.io) guild link.

## Env

| Variable | Required | Notes |
|----------|----------|--------|
| `RIO_ACCESS_KEY` | yes | Also accepts `RAIDERIO_ACCESS_KEY` / `RIO_API_KEY` |
| `TELEGRAM_BOT_TOKEN` | one of TG/DC | Same token as telegram-grok-bot |
| `TELEGRAM_RWF_CHAT_ID` | with TG | Destination group/channel |
| `DISCORD_BOT_TOKEN` | one of TG/DC | Same token as discord-grok-bot |
| `DISCORD_RWF_CHANNEL_ID` | with DC | Destination channel |
| `RWF_POLL_SECONDS` | no | Default `120` |
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
