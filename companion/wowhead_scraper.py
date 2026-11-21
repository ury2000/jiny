"""Optional offline-testable Wowhead Classic (1.15.x) scraper & updater."""

from __future__ import annotations

import html as html_lib
import json
import re
from typing import Any, Callable, Iterable
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from .rag_schema import (
    CLASSIC_DUNGEON_ALIASES,
    CLASSIC_DUNGEONS_WHITELIST,
    CLASSIC_ERA_VERSION,
    ClassicScopeError,
    FORBIDDEN_DUNGEONS,
    FORBIDDEN_ZONES,
    WOWHEAD_CLASSIC_URL_RE,
    WOWHEAD_TOOLTIP_URL_RE,
    detect_non_classic_terms,
    validate_coords,
    validate_drop_rate,
    validate_entity_dict,
)

USER_AGENT = "JinyClassicForeverCompanion/0.3 (+https://www.wowhead.com/classic)"

KNOWN_CLASSIC_DUNGEON_NAMES: dict[int, str] = {
    209: "Shadowfang Keep",
    491: "Razorfen Kraul",
    717: "The Stockade",
    718: "Wailing Caverns",
    719: "Blackfathom Deeps",
    721: "Gnomeregan",
    722: "Razorfen Downs",
    796: "Scarlet Monastery",
    1176: "Zul'Farrak",
    1337: "Uldaman",
    1477: "The Temple of Atal'Hakkar",
    1581: "The Deadmines",
    1583: "Upper Blackrock Spire",
    1584: "Blackrock Depths",
    1977: "Zul'Gurub",
    2017: "Stratholme",
    2057: "Scholomance",
    2100: "Maraudon",
    2159: "Onyxia's Lair",
    2437: "Ragefire Chasm",
    2557: "Dire Maul",
    2677: "Blackwing Lair",
    2717: "Molten Core",
    3428: "Temple of Ahn'Qiraj",
    3429: "Ruins of Ahn'Qiraj",
    3456: "Naxxramas",
}

KNOWN_CLASSIC_DUNGEON_IDS = frozenset(KNOWN_CLASSIC_DUNGEON_NAMES.keys())

_CANONICAL_LINK_RE = re.compile(
    r"""<link[^>]+rel=["']canonical["'][^>]+href=["']([^"']+)["']""",
    re.IGNORECASE,
)
_TITLE_TAG_RE = re.compile(r"<title>(.*?)</title>", re.IGNORECASE | re.DOTALL)
_H1_RE = re.compile(r"<h1[^>]*>(.*?)</h1>", re.IGNORECASE | re.DOTALL)
_TAG_STRIP_RE = re.compile(r"<[^>]+>")
_CHROME_STRIP_RE = re.compile(
    r"<(nav|footer|header|aside|script|style)\b[^>]*>.*?</\1>",
    re.IGNORECASE | re.DOTALL,
)


class ScraperError(Exception):
    """Raised when fetching or parsing Wowhead Classic data fails."""


def validate_classic_url(url: str) -> tuple[str, int, str]:
    """Validate and normalize a Wowhead Classic (1.15.x) URL.

    Returns (entity_type, entity_id, canonical_url).
    Raises ClassicScopeError (subclass of ValueError) for non-HTTPS, retail, or expansion URLs.
    """
    raw = (url or "").strip()
    if not raw:
        raise ClassicScopeError("URL cannot be empty.")

    lower = raw.lower()
    for marker in ("/tbc/", "/wotlk/", "/cata/", "/mop-classic/", "/classic-tbc/", "/retail/"):
        if marker in lower:
            raise ClassicScopeError(f"Non-Classic Wowhead URL rejected ({marker}): '{raw}'.")

    m_main = WOWHEAD_CLASSIC_URL_RE.match(raw)
    if m_main:
        etype, eid_str = m_main.group(1).lower(), m_main.group(2)
        eid = int(eid_str)
        if eid <= 0:
            raise ClassicScopeError(f"Invalid positive entity ID in URL: '{raw}'.")
        canonical = f"https://www.wowhead.com/classic/{etype}={eid}"
        return etype, eid, canonical

    m_tip = WOWHEAD_TOOLTIP_URL_RE.match(raw)
    if m_tip:
        etype, eid_str = m_tip.group(1).lower(), m_tip.group(2)
        eid = int(eid_str)
        if eid <= 0:
            raise ClassicScopeError(f"Invalid positive entity ID in URL: '{raw}'.")
        canonical = f"https://nether.wowhead.com/classic/tooltip/{etype}/{eid}"
        return etype, eid, canonical

    raise ClassicScopeError(
        f"Invalid Wowhead Classic URL '{raw}'. Only HTTPS wowhead.com/classic/(quest|npc|item|zone|dungeon)=<id> URLs are permitted."
    )


