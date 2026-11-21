"""Classic Era (Vanilla 1.15.x) strict schema and boundary enforcement for Jiny RAG."""

from __future__ import annotations

from dataclasses import dataclass, field
import math
import re
from typing import Any, Mapping, Sequence

CLASSIC_ERA_VERSION = "1.15.x"
CLASSIC_MAX_PLAYER_LEVEL = 60
CLASSIC_MAX_ITEM_LEVEL = 95
CLASSIC_MAX_ELITE_LEVEL = 62
CLASSIC_MAX_BOSS_LEVEL = 63

ERA_VERSION_RE = re.compile(r"^1\.15(?:\.(?:\d+|x))?$")
WOWHEAD_CLASSIC_URL_RE = re.compile(
    r"^https://(?:www\.|es\.|it\.|en\.)?wowhead\.com/classic/"
    r"(?:(?:es|it|en)/)?(quest|npc|item|zone|dungeon)=(\d+)(?:/[^\s?#]*)?(?:\?[^\s#]*)?(?:#[^\s]*)?$"
)
WOWHEAD_TOOLTIP_URL_RE = re.compile(
    r"^https://nether\.wowhead\.com/classic/tooltip/(quest|npc|item|zone)/(\d+)(?:\?[^\s#]*)?$"
)

VALID_ENTITY_TYPES = ("quest", "mob", "item", "dungeon")
VALID_FACTIONS = ("Alliance", "Horde", "Neutral", "Both")
VALID_ITEM_QUALITIES = ("Poor", "Common", "Uncommon", "Rare", "Epic", "Legendary")
VALID_BIND_TYPES = ("None", "BoP", "BoE", "BoU", "Quest")
VALID_MOB_CLASSIFICATIONS = (
    "Normal",
    "Elite",
    "Rare",
    "Rare Elite",
    "Boss",
    "Friendly NPC",
    "Quest Giver",
    "Trainer",
    "Vendor",
)
VALID_DUNGEON_CAPS = (5, 10, 20, 40)
VALID_ITEM_SOURCE_TYPES = (
    "mob",
    "boss",
    "quest",
    "vendor",
    "craft",
    "container",
    "world_drop",
)

CLASSIC_CLASSES = frozenset(
    {
        "Warrior",
        "Paladin",
        "Hunter",
        "Rogue",
        "Priest",
        "Shaman",
        "Mage",
        "Warlock",
        "Druid",
    }
)

CLASSIC_PROFESSIONS = frozenset(
    {
        "Alchemy",
        "Blacksmithing",
        "Enchanting",
        "Engineering",
        "Herbalism",
        "Leatherworking",
        "Mining",
        "Skinning",
        "Tailoring",
        "Cooking",
        "First Aid",
        "Fishing",
    }
)

CLASSIC_ZONES = frozenset(
    {
        # Continents / Broad Classic Regions
        "azeroth",
        "eastern kingdoms",
        "kalimdor",
        # Eastern Kingdoms
        "alterac mountains",
        "arathi highlands",
        "badlands",
        "blasted lands",
        "burning steppes",
        "deadwind pass",
        "dun morogh",
        "duskwood",
        "eastern plaguelands",
        "elwynn forest",
        "hillsbrad foothills",
        "ironforge",
        "loch modan",
        "redridge mountains",
        "searing gorge",
        "silverpine forest",
        "stormwind city",
        "stranglethorn vale",
        "swamp of sorrows",
        "the hinterlands",
        "tirisfal glades",
        "undercity",
        "western plaguelands",
        "westfall",
        "wetlands",
        "blackrock mountain",
        "deeprun tram",
        # Kalimdor
        "ashenvale",
        "azshara",
        "darkshore",
        "darnassus",
        "desolace",
        "durotar",
        "dustwallow marsh",
        "felwood",
        "feralas",
        "moonglade",
        "mulgore",
        "orgrimmar",
        "silithus",
        "stonetalon mountains",
        "tanaris",
        "teldrassil",
        "the barrens",
        "thousand needles",
        "thunder bluff",
        "un'goro crater",
        "winterspring",
        # Classic Battlegrounds
        "alterac valley",
        "arathi basin",
        "warsong gulch",
        # Classic Dungeon / Raid zone names
        "ragefire chasm",
        "wailing caverns",
        "the deadmines",
        "deadmines",
        "shadowfang keep",
        "blackfathom deeps",
        "the stockade",
        "stockade",
        "gnomeregan",
        "razorfen kraul",
        "scarlet monastery",
        "scarlet monastery graveyard",
        "scarlet monastery library",
        "scarlet monastery armory",
        "scarlet monastery cathedral",
        "razorfen downs",
        "uldaman",
        "zul'farrak",
        "maraudon",
        "the temple of atal'hakkar",
        "temple of atal'hakkar",
        "sunken temple",
        "blackrock depths",
        "blackrock spire",
        "lower blackrock spire",
        "upper blackrock spire",
        "dire maul",
        "dire maul east",
        "dire maul west",
        "dire maul north",
        "stratholme",
        "scholomance",
        "zul'gurub",
        "ruins of ahn'qiraj",
        "molten core",
        "onyxia's lair",
        "blackwing lair",
        "temple of ahn'qiraj",
        "ahn'qiraj",
        "naxxramas",
    }
)

CLASSIC_DUNGEON_ALIASES: dict[str, str] = {
    "sima ignea": "Ragefire Chasm",
    "baratro di fiamma": "Ragefire Chasm",
    "cuevas de los lamentos": "Wailing Caverns",
    "caverne dei lamenti": "Wailing Caverns",
    "minas de la muerte": "The Deadmines",
    "las minas de la muerte": "The Deadmines",
    "le miniere della morte": "The Deadmines",
    "miniere della morte": "The Deadmines",
    "castillo de colmillo oscuro": "Shadowfang Keep",
    "forte di zannascura": "Shadowfang Keep",
    "cavernas de brazanegra": "Blackfathom Deeps",
    "abissi di fondoscuro": "Blackfathom Deeps",
    "las mazmorras": "The Stockade",
    "segrete di roccavento": "The Stockade",
    "monasterio escarlata": "Scarlet Monastery",
    "monastero scarlatto": "Scarlet Monastery",
    "horado rajacieno": "Razorfen Kraul",
    "lamaspina": "Razorfen Kraul",
    "zahurda rajacieno": "Razorfen Downs",
    "sotterranei di lamaspina": "Razorfen Downs",
    "templo de atal'hakkar": "The Temple of Atal'Hakkar",
    "templo sumergido": "Sunken Temple",
    "tempio di atal'hakkar": "The Temple of Atal'Hakkar",
    "tempio sommerso": "Sunken Temple",
    "profundidades de roca negra": "Blackrock Depths",
    "sotterranei di roccianera": "Blackrock Depths",
    "profondita di roccianera": "Blackrock Depths",
    "profondità di roccianera": "Blackrock Depths",
    "cumbre de roca negra": "Blackrock Spire",
    "bastioni di roccianera": "Blackrock Spire",
    "cumbre de roca negra inferior": "Lower Blackrock Spire",
    "bastioni di roccianera inferiori": "Lower Blackrock Spire",
    "cumbre de roca negra superior": "Upper Blackrock Spire",
    "bastioni di roccianera superiori": "Upper Blackrock Spire",
    "la masacre": "Dire Maul",
    "maglio infausto": "Dire Maul",
    "guarida de onyxia": "Onyxia's Lair",
    "antro di onyxia": "Onyxia's Lair",
    "nucleo de magma": "Molten Core",
    "núcleo de magma": "Molten Core",
    "nucleo ardente": "Molten Core",
    "guarida alanegra": "Blackwing Lair",
    "fortezza dell'ala nera": "Blackwing Lair",
    "ruinas de ahn'qiraj": "Ruins of Ahn'Qiraj",
    "rovine di ahn'qiraj": "Ruins of Ahn'Qiraj",
    "templo de ahn'qiraj": "Temple of Ahn'Qiraj",
    "tempio di ahn'qiraj": "Temple of Ahn'Qiraj",
}

