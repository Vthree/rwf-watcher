"""Kill / new-best detection and Traditional Chinese notices.

Silent unless a tracked guild gets a new kill or a strictly better live
progress_display on the first undefeated boss. Never emits [SILENT].
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass

from models import (
    LAST_BOSS_SLUG,
    RAID_NAME_ZH,
    TOTAL_BOSSES,
    BestProgress,
    Boss,
    Guild,
    GuildSnap,
    Snapshot,
    boss_by_slug,
)

_PCT_RE = re.compile(r"(\d+(?:\.\d+)?)\s*%")
_PHASE_RE = re.compile(r"P(\d+(?:\.\d+)?)", re.I)
_HIDDEN_DISPLAYS = frozenset(
    {
        "",
        "hidden",
        "redacted",
        "restricted",
        "—",
        "-",
        "?",
        "n/a",
        "na",
        "null",
        "none",
    }
)
_HP_EPS = 0.005


def truthy_defeated(value: object) -> bool:
    if value is True or value == 1:
        return True
    if isinstance(value, str) and value.strip().lower() in {"1", "true", "yes"}:
        return True
    return False


def privacy_hides_percent(privacy: dict | None) -> bool:
    if not privacy:
        return False
    percents = privacy.get("share_live_raid_percents", privacy.get("raidPercents"))
    if percents is False:
        return True
    if isinstance(percents, str) and percents.strip().lower() in {
        "none",
        "off",
        "hidden",
        "false",
        "0",
        "restricted",
    }:
        return True
    if privacy.get("wereRaidPercentsRestricted") is True:
        return True
    return False


def parse_progress_display(display: str | None) -> tuple[float | None, float | None]:
    """Return (phase, remaining_pct) from live progress_display."""
    if not display:
        return None, None
    text = str(display)
    phase = None
    m = _PHASE_RE.search(text)
    if m:
        phase = float(m.group(1))
    pcts = [float(x) for x in _PCT_RE.findall(text)]
    remaining = pcts[-1] if pcts else None
    return phase, remaining


def classify_best(
    *,
    boss_slug: str = "",
    boss_name: str = "",
    display: str | None,
    error: object,
    privacy: dict | None,
    pull_count: int | None,
    overall: float | None = None,
) -> BestProgress:
    """Classify live boss-progress. Hidden ≠ 'not started yet'."""
    return _classify_best(
        boss_slug=boss_slug,
        boss_name=boss_name,
        display=display,
        error=error,
        privacy=privacy,
        pull_count=pull_count,
        overall=overall,
    )


def _classify_best(
    *,
    boss_slug: str,
    boss_name: str,
    display: str | None,
    error: object,
    privacy: dict | None,
    pull_count: int | None,
    overall: float | None = None,
) -> BestProgress:
    pulls = pull_count if isinstance(pull_count, int) else None
    if error or privacy_hides_percent(privacy):
        return BestProgress(boss_slug, boss_name, "hidden", _disp(display), None, None, pulls, overall)
    raw = (display or "").strip()
    if raw.lower() in _HIDDEN_DISPLAYS and raw.lower() not in {"", "null", "none"}:
        return BestProgress(boss_slug, boss_name, "hidden", raw, None, None, pulls, overall)
    phase, remaining = parse_progress_display(raw if raw else None)
    if remaining is not None:
        return BestProgress(
            boss_slug,
            boss_name,
            "numeric",
            raw or None,
            remaining,
            phase,
            pulls,
            overall,
        )
    if (pulls or 0) > 0:
        # Pulling but no number → treat as hidden (Liquid-style).
        return BestProgress(boss_slug, boss_name, "hidden", raw or None, None, None, pulls, overall)
    return BestProgress(boss_slug, boss_name, "none", None, None, None, pulls or 0, overall)


def _disp(display: str | None) -> str | None:
    raw = (display or "").strip()
    return raw or None


def first_undefeated(bosses: tuple[Boss, ...], killed: set[str] | tuple[str, ...]) -> Boss | None:
    dead = {s.lower() for s in killed}
    for b in bosses:
        if b.slug.lower() not in dead:
            return b
    return None


def killed_union(
    ranking_defeated: list[str],
    live_defeated: list[str],
    bosses: tuple[Boss, ...],
) -> tuple[str, ...]:
    """encountersDefeated ∪ live isDefeated, raid order. Never uses boss=latest."""
    have = {s.lower() for s in ranking_defeated} | {s.lower() for s in live_defeated}
    ordered = [b.slug for b in bosses if b.slug.lower() in have]
    extras = sorted(s for s in have if s not in {x.lower() for x in ordered})
    return tuple(ordered + extras)


def fingerprint(snapshot: Snapshot) -> str:
    """Stable fingerprint: kills + best display. No timestamps, no pull clock."""
    parts: list[str] = []
    for gid in sorted(snapshot.guilds):
        gs = snapshot.guilds[gid]
        killed = ",".join(gs.killed)
        best = gs.best
        if best is None or best.kind == "none":
            parts.append(f"{gid}:{killed}:none")
        elif best.kind == "hidden":
            parts.append(f"{gid}:{killed}:{best.boss_slug}:hidden")
        else:
            parts.append(f"{gid}:{killed}:{best.boss_slug}:{best.display or ''}")
    parts.append(f"ulatek:{int(snapshot.world_ulatek)}")
    blob = "|".join(parts)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:32]


def is_new_best(old: BestProgress | None, new: BestProgress | None) -> bool:
    """Same boss, remaining HP lower (or later phase). Hidden↔number is silent."""
    if new is None or new.kind != "numeric" or new.remaining is None:
        return False
    if old is None or old.kind == "none":
        return True
    if old.kind == "hidden" or new.kind == "hidden":
        return False
    if old.boss_slug.lower() != new.boss_slug.lower():
        # Moved onto the next undefeated boss — first numeric on it is a best.
        return True
    if (old.display or "") == (new.display or ""):
        return False
    old_phase = 0.0 if old.phase is None else old.phase
    new_phase = 0.0 if new.phase is None else new.phase
    if new_phase > old_phase + _HP_EPS:
        return True
    if new_phase < old_phase - _HP_EPS:
        return False
    if old.remaining is None:
        return True
    return new.remaining < old.remaining - _HP_EPS


def overall_confirms(old: BestProgress | None, new: BestProgress | None) -> bool:
    """Reject current-pull HP dips: display can drop while API bestPercent stays put.

    A later phase (hidden P4, I1, …) is real progression even if bestPercent
    has not moved yet. Same-phase remaining still needs overall to improve.
    """
    if new is None or old is None:
        return True
    old_phase = 0.0 if old.phase is None else old.phase
    new_phase = 0.0 if new.phase is None else new.phase
    if new_phase > old_phase + _HP_EPS:
        return True
    if old.overall is None or new.overall is None:
        return True
    return new.overall < old.overall - _HP_EPS


def ulatek_progress(best: BestProgress | None) -> BestProgress | None:
    if best is None:
        return None
    if (best.boss_slug or "").lower() != LAST_BOSS_SLUG:
        return None
    return best


def world_lead_ulatek(snapshot: Snapshot) -> BestProgress | None:
    """Best Ula'tek remaining among tracked guilds (later phase / lower %)."""
    lead: BestProgress | None = None
    for gs in snapshot.guilds.values():
        cand = ulatek_progress(gs.best)
        if is_new_best(lead, cand):
            lead = cand
    return lead


