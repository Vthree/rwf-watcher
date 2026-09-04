# HANDOFF.md — rwf-watcher

給**其他裝置上的 Grok Build／接手 agent**。改程式前先讀這份，再用繁體中文向主人覆述現況，不要還原下列規則。

Grok bot 路由規則仍以各 host 的 [AGENTS.md](https://github.com/Vthree/telegram-grok-bot/blob/main/AGENTS.md) 為準。本 repo **不是** grok-bot-core。

---

## First turn（新機器／新 Grok Build）

1. 讀完整份檔案。
2. 需要改 Discord／Telegram 指令時，再開 sister repo 的 `HANDOFF.md` / `AGENTS.md`。
3. 改完要 **commit + push**，並更新本檔「Current snapshot」。主人說「同步 GitHub + HANDOFF」= 連這份一起改。

---

## Current snapshot（2026-08-31）

**Version: v1.3.0.** GitHub: [Vthree/rwf-watcher](https://github.com/Vthree/rwf-watcher)

| 項目 | 現況 — 未經明示不要改 |
|------|----------------------|
| 用途 | **只跑台服**《烈毒之淵》Mythic。世界 RWF（Echo / Liquid / Method）**已停輪詢**（前三已出爐） |
| 台服 | **獨立** feed：不指定公會。只在台服 Mythic **整體最高 N/8 往上**才發擊殺（台服首殺）。**不發 best**。第一次 poll 種子不洗版 |
| 平台 | Telegram + Discord。**LINE 不做**（Push 配額） |
| 輪詢 | `RWF_POLL_SECONDS=30`（程式下限也是 30） |
| 只發尾王 | 世界 RWF 已關。台服 feed 報該次里程碑那隻王（一王…七王／尾王） |
| 新 best | 世界 RWF 已關（main 不輪詢）。`watcher.py` 仍留 Echo/Liquid/Method best 邏輯，未經明示不要重開 |
| 擊殺 | rankings `encountersDefeated` ∪ live `isDefeated` |
| Hidden | Liquid hidden 血量不報變化，擊殺仍報 |
| 指紋 | 無時間戳。第一次 poll 只寫 state、不洗版 |
| 目的地 | **只留** `/twnotifi on\|off` → `/data/tw-destinations.json`。`/rwfnotifi` 已從 bot 拿掉。空名單就不發 |
| Best 格式 | 第一行 `!best`，無網址。`pulls` → **嘗試次數**（不要寫「拉」） |
| 擊殺格式 | 公會名在前：`Echo 擊殺 尾王 Ula'tek（8/8）`。世界首殺再加 ` 世界首殺`。下一行 `嘗試次數 N`（有 pullCount 才寫） |
| 台服擊殺格式 | `台服 Fortune 擊殺 四王 Vashnik the Malignant（4/8） 台服首殺`（一王…七王，尾王仍寫尾王）。+ 嘗試次數。無 best |
| 安靜 | 不要把 `[SILENT]` 發到群裡 |
| 世界首殺 | 僅尾王，且先前 state 還沒見過 world ulatek |
| 金鑰 | `RIO_ACCESS_KEY` 只在 Railway env，**禁止 commit** |

---

## Repos

| Repo | 角色 |
|------|------|
| [Vthree/rwf-watcher](https://github.com/Vthree/rwf-watcher) | 本 sidecar：輪詢、組字、發訊、control HTTP |
| [Vthree/discord-grok-bot](https://github.com/Vthree/discord-grok-bot) | `/twnotifi`（`!` 亦可）→ POST watcher。**無** `/rwfnotifi` |
| [Vthree/telegram-grok-bot](https://github.com/Vthree/telegram-grok-bot) | `/twnotifi`（管理員）。**無** `/rwfnotifi` |
| grok-bot-core / line-grok-bot | **不要**為 RWF 改 routing 或加 LINE Push |

---

## Railway（同一專案 telegram-grok-bot）

| 名稱 | ID |
|------|-----|
| project | `2c4d2a6a-9582-470c-95c2-293bcfd582ee` |
| environment production | `cdaaa829-862d-4254-a1ed-0558472928a5` |
| **rwf-watcher** | `b46b5532-cb10-40ea-8551-5696e22ce3be` |
| discord-grok-bot | `7ef4224d-c464-4dea-a8c5-b88debbb15fd` |
| worker（Telegram） | `dc09fd31-b701-473d-b174-6187119e05bd` |
| line-grok-bot | `2a35a1ad-5af2-4684-8eab-1d00713bae96` |
| hermes | `dfc754f9-b3ef-4b76-a1d3-683b6ed28263` |

Watcher volume：`/data`（`rwf-state.json` 指紋、`rwf-destinations.json` 訂閱、`tw-state.json`、`tw-destinations.json`）。

Watcher 必要 env：`RIO_ACCESS_KEY`、`TELEGRAM_BOT_TOKEN`、`DISCORD_BOT_TOKEN`、`RWF_CONTROL_TOKEN`、`PORT=8080`、`RWF_POLL_SECONDS=30`。

Grok bots 必要 env：`RWF_WATCHER_URL=http://rwf-watcher.railway.internal:8080`、同一個 `RWF_CONTROL_TOKEN`。

Control HTTP **不要**公開網域（曾誤開 `*.up.railway.app` 已刪）。只走 Railway private network。

已訂閱的 Discord 頻道（2026-08-31）：`1534380075816980550`。之後以 volume 檔為準。

---

## 公會與團本

| 公會 | guild id | region/realm |
|------|----------|----------------|
| Echo | 1047044 | eu / tarren-mill |
| Liquid | 1712677 | us / illidan |
| Method | 316123 | eu / twisting-nether |

Raid slug：`the-venomous-abyss`，difficulty：`mythic`。尾王 slug：`ulatek`。

API（只要官方 JSON，禁止刮 WCL／PullCount HTML）：

- `GET /api/v1/raiding/static-data?expansion_id=11`
- `GET /api/v1/raiding/raid-rankings`（`guild_id` 過濾參數名是 `guilds`）
- `GET /api/v1/live-tracking/guild/raid-progress?guild_id=`
- `GET /api/v1/live-tracking/guild/boss-progress?guild_id=&boss=<slug>`  
  參數是 **`guild_id`**，不是 `guildId`。

---

## 通報格式

Best：

```text
!best
Echo 《烈毒之淵》Mythic
Ula'tek 剩餘 75.14%
嘗試次數 92
```

擊殺（公會名在「擊殺」前面；有 pullCount 就加嘗試次數）：

```text
Echo 擊殺 尾王 Ula'tek（8/8） 世界首殺
嘗試次數 92
```

一般擊殺（不是世界首殺）：

```text
Echo 擊殺 尾王 Ula'tek（8/8）
嘗試次數 92
```

（沒有世界首殺就不要寫那四個字。沒有 pullCount 就不要寫嘗試次數那一行。）

台服（區域最高進度往上才發，不發 best）：

```text
台服 Fortune 擊殺 四王 Vashnik the Malignant（4/8） 台服首殺
嘗試次數 7
```

---

## 程式入口

| 檔 | 做什麼 |
|----|--------|
| `main.py` | poll loop + 啟動 control HTTP |
| `watcher.py` | 指紋、diff、只發 ulatek、組字 |
| `tw.py` | 台服區域 N/8 里程碑、組字 |
| `rio.py` | Raider.io client |
| `destinations.py` | 訂閱名單 |
| `control.py` | `GET/POST /tw/destinations`、`GET /health` |
| `notify.py` | TG sendMessage + Discord REST |
| `tests_offline.py` | 無網路單元測試；改邏輯必跑 |

Discord 指令實作：`discord-grok-bot/tw_control.py` + `bot.py`。  
Telegram：`telegram-grok-bot/tw_control.py` + `bot.py`。

Tag **身分組** + `/twnotifi` 會被當成問 Grok。請用 `/twnotifi` 或 `!twnotifi`。

---

## Don't

- 不要把 RWF 塞進 `ask_grok`／Hermes／網搜。
- 不要 commit API token／bot token／`RWF_CONTROL_TOKEN`。
- 不要為了 RWF 改 grok-bot-core 分流。
- 不要 LINE Push。
- 不要還原 grok bot 的 always-on 網搜、`/sethermes`、OpenAI/DeepSeek 不走 Hermes、fast/smart 預設 grok-4.6。