CLASSIC_DUNGEONS_WHITELIST = frozenset(
    {
        "ragefire chasm",
        "wailing caverns",
        "the deadmines",
        "deadmines",
        "shadowfang keep",
        "blackfathom deeps",
        "the stockade",
        "stockade",
        "gnomeregan",
        "razorfen kraul",
        "scarlet monastery",
        "scarlet monastery graveyard",
        "scarlet monastery library",
        "scarlet monastery armory",
        "scarlet monastery cathedral",
        "razorfen downs",
        "uldaman",
        "zul'farrak",
        "maraudon",
        "temple of atal'hakkar",
        "the temple of atal'hakkar",
        "sunken temple",
        "blackrock depths",
        "blackrock spire",
        "lower blackrock spire",
        "upper blackrock spire",
        "dire maul",
        "dire maul east",
        "dire maul west",
        "dire maul north",
        "stratholme",
        "scholomance",
        "zul'gurub",
        "ruins of ahn'qiraj",
        "molten core",
        "onyxia's lair",
        "blackwing lair",
        "temple of ahn'qiraj",
        "ahn'qiraj",
        "naxxramas",
    }
)

FORBIDDEN_CLASSES = frozenset(
    {
        "death knight",
        "deathknight",
        "monk",
        "demon hunter",
        "demonhunter",
        "evoker",
    }
)

FORBIDDEN_RACES = frozenset(
    {
        "blood elf",
        "draenei",
        "worgen",
        "goblin",
        "pandaren",
        "dracthyr",
    }
)

FORBIDDEN_PROFESSIONS = frozenset(
    {
        "jewelcrafting",
        "inscription",
        "archaeology",
    }
)

FORBIDDEN_EXPANSION_TAGS = frozenset(
    {
        "tbc",
        "bc",
        "burning crusade",
        "the burning crusade",
        "classic-tbc",
        "wotlk",
        "wrath",
        "wrath of the lich king",
        "cata",
        "cataclysm",
        "mop",
        "mop-classic",
        "pandaria",
        "mists of pandaria",
        "wod",
        "warlords",
        "warlords of draenor",
        "draenor",
        "legion",
        "bfa",
        "battle for azeroth",
        "shadowlands",
        "dragonflight",
        "tww",
        "war within",
        "the war within",
        "midnight",
        "retail",
        "sod",
        "season of discovery",
    }
)

FORBIDDEN_ZONES = frozenset(
    {
        "outland",
        "hellfire peninsula",
        "zangarmarsh",
        "terokkar forest",
        "nagrand",
        "blade's edge mountains",
        "netherstorm",
        "shadowmoon valley",
        "shattrath city",
        "shattrath",
        "isle of quel'danas",
        "eversong woods",
        "ghostlands",
        "azuremyst isle",
        "bloodmyst isle",
        "silvermoon city",
        "the exodar",
        "exodar",
        "northrend",
        "borean tundra",
        "howling fjord",
        "dragonblight",
        "grizzly hills",
        "zul'drak",
        "sholazar basin",
        "the storm peaks",
        "storm peaks",
        "icecrown",
        "dalaran",
        "wintergrasp",
        "crystalsong forest",
        "vashj'ir",
        "deepholm",
        "uldum",
        "twilight highlands",
        "tol barad",
        "gilneas",
        "kezan",
        "pandaria",
        "jade forest",
        "valley of the four winds",
        "kun-lai summit",
        "townlong steppes",
        "dread wastes",
        "vale of eternal blossoms",
        "broken isles",
        "kul tiras",
        "zandalar",
        "oribos",
        "dragon isles",
        "valdrakken",
        "khaz algar",
    }
)

FORBIDDEN_DUNGEONS = frozenset(
    {
        "hellfire citadel",
        "hellfire ramparts",
        "the blood furnace",
        "blood furnace",
        "the shattered halls",
        "shattered halls",
        "the slave pens",
        "slave pens",
        "the underbog",
        "underbog",
        "the steamvault",
        "steamvault",
        "mana-tombs",
        "auchenai crypts",
        "sethekk halls",
        "shadow labyrinth",
        "karazhan",
        "gruul's lair",
        "magtheridon's lair",
        "serpentshrine cavern",
        "tempest keep",
        "hyjal summit",
        "black temple",
        "sunwell plateau",
        "zul'aman",
        "magisters' terrace",
        "utgarde keep",
        "the nexus",
        "azjol-nerub",
        "ahn'kahet",
        "drak'tharon keep",
        "the violet hold",
        "gundrak",
        "halls of stone",
        "halls of lightning",
        "the oculus",
        "ulduar",
        "trial of the crusader",
        "icecrown citadel",
        "the ruby sanctum",
    }
)

_FORBIDDEN_NON_CLASSIC_RACES = frozenset(
    race for race in FORBIDDEN_RACES if race != "goblin"
) | frozenset({"goblin race", "play as goblin", "playable goblin", "bilgewater"})

_NON_CLASSIC_CLASS_PHRASES = frozenset(
    cls_name for cls_name in FORBIDDEN_CLASSES if cls_name != "monk"
) | frozenset({"monk class", "mistweaver", "windwalker", "brewmaster", "play as monk"})

_EXTRA_EXPANSION_RAIDS_ZONES = frozenset(
    {
        "firelands",
        "sunwell",
        "val'sharah",
        "bastion",
        "suramar",
        "argus",
        "revendreth",
        "maldraxxus",
        "ardenweald",
        "zereth mortis",
        "dragon soul",
        "throne of thunder",
        "siege of orgrimmar",
        "blackrock foundry",
        "emerald nightmare",
        "nighthold",
        "antorus",
        "ny'alotha",
        "castle nathria",
    }
)

