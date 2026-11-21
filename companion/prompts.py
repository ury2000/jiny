"""System prompts and RAG grounding formatters for Jiny (WoW Classic Forever 1.15.x)."""

from __future__ import annotations

from typing import Any, Iterable, Mapping, Sequence

from .rag_schema import CLASSIC_ERA_VERSION, detect_non_classic_terms

LANGUAGE_DIRECTIVES = {
    "esES": "Responde siempre en español natural y claro.",
    "enUS": "Always respond in natural, clear English.",
    "itIT": "Rispondi sempre in italiano naturale e chiaro.",
}


def build_system_instruction(locale: str = "esES") -> str:
    """Build the WoW Classic Forever persona prompt for Jiny."""
    lang_line = LANGUAGE_DIRECTIVES.get(locale, LANGUAGE_DIRECTIVES["enUS"])
    return (
        "You are Jiny, a warm, helpful arcane mage companion inside World of Warcraft Classic Forever "
        "(Vanilla Era 1.15.x, level cap 60, Kalimdor & Eastern Kingdoms only).\n"
        f"{lang_line}\n\n"
        "Strict rules:\n"
        "1. ONLY give information valid for WoW Classic Forever (Vanilla 1.15.x). NEVER mix mechanics, "
        "zones, talents, or items from TBC, Wrath, Cataclysm, or Retail.\n"
        "2. Keep answers concise and easy to read inside a compact in-game chat frame (2 to 5 crisp sentences).\n"
        "3. When answering about quests, items, drops, or trainers, include concrete Classic details: "
        "zone name, NPC name, approximate (x, y) coordinates when relevant, and recommended level.\n"
        "4. MACROS: When the user asks for a WoW macro, ALWAYS enclose the executable macro code inside "
        "[JINY_MACRO name=\"MacroName\"]...[/JINY_MACRO]. Give it a concise name attribute (1-16 chars, e.g. name=\"HalconArcano\"). "
        "Put ONLY the valid Classic macro lines (#showtooltip, /cast, /use, etc., max 255 chars) inside the tag. "
        "Put your conversational explanation OUTSIDE the tag.\n"
        "5. For non-macro code or commands (e.g. /dump, /run, console cvar), use standard ```code``` blocks.\n"
        "6. Do NOT use Markdown tables or heavy HTML formatting—plain readable text and the specified tags only.\n"
        "7. If you are uncertain about a drop rate or coordinate, clearly say so instead of guessing.\n"
        "8. When a [CLASSIC_ERA_CONTEXT] block is provided, treat it as authoritative for Classic Era (1.15.x) "
        "coordinates, level requirements, NPCs, items, and drop rates. Never invent missing numbers; when "
        "NO_LOCAL_RAG_MATCH or NON_CLASSIC_SCOPE is shown, clearly state the limitation or Classic-only scope."
    )


def _field(obj: Any, name: str, default: Any = None) -> Any:
    if isinstance(obj, Mapping):
        return obj.get(name, default)
    return getattr(obj, name, default)


def _format_hit_lines(hit: Any, idx: int) -> list[str]:
    etype = str(_field(hit, "entity_type", _field(hit, "kind", "entity")) or "entity")
    eid = _field(hit, "entity_id", _field(hit, "id", ""))
    name = str(_field(hit, "name", _field(hit, "title", "Unknown")) or "Unknown")
    zone = str(_field(hit, "zone", "") or "")
    era = str(_field(hit, "era_version", _field(hit, "patch", CLASSIC_ERA_VERSION)) or CLASSIC_ERA_VERSION)
    source_url = str(_field(hit, "source_url", "") or "")
    snippet = str(_field(hit, "snippet", "") or "")
    score = _field(hit, "score", None)
    record = _field(hit, "record", None)
    if not isinstance(record, Mapping):
        record = {}

    header = f"{idx}. [{etype}:{eid}] {name}"
    if zone:
        header += f" | Zone: {zone}"
    if score is not None:
        header += f" | Relevance: {score}"
    lines = [header]

    details: list[str] = []
    if etype == "quest":
        q_lvl = record.get("quest_level")
        m_lvl = record.get("min_level")
        if q_lvl is not None:
            details.append(f"Level: {q_lvl} (min {m_lvl})" if m_lvl is not None else f"Level: {q_lvl}")
        if record.get("x") is not None and record.get("y") is not None:
            details.append(f"Coords: ({record['x']}, {record['y']})")
        giver = record.get("giver")
        if isinstance(giver, Mapping) and giver.get("name"):
            g_coords = f" ({giver['x']}, {giver['y']})" if giver.get("x") is not None else ""
            details.append(f"Giver: {giver['name']}{g_coords}")
        turnin = record.get("turnin")
        if isinstance(turnin, Mapping) and turnin.get("name"):
            t_coords = f" ({turnin['x']}, {turnin['y']})" if turnin.get("x") is not None else ""
            details.append(f"Turn-in: {turnin['name']}{t_coords}")
    elif etype == "mob":
        lmin = record.get("level_min")
        lmax = record.get("level_max")
        cls = record.get("classification", "")
        if lmin is not None:
            lvl_txt = str(lmin) if lmin == lmax or lmax is None else f"{lmin}-{lmax}"
            details.append(f"Level: {lvl_txt} {cls}".strip())
        if record.get("x") is not None and record.get("y") is not None:
            details.append(f"Coords: ({record['x']}, {record['y']})")
        drops = record.get("drops") or []
        if drops:
            drop_parts = [
                f"{d['item_name']} ({d['drop_rate']}%)" if d.get("drop_rate") is not None else f"{d['item_name']} (unknown %)"
                for d in drops[:4]
                if isinstance(d, Mapping) and d.get("item_name")
            ]
            if drop_parts:
                details.append("Drops: " + ", ".join(drop_parts))
    elif etype == "item":
        req = record.get("req_level")
        ilvl = record.get("item_level")
        bind = record.get("bind_type", "")
        if req is not None:
            details.append(f"Req Level: {req}, iLvl: {ilvl}, Bind: {bind}")
        sources = record.get("sources") or []
        if sources:
            src_parts = []
            for s in sources[:4]:
                if not isinstance(s, Mapping):
                    continue
                rate = f" ({s['drop_rate']}%)" if s.get("drop_rate") is not None else " (drop rate unconfirmed)"
                sz = f" in {s['zone']}" if s.get("zone") else ""
                sc = f" ({s['x']}, {s['y']})" if s.get("x") is not None and s.get("y") is not None else ""
                src_parts.append(f"{s.get('source_name', 'Unknown')}{sz}{sc}{rate}")
            if src_parts:
                details.append("Sources: " + "; ".join(src_parts))
    elif etype == "dungeon":
        cap = record.get("player_cap")
        rmin = record.get("rec_level_min")
        rmax = record.get("rec_level_max")
        mlvl = record.get("min_level")
        if cap is not None:
            details.append(f"Cap: {cap}-player | Rec Level: {rmin}-{rmax} (min {mlvl})")
        if record.get("entrance_x") is not None and record.get("entrance_y") is not None:
            details.append(f"Entrance Coords: ({record['entrance_x']}, {record['entrance_y']})")
        bosses = record.get("bosses") or []
        if bosses:
            details.append("Bosses: " + ", ".join(str(b) for b in bosses[:6]))

    if details:
        lines.append("   " + " | ".join(details))
    elif snippet:
        lines.append(f"   Summary: {snippet}")
    elif record.get("summary"):
        lines.append(f"   Summary: {record['summary']}")

    if record.get("summary") and details:
        lines.append(f"   Notes: {record['summary']}")

    meta = f"   Era: {era}"
    if source_url:
        meta += f" | Source: {source_url}"
    lines.append(meta)
    return lines


