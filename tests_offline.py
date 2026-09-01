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
from tw import (
    TwGuildSnap,
    TwKillEvent,
    TwSnapshot,
    coalesce_tw,
    diff_tw,
    format_tw_kill,
    guild_snap_from_ranking,
    snapshot_from_rankings,
    tw_region_max,
)
from watcher import (
    coalesce_best,
    coalesce_snapshot,
    diff_snapshot,
    fingerprint,
    first_undefeated,
    format_best,
    format_kill,
    is_new_best,
    overall_confirms,
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
    overall=None,
) -> BestProgress:
    return BestProgress(slug, name, kind, display, remaining, phase, pulls, overall)


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
    assert msg and msg.startswith("!best")
    assert "嘗試次數" in msg
    assert "拉" not in msg
    assert "[SILENT]" not in msg
    assert "剩餘" in msg
    assert "Ula'tek" in msg
    assert "Echo" in msg
    assert "raider.io" not in msg

    # personal best that does not take the world lead stays silent
    seven = tuple(s for s, _ in FALLBACK_BOSSES[:7])
    echo_lead = _best(remaining=73.58, display="73.58%")
    prev_lead_snap = _snap(
        echo_killed=FALLBACK_BOSSES[:7],
        echo_best=echo_lead,
        extra={LIQUID.id: GuildSnap(killed=seven, best=_best(remaining=75.14, display="75.14%"))},
    )
    liquid_not_enough = _snap(
        echo_killed=FALLBACK_BOSSES[:7],
        echo_best=echo_lead,
        extra={LIQUID.id: GuildSnap(killed=seven, best=_best(remaining=74.0, display="74%"))},
    )
    tick = diff_snapshot(prev_lead_snap, liquid_not_enough, BOSSES, GUILDS)
    assert tick.silent is True
    assert tick.events_best == []

    liquid_takes_lead = _snap(
        echo_killed=FALLBACK_BOSSES[:7],
        echo_best=echo_lead,
        extra={LIQUID.id: GuildSnap(killed=seven, best=_best(remaining=73.0, display="73%"))},
    )
    tick = diff_snapshot(prev_lead_snap, liquid_takes_lead, BOSSES, GUILDS)
    assert tick.silent is False
    assert len(tick.events_best) == 1
    assert tick.events_best[0].guild.id == LIQUID.id
    lead_msg = tick.message()
    assert lead_msg and lead_msg.startswith("!best")
    assert "Liquid" in lead_msg
    assert "Echo" not in lead_msg

    echo_extends = _snap(
        echo_killed=FALLBACK_BOSSES[:7],
        echo_best=_best(remaining=72.0, display="72%"),
        extra={LIQUID.id: GuildSnap(killed=seven, best=_best(remaining=75.14, display="75.14%"))},
    )
    tick = diff_snapshot(prev_lead_snap, echo_extends, BOSSES, GUILDS)
    assert tick.events_best and tick.events_best[0].guild.id == ECHO.id

    both_beat = _snap(
        echo_killed=FALLBACK_BOSSES[:7],
        echo_best=_best(remaining=72.0, display="72%"),
        extra={LIQUID.id: GuildSnap(killed=seven, best=_best(remaining=72.5, display="72.5%"))},
    )
    tick = diff_snapshot(prev_lead_snap, both_beat, BOSSES, GUILDS)
    assert len(tick.events_best) == 1
    assert tick.events_best[0].guild.id == ECHO.id
    assert tick.events_best[0].best.remaining == 72.0

    # later phase is better than unphased even if remaining % is higher
    unphased = _best(remaining=73.58, display="73.58%", overall=73.58)
    p3_high = _best(remaining=75.4, display="75.4% P3", phase=3, overall=18.85)
    assert is_new_best(unphased, p3_high) is True

    # current-pull dip: display remaining drops but API bestPercent does not
    p3_lead = _best(remaining=75.4, display="75.4% P3", phase=3, overall=18.85, pulls=158)
    p3_dip = _best(remaining=12.0, display="12% P3", phase=3, overall=18.85, pulls=159)
    assert is_new_best(p3_lead, p3_dip) is True
    assert overall_confirms(p3_lead, p3_dip) is False
    prev_p3 = _snap(echo_killed=FALLBACK_BOSSES[:7], echo_best=p3_lead)
    curr_dip = _snap(echo_killed=FALLBACK_BOSSES[:7], echo_best=p3_dip)
    tick = diff_snapshot(prev_p3, curr_dip, BOSSES, GUILDS)
    assert tick.silent is True
    healed = coalesce_best(p3_dip, p3_lead)
    assert healed is not None and healed.remaining == 75.4

    # real new best: display and overall both improve
    p3_real = _best(remaining=74.0, display="74% P3", phase=3, overall=18.4, pulls=160)
    assert overall_confirms(p3_lead, p3_real) is True
    curr_real = _snap(echo_killed=FALLBACK_BOSSES[:7], echo_best=p3_real)
    tick = diff_snapshot(prev_p3, curr_real, BOSSES, GUILDS)
    assert tick.silent is False
    assert "P3" in (tick.message() or "")

    # hidden P4: new phase even if bestPercent has not dropped yet
    p4_open = _best(remaining=99.0, display="99% P4", phase=4, overall=18.85, pulls=161)
    assert is_new_best(p3_lead, p4_open) is True
    assert overall_confirms(p3_lead, p4_open) is True
    curr_p4 = _snap(echo_killed=FALLBACK_BOSSES[:7], echo_best=p4_open)
    tick = diff_snapshot(prev_p3, curr_p4, BOSSES, GUILDS)
    assert tick.silent is False
    p4_msg = tick.message() or ""
    assert "P4" in p4_msg
    assert "剩餘 99%" in p4_msg
    # same P4 current-pull dip still blocked
    p4_dip = _best(remaining=8.0, display="8% P4", phase=4, overall=18.85, pulls=162)
    assert overall_confirms(p4_open, p4_dip) is False
    tick = diff_snapshot(curr_p4, _snap(echo_killed=FALLBACK_BOSSES[:7], echo_best=p4_dip), BOSSES, GUILDS)
    assert tick.silent is True

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
    stored_hidden = coalesce_snapshot(s1, hid_snap)
    tick = diff_snapshot(stored_hidden, s1, BOSSES, GUILDS)
    assert tick.silent is True
    baseline = coalesce_best(hidden, a)
    assert baseline.kind == "numeric" and baseline.remaining == 76.03

    # kill line format
    from models import Boss

    k = KillEvent(ECHO, Boss("the-coiled-altar", "The Coiled Altar", 7), 7)
    line = format_kill(k)
    assert line == "Echo 擊殺 第7王 The Coiled Altar（7/8）"
    last = KillEvent(ECHO, Boss("ulatek", "Ula'tek", 8), 8, world_first=True)
    line = format_kill(last)
    assert line == "Echo 擊殺 尾王 Ula'tek（8/8） 世界首殺"
    last_p = KillEvent(ECHO, Boss("ulatek", "Ula'tek", 8), 8, world_first=True, pulls=92)
    assert format_kill(last_p) == (
        "Echo 擊殺 尾王 Ula'tek（8/8） 世界首殺\n嘗試次數 92"
    )
    last2 = KillEvent(LIQUID, Boss("ulatek", "Ula'tek", 8), 8, world_first=False)
    assert format_kill(last2) == "Liquid 擊殺 尾王 Ula'tek（8/8）"
    assert "世界首殺" not in format_kill(last2)
    last2_p = KillEvent(LIQUID, Boss("ulatek", "Ula'tek", 8), 8, world_first=False, pulls=84)
    assert format_kill(last2_p) == "Liquid 擊殺 尾王 Ula'tek（8/8）\n嘗試次數 84"

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
    assert tick.events_kills[0].pulls == 91
    wf_msg = tick.message()
    assert wf_msg and "嘗試次數 91" in wf_msg
    assert wf_msg.startswith("Echo 擊殺 尾王 Ula'tek（8/8） 世界首殺")
    live_pulls = _snap(echo_killed=FALLBACK_BOSSES, echo_best=None, world=False)
    live_pulls.guilds[ECHO.id] = GuildSnap(
        killed=tuple(s for s, _ in FALLBACK_BOSSES), best=None, pulls=120
    )
    tick = diff_snapshot(prev_clear, live_pulls, BOSSES, GUILDS)
    assert tick.events_kills[0].pulls == 120
    assert "嘗試次數 120" in (tick.message() or "")
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
    text = format_best(BestEvent(ECHO, _best()))
    assert text == (
        "!best\n"
        "Echo 《烈毒之淵》Mythic\n"
        "Ula'tek 剩餘 76.03%\n"
        "嘗試次數 91"
    )
    assert "拉" not in text
    assert "raider.io" not in text
    assert "[SILENT]" not in text

    assert should_send(None) is False
    assert should_send("[SILENT]") is False
    assert should_send("  [SILENT]  ") is False
    assert should_send("Echo 擊殺 尾王 Ula'tek（8/8）") is True

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
        twp = Path(td) / "tw-dest.json"
        set_dest("discord", "tw-chan", True, twp, feed="tw")
        assert load_dests(twp)["discord"] == ["tw-chan"]
        assert load_dests(p)["discord"] == ["111"]

    vashnik = [b for b in BOSSES if b.slug == "vashnik-the-malignant"][0]
    line = format_tw_kill(TwKillEvent("Fortune", vashnik, 4, 7))
    assert line == "台服 Fortune 擊殺 四王 Vashnik the Malignant（4/8）\n嘗試次數 7"
    last_b = [b for b in BOSSES if b.slug == "ulatek"][0]
    assert format_tw_kill(TwKillEvent("Fortune", last_b, 8, None)) == (
        "台服 Fortune 擊殺 尾王 Ula'tek（8/8）"
    )

    def _tw_g(gid, name, killed, pulls=None, first=None):
        return TwGuildSnap(
            id=gid,
            name=name,
            realm="暗影之月",
            killed=tuple(killed),
            pulls=pulls or {},
            first_defeated=first or {},
        )

    three = [s for s, _ in FALLBACK_BOSSES[:3]]
    four = [s for s, _ in FALLBACK_BOSSES[:4]]
    prev_tw = TwSnapshot(
        region_max=3,
        guilds={1: _tw_g(1, "Fortune", three, {"vashnik-the-malignant": 7})},
    )
    curr_tw = TwSnapshot(
        region_max=4,
        guilds={
            1: _tw_g(
                1,
                "Fortune",
                four,
                {"vashnik-the-malignant": 7},
                {"vashnik-the-malignant": "2026-08-31T12:00:00Z"},
            ),
            2: _tw_g(2, "月刃", [s for s, _ in FALLBACK_BOSSES[:2]]),
        },
    )
    tick = diff_tw(None, curr_tw, BOSSES)
    assert tick.silent is True
    tick = diff_tw(prev_tw, prev_tw, BOSSES)
    assert tick.silent is True
    tick = diff_tw(prev_tw, curr_tw, BOSSES)
    assert tick.silent is False
    assert len(tick.events) == 1
    assert tick.events[0].guild_name == "Fortune"
    assert tick.events[0].killed_count == 4
    assert tick.events[0].boss.slug == "vashnik-the-malignant"
    msg = tick.message()
    assert msg and msg.startswith("台服 Fortune 擊殺 四王")
    assert "嘗試次數 7" in msg
    assert "!best" not in msg

    still_3 = TwSnapshot(
        region_max=3,
        guilds={
            1: _tw_g(1, "Fortune", three),
            2: _tw_g(2, "月刃", three),
        },
    )
    tick = diff_tw(prev_tw, still_3, BOSSES)
    assert tick.silent is True

    new_guild_4 = TwSnapshot(
        region_max=4,
        guilds={9: _tw_g(9, "NewGuild", four, {four[-1]: 11})},
    )
    tick = diff_tw(prev_tw, new_guild_4, BOSSES)
    assert len(tick.events) == 1
    assert tick.events[0].killed_count == 4
    assert tick.events[0].guild_name == "NewGuild"

    stored_tw = coalesce_tw(prev_tw, still_3)
    assert stored_tw.region_max == 3
    stored_tw = coalesce_tw(prev_tw, curr_tw)
    assert stored_tw.region_max == 4

    parsed = guild_snap_from_ranking(
        {
            "guild": {"id": 35688, "name": "Fortune", "realm": {"altName": "暗影之月"}},
            "encountersDefeated": [
                {"slug": "nekzali-the-soulcoiler", "firstDefeated": "2026-08-26T15:00:45.000Z"},
            ],
            "encountersPulled": [{"slug": "nekzali-the-soulcoiler", "numPulls": 7}],
        }
    )
    assert parsed is not None and parsed.name == "Fortune" and parsed.killed == ("nekzali-the-soulcoiler",)
    assert tw_region_max(snapshot_from_rankings([])) == 0

    print("ALL_UNIT_TESTS_PASSED")


if __name__ == "__main__":
    main()