def default_fetcher(url: str, timeout: float = 15.0) -> str:
    """Fetch a validated Wowhead Classic URL via stdlib urllib.request."""
    validate_classic_url(url)
    req = Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urlopen(req, timeout=timeout) as resp:
            charset = resp.headers.get_content_charset() or "utf-8"
            return resp.read().decode(charset, errors="replace")
    except (HTTPError, URLError, OSError, TimeoutError) as exc:
        raise ScraperError(f"Failed to fetch '{url}': {exc}") from exc


def _strip_html(raw: str) -> str:
    text = _TAG_STRIP_RE.sub(" ", raw or "")
    return re.sub(r"\s+", " ", html_lib.unescape(text)).strip()


def _extract_balanced(text: str, start_idx: int, open_ch: str = "{", close_ch: str = "}") -> str | None:
    if start_idx < 0 or start_idx >= len(text) or text[start_idx] != open_ch:
        return None
    depth = 0
    in_str: str | None = None
    escaped = False
    for idx in range(start_idx, len(text)):
        ch = text[idx]
        if in_str is not None:
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == in_str:
                in_str = None
            continue
        if ch in ('"', "'"):
            in_str = ch
        elif ch == open_ch:
            depth += 1
        elif ch == close_ch:
            depth -= 1
            if depth == 0:
                return text[start_idx : idx + 1]
    return None


def _js_object_to_json(js_literal: str) -> Any:
    """Safely convert a JS object/array literal (unquoted keys, single quotes) to Python via json.loads."""
    out: list[str] = []
    i = 0
    n = len(js_literal)
    last_sig = ""
    while i < n:
        ch = js_literal[i]
        if ch in ('"', "'"):
            quote = ch
            i += 1
            buf: list[str] = ['"']
            while i < n:
                c = js_literal[i]
                if c == "\\":
                    if i + 1 < n:
                        nxt = js_literal[i + 1]
                        if quote == "'" and nxt == "'":
                            buf.append("'")
                        elif nxt == '"':
                            buf.append('\\"')
                        else:
                            buf.append("\\" + nxt)
                        i += 2
                        continue
                if c == quote:
                    i += 1
                    break
                if c == '"':
                    buf.append('\\"')
                elif c == "\n":
                    buf.append("\\n")
                elif c == "\r":
                    buf.append("\\r")
                elif c == "\t":
                    buf.append("\\t")
                else:
                    buf.append(c)
                i += 1
            buf.append('"')
            out.append("".join(buf))
            last_sig = '"'
            continue

        # Unquoted identifier key before ':'
        if (ch.isalpha() or ch in ("_", "$")) and last_sig in ("", "{", ",", "["):
            m_ident = re.match(r"([A-Za-z_$][A-Za-z0-9_$]*)\s*:", js_literal[i:])
            if m_ident:
                out.append(f'"{m_ident.group(1)}":')
                i += len(m_ident.group(0))
                last_sig = ":"
                continue

        # Unquoted numeric object key before ':' (e.g. {14: [...]})
        if ch.isdigit() and last_sig in ("", "{", ","):
            m_num = re.match(r"(\d+)\s*:", js_literal[i:])
            if m_num:
                out.append(f'"{m_num.group(1)}":')
                i += len(m_num.group(0))
                last_sig = ":"
                continue

        out.append(ch)
        if not ch.isspace():
            last_sig = ch
        i += 1

    normalized = "".join(out)
    # Remove trailing commas before } or ]
    normalized = re.sub(r",\s*([}\]])", r"\1", normalized)
    return json.loads(normalized)


def _extract_gatherer_entries(html_text: str) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    for m in re.finditer(r"WH\.Gatherer\.addData\s*\(\s*(\d+)\s*,\s*(\d+)\s*,\s*", html_text):
        block = _extract_balanced(html_text, m.end(), "{", "}")
        if not block:
            continue
        try:
            parsed = _js_object_to_json(block)
            if isinstance(parsed, dict):
                entries.append(
                    {
                        "wh_type": int(m.group(1)),
                        "id": int(m.group(2)),
                        "data": parsed,
                    }
                )
        except Exception:
            continue
    return entries


