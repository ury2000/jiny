"""SQLite + FTS5 (BM25) local RAG store for WoW Classic Forever (1.15.x)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import sqlite3
from typing import Any, Mapping, Sequence
import unicodedata

from .rag_schema import (
    CLASSIC_ERA_VERSION,
    DungeonRecord,
    ItemRecord,
    MobRecord,
    QuestRecord,
    VALID_ENTITY_TYPES,
    is_non_classic_query,
    validate_dungeon,
    validate_era_version,
    validate_item,
    validate_mob,
    validate_quest,
)

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DB_PATH = REPO_ROOT / "companion" / "data" / "classic_era_rag.db"
DEFAULT_SEED_PATH = REPO_ROOT / "companion" / "data" / "classic_era_seed.json"

STOPWORDS = frozenset(
    {
        # Spanish
        "de",
        "la",
        "el",
        "en",
        "y",
        "o",
        "a",
        "un",
        "una",
        "los",
        "las",
        "del",
        "al",
        "para",
        "por",
        "con",
        "sin",
        "que",
        "como",
        "cual",
        "donde",
        "esta",
        "estan",
        "cae",
        "suelta",
        "nivel",
        "es",
        "son",
        "se",
        "me",
        "mi",
        "te",
        # English
        "the",
        "of",
        "in",
        "at",
        "to",
        "for",
        "on",
        "with",
        "and",
        "or",
        "not",
        "near",
        "is",
        "are",
        "where",
        "what",
        "who",
        "how",
        "does",
        "do",
        "drop",
        "drops",
        "from",
        "level",
        # Italian
        "il",
        "lo",
        "gli",
        "le",
        "di",
        "da",
        "che",
        "dove",
        "e",
        "con",
        "per",
        "su",
        "livello",
        "cade",
    }
)

BILINGUAL_EXPANSIONS: dict[str, tuple[str, ...]] = {
    "esposa": ("wife", "mankrik"),
    "moglie": ("wife", "mankrik"),
    "perdida": ("lost", "battle"),
    "persa": ("lost", "battle"),
    "mazmorra": ("dungeon",),
    "mision": ("quest",),
    "quest": ("mision",),
    "yelmo": ("helm",),
    "elmo": ("helm",),
    "corazon": ("heart", "lionheart"),
    "cuor": ("heart", "lionheart"),
    "leon": ("lion", "lionheart"),
    "leone": ("lion", "lionheart"),
    "baldios": ("barrens",),
    "savane": ("barrens",),
    "paramos": ("westfall",),
    "profundidades": ("depths",),
    "profondita": ("depths",),
    "roca": ("blackrock",),
    "roccianera": ("blackrock",),
    "nucleo": ("molten", "core"),
    "minas": ("deadmines",),
    "miniere": ("deadmines",),
    "morte": ("deadmines",),
    "muerte": ("deadmines",),
    "cruzada": ("scarlet",),
    "escarlata": ("scarlet",),
    "scarlatto": ("scarlet",),
    "hojahierro": ("ironfoe",),
    "fierro": ("ironfoe",),
    "justicia": ("justice",),
    "giustizia": ("justice",),
    "cruzado": ("crusader",),
    "crociato": ("crusader",),
    "montura": ("reins", "mount"),
    "destrero": ("deathcharger",),
    "destriero": ("deathcharger",),
    "trueno": ("thunderfury",),
    "tuono": ("thunderfury",),
    "armonizacion": ("attunement",),
    "armonizzazione": ("attunement",),
    "amuleto": ("amulet", "drakefire"),
    "lamentos": ("wailing", "caverns"),
    "lamenti": ("wailing", "caverns"),
}

_JINY_TAG_RE = re.compile(r"\[JINY_Q#[^\]]+\]\s*", re.IGNORECASE)


def normalize_text(text: str) -> str:
    """Fold diacritics, lowercase, and collapse whitespace."""
    decomposed = unicodedata.normalize("NFKD", text or "")
    stripped = "".join(ch for ch in decomposed if unicodedata.category(ch) != "Mn")
    return re.sub(r"\s+", " ", stripped).strip().lower()


def tokenize_query(query: str) -> tuple[list[str], list[str]]:
    """Extract sanitized query tokens: returns (meaningful_tokens, fts_tokens)."""
    cleaned = _JINY_TAG_RE.sub(" ", query or "")
    norm = normalize_text(cleaned)
    raw_tokens = re.findall(r"[^\W_]+", norm)
    kept: list[str] = []
    for tok in raw_tokens:
        if (len(tok) >= 2 or tok.isdigit()) and tok not in kept:
            kept.append(tok)
    if not kept:
        return [], []

    meaningful = [tok for tok in kept if tok not in STOPWORDS]
    if not meaningful:
        meaningful = list(kept)

    expanded = list(meaningful)
    for tok in meaningful:
        for syn in BILINGUAL_EXPANSIONS.get(tok, ()):
            if syn not in expanded:
                expanded.append(syn)
    return meaningful, expanded


def build_fts_match_expr(tokens: Sequence[str]) -> str:
    """Build an injection-proof, crash-proof FTS5 MATCH expression."""
    parts: list[str] = []
    for raw in tokens:
        safe = raw.replace('"', "").strip()
        if not safe:
            continue
        if len(safe) >= 3:
            parts.append(f'"{safe}"*')
        else:
            parts.append(f'"{safe}"')
    return " OR ".join(parts)


@dataclass(frozen=True)
class RagHit:
    doc_key: str
    entity_type: str
    entity_id: int
    name: str
    zone: str
    score: float
    era_version: str
    source_url: str
    record: dict[str, Any]
    snippet: str


class ClassicRagStore:
    """Local SQLite + FTS5 BM25 knowledge store scoped exclusively to Classic Era 1.15.x."""

    def __init__(
        self,
        db_path: Path | str | None = None,
        seed_path: Path | str | None = None,
        auto_build: bool = True,
    ) -> None:
        self.db_path = Path(db_path) if db_path is not None else DEFAULT_DB_PATH
        self.seed_path = Path(seed_path) if seed_path is not None else DEFAULT_SEED_PATH
        if str(self.db_path) != ":memory:":
            self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(self.db_path))
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA foreign_keys = ON")
        if str(self.db_path) != ":memory:":
            self._conn.execute("PRAGMA journal_mode = DELETE")
        self.ensure_schema()
        if auto_build and self.stats()["total"] == 0 and self.seed_path.exists():
            self.load_seed(self.seed_path)

    def __enter__(self) -> ClassicRagStore:
        return self

    def __exit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
        self.close()

    def close(self) -> None:
        if self._conn is not None:
            self._conn.close()
            self._conn = None  # type: ignore[assignment]

    def ensure_schema(self) -> None:
        cur = self._conn.cursor()
        cur.executescript(
            """
            CREATE TABLE IF NOT EXISTS rag_meta (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS quests (
                quest_id INTEGER PRIMARY KEY,
                name TEXT NOT NULL,
                zone TEXT NOT NULL,
                faction TEXT NOT NULL,
                quest_level INTEGER NOT NULL,
                min_level INTEGER NOT NULL,
                x REAL,
                y REAL,
                giver_name TEXT NOT NULL DEFAULT '',
                turnin_name TEXT NOT NULL DEFAULT '',
                era_version TEXT NOT NULL,
                source_url TEXT NOT NULL,
                payload_json TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS mobs (
                npc_id INTEGER PRIMARY KEY,
                name TEXT NOT NULL,
                zone TEXT NOT NULL,
                mob_type TEXT NOT NULL,
                classification TEXT NOT NULL,
                level_min INTEGER NOT NULL,
                level_max INTEGER NOT NULL,
                faction TEXT NOT NULL,
                x REAL,
                y REAL,
                dungeon_id INTEGER,
                dungeon_name TEXT NOT NULL DEFAULT '',
                era_version TEXT NOT NULL,
                source_url TEXT NOT NULL,
                payload_json TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS items (
                item_id INTEGER PRIMARY KEY,
                name TEXT NOT NULL,
                quality TEXT NOT NULL,
                item_level INTEGER NOT NULL,
                req_level INTEGER NOT NULL,
                item_type TEXT NOT NULL,
                slot TEXT NOT NULL,
                bind_type TEXT NOT NULL,
                zone TEXT NOT NULL,
                era_version TEXT NOT NULL,
                source_url TEXT NOT NULL,
                payload_json TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS dungeons (
                dungeon_id INTEGER PRIMARY KEY,
                name TEXT NOT NULL,
                zone TEXT NOT NULL,
                entrance_x REAL,
                entrance_y REAL,
                min_level INTEGER NOT NULL,
                rec_level_min INTEGER NOT NULL,
                rec_level_max INTEGER NOT NULL,
                player_cap INTEGER NOT NULL,
                faction TEXT NOT NULL,
                era_version TEXT NOT NULL,
                source_url TEXT NOT NULL,
                payload_json TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS drop_sources (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                item_id INTEGER,
                item_name TEXT NOT NULL,
                npc_id INTEGER,
                source_name TEXT NOT NULL,
                source_type TEXT NOT NULL,
                zone TEXT NOT NULL,
                x REAL,
                y REAL,
                drop_rate REAL,
                notes TEXT NOT NULL DEFAULT '',
                UNIQUE(item_name, source_name, source_type)
            );

            CREATE INDEX IF NOT EXISTS idx_drop_sources_item_id ON drop_sources(item_id);
            CREATE INDEX IF NOT EXISTS idx_drop_sources_npc_id ON drop_sources(npc_id);
            CREATE INDEX IF NOT EXISTS idx_drop_sources_item_name ON drop_sources(item_name);

            CREATE VIRTUAL TABLE IF NOT EXISTS rag_fts USING fts5(
                doc_key UNINDEXED,
                entity_type UNINDEXED,
                entity_id UNINDEXED,
                name,
                aliases,
                zone,
                body,
                tokenize='unicode61 remove_diacritics 2'
            );
            """
        )
        self._conn.commit()

    def _upsert_fts(
        self,
        doc_key: str,
        entity_type: str,
        entity_id: int,
        name: str,
        aliases: Sequence[str],
        zone: str,
        body: str,
    ) -> None:
        self._conn.execute("DELETE FROM rag_fts WHERE doc_key = ?", (doc_key,))
        self._conn.execute(
            """
            INSERT INTO rag_fts (doc_key, entity_type, entity_id, name, aliases, zone, body)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (doc_key, entity_type, entity_id, name, " | ".join(aliases), zone, body),
        )

    def upsert_quest(self, quest: QuestRecord | Mapping[str, Any]) -> str:
        rec = validate_quest(quest)
        payload = rec.to_dict()
        doc_key = f"quest:{rec.quest_id}"
        giver_name = rec.giver.name if rec.giver else ""
        turnin_name = rec.turnin.name if rec.turnin else ""
        with self._conn:
            self._conn.execute(
                """
                INSERT INTO quests (
                    quest_id, name, zone, faction, quest_level, min_level,
                    x, y, giver_name, turnin_name, era_version, source_url, payload_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(quest_id) DO UPDATE SET
                    name=excluded.name,
                    zone=excluded.zone,
                    faction=excluded.faction,
                    quest_level=excluded.quest_level,
                    min_level=excluded.min_level,
                    x=excluded.x,
                    y=excluded.y,
                    giver_name=excluded.giver_name,
                    turnin_name=excluded.turnin_name,
                    era_version=excluded.era_version,
                    source_url=excluded.source_url,
                    payload_json=excluded.payload_json
                """,
                (
                    rec.quest_id,
                    rec.name,
                    rec.zone,
                    rec.faction,
                    rec.quest_level,
                    rec.min_level,
                    rec.x,
                    rec.y,
                    giver_name,
                    turnin_name,
                    rec.era_version,
                    rec.source_url,
                    json.dumps(payload, ensure_ascii=False),
                ),
            )
            body = " ".join(
                filter(
                    None,
                    [
                        rec.faction,
                        f"level {rec.quest_level}",
                        f"min level {rec.min_level}",
                        giver_name,
                        turnin_name,
                        rec.dungeon_name,
                        " ".join(rec.objectives),
                        " ".join(r.item_name for r in rec.rewards),
                        " ".join(rec.tags),
                        rec.summary,
                    ],
                )
            )
            self._upsert_fts(doc_key, "quest", rec.quest_id, rec.name, rec.aliases, rec.zone, body)
        return doc_key

    def upsert_mob(self, mob: MobRecord | Mapping[str, Any]) -> str:
        rec = validate_mob(mob)
        payload = rec.to_dict()
        doc_key = f"mob:{rec.npc_id}"
        with self._conn:
            self._conn.execute(
                """
                INSERT INTO mobs (
                    npc_id, name, zone, mob_type, classification, level_min, level_max,
                    faction, x, y, dungeon_id, dungeon_name, era_version, source_url, payload_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(npc_id) DO UPDATE SET
                    name=excluded.name,
                    zone=excluded.zone,
                    mob_type=excluded.mob_type,
                    classification=excluded.classification,
                    level_min=excluded.level_min,
                    level_max=excluded.level_max,
                    faction=excluded.faction,
                    x=excluded.x,
                    y=excluded.y,
                    dungeon_id=excluded.dungeon_id,
                    dungeon_name=excluded.dungeon_name,
                    era_version=excluded.era_version,
                    source_url=excluded.source_url,
                    payload_json=excluded.payload_json
                """,
                (
                    rec.npc_id,
                    rec.name,
                    rec.zone,
                    rec.mob_type,
                    rec.classification,
                    rec.level_min,
                    rec.level_max,
                    rec.faction,
                    rec.x,
                    rec.y,
                    rec.dungeon_id,
                    rec.dungeon_name,
                    rec.era_version,
                    rec.source_url,
                    json.dumps(payload, ensure_ascii=False),
                ),
            )
            for d in rec.drops:
                self._conn.execute(
                    """
                    INSERT INTO drop_sources (
                        item_id, item_name, npc_id, source_name, source_type, zone, x, y, drop_rate, notes
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(item_name, source_name, source_type) DO UPDATE SET
                        item_id=COALESCE(excluded.item_id, drop_sources.item_id),
                        npc_id=COALESCE(excluded.npc_id, drop_sources.npc_id),
                        zone=excluded.zone,
                        x=excluded.x,
                        y=excluded.y,
                        drop_rate=COALESCE(excluded.drop_rate, drop_sources.drop_rate),
                        notes=excluded.notes
                    """,
                    (
                        d.item_id,
                        d.item_name,
                        rec.npc_id,
                        rec.name,
                        "boss" if rec.classification == "Boss" else "mob",
                        rec.zone,
                        rec.x,
                        rec.y,
                        d.drop_rate,
                        d.notes,
                    ),
                )
            body = " ".join(
                filter(
                    None,
                    [
                        rec.mob_type,
                        rec.classification,
                        f"level {rec.level_min} {rec.level_max}",
                        rec.faction,
                        rec.subzone,
                        rec.dungeon_name,
                        " ".join(d.item_name for d in rec.drops),
                        " ".join(rec.tags),
                        rec.summary,
                    ],
                )
            )
            self._upsert_fts(doc_key, "mob", rec.npc_id, rec.name, rec.aliases, rec.zone, body)
        return doc_key

    def upsert_item(self, item: ItemRecord | Mapping[str, Any]) -> str:
        rec = validate_item(item)
        payload = rec.to_dict()
        doc_key = f"item:{rec.item_id}"
        with self._conn:
            self._conn.execute(
                """
                INSERT INTO items (
                    item_id, name, quality, item_level, req_level, item_type,
                    slot, bind_type, zone, era_version, source_url, payload_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(item_id) DO UPDATE SET
                    name=excluded.name,
                    quality=excluded.quality,
                    item_level=excluded.item_level,
                    req_level=excluded.req_level,
                    item_type=excluded.item_type,
                    slot=excluded.slot,
                    bind_type=excluded.bind_type,
                    zone=excluded.zone,
                    era_version=excluded.era_version,
                    source_url=excluded.source_url,
                    payload_json=excluded.payload_json
                """,
                (
                    rec.item_id,
                    rec.name,
                    rec.quality,
                    rec.item_level,
                    rec.req_level,
                    rec.item_type,
                    rec.slot,
                    rec.bind_type,
                    rec.zone,
                    rec.era_version,
                    rec.source_url,
                    json.dumps(payload, ensure_ascii=False),
                ),
            )
            for s in rec.sources:
                self._conn.execute(
                    """
                    INSERT INTO drop_sources (
                        item_id, item_name, npc_id, source_name, source_type, zone, x, y, drop_rate, notes
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(item_name, source_name, source_type) DO UPDATE SET
                        item_id=COALESCE(excluded.item_id, drop_sources.item_id),
                        npc_id=COALESCE(excluded.npc_id, drop_sources.npc_id),
                        zone=excluded.zone,
                        x=excluded.x,
                        y=excluded.y,
                        drop_rate=COALESCE(excluded.drop_rate, drop_sources.drop_rate),
                        notes=excluded.notes
                    """,
                    (
                        rec.item_id,
                        rec.name,
                        s.source_id if s.source_type in ("mob", "boss") else None,
                        s.source_name,
                        s.source_type,
                        s.zone or rec.zone,
                        s.x,
                        s.y,
                        s.drop_rate,
                        s.notes,
                    ),
                )
            body = " ".join(
                filter(
                    None,
                    [
                        rec.quality,
                        rec.item_type,
                        rec.slot,
                        rec.bind_type,
                        f"req level {rec.req_level}",
                        f"ilvl {rec.item_level}",
                        " ".join(f"{s.source_name} {s.zone}" for s in rec.sources),
                        rec.quest_use,
                        " ".join(f"{k} {v}" for k, v in rec.stats.items()),
                        " ".join(rec.tags),
                        rec.summary,
                    ],
                )
            )
            self._upsert_fts(doc_key, "item", rec.item_id, rec.name, rec.aliases, rec.zone, body)
        return doc_key

    def upsert_dungeon(self, dungeon: DungeonRecord | Mapping[str, Any]) -> str:
        rec = validate_dungeon(dungeon)
        payload = rec.to_dict()
        doc_key = f"dungeon:{rec.dungeon_id}"
        with self._conn:
            self._conn.execute(
                """
                INSERT INTO dungeons (
                    dungeon_id, name, zone, entrance_x, entrance_y, min_level,
                    rec_level_min, rec_level_max, player_cap, faction, era_version, source_url, payload_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(dungeon_id) DO UPDATE SET
                    name=excluded.name,
                    zone=excluded.zone,
                    entrance_x=excluded.entrance_x,
                    entrance_y=excluded.entrance_y,
                    min_level=excluded.min_level,
                    rec_level_min=excluded.rec_level_min,
                    rec_level_max=excluded.rec_level_max,
                    player_cap=excluded.player_cap,
                    faction=excluded.faction,
                    era_version=excluded.era_version,
                    source_url=excluded.source_url,
                    payload_json=excluded.payload_json
                """,
                (
                    rec.dungeon_id,
                    rec.name,
                    rec.zone,
                    rec.entrance_x,
                    rec.entrance_y,
                    rec.min_level,
                    rec.rec_level_min,
                    rec.rec_level_max,
                    rec.player_cap,
                    rec.faction,
                    rec.era_version,
                    rec.source_url,
                    json.dumps(payload, ensure_ascii=False),
                ),
            )
            body = " ".join(
                filter(
                    None,
                    [
                        f"{rec.player_cap}-player",
                        f"level {rec.rec_level_min} {rec.rec_level_max}",
                        rec.faction,
                        " ".join(rec.bosses),
                        " ".join(rec.key_quests),
                        " ".join(rec.notable_loot),
                        rec.attunement_or_key,
                        " ".join(rec.tags),
                        rec.summary,
                    ],
                )
            )
            self._upsert_fts(doc_key, "dungeon", rec.dungeon_id, rec.name, rec.aliases, rec.zone, body)
        return doc_key

    def upsert_entity(self, entity_type: str, data: Any) -> str:
        etype = (entity_type or "").strip().lower()
        if etype == "quest":
            return self.upsert_quest(data)
        if etype == "mob":
            return self.upsert_mob(data)
        if etype == "item":
            return self.upsert_item(data)
        if etype == "dungeon":
            return self.upsert_dungeon(data)
        raise ValueError(f"Unsupported entity_type '{entity_type}'; expected {VALID_ENTITY_TYPES}.")

    def get_entity(self, entity_type: str, entity_id: int) -> dict[str, Any] | None:
        table_map = {
            "quest": ("quests", "quest_id"),
            "mob": ("mobs", "npc_id"),
            "item": ("items", "item_id"),
            "dungeon": ("dungeons", "dungeon_id"),
        }
        etype = (entity_type or "").strip().lower()
        if etype not in table_map:
            raise ValueError(f"Unsupported entity_type '{entity_type}'; expected {VALID_ENTITY_TYPES}.")
        table, col = table_map[etype]
        row = self._conn.execute(f"SELECT payload_json FROM {table} WHERE {col} = ?", (entity_id,)).fetchone()
        if row is None:
            return None
        return json.loads(row["payload_json"])

    def load_seed(self, seed_path: Path | str | None = None) -> dict[str, int]:
        path = Path(seed_path) if seed_path is not None else self.seed_path
        raw_bytes = path.read_bytes()
        raw_text = raw_bytes.decode("utf-8")
        seed = json.loads(raw_text)

        if not isinstance(seed, dict):
            raise ValueError("Seed JSON root must be an object.")
        if seed.get("schema_version") != 1:
            raise ValueError(f"Unsupported seed schema_version: {seed.get('schema_version')!r}.")
        validate_era_version(seed.get("era_version"))

        quests = seed.get("quests", [])
        mobs = seed.get("mobs", [])
        items = seed.get("items", [])
        dungeons = seed.get("dungeons", [])
        if not all(isinstance(arr, list) for arr in (quests, mobs, items, dungeons)):
            raise ValueError("Seed JSON must contain list fields: quests, mobs, items, dungeons.")

        for q in quests:
            self.upsert_quest(q)
        for m in mobs:
            self.upsert_mob(m)
        for it in items:
            self.upsert_item(it)
        for d in dungeons:
            self.upsert_dungeon(d)

        seed_sha = hashlib.sha256(raw_bytes).hexdigest()
        built_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
        with self._conn:
            for k, v in (
                ("schema_version", "1"),
                ("era_version", CLASSIC_ERA_VERSION),
                ("seed_sha256", seed_sha),
                ("built_at", built_at),
            ):
                self._conn.execute(
                    """
                    INSERT INTO rag_meta (key, value) VALUES (?, ?)
                    ON CONFLICT(key) DO UPDATE SET value=excluded.value
                    """,
                    (k, v),
                )
        return self.stats()

    def rebuild(self, seed_path: Path | str | None = None) -> dict[str, int]:
        with self._conn:
            for table in ("rag_fts", "drop_sources", "quests", "mobs", "items", "dungeons", "rag_meta"):
                self._conn.execute(f"DELETE FROM {table}")
        return self.load_seed(seed_path=seed_path)

    def rebuild_from_seed(self, seed_path: Path | str | None = None) -> dict[str, int]:
        """Compatibility alias for rebuild()."""
        return self.rebuild(seed_path=seed_path)

    def stats(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for key, table in (
            ("quests", "quests"),
            ("mobs", "mobs"),
            ("items", "items"),
            ("dungeons", "dungeons"),
        ):
            row = self._conn.execute(f"SELECT COUNT(*) AS cnt FROM {table}").fetchone()
            counts[key] = int(row["cnt"]) if row is not None else 0
        counts["total"] = counts["quests"] + counts["mobs"] + counts["items"] + counts["dungeons"]
        return counts

    def _build_snippet(self, entity_type: str, record: dict[str, Any]) -> str:
        if entity_type == "quest":
            coords = (
                f"({record['x']}, {record['y']})"
                if record.get("x") is not None and record.get("y") is not None
                else "coords unknown"
            )
            giver = record.get("giver") or {}
            giver_str = f" | Giver: {giver['name']}" if giver.get("name") else ""
            return (
                f"Quest [{record['faction']}] Lvl {record['quest_level']} (min {record['min_level']}) "
                f"in {record['zone']} {coords}{giver_str}"
            )
        if entity_type == "mob":
            coords = (
                f"({record['x']}, {record['y']})"
                if record.get("x") is not None and record.get("y") is not None
                else "instance/unknown coords"
            )
            lvl = (
                f"{record['level_min']}"
                if record["level_min"] == record["level_max"]
                else f"{record['level_min']}-{record['level_max']}"
            )
            drops = ", ".join(
                f"{d['item_name']} ({d['drop_rate']}%)" if d.get("drop_rate") is not None else d["item_name"]
                for d in record.get("drops", [])[:3]
            )
            drops_str = f" | Drops: {drops}" if drops else ""
            return f"{record['classification']} Lvl {lvl} in {record['zone']} ({coords}){drops_str}"
        if entity_type == "item":
            sources = []
            for s in record.get("sources", [])[:3]:
                rate = f" {s['drop_rate']}%" if s.get("drop_rate") is not None else ""
                zone = f" [{s['zone']}]" if s.get("zone") else ""
                sources.append(f"{s['source_name']}{zone}{rate}")
            src_str = "; ".join(sources) if sources else "see details"
            return (
                f"{record['quality']} {record['item_type']} (Req Lvl {record['req_level']}, "
                f"iLvl {record['item_level']}, {record['bind_type']}) | Source: {src_str}"
            )
        if entity_type == "dungeon":
            coords = (
                f"({record['entrance_x']}, {record['entrance_y']})"
                if record.get("entrance_x") is not None and record.get("entrance_y") is not None
                else "unknown entrance"
            )
            return (
                f"{record['player_cap']}-player instance in {record['zone']} {coords} | "
                f"Rec Lvl {record['rec_level_min']}-{record['rec_level_max']} (min {record['min_level']})"
            )
        return record.get("summary", "")

    def retrieve(
        self,
        query: str,
        top_k: int = 5,
        entity_type: str | None = None,
    ) -> list[RagHit]:
        if entity_type is not None:
            etype = entity_type.strip().lower()
            if etype not in VALID_ENTITY_TYPES:
                raise ValueError(f"Unsupported entity_type '{entity_type}'; expected {VALID_ENTITY_TYPES}.")
        else:
            etype = None

        if top_k <= 0 or is_non_classic_query(query):
            return []

        meaningful_tokens, fts_tokens = tokenize_query(query)
        if not fts_tokens:
            return []

        match_expr = build_fts_match_expr(fts_tokens)
        if not match_expr:
            return []

        limit = max(top_k * 5, 25)
        params: list[Any] = [match_expr]
        type_clause = ""
        if etype is not None:
            type_clause = "AND entity_type = ? "
            params.append(etype)
        params.append(limit)

        fts_rows = self._conn.execute(
            f"""
            SELECT
                doc_key,
                entity_type,
                entity_id,
                name,
                aliases,
                zone,
                body,
                bm25(rag_fts, 0.0, 0.0, 0.0, 6.0, 4.5, 2.5, 1.0) AS bm25_score
            FROM rag_fts
            WHERE rag_fts MATCH ? {type_clause}
            ORDER BY bm25_score ASC
            LIMIT ?
            """,
            params,
        ).fetchall()

        candidates: dict[str, dict[str, Any]] = {}
        for row in fts_rows:
            candidates[row["doc_key"]] = {
                "doc_key": row["doc_key"],
                "entity_type": row["entity_type"],
                "entity_id": int(row["entity_id"]),
                "name": row["name"],
                "aliases": row["aliases"],
                "zone": row["zone"],
                "body": row["body"],
                "bm25": float(row["bm25_score"]),
            }

        # SQL LIKE fallback for very short tokens (e.g. "MC", "WC", "DM", "VC", "ZG")
        if len(candidates) < top_k:
            short_tokens = [t for t in meaningful_tokens if len(t) <= 3] or meaningful_tokens[:2]
            for tok in short_tokens:
                like_pat = f"%{tok}%"
                like_params: list[Any] = [like_pat, like_pat]
                like_type_clause = ""
                if etype is not None:
                    like_type_clause = "AND entity_type = ? "
                    like_params.append(etype)
                like_params.append(limit)
                extra_rows = self._conn.execute(
                    f"""
                    SELECT doc_key, entity_type, entity_id, name, aliases, zone, body
                    FROM rag_fts
                    WHERE (lower(name) LIKE ? OR lower(aliases) LIKE ?) {like_type_clause}
                    LIMIT ?
                    """,
                    like_params,
                ).fetchall()
                for row in extra_rows:
                    if row["doc_key"] not in candidates:
                        candidates[row["doc_key"]] = {
                            "doc_key": row["doc_key"],
                            "entity_type": row["entity_type"],
                            "entity_id": int(row["entity_id"]),
                            "name": row["name"],
                            "aliases": row["aliases"],
                            "zone": row["zone"],
                            "body": row["body"],
                            "bm25": 0.0,
                        }

        if not candidates:
            return []

        norm_query = normalize_text(_JINY_TAG_RE.sub(" ", query or ""))
        norm_meaningful_set = set(meaningful_tokens)
        norm_expanded_set = set(fts_tokens)

        hits: list[RagHit] = []
        for cand in candidates.values():
            record = self.get_entity(cand["entity_type"], cand["entity_id"])
            if record is None:
                continue

            norm_name = normalize_text(cand["name"])
            raw_aliases = [normalize_text(a) for a in record.get("aliases", []) if normalize_text(a)]
            name_and_aliases = [norm_name] + raw_aliases

            score = max(0.0, -cand["bm25"])
            if any(label == norm_query for label in name_and_aliases):
                score += 50.0
            elif any(
                len(label) >= 2
                and re.search(r"(?<![a-z0-9])" + re.escape(label) + r"(?![a-z0-9])", norm_query)
                for label in name_and_aliases
            ):
                score += 25.0
            elif any(label.startswith(norm_query) and len(norm_query) >= 2 for label in name_and_aliases):
                score += 15.0

            name_tokens = set(re.findall(r"[^\W_]+", " ".join(name_and_aliases)))
            doc_tokens = name_tokens | set(re.findall(r"[^\W_]+", normalize_text(f"{cand['zone']} {cand['body']}")))

            denom = max(1, len(meaningful_tokens))
            matched_name = sum(
                1
                for tok in norm_expanded_set
                if tok in name_tokens or (len(tok) >= 3 and any(nt.startswith(tok) for nt in name_tokens))
            )
            matched_doc = sum(
                1
                for tok in norm_meaningful_set
                if tok in doc_tokens or (len(tok) >= 3 and any(dt.startswith(tok) for dt in doc_tokens))
            )
            score += 10.0 * (min(matched_name, len(norm_expanded_set)) / max(1, denom))
            score += 4.0 * (matched_doc / denom)

            hits.append(
                RagHit(
                    doc_key=cand["doc_key"],
                    entity_type=cand["entity_type"],
                    entity_id=cand["entity_id"],
                    name=cand["name"],
                    zone=cand["zone"],
                    score=round(score, 4),
                    era_version=record.get("era_version", CLASSIC_ERA_VERSION),
                    source_url=record.get("source_url", ""),
                    record=record,
                    snippet=self._build_snippet(cand["entity_type"], record),
                )
            )

        hits.sort(key=lambda h: (-h.score, h.entity_type, h.entity_id))
        return hits[:top_k]

    def search(
        self,
        query: str,
        top_k: int = 5,
        entity_type: str | None = None,
    ) -> list[RagHit]:
        """Compatibility alias for retrieve()."""
        return self.retrieve(query=query, top_k=top_k, entity_type=entity_type)


ClassicEraRAGStore = ClassicRagStore
