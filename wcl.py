"""Warcraft Logs v1 client. TW mythic kills — no HTML scrape.

Public api_key from env. Never commit the key.
"""

from __future__ import annotations

import json
import logging
import re
import time
from datetime import datetime, timezone
from typing import Any

import httpx

from models import FALLBACK_BOSSES, LAST_BOSS_SLUG, BestProgress, Boss, boss_by_slug, boss_list
from tw import TwGuildSnap, TwSnapshot, guild_key, guild_match_key, tw_region_max

logger = logging.getLogger("rwf.wcl")

API = "https://www.warcraftlogs.com/v1"
GQL = "https://www.warcraftlogs.com/api/v2/client"
OAUTH = "https://www.warcraftlogs.com/oauth/token"
UA = "rwf-watcher/1.0 (+https://github.com/Vthree/rwf-watcher)"
WCL_MYTHIC = 5
WCL_ZONE_VA = 53
WCL_RACE_TTL = 480
_DISP_RE = re.compile(r"^\s*([\d.]+)\s*%(?:\s*(P\d+|I\d+))?", re.I)

# Zone 53 The Venomous Abyss. Map to our slugs (ignore Nymrissa).
WCL_ENCOUNTER_BY_SLUG: dict[str, int] = {
    "nekzali-the-soulcoiler": 3470,
    "entombed-sentinels": 3445,
    "the-lost-explorers": 3497,
    "vashnik-the-malignant": 3455,
    "sszorak": 3420,
    "the-twin-fangs": 3421,
    "the-coiled-altar": 3429,
    "ulatek": 3492,
}


class WclError(RuntimeError):
    pass


def _iso_ms(ms: object) -> str | None:
    if not isinstance(ms, (int, float)):
        return None
    try:
        dt = datetime.fromtimestamp(ms / 1000.0, tz=timezone.utc)
    except (OSError, OverflowError, ValueError):
        return None
    return dt.strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


def snapshot_from_wcl_rankings(
    by_slug: dict[str, list[dict]],
    bosses: tuple[Boss, ...] | None = None,
) -> TwSnapshot:
    """Build a TW snapshot from per-slug WCL encounter ranking rows."""
    bosses = bosses or boss_list()
    by_key: dict[str, TwGuildSnap] = {}
    for slug, rows in (by_slug or {}).items():
        slug_l = slug.lower()
        for row in rows or []:
            name = str(row.get("guildName") or "").strip()
            if not name:
                continue
            realm = str(row.get("serverName") or "").strip()
            gid = row.get("guildID")
            if not isinstance(gid, int):
                gid = abs(hash((name.lower(), realm.lower()))) % 10_000_000
            iso = _iso_ms(row.get("startTime"))
            key = guild_key(name, realm)
            g = by_key.get(key)
            if g is None:
                g = TwGuildSnap(id=int(gid), name=name, realm=realm, killed=())
                by_key[key] = g
            killed = list(g.killed)
            if slug_l not in {s.lower() for s in killed}:
                killed.append(slug)
            first = dict(g.first_defeated)
            if iso and (slug not in first or iso < first[slug]):
                first[slug] = iso
            by_key[key] = TwGuildSnap(
                id=g.id,
                name=g.name,
                realm=g.realm,
                killed=tuple(killed),
                pulls=g.pulls,
                first_defeated=first,
                best=g.best,
            )
    guilds: dict[int, TwGuildSnap] = {}
    for g in by_key.values():
        have = {s.lower() for s in g.killed}
        ordered = [b.slug for b in bosses if b.slug.lower() in have]
        extras = [s for s in g.killed if s.lower() not in {x.lower() for x in ordered}]
        snap = TwGuildSnap(
            id=g.id,
            name=g.name,
            realm=g.realm,
            killed=tuple(ordered + extras),
            pulls=g.pulls,
            first_defeated=g.first_defeated,
            best=g.best,
        )
        gid = snap.id
        while gid in guilds:
            gid += 1
        if gid != snap.id:
            snap = TwGuildSnap(
                id=gid,
                name=snap.name,
                realm=snap.realm,
                killed=snap.killed,
                pulls=snap.pulls,
                first_defeated=snap.first_defeated,
                best=snap.best,
            )
        guilds[snap.id] = snap
    out = TwSnapshot(guilds=guilds)
    out.region_max = tw_region_max(out)
    return out