def format_rag_context(
    hits: Sequence[Any] | Iterable[Any] | None,
    locale: str = "esES",
    query: str | None = None,
) -> str:
    """Format retrieved Classic Era 1.15.x hits into a grounded context block."""
    hits_list = list(hits or [])
    non_classic = detect_non_classic_terms(query) if query else []

    lines: list[str] = ["[CLASSIC_ERA_CONTEXT]"]
    if non_classic:
        lines.append(
            f"SCOPE_WARNING: NON_CLASSIC_SCOPE ({', '.join(non_classic)}). "
            "Inform the user that Jiny strictly covers WoW Classic Forever (1.15.x) only."
        )

    if not hits_list:
        lines.extend(
            [
                "STATUS: NO_LOCAL_RAG_MATCH",
                f"ERA: WoW Classic Forever ({CLASSIC_ERA_VERSION})",
                f"LOCALE: {locale}",
                "NOTE: No verified local Classic Era (1.15.x) entries matched this query.",
                "[/CLASSIC_ERA_CONTEXT]",
            ]
        )
        return "\n".join(lines)

    lines.extend(
        [
            f"STATUS: GROUNDED_MATCHES ({len(hits_list)})",
            f"ERA: WoW Classic Forever ({CLASSIC_ERA_VERSION})",
            f"LOCALE: {locale}",
        ]
    )
    for idx, hit in enumerate(hits_list, start=1):
        lines.extend(_format_hit_lines(hit, idx))
    lines.append("[/CLASSIC_ERA_CONTEXT]")
    return "\n".join(lines)


def apply_rag_context(question: str, context: str, locale: str = "esES") -> str:
    """Combine a [CLASSIC_ERA_CONTEXT] block with zero-hallucination directives and user question."""
    clean_ctx = (context or "").strip()
    if not clean_ctx:
        return question

    if "NON_CLASSIC_SCOPE" in clean_ctx:
        guard = (
            "Grounding rule: The query mentions content outside WoW Classic Forever (1.15.x). "
            "Politely clarify in the requested locale that this content does not exist in Classic Era (1.15.x) "
            "and do NOT invent TBC/WotLK/Retail numbers."
        )
    elif "NO_LOCAL_RAG_MATCH" in clean_ctx:
        guard = (
            "Grounding rule: No verified local Classic Era (1.15.x) database entry matched this query. "
            "Do NOT guess or fabricate coordinates, level requirements, or drop rates; clearly state what is unverified."
        )
    else:
        guard = (
            "Grounding rule: Answer strictly using the verified Classic Era (1.15.x) facts in [CLASSIC_ERA_CONTEXT] "
            "for coordinates, level requirements, NPCs, items, and drop rates. If a detail is absent from the context, "
            "explicitly say it is unverified instead of guessing."
        )

    return f"{clean_ctx}\n\n{guard}\nUser question ({locale}): {question}"


def build_grounded_input(
    question: str,
    hits: Sequence[Any] | Iterable[Any] | None,
    locale: str = "esES",
) -> str:
    """Retrieve-free helper that formats hits and binds them to the user question."""
    context_block = format_rag_context(hits, locale=locale, query=question)
    return apply_rag_context(question=question, context=context_block, locale=locale)
