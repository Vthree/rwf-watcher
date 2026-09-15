"""Taiwan region feed.

From 六王 onward: notify the first 3 TW kills of that boss.
Only place 1 gets 台服首殺. Last boss also notifies TW-lead best %.

Independent of Echo/Liquid/Method RWF. No hardcoded guilds. LINE omitted.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from models import LAST_BOSS_SLUG, RAID_NAME_ZH, TOTAL_BOSSES, BestProgress, Boss, boss_by_slug
from watcher import (
    _classify_best,
    coalesce_best,
    format_remaining,
    is_new_best,
    overall_confirms,
    ulatek_progress,
)

_ZH_ORDINAL = {
    1: "一",
    2: "二",
    3: "三",
    4: "四",
    5: "五",
    6: "六",
    7: "七",
    8: "八",
}

TW_TOP_FROM_INDEX = 6
TW_TOP_SLOTS = 3


@dataclass
class TwGuildSnap:
    id: int
    name: str
    realm: str
    killed: tuple[str, ...]
    pulls: dict[str, int] = field(default_factory=dict)
    first_defeated: dict[str, str] = field(default_factory=dict)
    best: BestProgress | None = None


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
    tw_first: bool = False


@dataclass(frozen=True)
class TwBestEvent:
    guild_name: str
    best: BestProgress


@dataclass
class TwTick:
    kills: list[TwKillEvent]
    bests: list[TwBestEvent]
    silent: bool

    @property
    def events(self) -> list[TwKillEvent]:
        return self.kills

    def message(self) -> str | None:
        if not self.kills and not self.bests:
            return None
        blocks: list[str] = []
        kills_by: dict[str, list[TwKillEvent]] = {}
        for k in self.kills:
            kills_by.setdefault(k.guild_name, []).append(k)
        best_by = {b.guild_name: b for b in self.bests}
        names: list[str] = []
        for k in self.kills:
            if k.guild_name not in names:
                names.append(k.guild_name)
        for b in self.bests:
            if b.guild_name not in names:
                names.append(b.guild_name)
        for name in names:
            lines: list[str] = []
            for k in kills_by.get(name, []):
                lines.append(format_tw_kill(k))
            best = best_by.get(name)
            if best:
                if lines:
                    lines.append("")
                lines.extend(format_tw_best(best).splitlines())
            if lines:
                blocks.append("\n".join(lines))
        text = "\n\n".join(blocks).strip()
        if not text or text.strip() == "[SILENT]":
            return None
        return text


def tw_region_max(snapshot: TwSnapshot) -> int:
    if not snapshot.guilds:
        return 0
    return max(len(g.killed) for g in snapshot.guilds.values())


def guild_key(name: str | TwGuildSnap, realm: str | None = None) -> str:
    if isinstance(name, TwGuildSnap):
        return guild_key(name.name, name.realm)
    return f"{(name or '').strip().lower()}|{(realm or '').strip().lower()}"


def _earliest_first(a: dict[str, str], b: dict[str, str]) -> dict[str, str]:
    out = dict(a)
    for k, v in b.items():
        old = out.get(k)
        if old is None or v < old:
            out[k] = v
    return out


def _union_killed(a: tuple[str, ...], b: tuple[str, ...]) -> tuple[str, ...]:
    seen: set[str] = set()
    out: list[str] = []
    for s in list(a) + list(b):
        k = s.lower()
        if k in seen:
            continue
        seen.add(k)
        out.append(s)
    return tuple(out)


def merge_guild(old: TwGuildSnap, new: TwGuildSnap) -> TwGuildSnap:
    """Prefer new id/name; union kills; earliest firstDefeated; keep pulls/best."""
    return TwGuildSnap(
        id=new.id or old.id,
        name=new.name or old.name,
        realm=new.realm or old.realm,
        killed=_union_killed(old.killed, new.killed),
        pulls={**old.pulls, **new.pulls},
        first_defeated=_earliest_first(old.first_defeated, new.first_defeated),
        best=new.best or old.best,
    )


def merge_tw_snapshots(
    rio: TwSnapshot | None,
    wcl: TwSnapshot | None,
) -> TwSnapshot:
    """Union RIO + WCL by guild name+realm. Kills from either source count."""
    by_key: dict[str, TwGuildSnap] = {}
    for src in (rio, wcl):
        if src is None:
            continue
        for g in src.guilds.values():
            k = guild_key(g)
            old = by_key.get(k)
            by_key[k] = merge_guild(old, g) if old else g
    guilds: dict[int, TwGuildSnap] = {}
    for g in by_key.values():
        gid = int(g.id)
        while gid in guilds:
            gid += 1
        if gid != g.id:
            g = TwGuildSnap(
                id=gid,
                name=g.name,
                realm=g.realm,
                killed=g.killed,
                pulls=g.pulls,
                first_defeated=g.first_defeated,
                best=g.best,
            )
        guilds[g.id] = g
    out = TwSnapshot(guilds=guilds)
    out.region_max = tw_region_max(out)
    return out


def _has_kill(g: TwGuildSnap, slug: str) -> bool:
    return slug.lower() in {s.lower() for s in g.killed}


def _killers_ordered(snapshot: TwSnapshot, slug: str) -> list[TwGuildSnap]:
    rows = [g for g in snapshot.guilds.values() if _has_kill(g, slug)]
    rows.sort(
        key=lambda g: (
            g.first_defeated.get(slug) or g.first_defeated.get(slug.lower()) or "\uffff",
            g.name,
        )
    )
    return rows


def best_from_pulled(item: dict, boss: Boss) -> BestProgress | None:
    slug = ((item or {}).get("slug") or "").lower()
    if slug != boss.slug.lower():
        return None
    if (item or {}).get("isDefeated"):
        return None
    display = item.get("progressDisplay")
    if display is None:
        display = item.get("progress_display")
    pulls = item.get("numPulls")
    if pulls is None:
        pulls = item.get("pullCount") or item.get("pull_count")
    overall = item.get("bestPercent")
    if not isinstance(overall, (int, float)):
        overall = None
    api_phase = item.get("phase")
    if not isinstance(api_phase, (int, float)):
        api_phase = None
    api_label = item.get("phaseLabel") or item.get("phase_label")
    if not isinstance(api_label, str) or not api_label.strip():
        api_label = None
    return _classify_best(
        boss_slug=boss.slug,
        boss_name=boss.name,
        display=display if isinstance(display, str) else None,
        error=item.get("error"),
        privacy=None,
        pull_count=int(pulls) if isinstance(pulls, (int, float)) else None,
        overall=float(overall) if overall is not None else None,
        api_phase=float(api_phase) if api_phase is not None else None,
        api_phase_label=api_label,
    )


def guild_snap_from_ranking(row: dict, bosses: tuple[Boss, ...] | None = None) -> TwGuildSnap | None:
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
    best: BestProgress | None = None
    ulatek = boss_by_slug(bosses or (), LAST_BOSS_SLUG) if bosses else None
    killed_set = {s.lower() for s in killed}
    for item in row.get("encountersPulled") or []:
        slug = (item or {}).get("slug")
        n = (item or {}).get("numPulls")
        if slug and isinstance(n, (int, float)):
            pulls[slug] = int(n)
        if ulatek and LAST_BOSS_SLUG not in killed_set:
            parsed = best_from_pulled(item or {}, ulatek)
            if parsed is not None:
                best = parsed
    return TwGuildSnap(
        id=int(gid),
        name=str(guild.get("name") or gid),
        realm=realm,
        killed=tuple(killed),
        pulls=pulls,
        first_defeated=first,
        best=best,
    )


def snapshot_from_rankings(
    rows: list[dict],
    bosses: tuple[Boss, ...] | None = None,
) -> TwSnapshot:
    guilds: dict[int, TwGuildSnap] = {}
    for row in rows or []:
        snap = guild_snap_from_ranking(row, bosses)
        if snap is None:
            continue
        guilds[snap.id] = snap
    out = TwSnapshot(guilds=guilds)
    out.region_max = tw_region_max(out)
    return out


def tw_lead_ulatek(snapshot: TwSnapshot) -> BestProgress | None:
    lead: BestProgress | None = None
    for gs in snapshot.guilds.values():
        cand = ulatek_progress(gs.best)
        if is_new_best(lead, cand):
            lead = cand
    return lead


def _diff_tw_best(prev: TwSnapshot, curr: TwSnapshot) -> list[TwBestEvent]:
    prev_lead = tw_lead_ulatek(prev)
    candidates: list[TwBestEvent] = []
    for g in curr.guilds.values():
        if _has_kill(g, LAST_BOSS_SLUG):
            continue
        cand = ulatek_progress(g.best)
        if cand and is_new_best(prev_lead, cand) and overall_confirms(prev_lead, cand):
            candidates.append(TwBestEvent(g.name, cand))
    if not candidates:
        return []
    winner = candidates[0]
    for ev in candidates[1:]:
        if is_new_best(winner.best, ev.best):
            winner = ev
    return [winner]


def diff_tw(
    prev: TwSnapshot | None,
    curr: TwSnapshot,
    bosses: tuple[Boss, ...],
) -> TwTick:
    if prev is None:
        return TwTick([], [], silent=True)

    kills: list[TwKillEvent] = []
    for boss in bosses:
        if boss.index < TW_TOP_FROM_INDEX:
            continue
        prev_keys = {guild_key(g) for g in prev.guilds.values() if _has_kill(g, boss.slug)}
        ordered = _killers_ordered(curr, boss.slug)
        for place, g in enumerate(ordered, start=1):
            if guild_key(g) in prev_keys:
                continue
            if place > TW_TOP_SLOTS:
                continue
            pulls = g.pulls.get(boss.slug)
            if pulls is None:
                pulls = g.pulls.get(boss.slug.lower())
            kills.append(
                TwKillEvent(
                    guild_name=g.name,
                    boss=boss,
                    killed_count=len(g.killed),
                    pulls=pulls,
                    tw_first=(place == 1),
                )
            )
    kills.sort(
        key=lambda e: (
            e.boss.index,
            0 if e.tw_first else 1,
            e.guild_name,
        )
    )
    bests = _diff_tw_best(prev, curr)
    return TwTick(kills, bests, silent=not kills and not bests)


def coalesce_tw(prev: TwSnapshot | None, curr: TwSnapshot) -> TwSnapshot:
    if prev is None:
        return TwSnapshot(region_max=tw_region_max(curr), guilds=dict(curr.guilds))
    merged = merge_tw_snapshots(prev, curr)
    guilds: dict[int, TwGuildSnap] = {}
    prev_by = {guild_key(g): g for g in prev.guilds.values()}
    for gid, new in merged.guilds.items():
        old = prev_by.get(guild_key(new))
        best = coalesce_best(old.best if old else None, new.best)
        guilds[gid] = TwGuildSnap(
            id=new.id,
            name=new.name,
            realm=new.realm,
            killed=new.killed,
            pulls=new.pulls,
            first_defeated=new.first_defeated,
            best=best,
        )
    region_max = max(prev.region_max, tw_region_max(merged))
    return TwSnapshot(region_max=region_max, guilds=guilds)


def format_tw_kill(event: TwKillEvent) -> str:
    b = event.boss
    frac = f"（{event.killed_count}/{TOTAL_BOSSES}）"
    if b.slug.lower() == LAST_BOSS_SLUG:
        line = f"台服 {event.guild_name} 擊殺 尾王 {b.name}{frac}"
    else:
        ordinal = _ZH_ORDINAL.get(b.index, str(b.index))
        line = f"台服 {event.guild_name} 擊殺 {ordinal}王 {b.name}{frac}"
    if event.tw_first:
        line += " 台服首殺"
    if event.pulls is not None:
        line += f"\n嘗試次數 {event.pulls}"
    return line


def format_tw_best(event: TwBestEvent) -> str:
    best = event.best
    lines = [
        "!best",
        f"台服 {event.guild_name} 《{RAID_NAME_ZH}》Mythic",
        f"{best.boss_name} {format_remaining(best)}",
    ]
    if best.pulls is not None:
        lines.append(f"嘗試次數 {best.pulls}")
    return "\n".join(lines)


def _best_to_json(best: BestProgress | None) -> dict | None:
    if best is None:
        return None
    return {
        "boss_slug": best.boss_slug,
        "boss_name": best.boss_name,
        "kind": best.kind,
        "display": best.display,
        "remaining": best.remaining,
        "phase": best.phase,
        "pulls": best.pulls,
        "overall": best.overall,
        "phase_label": best.phase_label,
    }


def _best_from_json(raw: dict | None) -> BestProgress | None:
    if not raw:
        return None
    return BestProgress(
        boss_slug=raw.get("boss_slug") or "",
        boss_name=raw.get("boss_name") or "",
        kind=raw.get("kind") or "none",
        display=raw.get("display"),
        remaining=raw.get("remaining"),
        phase=raw.get("phase"),
        pulls=raw.get("pulls"),
        overall=raw.get("overall"),
        phase_label=raw.get("phase_label"),
    )


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
            "best": _best_to_json(gs.best),
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
            best=_best_from_json(raw.get("best")),
        )
    region_max = data.get("region_max")
    if not isinstance(region_max, int):
        region_max = max((len(g.killed) for g in guilds.values()), default=0)
    return TwSnapshot(region_max=region_max, guilds=guilds)