class WclClient:
    def __init__(self, api_key: str, timeout: float = 40.0) -> None:
        if not api_key:
            raise WclError("missing WCL api_key")
        self._key = api_key
        self._http = httpx.Client(
            timeout=timeout,
            headers={"User-Agent": UA, "Accept": "application/json"},
            follow_redirects=True,
        )

    def close(self) -> None:
        self._http.close()

    def _get(self, path: str, **params: Any) -> dict:
        q = {k: v for k, v in params.items() if v is not None}
        q["api_key"] = self._key
        url = API + path
        try:
            r = self._http.get(url, params=q)
        except httpx.HTTPError as e:
            raise WclError(f"GET {path} failed: {e}") from e
        if r.status_code == 429:
            raise WclError(f"rate limited GET {path}")
        if r.status_code >= 400:
            body = (r.text or "")[:240]
            raise WclError(f"GET {path} HTTP {r.status_code}: {body}")
        try:
            data = r.json()
        except ValueError as e:
            raise WclError(f"GET {path} not JSON") from e
        if not isinstance(data, dict):
            raise WclError(f"GET {path} unexpected JSON")
        return data

    def encounter_rankings_tw(self, encounter_id: int, metric: str = "speed") -> list[dict]:
        rows: list[dict] = []
        page = 1
        while page <= 20:
            data = self._get(
                f"/rankings/encounter/{encounter_id}",
                metric=metric,
                difficulty=WCL_MYTHIC,
                region="TW",
                page=page,
            )
            chunk = data.get("rankings") or []
            if isinstance(chunk, list):
                rows.extend(x for x in chunk if isinstance(x, dict))
            if not data.get("hasMorePages"):
                break
            page += 1
        return rows

    def fetch_tw_kills(self, bosses: tuple[Boss, ...] | None = None) -> TwSnapshot:
        bosses = bosses or boss_list()
        by_slug: dict[str, list[dict]] = {}
        slugs = [s for s, _ in FALLBACK_BOSSES]
        for slug in slugs:
            eid = WCL_ENCOUNTER_BY_SLUG.get(slug)
            if eid is None:
                continue
            try:
                by_slug[slug] = self.encounter_rankings_tw(eid)
            except WclError as e:
                logger.warning("wcl %s (%s) failed: %s", slug, eid, e)
                by_slug[slug] = []
        return snapshot_from_wcl_rankings(by_slug, bosses)


WCL_SLUG_BY_ENCOUNTER = {eid: slug for slug, eid in WCL_ENCOUNTER_BY_SLUG.items()}


def best_from_race_encounter(enc: dict, boss: Boss) -> BestProgress | None:
    if enc.get("isKilled"):
        return None
    pulls = enc.get("pullCount")
    overall = enc.get("bestPercent")
    if (not pulls) and (not isinstance(overall, (int, float)) or float(overall) >= 99.5):
        return None
    remaining = None
    label = None
    m = _DISP_RE.match(str(enc.get("bestPercentForDisplay") or ""))
    if m:
        remaining = float(m.group(1))
        if m.group(2):
            label = m.group(2).upper()
    elif isinstance(overall, (int, float)):
        remaining = float(overall)
    phase = None
    if label:
        if label.startswith("P"):
            try:
                phase = float(label[1:])
            except ValueError:
                phase = None
        elif label.startswith("I"):
            try:
                phase = 1.5 + float(label[1:])
            except ValueError:
                phase = None
    elif isinstance(enc.get("bestPhaseIndex"), (int, float)):
        phase = float(enc["bestPhaseIndex"]) + 1.0
    kind = "numeric" if remaining is not None else "none"
    return BestProgress(
        boss_slug=boss.slug,
        boss_name=boss.name,
        kind=kind,
        display=str(enc.get("bestPercentForDisplay") or "") or None,
        remaining=remaining,
        phase=phase,
        pulls=int(pulls) if isinstance(pulls, (int, float)) and pulls else None,
        overall=float(overall) if isinstance(overall, (int, float)) else None,
        phase_label=label,
    )


