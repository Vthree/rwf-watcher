"""Taiwan region feed: notify only when TW overall N/8 increases. No bests.

Independent of Echo/Liquid/Method RWF. No hardcoded guilds. LINE omitted.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from models import LAST_BOSS_SLUG, TOTAL_BOSSES, Boss, boss_by_slug


@dataclass
class TwGuildSnap:
    id: int
    name: str
    realm: str
    killed: tuple[str, ...]
    pulls: dict[str, int] = field(default_factory=dict)
    first_defeated: dict[str, str] = field(default_factory=dict)


@dataclass
class TwSnapshot:
    region_max: int = 0
    guilds: dict[int, TwGuildSnap] = field(default_factory=dict)


@dataclass(frozen=True)
class TwKillEvent:
    guild_name: str
    boss: Boss
    killed_count: int
    pulls: int | None = None


@dataclass
class TwTick:
    events: list[TwKillEvent]
    silent: bool

    def message(self) -> str | None:
        if not self.events:
            return None
        blocks = [format_tw_kill(ev) for ev in self.events]
        text = "\n\n".join(blocks).strip()
        if not text or text.strip() == "[SILENT]":
            return None
        return text


def tw_region_max(snapshot: TwSnapshot) -> int:
    if not snapshot.guilds:
        return 0
    return max(len(g.killed) for g in snapshot.guilds.values())


def guild_snap_from_ranking(row: dict) -> TwGuildSnap | None:
    guild = (row or {}).get("guild") or {}
    gid = guild.get("id")
    if gid is None:
        return None
    realm_raw = guild.get("realm") or {}
    realm = str(realm_raw.get("altName") or realm_raw.get("name") or "")
    killed: list[str] = []
    first: dict[str, str] = {}
    for enc in row.get("encountersDefeated") or []:
        slug = (enc or {}).get("slug")
        if not slug:
            continue
        killed.append(slug)
        fd = (enc or {}).get("firstDefeated")
        if fd:
            first[slug] = str(fd)
    pulls: dict[str, int] = {}
    for item in row.get("encountersPulled") or []:
        slug = (item or {}).get("slug")
        n = (item or {}).get("numPulls")
        if slug and isinstance(n, (int, float)):
            pulls[slug] = int(n)
    return TwGuildSnap(
        id=int(gid),
        name=str(guild.get("name") or gid),
        realm=realm,
        killed=tuple(killed),
        pulls=pulls,
        first_defeated=first,
    )


def snapshot_from_rankings(rows: list[dict]) -> TwSnapshot:
    guilds: dict[int, TwGuildSnap] = {}
    for row in rows or []:
        snap = guild_snap_from_ranking(row)
        if snap is None:
            continue
        guilds[snap.id] = snap
    out = TwSnapshot(guilds=guilds)
    out.region_max = tw_region_max(out)
    return out


def diff_tw(
    prev: TwSnapshot | None,
    curr: TwSnapshot,
    bosses: tuple[Boss, ...],
) -> TwTick:
    if prev is None:
        return TwTick([], silent=True)

    prev_max = prev.region_max
    curr_max = tw_region_max(curr)
    if curr_max <= prev_max:
        return TwTick([], silent=True)

    order = {b.slug.lower(): i for i, b in enumerate(bosses)}
    events: list[TwKillEvent] = []
    for g in curr.guilds.values():
        n = len(g.killed)
        if n <= prev_max:
            continue
        old = prev.guilds.get(g.id)
        old_n = len(old.killed) if old else 0
        emit_from = max(old_n, prev_max)
        n_emit = n - emit_from
        if n_emit <= 0:
            continue
        old_killed = {s.lower() for s in (old.killed if old else ())}
        new_slugs = [s for s in g.killed if s.lower() not in old_killed]
        if not new_slugs:
            continue
        new_slugs.sort(key=lambda s: g.first_defeated.get(s) or "")
        picked = new_slugs[-n_emit:]
        picked.sort(key=lambda s: order.get(s.lower(), 99))
        for i, slug in enumerate(picked):
            count_at = emit_from + i + 1
            boss = boss_by_slug(bosses, slug)
            if boss is None:
                boss = Boss(slug=slug, name=slug, index=count_at)
            pulls = g.pulls.get(slug)
            events.append(TwKillEvent(g.name, boss, count_at, pulls))
    events.sort(
        key=lambda e: (
            e.killed_count,
            order.get(e.boss.slug.lower(), 99),
            e.guild_name,
        )
    )
    return TwTick(events, silent=not events)


def coalesce_tw(prev: TwSnapshot | None, curr: TwSnapshot) -> TwSnapshot:
    if prev is None:
        return TwSnapshot(region_max=tw_region_max(curr), guilds=dict(curr.guilds))
    guilds = dict(curr.guilds) if curr.guilds else dict(prev.guilds)
    region_max = max(prev.region_max, tw_region_max(curr))
    return TwSnapshot(region_max=region_max, guilds=guilds)


def format_tw_kill(event: TwKillEvent) -> str:
    b = event.boss
    frac = f"（{event.killed_count}/{TOTAL_BOSSES}）"
    if b.slug.lower() == LAST_BOSS_SLUG:
        line = f"台服 {event.guild_name} 擊殺 尾王 {b.name}{frac}"
    else:
        line = f"台服 {event.guild_name} 擊殺 第{b.index}王 {b.name}{frac}"
    if event.pulls is not None:
        line += f"\n嘗試次數 {event.pulls}"
    return line


def tw_snapshot_to_json(snapshot: TwSnapshot) -> dict:
    guilds = {}
    for gid, gs in snapshot.guilds.items():
        guilds[str(gid)] = {
            "id": gs.id,
            "name": gs.name,
            "realm": gs.realm,
            "killed": list(gs.killed),
            "pulls": gs.pulls,
            "first_defeated": gs.first_defeated,
        }
    return {"region_max": snapshot.region_max, "guilds": guilds}


def tw_snapshot_from_json(data: dict | None) -> TwSnapshot | None:
    if not data or not isinstance(data, dict):
        return None
    guilds: dict[int, TwGuildSnap] = {}
    for k, raw in (data.get("guilds") or {}).items():
        raw = raw or {}
        pulls_raw = raw.get("pulls") or {}
        pulls = {str(sk): int(sv) for sk, sv in pulls_raw.items() if isinstance(sv, (int, float))}
        first_raw = raw.get("first_defeated") or {}
        first = {str(sk): str(sv) for sk, sv in first_raw.items()}
        gid = int(raw.get("id") or k)
        guilds[gid] = TwGuildSnap(
            id=gid,
            name=str(raw.get("name") or gid),
            realm=str(raw.get("realm") or ""),
            killed=tuple(raw.get("killed") or ()),
            pulls=pulls,
            first_defeated=first,
        )
    region_max = data.get("region_max")
    if not isinstance(region_max, int):
        region_max = max((len(g.killed) for g in guilds.values()), default=0)
    return TwSnapshot(region_max=region_max, guilds=guilds)