_NON_CLASSIC_QUERY_PHRASES = tuple(
    sorted(
        FORBIDDEN_ZONES
        | FORBIDDEN_DUNGEONS
        | _NON_CLASSIC_CLASS_PHRASES
        | _FORBIDDEN_NON_CLASSIC_RACES
        | FORBIDDEN_PROFESSIONS
        | FORBIDDEN_EXPANSION_TAGS
        | _EXTRA_EXPANSION_RAIDS_ZONES,
        key=len,
        reverse=True,
    )
)

_NON_CLASSIC_URL_MARKERS = ("/tbc/", "/wotlk/", "/cata/", "/mop-classic/", "/classic-tbc/", "/retail/")
_POST_60_LEVEL_RE = re.compile(
    r"(?<![a-z0-9])(?:level|lvl|nivel|livello)\s+(?:6[1-9]|[7-9]\d|1\d\d)(?![a-z0-9])"
)
_DALARAN_CLASSIC_RE = re.compile(r"(?<![a-z0-9])dalaran\s+(?:crater|wizards?)(?![a-z0-9])")


class ClassicScopeError(ValueError):
    """Raised when a record, URL, or payload violates WoW Classic Era (1.15.x) boundaries."""


def _norm(value: str) -> str:
    return re.sub(r"\s+", " ", (value or "").strip().lower())


def detect_non_classic_terms(text: str | None) -> list[str]:
    """Return non-Classic (TBC/WotLK/Cata/MoP/Retail/SoD) markers found in text."""
    raw = (text or "").strip()
    if not raw:
        return []
    lower = _norm(raw)
    dalaran_masked = _DALARAN_CLASSIC_RE.sub(" ", lower)
    found: list[str] = []
    for marker in _NON_CLASSIC_URL_MARKERS:
        if marker in lower and marker not in found:
            found.append(marker)
    for phrase in _NON_CLASSIC_QUERY_PHRASES:
        haystack = dalaran_masked if phrase == "dalaran" else lower
        pattern = r"(?<![a-z0-9])" + re.escape(phrase) + r"(?![a-z0-9])"
        if re.search(pattern, haystack) and phrase not in found:
            found.append(phrase)
    for m in _POST_60_LEVEL_RE.finditer(lower):
        prefix = lower[max(0, m.start() - 8) : m.start()]
        if prefix.endswith("item "):
            continue
        suffix = lower[m.end() : m.end() + 16]
        lvl_num = int(re.search(r"\d+", m.group(0)).group(0))  # type: ignore[union-attr]
        if lvl_num <= CLASSIC_MAX_BOSS_LEVEL and re.match(
            r"\s+(?:raid\s+|world\s+)?(?:boss|elite)\b", suffix
        ):
            continue
        term = m.group(0)
        if term not in found:
            found.append(term)
    return found


def is_non_classic_query(text: str | None) -> bool:
    """Return True if the text references expansions/features outside Classic Era 1.15.x."""
    return bool(detect_non_classic_terms(text))


def is_classic_era_allowed(era_version: str | None) -> bool:
    """Return True iff era_version matches Classic Era 1.15.x."""
    return bool(ERA_VERSION_RE.match((era_version or "").strip()))


def validate_era_version(era_version: str | None) -> str:
    """Enforce Classic Era 1.15.x version string."""
    candidate = (era_version or "").strip()
    if not ERA_VERSION_RE.match(candidate):
        raise ClassicScopeError(
            f"Unsupported era_version '{era_version}'; only Classic Era '{CLASSIC_ERA_VERSION}' is permitted."
        )
    return CLASSIC_ERA_VERSION


def validate_source_url(url: str | None) -> str:
    """Enforce HTTPS wowhead.com/classic URLs or local seed:// / empty sources."""
    candidate = (url or "").strip()
    if not candidate or candidate.startswith("seed://"):
        return candidate
    lower = candidate.lower()
    for forbidden in _NON_CLASSIC_URL_MARKERS:
        if forbidden in lower:
            raise ClassicScopeError(
                f"Non-Classic Wowhead URL rejected ({forbidden}): '{candidate}'."
            )
    m_main = WOWHEAD_CLASSIC_URL_RE.match(candidate)
    if m_main:
        if int(m_main.group(2)) <= 0:
            raise ClassicScopeError(f"Invalid source_url '{candidate}'; entity ID must be > 0.")
        return candidate
    m_tip = WOWHEAD_TOOLTIP_URL_RE.match(candidate)
    if m_tip:
        if int(m_tip.group(2)) <= 0:
            raise ClassicScopeError(f"Invalid source_url '{candidate}'; entity ID must be > 0.")
        return candidate
    raise ClassicScopeError(
        f"Invalid source_url '{candidate}'; external URLs must be HTTPS wowhead.com/classic/... links."
    )


def _is_finite_number(value: Any) -> bool:
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(float(value))
    )


def validate_coords(
    x: float | None,
    y: float | None,
    label: str = "coords",
) -> tuple[float | None, float | None]:
    """Validate paired map coordinates in [0.0, 100.0] or both None."""
    if x is None and y is None:
        return None, None
    if (x is None) != (y is None):
        raise ClassicScopeError(f"{label} must specify both x and y or neither (got x={x!r}, y={y!r}).")
    if not _is_finite_number(x) or not _is_finite_number(y):
        raise ClassicScopeError(f"{label} must be finite numbers in [0.0, 100.0] (got x={x!r}, y={y!r}).")
    fx = round(float(x), 2)
    fy = round(float(y), 2)
    if not (0.0 <= fx <= 100.0 and 0.0 <= fy <= 100.0):
        raise ClassicScopeError(f"{label} out of [0.0, 100.0] range: ({fx}, {fy}).")
    return fx, fy


def validate_drop_rate(rate: float | None) -> float | None:
    """Validate optional drop rate percentage in [0.0, 100.0]."""
    if rate is None:
        return None
    if not _is_finite_number(rate):
        raise ClassicScopeError(f"drop_rate must be a finite number or None (got {rate!r}).")
    fr = round(float(rate), 2)
    if not (0.0 <= fr <= 100.0):
        raise ClassicScopeError(f"drop_rate out of [0.0, 100.0] range: {fr}.")
    return fr


def validate_level(
    level: int | None,
    *,
    min_val: int = 0,
    max_val: int = CLASSIC_MAX_PLAYER_LEVEL,
    field_name: str = "level",
) -> int | None:
    """Validate integer level within Classic Era bounds."""
    if level is None:
        return None
    if isinstance(level, bool) or not isinstance(level, int):
        raise ClassicScopeError(f"{field_name} must be an integer (got {level!r}).")
    if not (min_val <= level <= max_val):
        raise ClassicScopeError(
            f"{field_name}={level} violates Classic Era bounds [{min_val}, {max_val}]."
        )
    return level