def snapshot_from_progress_race(
    race: list[dict] | dict | None,
    bosses: tuple[Boss, ...] | None = None,
) -> TwSnapshot:
    bosses = bosses or boss_list()
    rows = race if isinstance(race, list) else []
    ulatek = boss_by_slug(bosses, LAST_BOSS_SLUG)
    by_name: dict[str, TwGuildSnap] = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        name = str(row.get("name") or "").strip()
        if not name:
            continue
        gid = row.get("id")
        if not isinstance(gid, int):
            gid = abs(hash(name.lower())) % 10_000_000
        realm = ""
        killed: list[str] = []
        first: dict[str, str] = {}
        pulls: dict[str, int] = {}
        best = None
        for enc in row.get("encounters") or []:
            if not isinstance(enc, dict):
                continue
            slug = WCL_SLUG_BY_ENCOUNTER.get(enc.get("id"))
            if not slug:
                continue
            n = enc.get("pullCount")
            if isinstance(n, (int, float)) and n:
                pulls[slug] = int(n)
            if enc.get("isKilled"):
                killed.append(slug)
                iso = _iso_ms(enc.get("killedAtTimestamp"))
                if iso:
                    first[slug] = iso
            elif slug == LAST_BOSS_SLUG and ulatek is not None:
                best = best_from_race_encounter(enc, ulatek)
        have = {s.lower() for s in killed}
        ordered = [b.slug for b in bosses if b.slug.lower() in have]
        extras = [s for s in killed if s.lower() not in {x.lower() for x in ordered}]
        snap = TwGuildSnap(
            id=int(gid),
            name=name,
            realm=realm,
            killed=tuple(ordered + extras),
            pulls=pulls,
            first_defeated=first,
            best=best,
        )
        by_name[guild_match_key(snap)] = snap
    guilds = {g.id: g for g in by_name.values()}
    out = TwSnapshot(guilds=guilds)
    out.region_max = tw_region_max(out)
    return out


class WclV2Client:
    """GraphQL progressRace — same board as /zone/race/latest?region=4."""

    def __init__(
        self,
        client_id: str,
        client_secret: str,
        timeout: float = 40.0,
        race_ttl: int = WCL_RACE_TTL,
    ) -> None:
        if not client_id or not client_secret:
            raise WclError("missing WCL client id/secret")
        self._id = client_id
        self._secret = client_secret
        self._race_ttl = max(60, int(race_ttl))
        self._token: str | None = None
        self._token_exp = 0.0
        self._race: TwSnapshot | None = None
        self._race_at = 0.0
        self._http = httpx.Client(
            timeout=timeout,
            headers={"User-Agent": UA, "Accept": "application/json"},
            follow_redirects=True,
        )

    def close(self) -> None:
        self._http.close()

    def _access_token(self) -> str:
        now = time.time()
        if self._token and now < self._token_exp - 60:
            return self._token
        try:
            r = self._http.post(
                OAUTH,
                data={"grant_type": "client_credentials"},
                auth=(self._id, self._secret),
            )
        except httpx.HTTPError as e:
            raise WclError(f"oauth failed: {e}") from e
        if r.status_code >= 400:
            raise WclError(f"oauth HTTP {r.status_code}: {(r.text or '')[:200]}")
        data = r.json()
        tok = data.get("access_token")
        if not tok:
            raise WclError("oauth missing access_token")
        self._token = str(tok)
        self._token_exp = now + float(data.get("expires_in") or 3600)
        return self._token

    def graphql(self, query: str, variables: dict | None = None) -> dict:
        try:
            r = self._http.post(
                GQL,
                json={"query": query, "variables": variables or {}},
                headers={"Authorization": f"Bearer {self._access_token()}"},
            )
        except httpx.HTTPError as e:
            raise WclError(f"graphql failed: {e}") from e
        if r.status_code >= 400:
            raise WclError(f"graphql HTTP {r.status_code}: {(r.text or '')[:240]}")
        payload = r.json()
        if payload.get("errors"):
            raise WclError(f"graphql errors: {payload['errors']!r}"[:400])
        data = payload.get("data")
        if not isinstance(data, dict):
            raise WclError("graphql missing data")
        return data

    def fetch_tw_race(self, bosses: tuple[Boss, ...] | None = None, force: bool = False) -> TwSnapshot:
        now = time.time()
        if not force and self._race is not None and now - self._race_at < self._race_ttl:
            return self._race
        data = self.graphql(
            """
            query TwRace($region: String, $zone: Int, $diff: Int, $size: Int) {
              progressRaceData {
                progressRace(serverRegion: $region, zoneID: $zone, difficulty: $diff, size: $size)
              }
            }
            """,
            {"region": "TW", "zone": WCL_ZONE_VA, "diff": WCL_MYTHIC, "size": 20},
        )
        race = (data.get("progressRaceData") or {}).get("progressRace")
        if isinstance(race, str):
            race = json.loads(race)
        snap = snapshot_from_progress_race(race, bosses)
        self._race = snap
        self._race_at = now
        logger.info("wcl v2 progressRace guilds=%s ttl=%ss", len(snap.guilds), self._race_ttl)
        return snap
