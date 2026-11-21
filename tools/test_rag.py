"""Comprehensive offline unit tests for Jiny Classic Era (1.15.x) RAG (v0.3)."""

from __future__ import annotations

from contextlib import redirect_stdout
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from companion.config import load_config
from companion.gemini_client import JinyGeminiClient
from companion.main import main as companion_main
from companion.prompts import (
    apply_rag_context,
    build_grounded_input,
    build_system_instruction,
    format_rag_context,
)
from companion.rag_schema import (
    ClassicScopeError,
    DungeonRecord,
    ItemRecord,
    ItemSource,
    MobDrop,
    MobRecord,
    QuestNpcRef,
    QuestRecord,
    QuestReward,
    detect_non_classic_terms,
    is_non_classic_query,
    validate_entity_dict,
)
from companion.rag_store import ClassicRagStore, DEFAULT_SEED_PATH
from companion.wowhead_scraper import (
    ScraperError,
    parse_tooltip_json,
    parse_wowhead_html,
    scrape_entity,
    update_store_from_urls,
    validate_classic_url,
)


class _FakeInteraction:
    def __init__(self, interaction_id: str, output_text: str) -> None:
        self.id = interaction_id
        self.output_text = output_text


class _FakeInteractionsAPI:
    def __init__(self) -> None:
        self.calls: list[dict] = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        idx = len(self.calls)
        return _FakeInteraction(f"rag-int-{idx}", f"Grounded reply #{idx}")


class _FakeGenAIClient:
    def __init__(self) -> None:
        self.interactions = _FakeInteractionsAPI()