def _reject_forbidden_name(value: str, field_name: str) -> None:
    lower = _norm(value)
    if not lower:
        return
    if lower in FORBIDDEN_ZONES:
        raise ClassicScopeError(f"{field_name} '{value}' belongs to a non-Classic zone.")
    if lower in FORBIDDEN_DUNGEONS:
        raise ClassicScopeError(f"{field_name} '{value}' belongs to a non-Classic dungeon/raid.")
    if lower in FORBIDDEN_CLASSES:
        raise ClassicScopeError(f"{field_name} '{value}' references a non-Classic class.")
    if lower in _FORBIDDEN_NON_CLASSIC_RACES:
        raise ClassicScopeError(f"{field_name} '{value}' references a non-Classic race.")
    if lower in FORBIDDEN_PROFESSIONS:
        raise ClassicScopeError(f"{field_name} '{value}' references a non-Classic profession.")
    if lower in FORBIDDEN_EXPANSION_TAGS:
        raise ClassicScopeError(f"{field_name} '{value}' references a non-Classic expansion.")
    for forbidden_zone in FORBIDDEN_ZONES:
        if re.search(r"(?<![a-z0-9])" + re.escape(forbidden_zone) + r"(?![a-z0-9])", lower):
            raise ClassicScopeError(f"{field_name} '{value}' references non-Classic zone '{forbidden_zone}'.")
    for forbidden_dungeon in FORBIDDEN_DUNGEONS:
        if re.search(r"(?<![a-z0-9])" + re.escape(forbidden_dungeon) + r"(?![a-z0-9])", lower):
            raise ClassicScopeError(f"{field_name} '{value}' references non-Classic dungeon '{forbidden_dungeon}'.")
    for forbidden_race in _FORBIDDEN_NON_CLASSIC_RACES:
        if re.search(r"(?<![a-z0-9])" + re.escape(forbidden_race) + r"(?![a-z0-9])", lower):
            raise ClassicScopeError(f"{field_name} '{value}' references non-Classic race '{forbidden_race}'.")
    for forbidden_prof in FORBIDDEN_PROFESSIONS:
        if re.search(r"(?<![a-z0-9])" + re.escape(forbidden_prof) + r"(?![a-z0-9])", lower):
            raise ClassicScopeError(f"{field_name} '{value}' references non-Classic profession '{forbidden_prof}'.")
    for forbidden_exp in FORBIDDEN_EXPANSION_TAGS:
        if re.search(r"(?<![a-z0-9])" + re.escape(forbidden_exp) + r"(?![a-z0-9])", lower):
            raise ClassicScopeError(f"{field_name} '{value}' references non-Classic expansion '{forbidden_exp}'.")


def validate_zone(zone: str, allow_empty: bool = False) -> str:
    """Enforce Classic Era 1.15.x zone whitelist (Kalimdor, Eastern Kingdoms, Classic instances)."""
    cleaned = (zone or "").strip()
    if not cleaned:
        if allow_empty:
            return ""
        raise ClassicScopeError("zone cannot be empty.")
    _reject_forbidden_name(cleaned, "zone")
    lower = _norm(cleaned)
    if lower not in CLASSIC_ZONES and lower not in CLASSIC_DUNGEON_ALIASES:
        raise ClassicScopeError(
            f"Zone '{cleaned}' is not in the Classic Era 1.15.x zone/instance whitelist."
        )
    return cleaned


def validate_tags(tags: Sequence[str]) -> list[str]:
    """Reject expansion/non-Classic tags."""
    result: list[str] = []
    for raw in tags:
        tag = str(raw).strip()
        if not tag:
            continue
        lower = _norm(tag)
        if (
            lower in FORBIDDEN_EXPANSION_TAGS
            or lower in FORBIDDEN_CLASSES
            or lower in FORBIDDEN_PROFESSIONS
            or lower in _FORBIDDEN_NON_CLASSIC_RACES
        ):
            raise ClassicScopeError(f"Non-Classic tag '{tag}' is forbidden in Classic Era 1.15.x.")
        _reject_forbidden_name(tag, "tag")
        result.append(tag)
    return result


def validate_classes(classes: Sequence[str]) -> list[str]:
    """Enforce the 9 Classic Era playable classes only."""
    result: list[str] = []
    for raw in classes:
        cls_name = str(raw).strip()
        if not cls_name:
            continue
        lower = _norm(cls_name)
        if lower in FORBIDDEN_CLASSES:
            raise ClassicScopeError(f"Class '{cls_name}' does not exist in Classic Era 1.15.x.")
        matched = next((c for c in CLASSIC_CLASSES if c.lower() == lower), None)
        if matched is None:
            raise ClassicScopeError(f"Unknown or non-Classic class '{cls_name}'.")
        result.append(matched)
    return result