@dataclass(frozen=True)
class KillEvent:
    guild: Guild
    boss: Boss
    killed_count: int
    world_first: bool = False
    pulls: int | None = None


@dataclass(frozen=True)
class BestEvent:
    guild: Guild
    best: BestProgress


@dataclass
class TickResult:
    events_kills: list[KillEvent]
    events_best: list[BestEvent]
    fingerprint: str
    silent: bool

    def notices(self) -> list[str]:
        blocks: list[str] = []
        kills_by_gid: dict[int, list[KillEvent]] = {}
        for k in self.events_kills:
            kills_by_gid.setdefault(k.guild.id, []).append(k)
        best_by_gid = {b.guild.id: b for b in self.events_best}
        gids = []
        for k in self.events_kills:
            if k.guild.id not in gids:
                gids.append(k.guild.id)
        for b in self.events_best:
            if b.guild.id not in gids:
                gids.append(b.guild.id)
        for gid in gids:
            lines: list[str] = []
            for k in kills_by_gid.get(gid, []):
                lines.append(format_kill(k))
            best = best_by_gid.get(gid)
            if best:
                if lines:
                    lines.append("")
                lines.extend(format_best(best).splitlines())
            if lines:
                blocks.append("\n".join(lines))
        return blocks

    def message(self) -> str | None:
        notices = self.notices()
        if not notices:
            return None
        text = "\n\n".join(notices).strip()
        if not text or text.strip() == "[SILENT]":
            return None
        return text