def _extract_mapper_coords(html_text: str) -> tuple[float | None, float | None]:
    def _walk(node: Any, pairs: list[tuple[float, float]]) -> None:
        if isinstance(node, list):
            if (
                len(node) == 2
                and isinstance(node[0], (int, float))
                and isinstance(node[1], (int, float))
                and not isinstance(node[0], bool)
                and not isinstance(node[1], bool)
            ):
                pairs.append((float(node[0]), float(node[1])))
            else:
                for item in node:
                    _walk(item, pairs)
        elif isinstance(node, dict):
            if "coords" in node:
                _walk(node["coords"], pairs)
            else:
                for val in node.values():
                    _walk(val, pairs)

    for m in re.finditer(r"g_mapperData\s*(?:\[\s*\d+\s*\])?\s*=\s*", html_text):
        start = m.end()
        if start >= len(html_text):
            continue
        open_ch = html_text[start]
        if open_ch not in ("{", "["):
            continue
        close_ch = "}" if open_ch == "{" else "]"
        block = _extract_balanced(html_text, start, open_ch, close_ch)
        if not block:
            continue
        try:
            parsed = _js_object_to_json(block)
        except Exception:
            continue

        pairs: list[tuple[float, float]] = []
        _walk(parsed, pairs)
        if pairs:
            return validate_coords(pairs[0][0], pairs[0][1], label="g_mapperData")
    return None, None


def _extract_listviews(html_text: str) -> dict[str, list[dict[str, Any]]]:
    views: dict[str, list[dict[str, Any]]] = {}
    for m in re.finditer(r"new\s+Listview\s*\(\s*", html_text):
        block = _extract_balanced(html_text, m.end(), "{", "}")
        if not block:
            continue
        try:
            obj = _js_object_to_json(block)
        except Exception:
            continue
        if isinstance(obj, dict):
            vid = str(obj.get("id") or obj.get("template") or "unknown").strip().lower()
            data = obj.get("data")
            if isinstance(data, list):
                views[vid] = [row for row in data if isinstance(row, dict)]
    return views


def _guard_html_classic_scope(html_text: str, source_url: str) -> None:
    m_canon = _CANONICAL_LINK_RE.search(html_text)
    if m_canon:
        validate_classic_url(m_canon.group(1).strip())

    scoped_html = _CHROME_STRIP_RE.sub(" ", html_text or "")
    plain = _strip_html(scoped_html)

    gatherer_bits: list[str] = []
    for entry in _extract_gatherer_entries(html_text):
        gdata = entry.get("data") or {}
        gname = str(gdata.get("name_enus") or gdata.get("name") or "").strip()
        if gname:
            gatherer_bits.append(gname)
        g_req = gdata.get("reqlevel")
        if isinstance(g_req, int) and not isinstance(g_req, bool) and g_req > 60:
            raise ClassicScopeError(
                f"Scraped entity requires level {g_req} (> 60 Classic Era cap)."
            )

    scoped_text = f"{plain} {' '.join(gatherer_bits)}".strip()
    non_classic = detect_non_classic_terms(scoped_text)
    if non_classic:
        raise ClassicScopeError(
            f"Scraped HTML from '{source_url}' contains non-Classic markers: {non_classic}."
        )
    req_lvl_match = re.search(r"Requires\s+Level\s+(\d+)", scoped_text, re.IGNORECASE)
    if req_lvl_match and int(req_lvl_match.group(1)) > 60:
        raise ClassicScopeError(
            f"Scraped entity requires level {req_lvl_match.group(1)} (> 60 Classic Era cap)."
        )


def _extract_name(html_text: str, gatherer: list[dict[str, Any]], entity_id: int) -> str:
    for entry in gatherer:
        if entry["id"] == entity_id:
            g_name = str(entry["data"].get("name_enus") or entry["data"].get("name") or "").strip()
            if g_name:
                return g_name
    m_h1 = _H1_RE.search(html_text)
    if m_h1:
        text = _strip_html(m_h1.group(1))
        if text:
            return text
    m_title = _TITLE_TAG_RE.search(html_text)
    if m_title:
        title = _strip_html(m_title.group(1))
        title = re.sub(r"\s*-\s*(?:Item|Quest|NPC|Zone|Dungeon).*$", "", title, flags=re.IGNORECASE).strip()
        if title:
            return title
    raise ScraperError(f"Could not extract entity name from HTML for id={entity_id}.")