def _validate_positive_id(value: Any, field_name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ClassicScopeError(f"{field_name} must be a positive integer (got {value!r}).")
    return value


def _validate_faction(faction: str) -> str:
    cleaned = (faction or "").strip()
    if cleaned not in VALID_FACTIONS:
        raise ClassicScopeError(f"Invalid faction '{faction}'; expected one of {VALID_FACTIONS}.")
    return cleaned


def _coerce_coords_pair(data: Mapping[str, Any], x_key: str = "x", y_key: str = "y", pair_key: str = "coords") -> tuple[float | None, float | None]:
    if x_key in data or y_key in data:
        return data.get(x_key), data.get(y_key)
    pair = data.get(pair_key)
    if pair is None:
        return None, None
    if isinstance(pair, (list, tuple)) and len(pair) == 2:
        return pair[0], pair[1]
    raise ClassicScopeError(f"{pair_key} must be a [x, y] pair or null (got {pair!r}).")


@dataclass
class QuestNpcRef:
    name: str
    npc_id: int | None = None
    zone: str = ""
    x: float | None = None
    y: float | None = None

    def __post_init__(self) -> None:
        self.name = (self.name or "").strip()
        if not self.name:
            raise ClassicScopeError("QuestNpcRef.name cannot be empty.")
        if self.npc_id is not None:
            self.npc_id = _validate_positive_id(self.npc_id, "QuestNpcRef.npc_id")
        self.zone = validate_zone(self.zone, allow_empty=True)
        self.x, self.y = validate_coords(self.x, self.y, label="QuestNpcRef.coords")

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "npc_id": self.npc_id,
            "zone": self.zone,
            "x": self.x,
            "y": self.y,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> QuestNpcRef:
        x, y = _coerce_coords_pair(data)
        return cls(
            name=str(data.get("name", "")),
            npc_id=data.get("npc_id"),
            zone=str(data.get("zone", "")),
            x=x,
            y=y,
        )


@dataclass
class QuestReward:
    item_name: str
    item_id: int | None = None
    quantity: int = 1
    choice: bool = False

    def __post_init__(self) -> None:
        self.item_name = (self.item_name or "").strip()
        if not self.item_name:
            raise ClassicScopeError("QuestReward.item_name cannot be empty.")
        if self.item_id is not None:
            self.item_id = _validate_positive_id(self.item_id, "QuestReward.item_id")
        if isinstance(self.quantity, bool) or not isinstance(self.quantity, int) or self.quantity < 1:
            raise ClassicScopeError(f"QuestReward.quantity must be >= 1 (got {self.quantity!r}).")
        self.choice = bool(self.choice)

    def to_dict(self) -> dict[str, Any]:
        return {
            "item_name": self.item_name,
            "item_id": self.item_id,
            "quantity": self.quantity,
            "choice": self.choice,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> QuestReward:
        return cls(
            item_name=str(data.get("item_name", "")),
            item_id=data.get("item_id"),
            quantity=data.get("quantity", 1),
            choice=bool(data.get("choice", False)),
        )


@dataclass
class MobDrop:
    item_name: str
    item_id: int | None = None
    drop_rate: float | None = None
    notes: str = ""

    def __post_init__(self) -> None:
        self.item_name = (self.item_name or "").strip()
        if not self.item_name:
            raise ClassicScopeError("MobDrop.item_name cannot be empty.")
        if self.item_id is not None:
            self.item_id = _validate_positive_id(self.item_id, "MobDrop.item_id")
        self.drop_rate = validate_drop_rate(self.drop_rate)
        self.notes = (self.notes or "").strip()

    def to_dict(self) -> dict[str, Any]:
        return {
            "item_name": self.item_name,
            "item_id": self.item_id,
            "drop_rate": self.drop_rate,
            "notes": self.notes,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> MobDrop:
        return cls(
            item_name=str(data.get("item_name", "")),
            item_id=data.get("item_id"),
            drop_rate=data.get("drop_rate"),
            notes=str(data.get("notes", "")),
        )


@dataclass
class ItemSource:
    source_type: str
    source_name: str
    source_id: int | None = None
    zone: str = ""
    x: float | None = None
    y: float | None = None
    drop_rate: float | None = None
    notes: str = ""

    def __post_init__(self) -> None:
        self.source_type = (self.source_type or "").strip().lower()
        if self.source_type not in VALID_ITEM_SOURCE_TYPES:
            raise ClassicScopeError(
                f"Invalid ItemSource.source_type '{self.source_type}'; expected {VALID_ITEM_SOURCE_TYPES}."
            )
        self.source_name = (self.source_name or "").strip()
        if not self.source_name:
            raise ClassicScopeError("ItemSource.source_name cannot be empty.")
        _reject_forbidden_name(self.source_name, "ItemSource.source_name")
        if self.source_id is not None:
            self.source_id = _validate_positive_id(self.source_id, "ItemSource.source_id")
        self.zone = validate_zone(self.zone, allow_empty=True)
        self.x, self.y = validate_coords(self.x, self.y, label="ItemSource.coords")
        self.drop_rate = validate_drop_rate(self.drop_rate)
        self.notes = (self.notes or "").strip()

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_type": self.source_type,
            "source_name": self.source_name,
            "source_id": self.source_id,
            "zone": self.zone,
            "x": self.x,
            "y": self.y,
            "drop_rate": self.drop_rate,
            "notes": self.notes,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> ItemSource:
        x, y = _coerce_coords_pair(data)
        return cls(
            source_type=str(data.get("source_type", "")),
            source_name=str(data.get("source_name", "")),
            source_id=data.get("source_id"),
            zone=str(data.get("zone", "")),
            x=x,
            y=y,
            drop_rate=data.get("drop_rate"),
            notes=str(data.get("notes", "")),
        )


@dataclass
class QuestRecord:
    quest_id: int
    name: str
    zone: str
    faction: str = "Neutral"
    quest_level: int = 1
    min_level: int = 1
    x: float | None = None
    y: float | None = None
    giver: QuestNpcRef | None = None
    turnin: QuestNpcRef | None = None
    objectives: list[str] = field(default_factory=list)
    rewards: list[QuestReward] = field(default_factory=list)
    reward_xp: int = 0
    reward_copper: int = 0
    prerequisite_quest_ids: list[int] = field(default_factory=list)
    followup_quest_ids: list[int] = field(default_factory=list)
    class_restriction: list[str] = field(default_factory=list)
    is_dungeon: bool = False
    dungeon_name: str = ""
    aliases: list[str] = field(default_factory=list)
    summary: str = ""
    tags: list[str] = field(default_factory=list)
    era_version: str = CLASSIC_ERA_VERSION
    source_url: str = ""

    @property
    def entity_type(self) -> str:
        return "quest"

    def __post_init__(self) -> None:
        self.validate()

    def validate(self) -> None:
        self.quest_id = _validate_positive_id(self.quest_id, "quest_id")
        self.name = (self.name or "").strip()
        if not self.name:
            raise ClassicScopeError("QuestRecord.name cannot be empty.")
        _reject_forbidden_name(self.name, "QuestRecord.name")
        self.zone = validate_zone(self.zone)
        self.faction = _validate_faction(self.faction)
        self.quest_level = int(
            validate_level(self.quest_level, min_val=1, max_val=CLASSIC_MAX_PLAYER_LEVEL, field_name="quest_level")
        )
        self.min_level = int(
            validate_level(self.min_level, min_val=1, max_val=CLASSIC_MAX_PLAYER_LEVEL, field_name="min_level")
        )
        if self.min_level > self.quest_level:
            raise ClassicScopeError(
                f"Quest min_level ({self.min_level}) cannot exceed quest_level ({self.quest_level})."
            )
        self.x, self.y = validate_coords(self.x, self.y, label="QuestRecord.coords")
        if self.giver is not None and not isinstance(self.giver, QuestNpcRef):
            self.giver = QuestNpcRef.from_dict(self.giver)
        if self.turnin is not None and not isinstance(self.turnin, QuestNpcRef):
            self.turnin = QuestNpcRef.from_dict(self.turnin)
        self.objectives = [str(o).strip() for o in self.objectives if str(o).strip()]
        self.rewards = [
            r if isinstance(r, QuestReward) else QuestReward.from_dict(r)
            for r in self.rewards
        ]
        if isinstance(self.reward_xp, bool) or not isinstance(self.reward_xp, int) or self.reward_xp < 0:
            raise ClassicScopeError(f"reward_xp must be >= 0 (got {self.reward_xp!r}).")
        if isinstance(self.reward_copper, bool) or not isinstance(self.reward_copper, int) or self.reward_copper < 0:
            raise ClassicScopeError(f"reward_copper must be >= 0 (got {self.reward_copper!r}).")
        self.prerequisite_quest_ids = [
            _validate_positive_id(qid, "prerequisite_quest_ids[]") for qid in self.prerequisite_quest_ids
        ]
        self.followup_quest_ids = [
            _validate_positive_id(qid, "followup_quest_ids[]") for qid in self.followup_quest_ids
        ]
        self.class_restriction = validate_classes(self.class_restriction)
        self.is_dungeon = bool(self.is_dungeon)
        self.dungeon_name = (self.dungeon_name or "").strip()
        if self.dungeon_name:
            _reject_forbidden_name(self.dungeon_name, "QuestRecord.dungeon_name")
        self.aliases = [str(a).strip() for a in self.aliases if str(a).strip()]
        self.summary = (self.summary or "").strip()
        self.tags = validate_tags(self.tags)
        self.era_version = validate_era_version(self.era_version)
        self.source_url = validate_source_url(self.source_url)

    def to_dict(self) -> dict[str, Any]:
        return {
            "quest_id": self.quest_id,
            "name": self.name,
            "zone": self.zone,
            "faction": self.faction,
            "quest_level": self.quest_level,
            "min_level": self.min_level,
            "x": self.x,
            "y": self.y,
            "giver": self.giver.to_dict() if self.giver is not None else None,
            "turnin": self.turnin.to_dict() if self.turnin is not None else None,
            "objectives": list(self.objectives),
            "rewards": [r.to_dict() for r in self.rewards],
            "reward_xp": self.reward_xp,
            "reward_copper": self.reward_copper,
            "prerequisite_quest_ids": list(self.prerequisite_quest_ids),
            "followup_quest_ids": list(self.followup_quest_ids),
            "class_restriction": list(self.class_restriction),
            "is_dungeon": self.is_dungeon,
            "dungeon_name": self.dungeon_name,
            "aliases": list(self.aliases),
            "summary": self.summary,
            "tags": list(self.tags),
            "era_version": self.era_version,
            "source_url": self.source_url,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> QuestRecord:
        x, y = _coerce_coords_pair(data)
        giver_raw = data.get("giver")
        turnin_raw = data.get("turnin")
        return cls(
            quest_id=data["quest_id"],
            name=str(data.get("name") or data.get("title") or ""),
            zone=str(data.get("zone", "")),
            faction=str(data.get("faction", "Neutral")),
            quest_level=data.get("quest_level", 1),
            min_level=data.get("min_level", 1),
            x=x,
            y=y,
            giver=QuestNpcRef.from_dict(giver_raw) if isinstance(giver_raw, Mapping) else giver_raw,
            turnin=QuestNpcRef.from_dict(turnin_raw) if isinstance(turnin_raw, Mapping) else turnin_raw,
            objectives=list(data.get("objectives", [])),
            rewards=list(data.get("rewards", [])),
            reward_xp=data.get("reward_xp", 0),
            reward_copper=data.get("reward_copper", 0),
            prerequisite_quest_ids=list(data.get("prerequisite_quest_ids", [])),
            followup_quest_ids=list(data.get("followup_quest_ids", [])),
            class_restriction=list(data.get("class_restriction", [])),
            is_dungeon=bool(data.get("is_dungeon", False)),
            dungeon_name=str(data.get("dungeon_name", "")),
            aliases=list(data.get("aliases", [])),
            summary=str(data.get("summary") or data.get("notes") or ""),
            tags=list(data.get("tags", [])),
            era_version=str(data.get("era_version", CLASSIC_ERA_VERSION)),
            source_url=str(data.get("source_url", "")),
        )


@dataclass
class MobRecord:
    npc_id: int
    name: str
    zone: str
    mob_type: str = "Humanoid"
    classification: str = "Normal"
    level_min: int = 1
    level_max: int = 1
    faction: str = "Neutral"
    x: float | None = None
    y: float | None = None
    subzone: str = ""
    dungeon_id: int | None = None
    dungeon_name: str = ""
    drops: list[MobDrop] = field(default_factory=list)
    is_quest_giver: bool = False
    aliases: list[str] = field(default_factory=list)
    summary: str = ""
    tags: list[str] = field(default_factory=list)
    era_version: str = CLASSIC_ERA_VERSION
    source_url: str = ""

    @property
    def entity_type(self) -> str:
        return "mob"

    def __post_init__(self) -> None:
        self.validate()

    def validate(self) -> None:
        self.npc_id = _validate_positive_id(self.npc_id, "npc_id")
        self.name = (self.name or "").strip()
        if not self.name:
            raise ClassicScopeError("MobRecord.name cannot be empty.")
        _reject_forbidden_name(self.name, "MobRecord.name")
        self.zone = validate_zone(self.zone)
        self.mob_type = (self.mob_type or "").strip() or "Humanoid"
        self.classification = (self.classification or "").strip()
        if self.classification not in VALID_MOB_CLASSIFICATIONS:
            raise ClassicScopeError(
                f"Invalid classification '{self.classification}'; expected {VALID_MOB_CLASSIFICATIONS}."
            )
        if self.classification == "Boss":
            max_allowed = CLASSIC_MAX_BOSS_LEVEL
        elif self.classification in {"Elite", "Rare Elite"}:
            max_allowed = CLASSIC_MAX_ELITE_LEVEL
        else:
            max_allowed = CLASSIC_MAX_PLAYER_LEVEL

        self.level_min = int(
            validate_level(self.level_min, min_val=1, max_val=max_allowed, field_name="level_min")
        )
        self.level_max = int(
            validate_level(self.level_max, min_val=1, max_val=max_allowed, field_name="level_max")
        )
        if self.level_min > self.level_max:
            raise ClassicScopeError(
                f"Mob level_min ({self.level_min}) cannot exceed level_max ({self.level_max})."
            )
        self.faction = _validate_faction(self.faction)
        self.x, self.y = validate_coords(self.x, self.y, label="MobRecord.coords")
        self.subzone = (self.subzone or "").strip()
        if self.subzone:
            _reject_forbidden_name(self.subzone, "subzone")
        if self.dungeon_id is not None:
            self.dungeon_id = _validate_positive_id(self.dungeon_id, "MobRecord.dungeon_id")
        self.dungeon_name = (self.dungeon_name or "").strip()
        if self.dungeon_name:
            _reject_forbidden_name(self.dungeon_name, "MobRecord.dungeon_name")
        self.drops = [
            d if isinstance(d, MobDrop) else MobDrop.from_dict(d)
            for d in self.drops
        ]
        self.is_quest_giver = bool(self.is_quest_giver)
        self.aliases = [str(a).strip() for a in self.aliases if str(a).strip()]
        self.summary = (self.summary or "").strip()
        self.tags = validate_tags(self.tags)
        self.era_version = validate_era_version(self.era_version)
        self.source_url = validate_source_url(self.source_url)

    def to_dict(self) -> dict[str, Any]:
        return {
            "npc_id": self.npc_id,
            "name": self.name,
            "zone": self.zone,
            "mob_type": self.mob_type,
            "classification": self.classification,
            "level_min": self.level_min,
            "level_max": self.level_max,
            "faction": self.faction,
            "x": self.x,
            "y": self.y,
            "subzone": self.subzone,
            "dungeon_id": self.dungeon_id,
            "dungeon_name": self.dungeon_name,
            "drops": [d.to_dict() for d in self.drops],
            "is_quest_giver": self.is_quest_giver,
            "aliases": list(self.aliases),
            "summary": self.summary,
            "tags": list(self.tags),
            "era_version": self.era_version,
            "source_url": self.source_url,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> MobRecord:
        x, y = _coerce_coords_pair(data)
        return cls(
            npc_id=data["npc_id"],
            name=str(data.get("name", "")),
            zone=str(data.get("zone", "")),
            mob_type=str(data.get("mob_type") or data.get("npc_type") or "Humanoid"),
            classification=str(data.get("classification", "Normal")),
            level_min=data.get("level_min", data.get("min_level", 1)),
            level_max=data.get("level_max", data.get("max_level", 1)),
            faction=str(data.get("faction", "Neutral")),
            x=x,
            y=y,
            subzone=str(data.get("subzone", "")),
            dungeon_id=data.get("dungeon_id"),
            dungeon_name=str(data.get("dungeon_name", "")),
            drops=list(data.get("drops", [])),
            is_quest_giver=bool(data.get("is_quest_giver", False)),
            aliases=list(data.get("aliases", [])),
            summary=str(data.get("summary") or data.get("notes") or ""),
            tags=list(data.get("tags", [])),
            era_version=str(data.get("era_version", CLASSIC_ERA_VERSION)),
            source_url=str(data.get("source_url", "")),
        )


@dataclass
class ItemRecord:
    item_id: int
    name: str
    quality: str = "Common"
    item_level: int = 1
    req_level: int = 0
    item_type: str = "Miscellaneous"
    slot: str = ""
    bind_type: str = "None"
    zone: str = ""
    sources: list[ItemSource] = field(default_factory=list)
    stats: dict[str, str | int | float] = field(default_factory=dict)
    class_restriction: list[str] = field(default_factory=list)
    quest_use: str = ""
    aliases: list[str] = field(default_factory=list)
    summary: str = ""
    tags: list[str] = field(default_factory=list)
    era_version: str = CLASSIC_ERA_VERSION
    source_url: str = ""

    @property
    def entity_type(self) -> str:
        return "item"

    def __post_init__(self) -> None:
        self.validate()

    def validate(self) -> None:
        self.item_id = _validate_positive_id(self.item_id, "item_id")
        self.name = (self.name or "").strip()
        if not self.name:
            raise ClassicScopeError("ItemRecord.name cannot be empty.")
        _reject_forbidden_name(self.name, "ItemRecord.name")
        self.quality = (self.quality or "").strip()
        if self.quality not in VALID_ITEM_QUALITIES:
            raise ClassicScopeError(
                f"Invalid item quality '{self.quality}'; expected {VALID_ITEM_QUALITIES}."
            )
        self.item_level = int(
            validate_level(self.item_level, min_val=1, max_val=CLASSIC_MAX_ITEM_LEVEL, field_name="item_level")
        )
        self.req_level = int(
            validate_level(self.req_level, min_val=0, max_val=CLASSIC_MAX_PLAYER_LEVEL, field_name="req_level")
        )
        self.item_type = (self.item_type or "").strip() or "Miscellaneous"
        self.slot = (self.slot or "").strip()
        self.bind_type = (self.bind_type or "").strip() or "None"
        if self.bind_type not in VALID_BIND_TYPES:
            raise ClassicScopeError(
                f"Invalid bind_type '{self.bind_type}'; expected {VALID_BIND_TYPES}."
            )
        self.zone = validate_zone(self.zone, allow_empty=True)
        self.sources = [
            s if isinstance(s, ItemSource) else ItemSource.from_dict(s)
            for s in self.sources
        ]
        cleaned_stats: dict[str, str | int | float] = {}
        for k, v in self.stats.items():
            key = str(k).strip()
            if not key:
                continue
            if not isinstance(v, (str, int, float)) or isinstance(v, bool):
                raise ClassicScopeError(f"ItemRecord.stats['{key}'] must be str, int, or float.")
            cleaned_stats[key] = v
        self.stats = cleaned_stats
        self.class_restriction = validate_classes(self.class_restriction)
        self.quest_use = (self.quest_use or "").strip()
        if self.quest_use:
            _reject_forbidden_name(self.quest_use, "ItemRecord.quest_use")
        self.aliases = [str(a).strip() for a in self.aliases if str(a).strip()]
        self.summary = (self.summary or "").strip()
        self.tags = validate_tags(self.tags)
        self.era_version = validate_era_version(self.era_version)
        self.source_url = validate_source_url(self.source_url)

    def to_dict(self) -> dict[str, Any]:
        return {
            "item_id": self.item_id,
            "name": self.name,
            "quality": self.quality,
            "item_level": self.item_level,
            "req_level": self.req_level,
            "item_type": self.item_type,
            "slot": self.slot,
            "bind_type": self.bind_type,
            "zone": self.zone,
            "sources": [s.to_dict() for s in self.sources],
            "stats": dict(self.stats),
            "class_restriction": list(self.class_restriction),
            "quest_use": self.quest_use,
            "aliases": list(self.aliases),
            "summary": self.summary,
            "tags": list(self.tags),
            "era_version": self.era_version,
            "source_url": self.source_url,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> ItemRecord:
        return cls(
            item_id=data["item_id"],
            name=str(data.get("name", "")),
            quality=str(data.get("quality", "Common")),
            item_level=data.get("item_level", 1),
            req_level=data.get("req_level", 0),
            item_type=str(data.get("item_type", "Miscellaneous")),
            slot=str(data.get("slot", "")),
            bind_type=str(data.get("bind_type", "None")),
            zone=str(data.get("zone", "")),
            sources=list(data.get("sources", [])),
            stats=dict(data.get("stats", {})),
            class_restriction=list(data.get("class_restriction", [])),
            quest_use=str(data.get("quest_use", "")),
            aliases=list(data.get("aliases", [])),
            summary=str(data.get("summary") or data.get("stats_summary") or ""),
            tags=list(data.get("tags", [])),
            era_version=str(data.get("era_version", CLASSIC_ERA_VERSION)),
            source_url=str(data.get("source_url", "")),
        )


def _matches_classic_dungeon_whitelist(name: str) -> bool:
    norm_name = _norm(name)
    if norm_name in FORBIDDEN_DUNGEONS:
        return False
    for forbidden_exp in FORBIDDEN_EXPANSION_TAGS:
        if re.search(r"(?<![a-z0-9])" + re.escape(forbidden_exp) + r"(?![a-z0-9])", norm_name):
            return False
    if norm_name in CLASSIC_DUNGEONS_WHITELIST or norm_name in CLASSIC_DUNGEON_ALIASES:
        return True
    base_name = re.split(r"\s*[-–(:]\s*", norm_name, maxsplit=1)[0].strip()
    return (
        base_name in CLASSIC_DUNGEONS_WHITELIST or base_name in CLASSIC_DUNGEON_ALIASES
    ) and base_name not in FORBIDDEN_DUNGEONS


@dataclass
class DungeonRecord:
    dungeon_id: int
    name: str
    zone: str
    entrance_x: float | None = None
    entrance_y: float | None = None
    min_level: int = 1
    rec_level_min: int = 1
    rec_level_max: int = 60
    player_cap: int = 5
    faction: str = "Both"
    bosses: list[str] = field(default_factory=list)
    key_quests: list[str] = field(default_factory=list)
    notable_loot: list[str] = field(default_factory=list)
    attunement_or_key: str = ""
    aliases: list[str] = field(default_factory=list)
    summary: str = ""
    tags: list[str] = field(default_factory=list)
    era_version: str = CLASSIC_ERA_VERSION
    source_url: str = ""

    @property
    def entity_type(self) -> str:
        return "dungeon"

    def __post_init__(self) -> None:
        self.validate()

    def validate(self) -> None:
        self.dungeon_id = _validate_positive_id(self.dungeon_id, "dungeon_id")
        self.name = (self.name or "").strip()
        if not self.name:
            raise ClassicScopeError("DungeonRecord.name cannot be empty.")
        _reject_forbidden_name(self.name, "DungeonRecord.name")
        if not _matches_classic_dungeon_whitelist(self.name):
            raise ClassicScopeError(
                f"Dungeon '{self.name}' is not in the Classic Era 1.15.x dungeon/raid whitelist."
            )
        self.zone = validate_zone(self.zone)
        self.entrance_x, self.entrance_y = validate_coords(
            self.entrance_x, self.entrance_y, label="DungeonRecord.entrance_coords"
        )
        self.min_level = int(
            validate_level(self.min_level, min_val=1, max_val=CLASSIC_MAX_PLAYER_LEVEL, field_name="min_level")
        )
        self.rec_level_min = int(
            validate_level(self.rec_level_min, min_val=1, max_val=CLASSIC_MAX_PLAYER_LEVEL, field_name="rec_level_min")
        )
        self.rec_level_max = int(
            validate_level(self.rec_level_max, min_val=1, max_val=CLASSIC_MAX_PLAYER_LEVEL, field_name="rec_level_max")
        )
        if self.rec_level_min > self.rec_level_max:
            raise ClassicScopeError(
                f"Dungeon rec_level_min ({self.rec_level_min}) cannot exceed rec_level_max ({self.rec_level_max})."
            )
        if self.min_level > self.rec_level_max:
            raise ClassicScopeError(
                f"Dungeon min_level ({self.min_level}) cannot exceed rec_level_max ({self.rec_level_max})."
            )
        if isinstance(self.player_cap, bool) or not isinstance(self.player_cap, int) or self.player_cap not in VALID_DUNGEON_CAPS:
            raise ClassicScopeError(
                f"Invalid player_cap={self.player_cap!r}; Classic Era dungeons/raids support {VALID_DUNGEON_CAPS}."
            )
        self.faction = _validate_faction(self.faction)
        self.bosses = [str(b).strip() for b in self.bosses if str(b).strip()]
        self.key_quests = [str(q).strip() for q in self.key_quests if str(q).strip()]
        self.notable_loot = [str(l).strip() for l in self.notable_loot if str(l).strip()]
        self.attunement_or_key = (self.attunement_or_key or "").strip()
        self.aliases = [str(a).strip() for a in self.aliases if str(a).strip()]
        self.summary = (self.summary or "").strip()
        self.tags = validate_tags(self.tags)
        self.era_version = validate_era_version(self.era_version)
        self.source_url = validate_source_url(self.source_url)

    def to_dict(self) -> dict[str, Any]:
        return {
            "dungeon_id": self.dungeon_id,
            "name": self.name,
            "zone": self.zone,
            "entrance_x": self.entrance_x,
            "entrance_y": self.entrance_y,
            "min_level": self.min_level,
            "rec_level_min": self.rec_level_min,
            "rec_level_max": self.rec_level_max,
            "player_cap": self.player_cap,
            "faction": self.faction,
            "bosses": list(self.bosses),
            "key_quests": list(self.key_quests),
            "notable_loot": list(self.notable_loot),
            "attunement_or_key": self.attunement_or_key,
            "aliases": list(self.aliases),
            "summary": self.summary,
            "tags": list(self.tags),
            "era_version": self.era_version,
            "source_url": self.source_url,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> DungeonRecord:
        ex, ey = _coerce_coords_pair(data, x_key="entrance_x", y_key="entrance_y", pair_key="entrance_coords")
        return cls(
            dungeon_id=data["dungeon_id"],
            name=str(data.get("name", "")),
            zone=str(data.get("zone", "")),
            entrance_x=ex,
            entrance_y=ey,
            min_level=data.get("min_level", 1),
            rec_level_min=data.get("rec_level_min", 1),
            rec_level_max=data.get("rec_level_max", 60),
            player_cap=data.get("player_cap", 5),
            faction=str(data.get("faction", "Both")),
            bosses=list(data.get("bosses", [])),
            key_quests=list(data.get("key_quests", [])),
            notable_loot=list(data.get("notable_loot", [])),
            attunement_or_key=str(data.get("attunement_or_key", "")),
            aliases=list(data.get("aliases", [])),
            summary=str(data.get("summary") or data.get("notes") or ""),
            tags=list(data.get("tags", [])),
            era_version=str(data.get("era_version", CLASSIC_ERA_VERSION)),
            source_url=str(data.get("source_url", "")),
        )


EntityRecord = QuestRecord | MobRecord | ItemRecord | DungeonRecord


def validate_entity_dict(entity_type: str, data: Mapping[str, Any]) -> EntityRecord:
    """Validate and construct a normalized Classic Era record from a dict."""
    etype = (entity_type or "").strip().lower()
    if etype == "quest":
        return QuestRecord.from_dict(data)
    if etype == "mob":
        return MobRecord.from_dict(data)
    if etype == "item":
        return ItemRecord.from_dict(data)
    if etype == "dungeon":
        return DungeonRecord.from_dict(data)
    raise ClassicScopeError(f"Unsupported entity_type '{entity_type}'; expected {VALID_ENTITY_TYPES}.")


def validate_quest(data: Mapping[str, Any] | QuestRecord) -> QuestRecord:
    return data if isinstance(data, QuestRecord) else QuestRecord.from_dict(data)


def validate_mob(data: Mapping[str, Any] | MobRecord) -> MobRecord:
    return data if isinstance(data, MobRecord) else MobRecord.from_dict(data)


def validate_item(data: Mapping[str, Any] | ItemRecord) -> ItemRecord:
    return data if isinstance(data, ItemRecord) else ItemRecord.from_dict(data)


def validate_dungeon(data: Mapping[str, Any] | DungeonRecord) -> DungeonRecord:
    return data if isinstance(data, DungeonRecord) else DungeonRecord.from_dict(data)


def validate_classic_era_record(entity_type: str, data: Mapping[str, Any] | EntityRecord) -> EntityRecord:
    if isinstance(data, (QuestRecord, MobRecord, ItemRecord, DungeonRecord)):
        data.validate()
        if data.entity_type != (entity_type or "").strip().lower():
            raise ClassicScopeError(
                f"Entity type mismatch: expected '{entity_type}', got '{data.entity_type}'."
            )
        return data
    return validate_entity_dict(entity_type, data)