def diff_snapshot(
    prev: Snapshot | None,
    curr: Snapshot,
    bosses: tuple[Boss, ...],
    guilds: tuple[Guild, ...],
) -> TickResult:
    fp = fingerprint(curr)
    if prev is None:
        return TickResult([], [], fp, silent=True)

    kills: list[KillEvent] = []
    bests: list[BestEvent] = []
    # First time we observe Ula'tek anywhere: the first ulatek kill line this tick
    # may say 世界首殺. Rankings already having it last tick → prev.world_ulatek.
    wf_available = not prev.world_ulatek

    for g in guilds:
        old = prev.guilds.get(g.id) or GuildSnap(killed=())
        new = curr.guilds.get(g.id)
        if new is None:
            continue
        old_killed = set(old.killed)
        new_kills = [s for s in new.killed if s not in old_killed]
        for slug in new_kills:
            if slug.lower() != LAST_BOSS_SLUG:
                continue
            boss = boss_by_slug(bosses, slug)
            if boss is None:
                boss = Boss(slug=slug, name=slug, index=len(new.killed))
            count = list(new.killed).index(slug) + 1 if slug in new.killed else len(new.killed)
            world_first = False
            if wf_available:
                world_first = True
                wf_available = False
            kills.append(
                KillEvent(g, boss, count, world_first=world_first, pulls=_kill_pulls(old, new))
            )
    prev_lead = world_lead_ulatek(prev)
    candidates: list[BestEvent] = []
    for g in guilds:
        gs = curr.guilds.get(g.id)
        if gs is None:
            continue
        cand = ulatek_progress(gs.best)
        if cand and is_new_best(prev_lead, cand) and overall_confirms(prev_lead, cand):
            candidates.append(BestEvent(g, cand))
    if candidates:
        winner = candidates[0]
        for ev in candidates[1:]:
            if is_new_best(winner.best, ev.best):
                winner = ev
        bests.append(winner)

    silent = not kills and not bests
    return TickResult(kills, bests, fp, silent=silent)


def coalesce_best(old: BestProgress | None, new: BestProgress | None) -> BestProgress | None:
    """Keep the strictly-better numeric baseline. Hidden↔number does not reset it."""
    if new is None:
        return old
    if old is None:
        return new
    if (new.boss_slug or "").lower() != (old.boss_slug or "").lower():
        return new
    if is_new_best(old, new) and overall_confirms(old, new):
        return new
    # Same overall bestPercent but live remaining recovered → stored was a pull dip.
    if (
        old.kind == "numeric"
        and new.kind == "numeric"
        and old.overall is not None
        and new.overall is not None
        and abs(old.overall - new.overall) <= 0.5
        and old.remaining is not None
        and new.remaining is not None
        and new.remaining > old.remaining + _HP_EPS
    ):
        return new
    if old.kind == "numeric" and new.kind != "numeric":
        return old
    if old.kind == "numeric" and new.kind == "numeric":
        return old
    return new


def coalesce_snapshot(prev: Snapshot | None, curr: Snapshot) -> Snapshot:
    if prev is None:
        return curr
    guilds: dict[int, GuildSnap] = {}
    for gid, new in curr.guilds.items():
        old = prev.guilds.get(gid)
        best = coalesce_best(old.best if old else None, new.best)
        pulls = new.pulls if new.pulls is not None else (old.pulls if old else None)
        guilds[gid] = GuildSnap(killed=new.killed, best=best, pulls=pulls)
    world = bool(curr.world_ulatek or prev.world_ulatek)
    if any(LAST_BOSS_SLUG in gs.killed for gs in guilds.values()):
        world = True
    return Snapshot(guilds=guilds, world_ulatek=world)


