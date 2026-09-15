"""Warcraft Logs v1 client. TW mythic kills — no HTML scrape.

Public api_key from env. Never commit the key.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

import httpx

from models import FALLBACK_BOSSES, Boss, boss_list
from tw import TwGuildSnap, TwSnapshot, guild_key, tw_region_max

logger = logging.getLogger("rwf.wcl")

API = "https://www.warcraftlogs.com/v1"
UA = "rwf-watcher/1.0 (+https://github.com/Vthree/rwf-watcher)"
WCL_MYTHIC = 5

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
