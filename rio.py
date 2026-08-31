"""Raider.io API client. Official endpoints only — no HTML scrape."""

from __future__ import annotations

import logging
from typing import Any

import httpx

from models import (
    DIFFICULTY,
    GUILDS,
    LAST_BOSS_SLUG,
    RAID_SLUG,
    BestProgress,
    Boss,
    Guild,
    GuildSnap,
    Snapshot,
    boss_by_slug,
    boss_list,
)
from watcher import (
    _classify_best,
    first_undefeated,
    killed_union,
    truthy_defeated,
)

logger = logging.getLogger("rwf.rio")

API = "https://raider.io/api/v1"
UA = "rwf-watcher/1.0 (+https://github.com/Vthree/rwf-watcher)"


class RioError(RuntimeError):
    pass


class RioClient:
    def __init__(self, access_key: str, timeout: float = 40.0) -> None:
        if not access_key:
            raise RioError("missing Raider.io access_key")
        self._key = access_key
        self._http = httpx.Client(
            timeout=timeout,
            headers={"User-Agent": UA, "Accept": "application/json"},
            follow_redirects=True,
        )

    def close(self) -> None:
        self._http.close()

    def _get(self, path: str, **params: Any) -> dict:
        q = {k: v for k, v in params.items() if v is not None}
        q["access_key"] = self._key
        url = API + path
        try:
            r = self._http.get(url, params=q)
        except httpx.HTTPError as e:
            raise RioError(f"GET {path} failed: {e}") from e
        if r.status_code == 429:
            retry = r.headers.get("Retry-After", "?")
            raise RioError(f"rate limited Retry-After={retry}")
        if r.status_code >= 400:
            body = (r.text or "")[:240]
            raise RioError(f"GET {path} HTTP {r.status_code}: {body}")
        try:
            data = r.json()
        except ValueError as e:
            raise RioError(f"GET {path} not JSON") from e
        if not isinstance(data, dict):
            raise RioError(f"GET {path} unexpected JSON")
        return data

    def static_bosses(self, expansion_id: int = 11) -> tuple[Boss, ...]:
        data = self._get("/raiding/static-data", expansion_id=expansion_id)
        for raid in data.get("raids") or []:
            if (raid.get("slug") or "") == RAID_SLUG:
                enc = []
                for e in raid.get("encounters") or []:
                    slug = e.get("slug")
                    name = e.get("name") or slug
                    if slug:
                        enc.append((slug, name))
                if enc:
                    return boss_list(enc)
        logger.warning("static-data missing %s; using fallback bosses", RAID_SLUG)
        return boss_list()

    def world_rankings(self, limit: int = 20) -> list[dict]:
        data = self._get(
            "/raiding/raid-rankings",
            raid=RAID_SLUG,
            difficulty=DIFFICULTY,
            region="world",
            limit=limit,
        )
        rows = data.get("raidRankings") or []
        return rows if isinstance(rows, list) else []

    def guild_rankings(self) -> dict[int, dict]:
        ids = ",".join(str(g.id) for g in GUILDS)
        data = self._get(
            "/raiding/raid-rankings",
            raid=RAID_SLUG,
            difficulty=DIFFICULTY,
            region="world",
            guilds=ids,
        )
        out: dict[int, dict] = {}
        for row in data.get("raidRankings") or []:
            gid = (row.get("guild") or {}).get("id")
            if gid is not None:
                out[int(gid)] = row
        return out

    def live_raid_progress(self, guild_id: int) -> dict:
        return self._get(
            "/live-tracking/guild/raid-progress",
            raid=RAID_SLUG,
            difficulty=DIFFICULTY,
            guild_id=guild_id,
        )

    def live_boss_progress(self, guild_id: int, boss_slug: str) -> dict:
        return self._get(
            "/live-tracking/guild/boss-progress",
            raid=RAID_SLUG,
            difficulty=DIFFICULTY,
            guild_id=guild_id,
            boss=boss_slug,
        )

    def fetch_snapshot(self, bosses: tuple[Boss, ...]) -> Snapshot:
        world_rows: list[dict] = []
        try:
            world_rows = self.world_rankings()
        except RioError as e:
            logger.warning("world rankings failed: %s", e)

        world_ulatek = False
        for row in world_rows:
            if LAST_BOSS_SLUG in _ranking_defeated(row):
                world_ulatek = True
                break

        ranking_by_id: dict[int, dict] = {}
        try:
            ranking_by_id = self.guild_rankings()
        except RioError as e:
            logger.warning("guild rankings failed: %s", e)
            for row in world_rows:
                gid = (row.get("guild") or {}).get("id")
                if gid in {g.id for g in GUILDS}:
                    ranking_by_id[int(gid)] = row

        guilds: dict[int, GuildSnap] = {}
        for g in GUILDS:
            guilds[g.id] = self._guild_snap(g, ranking_by_id.get(g.id), bosses)
        if any(LAST_BOSS_SLUG in gs.killed for gs in guilds.values()):
            world_ulatek = True
        return Snapshot(guilds=guilds, world_ulatek=world_ulatek)

    def _guild_snap(
        self,
        guild: Guild,
        ranking: dict | None,
        bosses: tuple[Boss, ...],
    ) -> GuildSnap:
        ranking_killed = _ranking_defeated(ranking) if ranking else []
        live_killed: list[str] = []
        live_privacy: dict | None = None
        try:
            live = self.live_raid_progress(guild.id)
            live_privacy = live.get("guildPrivacy") if isinstance(live, dict) else None
            live_killed = _live_defeated(live)
        except RioError as e:
            logger.warning("%s raid-progress failed: %s", guild.name, e)

        killed = killed_union(ranking_killed, live_killed, bosses)
        target = first_undefeated(bosses, killed)
        best: BestProgress | None = None
        kill_pulls: int | None = None
        if target is not None:
            try:
                bp = self.live_boss_progress(guild.id, target.slug)
                best = parse_boss_progress(bp, target, live_privacy)
            except RioError as e:
                logger.warning("%s boss-progress %s failed: %s", guild.name, target.slug, e)
        elif LAST_BOSS_SLUG in {s.lower() for s in killed}:
            # 8/8: still read ulatek pullCount for the kill notice.
            try:
                bp = self.live_boss_progress(guild.id, LAST_BOSS_SLUG)
                ulatek = boss_by_slug(bosses, LAST_BOSS_SLUG)
                if ulatek is not None:
                    parsed = parse_boss_progress(bp, ulatek, live_privacy)
                    kill_pulls = parsed.pulls
            except RioError as e:
                logger.warning("%s boss-progress ulatek (killed) failed: %s", guild.name, e)
        return GuildSnap(killed=killed, best=best, pulls=kill_pulls)


def _ranking_defeated(row: dict | None) -> list[str]:
    if not row:
        return []
    out = []
    for enc in row.get("encountersDefeated") or []:
        slug = (enc or {}).get("slug")
        if slug:
            out.append(slug)
    return out


def _live_defeated(live: dict | None) -> list[str]:
    if not live:
        return []
    out = []
    for item in live.get("bosses") or []:
        boss = (item or {}).get("boss") or {}
        if truthy_defeated((item or {}).get("isDefeated")):
            slug = boss.get("slug")
            if slug:
                out.append(slug)
    return out


def parse_boss_progress(
    data: dict,
    boss: Boss,
    raid_privacy: dict | None,
) -> BestProgress:
    privacy = data.get("guildPrivacy") or raid_privacy
    display = data.get("progress_display")
    if display is None:
        display = data.get("progressDisplay")
    pulls = data.get("pullCount")
    if pulls is None:
        pulls = data.get("pull_count")
    return _classify_best(
        boss_slug=boss.slug,
        boss_name=boss.name,
        display=display if isinstance(display, str) else display,
        error=data.get("error"),
        privacy=privacy if isinstance(privacy, dict) else None,
        pull_count=int(pulls) if isinstance(pulls, (int, float)) else None,
    )
