"""Offline unit checks — no Raider.io / Telegram / Discord network."""

from __future__ import annotations

import tempfile
from pathlib import Path

from destinations import load as load_dests
from destinations import set_dest
from models import (
    FALLBACK_BOSSES,
    GUILDS,
    BestProgress,
    GuildSnap,
    Snapshot,
    boss_list,
)
from notify import should_send
from rio import parse_boss_progress
from watcher import (
    coalesce_best,
    coalesce_snapshot,
    diff_snapshot,
    fingerprint,
    first_undefeated,
    format_best,
    format_kill,
    is_new_best,
    killed_union,
    parse_progress_display,
    snapshot_from_json,
    snapshot_to_json,
    truthy_defeated,
    KillEvent,
    BestEvent,
)


BOSSES = boss_list()
ECHO, LIQUID, METHOD = GUILDS


def _best(
    slug="ulatek",
    name="Ula'tek",
    kind="numeric",
    display="76.03%",
    remaining=76.03,
    phase=None,
    pulls=91,
) -> BestProgress:
    return BestProgress(slug, name, kind, display, remaining, phase, pulls)


def _snap(echo_killed=None, echo_best=None, world=False, extra=None) -> Snapshot:
    killed = echo_killed or FALLBACK_BOSSES[:7]
    slugs = tuple(s for s, _ in killed) if killed and isinstance(killed[0], tuple) else tuple(killed)
    guilds = {
        ECHO.id: GuildSnap(killed=slugs, best=echo_best),
        LIQUID.id: GuildSnap(killed=slugs, best=None),
        METHOD.id: GuildSnap(killed=tuple(s for s, _ in FALLBACK_BOSSES[:6]), best=None),
    }
    if extra:
        guilds.update(extra)
    return Snapshot(guilds=guilds, world_ulatek=world)