def _compute_drop_rate(row: dict[str, Any]) -> float | None:
    if "drop_rate" in row and row["drop_rate"] is not None:
        return validate_drop_rate(float(row["drop_rate"]))
    count = row.get("count")
    outof = row.get("outof")
    if isinstance(count, (int, float)) and isinstance(outof, (int, float)) and outof > 0:
        return validate_drop_rate(round((float(count) / float(outof)) * 100.0, 2))
    return None


def _parse_infobox_kv(plain_text: str) -> dict[str, str]:
    kv: dict[str, str] = {}
    patterns = {
        "zone": r"Zone:\s*([A-Za-z0-9' -]+?)(?:\s+(?:Level|Faction|Players|Type|Min|Binds|$))",
        "faction": r"Faction:\s*(Alliance|Horde|Neutral|Both)",
        "level": r"(?<!Requires\s)(?<!Min\s)Level:\s*(\d+)(?:\s*-\s*(\d+))?",
        "min_level": r"Min(?:imum)?\s+Level:\s*(\d+)",
        "req_level": r"Requires\s+Level\s+(\d+)",
        "item_level": r"Item\s+Level\s+(\d+)",
        "players": r"Players:\s*(\d+)",
        "classification": r"Classification:\s*(Boss|Rare Elite|Rare|Elite|Normal|Quest Giver)",
        "mob_type": r"Type:\s*(Humanoid|Beast|Demon|Dragonkin|Elemental|Giant|Mechanical|Undead)",
    }
    for key, pat in patterns.items():
        m = re.search(pat, plain_text, re.IGNORECASE)
        if m:
            if key == "level" and m.group(2):
                kv[key] = f"{m.group(1)}-{m.group(2)}"
            else:
                kv[key] = m.group(1).strip()
    return kv


def parse_tooltip_json(
    payload: str,
    entity_type: str,
    entity_id: int,
    source_url: str,
) -> dict[str, Any]:
    """Parse a Wowhead Classic tooltip JSON payload into a validated entity dict."""
    validate_classic_url(source_url)
    try:
        data = json.loads(payload)
    except json.JSONDecodeError as exc:
        raise ScraperError(f"Invalid tooltip JSON from '{source_url}': {exc}") from exc

    if not isinstance(data, dict):
        raise ScraperError("Tooltip JSON root must be an object.")

    name = str(data.get("name") or "").strip()
    tooltip_html = str(data.get("tooltip") or "")
    plain = _strip_html(tooltip_html)
    _guard_html_classic_scope(f"{name} {plain}", source_url)

    quality_map = {
        0: "Poor",
        1: "Common",
        2: "Uncommon",
        3: "Rare",
        4: "Epic",
        5: "Legendary",
    }
    etype = entity_type.lower()
    if etype == "item":
        q_raw = data.get("quality", 1)
        quality = quality_map.get(q_raw, str(q_raw)) if isinstance(q_raw, int) else str(q_raw)
        m_ilvl = re.search(r"Item\s+Level\s+(\d+)", plain, re.IGNORECASE)
        m_req = re.search(r"Requires\s+Level\s+(\d+)", plain, re.IGNORECASE)
        bind_type = "None"
        if "Binds when picked up" in plain:
            bind_type = "BoP"
        elif "Binds when equipped" in plain:
            bind_type = "BoE"
        elif "Binds when used" in plain:
            bind_type = "BoU"
        elif "Quest Item" in plain:
            bind_type = "Quest"
        rec = {
            "item_id": entity_id,
            "name": name,
            "quality": quality,
            "item_level": int(m_ilvl.group(1)) if m_ilvl else int(data.get("level", 1) or 1),
            "req_level": int(m_req.group(1)) if m_req else int(data.get("reqlevel", 0) or 0),
            "bind_type": bind_type,
            "summary": plain[:240],
            "era_version": CLASSIC_ERA_VERSION,
            "source_url": source_url,
        }
        return validate_entity_dict("item", rec).to_dict()

    raise ScraperError(f"Tooltip JSON parsing only supports 'item' (got '{entity_type}').")