class TestRagSchemaValidation(unittest.TestCase):
    def test_roundtrip_all_four_entities_and_value_objects(self) -> None:
        quest = QuestRecord(
            quest_id=4921,
            name="Lost in Battle",
            zone="The Barrens",
            faction="Horde",
            quest_level=20,
            min_level=14,
            x=52.1,
            y=31.6,
            giver=QuestNpcRef(name="Mankrik", npc_id=3432, zone="The Barrens", x=52.1, y=31.6),
            turnin=QuestNpcRef(name="Mankrik", npc_id=3432, zone="The Barrens", x=52.1, y=31.6),
            objectives=["Find Mankrik's Wife at (49.3, 50.4)."],
            rewards=[QuestReward(item_name="Sample Reward", item_id=1234, quantity=1, choice=False)],
            aliases=["Esposa de Mankrik"],
            source_url="https://www.wowhead.com/classic/quest=4921/lost-in-battle",
        )
        self.assertEqual(quest.entity_type, "quest")
        self.assertEqual(QuestRecord.from_dict(quest.to_dict()).to_dict(), quest.to_dict())

        mob = MobRecord(
            npc_id=9019,
            name="Emperor Dagran Thaurissan",
            zone="Blackrock Depths",
            classification="Boss",
            level_min=59,
            level_max=59,
            dungeon_id=1584,
            dungeon_name="Blackrock Depths",
            drops=[MobDrop(item_name="Ironfoe", item_id=11684, drop_rate=1.0)],
        )
        self.assertEqual(mob.entity_type, "mob")
        self.assertEqual(MobRecord.from_dict(mob.to_dict()).to_dict(), mob.to_dict())

        item = ItemRecord(
            item_id=11684,
            name="Ironfoe",
            quality="Epic",
            item_level=60,
            req_level=55,
            item_type="One-Handed Mace",
            slot="Main Hand",
            bind_type="BoP",
            zone="Blackrock Depths",
            sources=[
                ItemSource(
                    source_type="boss",
                    source_name="Emperor Dagran Thaurissan",
                    source_id=9019,
                    zone="Blackrock Depths",
                    drop_rate=1.0,
                )
            ],
        )
        self.assertEqual(item.entity_type, "item")
        self.assertEqual(ItemRecord.from_dict(item.to_dict()).to_dict(), item.to_dict())

        dungeon = DungeonRecord(
            dungeon_id=1584,
            name="Blackrock Depths",
            zone="Blackrock Mountain",
            entrance_x=45.0,
            entrance_y=56.0,
            min_level=48,
            rec_level_min=52,
            rec_level_max=60,
            player_cap=5,
            bosses=["Emperor Dagran Thaurissan"],
        )
        self.assertEqual(dungeon.entity_type, "dungeon")
        self.assertEqual(DungeonRecord.from_dict(dungeon.to_dict()).to_dict(), dungeon.to_dict())

        self.assertIsInstance(validate_entity_dict("quest", quest.to_dict()), QuestRecord)

    def test_bounds_coords_drop_rate_levels_and_dungeon_caps(self) -> None:
        # Paired None coords allowed; half-None or out-of-range rejected
        MobRecord(npc_id=639, name="Edwin VanCleef", zone="The Deadmines", classification="Boss", level_min=20, level_max=21)
        with self.assertRaises(ClassicScopeError):
            QuestRecord(quest_id=1, name="Bad Coords", zone="Westfall", x=50.0, y=None)
        with self.assertRaises(ClassicScopeError):
            QuestRecord(quest_id=1, name="Out of Range", zone="Westfall", x=101.0, y=50.0)
        with self.assertRaises(ClassicScopeError):
            MobDrop(item_name="Bad Rate", drop_rate=105.0)
        with self.assertRaises(ClassicScopeError):
            MobDrop(item_name="Negative Rate", drop_rate=-0.5)

        # Raid Boss level <= 63 allowed; > 63 rejected; non-boss > 60 rejected; elite <= 62
        MobRecord(npc_id=12057, name="Garr", zone="Molten Core", classification="Boss", level_min=63, level_max=63)
        MobRecord(npc_id=99999, name="Elite Guard", zone="Silithus", classification="Elite", level_min=61, level_max=62)
        with self.assertRaises(ClassicScopeError):
            MobRecord(npc_id=1, name="Lvl 64 Boss", zone="Molten Core", classification="Boss", level_min=64, level_max=64)
        with self.assertRaises(ClassicScopeError):
            MobRecord(npc_id=2, name="Lvl 61 Normal", zone="Silithus", classification="Normal", level_min=61, level_max=61)

        # Item level <= 95 allowed (Naxxramas); >= 100 rejected; req_level > 60 rejected
        ItemRecord(item_id=22691, name="Corrupted Ashbringer", quality="Epic", item_level=88, req_level=60)
        with self.assertRaises(ClassicScopeError):
            ItemRecord(item_id=28438, name="TBC Mace", quality="Epic", item_level=120, req_level=60)
        with self.assertRaises(ClassicScopeError):
            ItemRecord(item_id=28439, name="Lvl 70 Item", quality="Rare", item_level=90, req_level=70)

        # Valid dungeon caps {5, 10, 20, 40}; 25-man rejected
        for cap in (5, 10, 20, 40):
            DungeonRecord(dungeon_id=2717, name="Molten Core", zone="Blackrock Mountain", min_level=55, rec_level_min=60, rec_level_max=60, player_cap=cap)
        with self.assertRaises(ClassicScopeError):
            DungeonRecord(dungeon_id=2717, name="Molten Core", zone="Blackrock Mountain", min_level=55, rec_level_min=60, rec_level_max=60, player_cap=25)


class TestClassicOnlyBoundaryRejection(unittest.TestCase):
    def test_rejects_non_classic_eras_zones_classes_dungeons_and_urls(self) -> None:
        for bad_era in ("2.4.3", "3.3.5", "1.14.0", "retail"):
            with self.assertRaises(ValueError) as ctx:
                QuestRecord(quest_id=1, name="Test", zone="Elwynn Forest", era_version=bad_era)
            self.assertIsInstance(ctx.exception, ClassicScopeError)

        for bad_tag in ("tbc", "wotlk", "cata", "mop", "sod"):
            with self.assertRaises(ClassicScopeError):
                ItemRecord(item_id=1, name="Test Item", tags=[bad_tag])

        for bad_zone in ("Hellfire Peninsula", "Nagrand", "Icecrown", "Dalaran", "Jade Forest"):
            with self.assertRaises(ClassicScopeError):
                MobRecord(npc_id=10, name="Alien Mob", zone=bad_zone)

        for bad_cls in ("Death Knight", "Monk", "Demon Hunter", "Evoker"):
            with self.assertRaises(ClassicScopeError):
                QuestRecord(quest_id=10, name="Class Quest", zone="Elwynn Forest", class_restriction=[bad_cls])

        for bad_dungeon in ("Karazhan", "Hellfire Ramparts", "Ulduar", "Utgarde Keep"):
            with self.assertRaises(ClassicScopeError):
                DungeonRecord(dungeon_id=9999, name=bad_dungeon, zone="Eastern Kingdoms", player_cap=10)

        for bad_url in (
            "https://www.wowhead.com/tbc/item=28438",
            "https://www.wowhead.com/wotlk/npc=36597",
            "https://www.wowhead.com/item=11684",
            "http://www.wowhead.com/classic/item=11684",
        ):
            with self.assertRaises(ClassicScopeError):
                ItemRecord(item_id=11684, name="Ironfoe", source_url=bad_url)

    def test_non_classic_query_detection_helper(self) -> None:
        self.assertTrue(is_non_classic_query("Where is Utgarde Keep in Northrend?"))
        self.assertTrue(is_non_classic_query("Death Knight starting gear in Outland"))
        self.assertIn("karazhan", detect_non_classic_terms("How to attune for Karazhan?"))
        self.assertFalse(is_non_classic_query("Donde esta la esposa de Mankrik en Los Baldios?"))