def main() -> None:
    assert truthy_defeated(1) is True
    assert truthy_defeated(True) is True
    assert truthy_defeated("true") is True
    assert truthy_defeated(False) is False
    assert truthy_defeated(0) is False
    assert truthy_defeated(None) is False

    # kill union: rankings + live, raid order, ignore latest
    ranking = ["ulatek", "nekzali-the-soulcoiler"]
    live = ["the-coiled-altar", "nekzali-the-soulcoiler"]
    union = killed_union(ranking, live, BOSSES)
    assert union[0] == "nekzali-the-soulcoiler"
    assert "the-coiled-altar" in union and "ulatek" in union
    assert union.index("the-coiled-altar") < union.index("ulatek")

    # first undefeated is NOT latest-pulled
    six = [s for s, _ in FALLBACK_BOSSES[:6]]
    target = first_undefeated(BOSSES, six)
    assert target is not None and target.slug == "the-coiled-altar"
    seven = [s for s, _ in FALLBACK_BOSSES[:7]]
    target = first_undefeated(BOSSES, seven)
    assert target is not None and target.slug == "ulatek"
    all8 = [s for s, _ in FALLBACK_BOSSES]
    assert first_undefeated(BOSSES, all8) is None

    phase, remaining = parse_progress_display("76.03%")
    assert phase is None and remaining == 76.03
    phase, remaining = parse_progress_display("4.44% P3")
    assert phase == 3 and remaining == 4.44
    phase, remaining = parse_progress_display("P2 32.1%")
    assert phase == 2 and remaining == 32.1

    # new best: lower remaining only
    a = _best(remaining=76.03, display="76.03%")
    b = _best(remaining=75.14, display="75.14%")
    assert is_new_best(a, b) is True
    assert is_new_best(b, a) is False
    assert is_new_best(a, a) is False
    # later phase is better even if % is higher
    p2 = _best(display="1.00% P2", remaining=1.0, phase=2, slug="the-coiled-altar", name="The Coiled Altar")
    p3 = _best(display="4.44% P3", remaining=4.44, phase=3, slug="the-coiled-altar", name="The Coiled Altar")
    assert is_new_best(p2, p3) is True
    assert is_new_best(p3, p2) is False

    hidden = _best(kind="hidden", display="hidden", remaining=None)
    assert is_new_best(hidden, a) is False
    assert is_new_best(a, hidden) is False
    none = _best(kind="none", display=None, remaining=None, pulls=0)
    assert is_new_best(none, a) is True

    # fingerprint ignores timestamps (they are not in snapshot at all)
    s1 = _snap(echo_best=a)
    s2 = _snap(echo_best=a)
    assert fingerprint(s1) == fingerprint(s2)
    s3 = _snap(echo_best=b)
    assert fingerprint(s1) != fingerprint(s3)

    # first poll silent
    tick = diff_snapshot(None, s1, BOSSES, GUILDS)
    assert tick.silent is True
    assert tick.message() is None

    # same state silent
    tick = diff_snapshot(s1, s2, BOSSES, GUILDS)
    assert tick.silent is True
    assert tick.message() is None

    # new best notifies, 嘗試次數, no 拉
    tick = diff_snapshot(s1, s3, BOSSES, GUILDS)
    assert tick.silent is False
    msg = tick.message()
    assert msg and "嘗試次數" in msg
    assert "拉" not in msg
    assert "[SILENT]" not in msg
    assert "剩餘" in msg
    assert "Ula'tek" in msg
    assert "Echo" in msg

    # HP went up → silent, coalesce keeps lower
    worse = _snap(echo_best=_best(remaining=80.0, display="80%"))
    tick = diff_snapshot(s1, worse, BOSSES, GUILDS)
    assert tick.silent is True
    kept = coalesce_best(a, worse.guilds[ECHO.id].best)
    assert kept is not None and kept.remaining == 76.03

    # hidden ↔ number silent; number is stored as new baseline
    hid_snap = _snap(echo_best=hidden)
    tick = diff_snapshot(s1, hid_snap, BOSSES, GUILDS)
    assert tick.silent is True
    assert coalesce_best(a, hidden).remaining == 76.03
    tick = diff_snapshot(hid_snap, s1, BOSSES, GUILDS)
    assert tick.silent is True
    baseline = coalesce_best(hidden, a)
    assert baseline.kind == "numeric" and baseline.remaining == 76.03

    # kill line format
    from models import Boss

    k = KillEvent(ECHO, Boss("the-coiled-altar", "The Coiled Altar", 7), 7)
    line = format_kill(k)
    assert line == "擊殺 Echo 第7王 The Coiled Altar（7/8）"
    last = KillEvent(ECHO, Boss("ulatek", "Ula'tek", 8), 8, world_first=True)
    line = format_kill(last)
    assert line == "擊殺 Echo 尾王 Ula'tek（8/8） 世界首殺"
    last2 = KillEvent(LIQUID, Boss("ulatek", "Ula'tek", 8), 8, world_first=False)
    assert "世界首殺" not in format_kill(last2)

    # bosses 1–7 are tracked but never posted (only 尾王 Ula'tek)
    prev = _snap(echo_killed=FALLBACK_BOSSES[:6], echo_best=p2)
    seven = tuple(s for s, _ in FALLBACK_BOSSES[:7])
    curr = _snap(
        echo_killed=FALLBACK_BOSSES[:7],
        echo_best=_best(),
        extra={ECHO.id: GuildSnap(killed=seven, best=_best())},
    )
    tick = diff_snapshot(prev, curr, BOSSES, GUILDS)
    assert tick.events_kills == []
    # first numeric on ulatek (moved onto last boss) is a last-boss best
    assert tick.events_best and tick.events_best[0].best.boss_slug == "ulatek"
    msg = tick.message()
    assert msg and "Ula'tek" in msg
    assert "第7王" not in msg
    assert "The Coiled Altar" not in msg

    method_old = _snap(
        extra={
            METHOD.id: GuildSnap(
                killed=tuple(s for s, _ in FALLBACK_BOSSES[:6]),
                best=p2,
            )
        }
    )
    method_new = _snap(
        extra={
            METHOD.id: GuildSnap(
                killed=tuple(s for s, _ in FALLBACK_BOSSES[:6]),
                best=p3,
            )
        }
    )
    tick = diff_snapshot(method_old, method_new, BOSSES, GUILDS)
    assert tick.silent is True

    # world first only when prev did not already know ulatek
    prev_clear = _snap(echo_killed=FALLBACK_BOSSES[:7], echo_best=a, world=False)
    curr_wf = _snap(echo_killed=FALLBACK_BOSSES, echo_best=None, world=False)
    curr_wf.guilds[ECHO.id] = GuildSnap(killed=tuple(s for s, _ in FALLBACK_BOSSES), best=None)
    tick = diff_snapshot(prev_clear, curr_wf, BOSSES, GUILDS)
    assert tick.events_kills and tick.events_kills[0].world_first is True
    prev_known = _snap(echo_killed=FALLBACK_BOSSES[:7], echo_best=a, world=True)
    tick = diff_snapshot(prev_known, curr_wf, BOSSES, GUILDS)
    assert tick.events_kills and tick.events_kills[0].world_first is False
    stored_wf = coalesce_snapshot(prev_clear, curr_wf)
    assert stored_wf.world_ulatek is True
    tick = diff_snapshot(stored_wf, curr_wf, BOSSES, GUILDS)
    assert tick.silent is True

    # live boss-progress parser uses progress_display not bestPercent
    boss = [b for b in BOSSES if b.slug == "the-coiled-altar"][0]
    parsed = parse_boss_progress(
        {
            "progress_display": "4.44% P3",
            "bestPercent": 1.33,
            "pullCount": 393,
            "isDefeated": False,
            "error": None,
            "phase": 3,
        },
        boss,
        {"share_live_raid_percents": "all"},
    )
    assert parsed.kind == "numeric"
    assert parsed.remaining == 4.44
    assert parsed.phase == 3
    assert parsed.pulls == 393

    hidden_parsed = parse_boss_progress(
        {"progress_display": "hidden", "pullCount": 84, "error": None},
        [b for b in BOSSES if b.slug == "ulatek"][0],
        {"share_live_raid_percents": "none"},
    )
    assert hidden_parsed.kind == "hidden"

    pulling_no_pct = parse_boss_progress(
        {"progress_display": None, "pullCount": 12, "error": None},
        [b for b in BOSSES if b.slug == "ulatek"][0],
        None,
    )
    assert pulling_no_pct.kind == "hidden"

    not_started = parse_boss_progress(
        {"progress_display": None, "pullCount": 0, "error": None},
        [b for b in BOSSES if b.slug == "ulatek"][0],
        None,
    )
    assert not_started.kind == "none"

    # best message wording
    text = format_best(BestEvent(ECHO, p3))
    assert "嘗試次數 91" in text or "嘗試次數 91" in text.replace("91", str(p3.pulls))
    assert "拉" not in text
    assert "Method" not in text
    assert "raider.io/guilds/eu/tarren-mill/Echo" in text
    assert "[SILENT]" not in text

    assert should_send(None) is False
    assert should_send("[SILENT]") is False
    assert should_send("  [SILENT]  ") is False
    assert should_send("擊殺 Echo 尾王 Ula'tek（8/8）") is True

    # state roundtrip has no timestamp keys
    blob = snapshot_to_json(s1)
    assert "pullStartedAt" not in str(blob)
    assert "firstDefeated" not in str(blob)
    roundtrip = snapshot_from_json(blob)
    assert roundtrip is not None
    assert fingerprint(roundtrip) == fingerprint(s1)

    stored = coalesce_snapshot(s1, worse)
    assert stored.guilds[ECHO.id].best.remaining == 76.03
    assert stored.world_ulatek is False

    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / "dest.json"
        assert load_dests(p) == {"discord": [], "telegram": []}
        r = set_dest("discord", "1047807735779045406", True, p)
        assert r["enabled"] is True
        assert r["ids"] == ["1047807735779045406"]
        set_dest("discord", "111", True, p)
        set_dest("telegram", "-1001603086249", True, p)
        data = load_dests(p)
        assert data["discord"] == ["1047807735779045406", "111"]
        assert data["telegram"] == ["-1001603086249"]
        set_dest("discord", "1047807735779045406", False, p)
        assert load_dests(p)["discord"] == ["111"]
        try:
            set_dest("line", "x", True, p)
            raise AssertionError("line should fail")
        except ValueError:
            pass

    print("ALL_UNIT_TESTS_PASSED")


if __name__ == "__main__":
    main()