def _target_entity_type(entity_type: str, entity_id: int, name: str, kv: dict[str, str]) -> str:
    etype = entity_type.lower()
    if etype == "npc":
        return "mob"
    if etype == "zone":
        lower_name = name.lower()
        if (
            entity_id in KNOWN_CLASSIC_DUNGEON_IDS
            or lower_name in CLASSIC_DUNGEONS_WHITELIST
            or lower_name in CLASSIC_DUNGEON_ALIASES
            or lower_name in FORBIDDEN_DUNGEONS
            or "players" in kv
        ):
            return "dungeon"
        if lower_name in FORBIDDEN_ZONES:
            raise ClassicScopeError(f"Zone '{name}' is outside Classic Era 1.15.x.")
        raise ScraperError(
            f"Outdoor zone pages ('{name}', zone={entity_id}) are not indexed as Dungeon records; "
            "use a Classic dungeon/raid, quest, npc, or item URL."
        )
    return etype


def parse_wowhead_html(
    html: str,
    entity_type: str,
    entity_id: int,
    source_url: str,
) -> dict[str, Any]:
    """Parse Wowhead Classic HTML into a validated Classic Era 1.15.x entity dictionary."""
    validate_classic_url(source_url)
    _guard_html_classic_scope(html, source_url)

    gatherer = _extract_gatherer_entries(html)
    x, y = _extract_mapper_coords(html)
    listviews = _extract_listviews(html)
    plain = _strip_html(html)
    kv = _parse_infobox_kv(plain)
    name = _extract_name(html, gatherer, entity_id)
    target_type = _target_entity_type(entity_type, entity_id, name, kv)

    g_data = next((e["data"] for e in gatherer if e["id"] == entity_id), {})

    if target_type == "quest":
        lvl = int(kv.get("level", "1").split("-")[0]) if "level" in kv else int(g_data.get("level", 1) or 1)
        min_lvl = int(kv["min_level"]) if "min_level" in kv else min(lvl, int(g_data.get("reqlevel", 1) or 1))
        zone = kv.get("zone", "Eastern Kingdoms")
        faction = kv.get("faction", "Both")
        rec: dict[str, Any] = {
            "quest_id": entity_id,
            "name": name,
            "zone": zone,
            "faction": faction,
            "quest_level": lvl,
            "min_level": max(1, min_lvl),
            "x": x,
            "y": y,
            "era_version": CLASSIC_ERA_VERSION,
            "source_url": source_url,
            "summary": f"Wowhead Classic quest {name} in {zone}.",
        }
        return validate_entity_dict("quest", rec).to_dict()

    if target_type == "mob":
        lvl_str = kv.get("level", "1")
        if "-" in lvl_str:
            lmin, lmax = (int(p) for p in lvl_str.split("-", 1))
        else:
            lmin = lmax = int(lvl_str)
        classification = kv.get("classification", "Normal")
        zone = kv.get("zone", "Eastern Kingdoms")
        drops = []
        for row in listviews.get("drops", []):
            item_name = str(row.get("name") or "").strip()
            if not item_name:
                continue
            drops.append(
                {
                    "item_name": item_name,
                    "item_id": int(row["id"]) if row.get("id") else None,
                    "drop_rate": _compute_drop_rate(row),
                }
            )
        rec = {
            "npc_id": entity_id,
            "name": name,
            "zone": zone,
            "mob_type": kv.get("mob_type", "Humanoid"),
            "classification": classification,
            "level_min": lmin,
            "level_max": lmax,
            "faction": kv.get("faction", "Neutral"),
            "x": x,
            "y": y,
            "drops": drops,
            "era_version": CLASSIC_ERA_VERSION,
            "source_url": source_url,
            "summary": f"Wowhead Classic NPC {name} in {zone}.",
        }
        return validate_entity_dict("mob", rec).to_dict()

    if target_type == "item":
        quality_map = {0: "Poor", 1: "Common", 2: "Uncommon", 3: "Rare", 4: "Epic", 5: "Legendary"}
        q_val = g_data.get("quality", "Common")
        quality = quality_map.get(q_val, str(q_val)) if isinstance(q_val, int) else str(q_val)
        req_level = int(kv["req_level"]) if "req_level" in kv else int(g_data.get("reqlevel", 0) or 0)
        item_level = int(kv["item_level"]) if "item_level" in kv else int(g_data.get("level", 1) or 1)
        bind_type = "None"
        if "Binds when picked up" in plain:
            bind_type = "BoP"
        elif "Binds when equipped" in plain:
            bind_type = "BoE"
        elif "Binds when used" in plain:
            bind_type = "BoU"

        sources = []
        for row in listviews.get("dropped-by", []):
            src_name = str(row.get("name") or "").strip()
            if not src_name:
                continue
            sources.append(
                {
                    "source_type": "boss" if row.get("classification") == 3 else "mob",
                    "source_name": src_name,
                    "source_id": int(row["id"]) if row.get("id") else None,
                    "zone": kv.get("zone", ""),
                    "drop_rate": _compute_drop_rate(row),
                }
            )
        rec = {
            "item_id": entity_id,
            "name": name,
            "quality": quality,
            "item_level": item_level,
            "req_level": req_level,
            "bind_type": bind_type,
            "zone": kv.get("zone", ""),
            "sources": sources,
            "era_version": CLASSIC_ERA_VERSION,
            "source_url": source_url,
            "summary": f"Wowhead Classic item {name}.",
        }
        return validate_entity_dict("item", rec).to_dict()

    if target_type == "dungeon":
        canonical_name = name
        aliases: list[str] = []
        lower_name = name.lower()
        if lower_name in CLASSIC_DUNGEON_ALIASES:
            canonical_name = CLASSIC_DUNGEON_ALIASES[lower_name]
        elif entity_id in KNOWN_CLASSIC_DUNGEON_NAMES and lower_name not in CLASSIC_DUNGEONS_WHITELIST:
            canonical_name = KNOWN_CLASSIC_DUNGEON_NAMES[entity_id]
        if canonical_name.lower() != lower_name:
            aliases.append(name)

        lvl_str = kv.get("level", "60")
        if "-" in lvl_str:
            rmin, rmax = (int(p) for p in lvl_str.split("-", 1))
        else:
            rmin = rmax = int(lvl_str)
        min_lvl = int(kv["min_level"]) if "min_level" in kv else min(rmin, rmax)
        cap = int(kv.get("players", 5))
        zone = kv.get("zone", canonical_name)
        if zone.lower() in FORBIDDEN_ZONES:
            raise ClassicScopeError(f"Zone '{zone}' is outside Classic Era 1.15.x.")
        bosses = [str(r.get("name")).strip() for r in listviews.get("bosses", []) if r.get("name")]
        rec = {
            "dungeon_id": entity_id,
            "name": canonical_name,
            "zone": zone,
            "entrance_x": x,
            "entrance_y": y,
            "min_level": min_lvl,
            "rec_level_min": rmin,
            "rec_level_max": rmax,
            "player_cap": cap,
            "faction": kv.get("faction", "Both"),
            "bosses": bosses,
            "aliases": aliases,
            "era_version": CLASSIC_ERA_VERSION,
            "source_url": source_url,
            "summary": f"Wowhead Classic {cap}-player instance {canonical_name} in {zone}.",
        }
        return validate_entity_dict("dungeon", rec).to_dict()

    raise ScraperError(f"Unsupported entity type '{entity_type}'.")


