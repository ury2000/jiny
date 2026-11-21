"""Unit tests for Jiny Companion (baseline + discovered feature suites)."""

import importlib
from pathlib import Path
import sys
import tempfile
import unittest
import warnings

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from companion.config import DEFAULT_MODEL, sanitize_model_name
from companion.gemini_client import JinyGeminiClient
from companion.log_reader import ChatLogReader, extract_savedvariables_outbox, parse_query_line
from companion.lua_writer import escape_lua_string, render_companion_lua, write_companion_data


class FakeInteraction:
    def __init__(self, interaction_id: str, output_text: str) -> None:
        self.id = interaction_id
        self.output_text = output_text


class FakeInteractionsAPI:
    def __init__(self) -> None:
        self.calls: list[dict] = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        idx = len(self.calls)
        return FakeInteraction(f"int-{idx}", f"Respuesta #{idx} para: {kwargs['input']}")


class FakeGenAIClient:
    def __init__(self) -> None:
        self.interactions = FakeInteractionsAPI()


class TestLogReader(unittest.TestCase):
    def test_privacy_filter_ignores_normal_chat(self) -> None:
        self.assertIsNone(parse_query_line("11/21 20:30:01.000  [Guild] Arthas: hola grupo"))
        self.assertIsNone(parse_query_line("11/21 20:30:02.000  [Whisper] Mankrik: secreto"))
        parsed = parse_query_line(
            "11/21 20:30:03.000  To [Azok]: [JINY_Q#1795-1234#esES] Donde esta Mankrik?"
        )
        self.assertEqual(parsed, ("1795-1234", "esES", "Donde esta Mankrik?"))

    def test_deduplicates_whisper_and_whisper_inform(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            log_path = Path(tmp) / "WoWChatLog.txt"
            log_path.write_text("", encoding="utf-8")
            reader = ChatLogReader(log_path, start_at_end=False)

            with log_path.open("a", encoding="utf-8") as fh:
                fh.write("11/21 20:31:00.000  [Guild] Bob: Ignorar esto\n")
                fh.write("11/21 20:31:01.000  To [Azok]: [JINY_Q#100-42#esES] Donde cae Ironfoe?\n")
                fh.write("11/21 20:31:01.050  [Azok] whispers: [JINY_Q#100-42#esES] Donde cae Ironfoe?\n")

            batch1 = reader.poll()
            self.assertEqual(batch1, [("100-42", "esES", "Donde cae Ironfoe?")])

            # Polling again with no new lines returns empty
            self.assertEqual(reader.poll(), [])

            # Log rotation / truncation resets offset cleanly
            log_path.write_text(
                "11/21 20:32:00.000  To [Azok]: [JINY_Q#101-99#enUS] Level cap?\n",
                encoding="utf-8",
            )
            batch2 = reader.poll()
            self.assertEqual(batch2, [("101-99", "enUS", "Level cap?")])

    def test_savedvariables_outbox_fallback(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            sv = Path(tmp) / "Jiny.lua"
            sv.write_text(
                'JinyDB = {\n'
                '  ["outbox"] = {\n'
                '    {\n'
                '      ["id"] = "sv-77",\n'
                '      ["q"] = "Mejor ruta \\"Crossroads\\"?",\n'
                '      ["lang"] = "esES",\n'
                '      ["t"] = 1795285584,\n'
                '    },\n'
                '  },\n'
                '}\n',
                encoding="utf-8",
            )
            seen: set[str] = set()
            items = extract_savedvariables_outbox(sv, seen)
            self.assertEqual(items, [("sv-77", "esES", 'Mejor ruta "Crossroads"?')])
            self.assertEqual(extract_savedvariables_outbox(sv, seen), [])


class TestLuaWriter(unittest.TestCase):
    def test_escape_and_atomic_write(self) -> None:
        escaped = escape_lua_string('Línea 1 "cita" \\ ruta\nLínea 2')
        self.assertEqual(escaped, 'Línea 1 \\"cita\\" \\\\ ruta\\nLínea 2')

        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "CompanionData.lua"
            write_companion_data(
                [target],
                [
                    {
                        "id": "100-42",
                        "lang": "esES",
                        "q": 'Drop de "Ironfoe"?',
                        "a": "Cae de Emperor Dagran Thaurissan en BRD.\nProbabilidad baja (~1-2%).",
                        "t": 1795285600,
                    }
                ],
                status="online",
                updated_at=1795285600,
            )
            raw = target.read_bytes()
            self.assertFalse(raw.startswith(b"\xef\xbb\xbf"))
            text = raw.decode("utf-8")
            self.assertTrue(text.startswith("local ADDON, ns = ..."))
            self.assertIn('id = "100-42"', text)
            self.assertIn('companionStatus = "online"', text)
            self.assertFalse(target.with_suffix(".lua.tmp").exists())

    def test_render_caps_last_50(self) -> None:
        many = [{"id": f"id-{i}", "q": "q", "a": "a", "lang": "enUS", "t": i} for i in range(60)]
        rendered = render_companion_lua(many, updated_at=100)
        self.assertNotIn('id = "id-0"', rendered)
        self.assertIn('id = "id-59"', rendered)


class TestGeminiClient(unittest.TestCase):
    def test_stateful_interactions_and_model_guard(self) -> None:
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            model = sanitize_model_name("gemini-1.5-flash")
        self.assertEqual(model, DEFAULT_MODEL)
        self.assertTrue(len(caught) == 1)

        fake = FakeGenAIClient()
        client = JinyGeminiClient(api_key="test-key", model="gemini-3.8-flash", client=fake)

        r1 = client.ask("Donde esta Mankrik?", locale="esES")
        self.assertIn("Respuesta #1", r1)
        self.assertEqual(fake.interactions.calls[0]["model"], "gemini-3.8-flash")
        self.assertNotIn("previous_interaction_id", fake.interactions.calls[0])
        self.assertIn("Classic Forever", fake.interactions.calls[0]["system_instruction"])

        r2 = client.ask("Y que nivel recomiendas?", locale="esES")
        self.assertIn("Respuesta #2", r2)
        self.assertEqual(fake.interactions.calls[1]["previous_interaction_id"], "int-1")


def load_tests(
    loader: unittest.TestLoader,
    tests: unittest.TestSuite,
    pattern: str | None,
) -> unittest.TestSuite:
    """Include sibling feature test modules when running test_companion.py directly."""
    if pattern is None:
        tools_dir = Path(__file__).resolve().parent
        if str(tools_dir) not in sys.path:
            sys.path.insert(0, str(tools_dir))
        for module_name in ("test_rag", "test_v04", "test_integration"):
            if (tools_dir / f"{module_name}.py").exists():
                mod = importlib.import_module(module_name)
                tests.addTests(loader.loadTestsFromModule(mod))
    return tests


if __name__ == "__main__":
    unittest.main(verbosity=2)