def _kill_pulls(old: GuildSnap | None, new: GuildSnap) -> int | None:
    """Live ulatek pullCount this tick, else last stored ulatek pulls."""
    if new.pulls is not None:
        return new.pulls
    for src in (new.best, old.best if old else None):
        if src is None:
            continue
        if (src.boss_slug or "").lower() == LAST_BOSS_SLUG and src.pulls is not None:
            return src.pulls
    if old is not None and old.pulls is not None:
        return old.pulls
    return None


def format_kill(event: KillEvent) -> str:
    g = event.guild.name
    b = event.boss
    frac = f"（{event.killed_count}/{TOTAL_BOSSES}）"
    if b.slug.lower() == LAST_BOSS_SLUG:
        line = f"{g} 擊殺 尾王 {b.name}{frac}"
        if event.world_first:
            line += " 世界首殺"
    else:
        line = f"{g} 擊殺 第{b.index}王 {b.name}{frac}"
    if event.pulls is not None:
        line += f"\n嘗試次數 {event.pulls}"
    return line


def format_best(event: BestEvent) -> str:
    g = event.guild
    best = event.best
    lines = [
        "!best",
        f"{g.name} 《{RAID_NAME_ZH}》Mythic",
        f"{best.boss_name} {format_remaining(best)}",
    ]
    if best.pulls is not None:
        lines.append(f"嘗試次數 {best.pulls}")
    return "\n".join(lines)


def format_remaining(best: BestProgress) -> str:
    if best.kind == "hidden":
        return "hidden"
    if best.remaining is None:
        return best.display or ""
    pct = _fmt_num(best.remaining)
    if best.phase is not None:
        return f"P{_fmt_num(best.phase)} 剩餘 {pct}%"
    return f"剩餘 {pct}%"


def _fmt_num(n: float) -> str:
    if abs(n - round(n)) < 1e-9:
        return str(int(round(n)))
    text = f"{n:.2f}".rstrip("0").rstrip(".")
    return text


def snapshot_to_json(snapshot: Snapshot) -> dict:
    guilds = {}
    for gid, gs in snapshot.guilds.items():
        best = None
        if gs.best is not None:
            best = {
                "boss_slug": gs.best.boss_slug,
                "boss_name": gs.best.boss_name,
                "kind": gs.best.kind,
                "display": gs.best.display,
                "remaining": gs.best.remaining,
                "phase": gs.best.phase,
                "pulls": gs.best.pulls,
                "overall": gs.best.overall,
            }
        guilds[str(gid)] = {"killed": list(gs.killed), "best": best, "pulls": gs.pulls}
    return {
        "world_ulatek": snapshot.world_ulatek,
        "guilds": guilds,
        "fingerprint": fingerprint(snapshot),
    }


def snapshot_from_json(data: dict | None) -> Snapshot | None:
    if not data or not isinstance(data, dict) or "guilds" not in data:
        return None
    guilds: dict[int, GuildSnap] = {}
    for k, raw in (data.get("guilds") or {}).items():
        best_raw = (raw or {}).get("best")
        best = None
        if best_raw:
            best = BestProgress(
                boss_slug=best_raw.get("boss_slug") or "",
                boss_name=best_raw.get("boss_name") or "",
                kind=best_raw.get("kind") or "none",
                display=best_raw.get("display"),
                remaining=best_raw.get("remaining"),
                phase=best_raw.get("phase"),
                pulls=best_raw.get("pulls"),
                overall=best_raw.get("overall"),
            )
        guilds[int(k)] = GuildSnap(
            killed=tuple(raw.get("killed") or ()),
            best=best,
            pulls=raw.get("pulls"),
        )
    return Snapshot(guilds=guilds, world_ulatek=bool(data.get("world_ulatek")))


def dump_fingerprint_payload(snapshot: Snapshot) -> str:
    """Debug helper — still no timestamps."""
    return json.dumps(snapshot_to_json(snapshot), ensure_ascii=False, sort_keys=True)