def scrape_entity(
    url: str,
    fetcher: Callable[[str], str] | None = None,
) -> tuple[str, dict[str, Any]]:
    """Validate URL, fetch HTML/JSON via injected or default fetcher, and parse into a Classic record."""
    raw_type, entity_id, canonical_url = validate_classic_url(url)
    fetch_fn = fetcher or default_fetcher
    payload = fetch_fn(canonical_url)

    stripped = (payload or "").lstrip()
    if stripped.startswith("{"):
        record = parse_tooltip_json(payload, raw_type, entity_id, canonical_url)
        target_type = "mob" if raw_type == "npc" else ("dungeon" if raw_type == "zone" else raw_type)
        return target_type, record

    record = parse_wowhead_html(payload, raw_type, entity_id, canonical_url)
    if "quest_id" in record:
        return "quest", record
    if "npc_id" in record:
        return "mob", record
    if "item_id" in record:
        return "item", record
    if "dungeon_id" in record:
        return "dungeon", record
    raise ScraperError(f"Unable to classify parsed record from '{canonical_url}'.")


def update_store_from_urls(
    urls: Iterable[str],
    store: Any,
    fetcher: Callable[[str], str] | None = None,
) -> int:
    """Scrape Classic Wowhead URLs and upsert validated records into ClassicRagStore."""
    count = 0
    for url in urls:
        entity_type, record = scrape_entity(url, fetcher=fetcher)
        id_key = {
            "quest": "quest_id",
            "mob": "npc_id",
            "item": "item_id",
            "dungeon": "dungeon_id",
        }[entity_type]
        existing = store.get_entity(entity_type, int(record[id_key]))
        if existing and not record.get("aliases"):
            record["aliases"] = list(existing.get("aliases", []))
        if existing and not record.get("tags"):
            record["tags"] = list(existing.get("tags", []))
        store.upsert_entity(entity_type, record)
        count += 1
    return count
