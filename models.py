"""RWF snapshot types. Fingerprints never include timestamps."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

RAID_SLUG = "the-venomous-abyss"
RAID_NAME_ZH = "烈毒之淵"
DIFFICULTY = "mythic"
LAST_BOSS_SLUG = "ulatek"
TOTAL_BOSSES = 8

# Static order if /raiding/static-data is unavailable.
FALLBACK_BOSSES: tuple[tuple[str, str], ...] = (
    ("nekzali-the-soulcoiler", "Nek'zali the Soulcoiler"),
    ("entombed-sentinels", "Entombed Sentinels"),
    ("the-lost-explorers", "The Lost Explorers"),
    ("vashnik-the-malignant", "Vashnik the Malignant"),
    ("sszorak", "Sszorak"),
    ("the-twin-fangs", "The Twin Fangs"),
    ("the-coiled-altar", "The Coiled Altar"),
    ("ulatek", "Ula'tek"),
)


@dataclass(frozen=True)
class Guild:
    id: int
    name: str
    region: str
    realm: str

    @property
    def path(self) -> str:
        from urllib.parse import quote

        return f"/guilds/{self.region}/{self.realm}/{quote(self.name)}"

    @property
    def rio_url(self) -> str:
        return f"https://raider.io{self.path}"


GUILDS: tuple[Guild, ...] = (
    Guild(1047044, "Echo", "eu", "tarren-mill"),
    Guild(1712677, "Liquid", "us", "illidan"),
    Guild(316123, "Method", "eu", "twisting-nether"),
)
GUILD_BY_ID = {g.id: g for g in GUILDS}


@dataclass(frozen=True)
class Boss:
    slug: str
    name: str
    index: int  # 1-based


BestKind = Literal["numeric", "hidden", "none"]


@dataclass(frozen=True)
class BestProgress:
    boss_slug: str
    boss_name: str
    kind: BestKind
    display: str | None
    remaining: float | None
    phase: float | None
    pulls: int | None
    overall: float | None = None  # API bestPercent 0-100; guards current-pull dips
    phase_label: str | None = None  # P3 / I1 / P4 from API; intermissions are phase x.5

    @property
    def hidden(self) -> bool:
        return self.kind == "hidden"


@dataclass
class GuildSnap:
    killed: tuple[str, ...]
    best: BestProgress | None = None
    pulls: int | None = None  # ulatek pullCount after 8/8 (kill notice)


@dataclass
class Snapshot:
    guilds: dict[int, GuildSnap] = field(default_factory=dict)
    world_ulatek: bool = False


def boss_list(encounters: list[tuple[str, str]] | None = None) -> tuple[Boss, ...]:
    rows = encounters or list(FALLBACK_BOSSES)
    return tuple(Boss(slug=s, name=n, index=i) for i, (s, n) in enumerate(rows, start=1))


def boss_by_slug(bosses: tuple[Boss, ...], slug: str) -> Boss | None:
    slug = (slug or "").lower()
    for b in bosses:
        if b.slug.lower() == slug:
            return b
    return None