class TestClassicSeedIntegrity(unittest.TestCase):
    def test_seed_json_validates_cleanly_without_bom(self) -> None:
        raw_bytes = DEFAULT_SEED_PATH.read_bytes()
        self.assertFalse(raw_bytes.startswith(b"\xef\xbb\xbf"), "Seed JSON must be UTF-8 without BOM")
        seed = json.loads(raw_bytes.decode("utf-8"))

        self.assertEqual(seed["schema_version"], 1)
        self.assertEqual(seed["era_version"], "1.15.x")
        self.assertGreaterEqual(len(seed["quests"]), 11)
        self.assertGreaterEqual(len(seed["mobs"]), 14)
        self.assertGreaterEqual(len(seed["items"]), 11)
        self.assertGreaterEqual(len(seed["dungeons"]), 14)

        for etype, key in (("quest", "quests"), ("mob", "mobs"), ("item", "items"), ("dungeon", "dungeons")):
            for entry in seed[key]:
                rec = validate_entity_dict(etype, entry)
                self.assertEqual(rec.era_version, "1.15.x")


class TestRagStoreFTS5AndRetrieval(unittest.TestCase):
    def test_autobuild_rebuild_stats_and_idempotent_upsert(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "rag.db"
            with ClassicRagStore(db_path=db_path, auto_build=True) as store:
                st = store.stats()
                self.assertGreaterEqual(st["quests"], 11)
                self.assertGreaterEqual(st["mobs"], 14)
                self.assertGreaterEqual(st["items"], 11)
                self.assertGreaterEqual(st["dungeons"], 14)
                self.assertEqual(st["total"], st["quests"] + st["mobs"] + st["items"] + st["dungeons"])

                # Idempotent rebuild keeps exact counts
                rebuilt = store.rebuild()
                self.assertEqual(rebuilt, st)

                # Idempotent upsert updates existing record without duplicating
                store.upsert_item(
                    ItemRecord(
                        item_id=11684,
                        name="Ironfoe",
                        quality="Epic",
                        item_level=60,
                        req_level=55,
                        bind_type="BoP",
                        zone="Blackrock Depths",
                        aliases=["Hojahierro"],
                        source_url="https://www.wowhead.com/classic/item=11684/ironfoe",
                    )
                )
                self.assertEqual(store.stats(), st)

    def test_fts5_sanitization_and_multilingual_bm25_ranking(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "rag.db"
            with ClassicRagStore(db_path=db_path, auto_build=True) as store:
                # Fuzz / injection / special-character queries must never raise OperationalError
                nasty_queries = [
                    '[JINY_Q#100-42#esES] ¿Dónde está [Mankrik\'s Wife] (49.3/50.4)? % * " \' : - + AND OR NOT NEAR',
                    '"""((()))***///:::',
                    "AND OR NOT NEAR",
                    "",
                    "   ???   ",
                ]
                for q in nasty_queries:
                    res = store.retrieve(q, top_k=3)
                    self.assertIsInstance(res, list)

                # All 4 entity types return exact top hits
                q_hits = store.retrieve("Mankrik's Wife", top_k=3, entity_type="quest")
                self.assertTrue(q_hits)
                self.assertEqual(q_hits[0].entity_id, 4921)

                m_hits = store.retrieve("Emperor Dagran Thaurissan", top_k=3, entity_type="mob")
                self.assertTrue(m_hits)
                self.assertEqual(m_hits[0].entity_id, 9019)

                i_hits = store.retrieve("Ironfoe", top_k=3, entity_type="item")
                self.assertTrue(i_hits)
                self.assertEqual(i_hits[0].entity_id, 11684)

                d_hits = store.retrieve("BRD", top_k=3, entity_type="dungeon")
                self.assertTrue(d_hits)
                self.assertEqual(d_hits[0].entity_id, 1584)

                # Short token SQL LIKE fallback ("MC" -> Molten Core)
                mc_hits = store.retrieve("MC", top_k=3, entity_type="dungeon")
                self.assertTrue(mc_hits)
                self.assertEqual(mc_hits[0].entity_id, 2717)

                # Cross-lingual ES/IT + diacritic folding
                self.assertEqual(store.retrieve("corazón de león", top_k=2, entity_type="item")[0].entity_id, 12640)
                self.assertEqual(store.retrieve("esposa de mankrik", top_k=2, entity_type="quest")[0].entity_id, 4921)
                self.assertEqual(store.retrieve("Miniere della Morte", top_k=2, entity_type="dungeon")[0].entity_id, 1581)
                self.assertEqual(store.retrieve("Profondità di Roccianera", top_k=2, entity_type="dungeon")[0].entity_id, 1584)

                # Non-Classic queries abstain cleanly without surfacing unrelated Classic records
                self.assertEqual(store.retrieve("Illidan Black Temple"), [])
                self.assertEqual(store.retrieve("Where is Utgarde Keep?"), [])


class TestWowheadClassicScraper(unittest.TestCase):
    def test_url_allowlist_and_expansion_rejection(self) -> None:
        etype, eid, canon = validate_classic_url("https://www.wowhead.com/classic/it/zone=1584/profondit%C3%A0-di-roccianera")
        self.assertEqual((etype, eid, canon), ("zone", 1584, "https://www.wowhead.com/classic/zone=1584"))

        etype2, eid2, canon2 = validate_classic_url("https://es.wowhead.com/classic/item=11684/ironfoe")
        self.assertEqual((etype2, eid2, canon2), ("item", 11684, "https://www.wowhead.com/classic/item=11684"))

        for bad in (
            "https://www.wowhead.com/tbc/item=28438",
            "https://www.wowhead.com/wotlk/npc=36597",
            "https://www.wowhead.com/cata/zone=1581",
            "https://www.wowhead.com/mop-classic/quest=30000",
            "https://www.wowhead.com/item=11684",
            "http://www.wowhead.com/classic/item=11684",
            "https://www.wowhead.com/classic/spell=133",
        ):
            with self.assertRaises(ClassicScopeError):
                validate_classic_url(bad)

    def test_offline_fixtures_parse_validate_and_upsert(self) -> None:
        item_html = """
        <html><head>
        <link rel="canonical" href="https://www.wowhead.com/classic/item=11684/ironfoe" />
        <title>Ironfoe - Item - Classic World of Warcraft</title>
        </head><body>
        <h1>Ironfoe</h1>
        <div>Binds when picked up. Item Level 60. Requires Level 55. Zone: Blackrock Depths.</div>
        <script>
        WH.Gatherer.addData(3, 11684, {name_enus: "Ironfoe", quality: 4, level: 60, reqlevel: 55});
        new Listview({template: 'npc', id: 'dropped-by', data: [{id: 9019, name: 'Emperor Dagran Thaurissan', classification: 3, count: 12, outof: 1000}, {id: 99999, name: 'Mystery Chest', count: 1, outof: 0}]});
        </script></body></html>
        """
        quest_html = """
        <html><head><title>Lost in Battle - Quest</title></head><body>
        <h1>Lost in Battle</h1>
        <div>Zone: The Barrens Faction: Horde Level: 20 Min Level: 14</div>
        <script>
        g_mapperData[17] = [{"coords": [[49.3, 50.4]]}];
        </script></body></html>
        """
        mob_html = """
        <html><head><title>Hogger - NPC</title></head><body>
        <h1>Hogger</h1>
        <div>Zone: Elwynn Forest Level: 11 Classification: Elite Type: Humanoid</div>
        <script>
        g_mapperData[12] = [[26.2, 92.3]];
        new Listview({template: 'item', id: 'drops', data: [{id: 1931, name: 'Huge Gnoll Claw', count: 50, outof: 50}]});
        </script></body></html>
        """
        dungeon_html = """
        <html><head><title>Blackrock Depths - Zone</title></head><body>
        <h1>Blackrock Depths</h1>
        <div>Zone: Blackrock Mountain Players: 5 Level: 52-60 Min Level: 48</div>
        <script>
        g_mapperData = {46: [[45.0, 56.0]]};
        new Listview({template: 'npc', id: 'bosses', data: [{id: 9019, name: 'Emperor Dagran Thaurissan'}]});
        </script></body></html>
        """
        tooltip_json = json.dumps(
            {
                "name": "Hand of Justice",
                "quality": 3,
                "tooltip": "<table><tr><td>Binds when picked up</td></tr><tr><td>Item Level 58</td></tr><tr><td>Requires Level 53</td></tr></table>",
            }
        )

        fixtures = {
            "https://www.wowhead.com/classic/item=11684": item_html,
            "https://www.wowhead.com/classic/quest=4921": quest_html,
            "https://www.wowhead.com/classic/npc=448": mob_html,
            "https://www.wowhead.com/classic/zone=1584": dungeon_html,
            "https://nether.wowhead.com/classic/tooltip/item/11815": tooltip_json,
        }

        def fake_fetcher(url: str) -> str:
            if url not in fixtures:
                raise ScraperError(f"Unexpected URL {url}")
            return fixtures[url]

        with tempfile.TemporaryDirectory() as tmp:
            with ClassicRagStore(db_path=Path(tmp) / "scrape.db", auto_build=True) as store:
                updated = update_store_from_urls(list(fixtures.keys()), store, fetcher=fake_fetcher)
                self.assertEqual(updated, 5)
                item_rec = store.get_entity("item", 11684)
                self.assertIsNotNone(item_rec)
                # Preserved seed alias while updating drop rate from Listview (12/1000 -> 1.2%)
                self.assertIn("Hojahierro", item_rec["aliases"])
                self.assertEqual(item_rec["sources"][0]["drop_rate"], 1.2)
                self.assertIsNone(item_rec["sources"][1]["drop_rate"])  # outof == 0 -> None

        # Reject scraped non-Classic payload (e.g. Level 70 TBC item)
        bad_html = """
        <html><head><title>TBC Blade</title></head><body>
        <h1>Warglaive</h1>
        <div>Requires Level 70. Zone: Outland.</div>
        </body></html>
        """
        with self.assertRaises(ClassicScopeError):
            scrape_entity("https://www.wowhead.com/classic/item=32837", fetcher=lambda _u: bad_html)


class TestPromptGroundingAndClient(unittest.TestCase):
    def test_format_rag_context_and_client_grounding(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            with ClassicRagStore(db_path=Path(tmp) / "prompt.db", auto_build=True) as store:
                hits = store.retrieve("Ironfoe", top_k=2, entity_type="item")
                ctx = format_rag_context(hits, locale="esES", query="Donde cae Ironfoe?")
                self.assertIn("[CLASSIC_ERA_CONTEXT]", ctx)
                self.assertIn("1.15.x", ctx)
                self.assertIn("Ironfoe", ctx)
                self.assertIn("1.0%", ctx)
                self.assertIn("https://www.wowhead.com/classic/item=11684/ironfoe", ctx)

                empty_ctx = format_rag_context([], locale="enUS", query="Where is Utgarde Keep?")
                self.assertIn("NO_LOCAL_RAG_MATCH", empty_ctx)
                self.assertIn("NON_CLASSIC_SCOPE", empty_ctx)

                grounded = build_grounded_input("Donde cae Ironfoe?", hits, locale="esES")
                self.assertIn("[CLASSIC_ERA_CONTEXT]", grounded)
                self.assertIn("Donde cae Ironfoe?", grounded)

                fake = _FakeGenAIClient()
                client = JinyGeminiClient(api_key="dummy", model="gemini-3.8-flash", client=fake)
                # Backward-compatible when context is None
                client.ask("Hola Jiny", locale="esES")
                self.assertEqual(fake.interactions.calls[0]["input"], "Hola Jiny")
                self.assertIn("Classic Forever", fake.interactions.calls[0]["system_instruction"])

                # Grounded when context is supplied
                client.ask("Donde cae Ironfoe?", locale="esES", context=ctx)
                self.assertIn("[CLASSIC_ERA_CONTEXT]", fake.interactions.calls[1]["input"])
                self.assertIn("Ironfoe", fake.interactions.calls[1]["input"])
                self.assertEqual(apply_rag_context("Q", "", locale="esES"), "Q")
                self.assertIn("NO_LOCAL_RAG_MATCH", build_system_instruction("esES"))


class TestCompanionCliRagFlows(unittest.TestCase):
    def test_cli_rag_commands_and_dry_run_offline(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            db_path = tmp_path / "cli_rag.db"
            cfg_path = tmp_path / "config.json"
            lua_out = tmp_path / "CompanionData.lua"
            cfg_path.write_text(
                json.dumps(
                    {
                        "api_key": "",
                        "model": "gemini-3.8-flash",
                        "wow_forever_dir": str(tmp_path / "_forever_"),
                        "rag_enabled": True,
                        "rag_db_path": str(db_path),
                        "rag_seed_path": str(DEFAULT_SEED_PATH),
                        "rag_top_k": 3,
                    }
                ),
                encoding="utf-8",
            )

            with patch.dict(os.environ, {"GEMINI_API_KEY": ""}, clear=False):
                cfg = load_config(cfg_path)
                self.assertTrue(cfg.rag_enabled)
                self.assertEqual(cfg.rag_db_path, db_path.resolve())
                self.assertEqual(cfg.rag_top_k, 3)

                buf = io.StringIO()
                with redirect_stdout(buf):
                    rc = companion_main(["--config", str(cfg_path), "--rag-rebuild"])
                self.assertEqual(rc, 0)
                self.assertIn("Rebuilt Classic Era 1.15.x", buf.getvalue())
                self.assertTrue(db_path.exists())

                buf = io.StringIO()
                with redirect_stdout(buf):
                    rc = companion_main(["--config", str(cfg_path), "--rag-stats"])
                self.assertEqual(rc, 0)
                self.assertIn("Quests", buf.getvalue())

                buf = io.StringIO()
                with redirect_stdout(buf):
                    rc = companion_main(
                        [
                            "--config",
                            str(cfg_path),
                            "--rag-query",
                            "Ironfoe",
                            "--rag-type",
                            "item",
                            "--rag-top-k",
                            "2",
                        ]
                    )
                self.assertEqual(rc, 0)
                self.assertIn("[CLASSIC_ERA_CONTEXT]", buf.getvalue())
                self.assertIn("Ironfoe", buf.getvalue())

                with patch("companion.main._resolve_target_paths", return_value=[lua_out]):
                    buf = io.StringIO()
                    with redirect_stdout(buf):
                        rc = companion_main(
                            [
                                "--config",
                                str(cfg_path),
                                "--ask",
                                "¿Dónde cae Ironfoe?",
                                "--dry-run",
                                "--lang",
                                "esES",
                            ]
                        )
                    self.assertEqual(rc, 0)
                    self.assertIn("Ironfoe", buf.getvalue())
                    self.assertTrue(lua_out.exists())
                    self.assertIn("Ironfoe", lua_out.read_text(encoding="utf-8"))

                    buf = io.StringIO()
                    with redirect_stdout(buf):
                        rc = companion_main(
                            [
                                "--config",
                                str(cfg_path),
                                "--ask",
                                "¿Dónde cae Ironfoe?",
                                "--no-rag",
                                "--dry-run",
                                "--lang",
                                "esES",
                            ]
                        )
                    self.assertEqual(rc, 0)
                    self.assertIn("RAG=DISABLED", buf.getvalue())

                buf = io.StringIO()
                with redirect_stdout(buf):
                    rc = companion_main(["--config", str(cfg_path), "--status"])
                self.assertEqual(rc, 0)
                self.assertIn("RAG enabled", buf.getvalue())


if __name__ == "__main__":
    unittest.main(verbosity=2)
