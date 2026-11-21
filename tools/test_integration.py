"""Combined offline integration tests for Jiny v0.3 (RAG) + v0.4 (Providers, TTS, Overlay, Config)."""

from __future__ import annotations

import contextlib
from http.server import BaseHTTPRequestHandler, HTTPServer
import io
import json
import math
import os
from pathlib import Path
import sys
import tempfile
import threading
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from companion.config import CompanionConfig, DEFAULT_MODEL, DEFAULT_RAG_SEED_PATH, load_config
from companion.gemini_client import JinyGeminiClient
from companion.main import cmd_ask, cmd_watch, main as companion_main
from companion.oauth import OAuthManager, OAuthToken
from companion.overlay import OverlayManager
from companion.providers import GeminiOAuthProvider, OllamaProvider
from companion.tts import TTSBackend, TTSManager


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
        return _FakeInteraction(
            f"int-{idx}",
            f"Grounded reply #{idx} | [JINY_MACRO name=\"Test\"] /cast Frostbolt [/JINY_MACRO]",
        )


class _FakeGenAIClient:
    def __init__(self) -> None:
        self.interactions = _FakeInteractionsAPI()


class _RecordingTTSBackend(TTSBackend):
    name = "recording_tts"

    def __init__(self) -> None:
        self.spoken: list[tuple[str, str]] = []

    def is_available(self) -> bool:
        return True

    def speak(self, text: str, locale: str = "esES") -> None:
        self.spoken.append((locale, text))


class TestCombinedRagProvidersOutputsIntegration(unittest.TestCase):
    def _make_cfg(self, tmp_path: Path, **overrides) -> CompanionConfig:
        wow_dir = tmp_path / "_forever_"
        (wow_dir / "Logs").mkdir(parents=True, exist_ok=True)
        defaults = dict(
            api_key="dummy-api-key",
            model=DEFAULT_MODEL,
            wow_forever_dir=wow_dir,
            chat_log_path=wow_dir / "Logs" / "WoWChatLog.txt",
            dev_companion_data_path=tmp_path / "CompanionData.lua",
            deployed_companion_data_path=wow_dir / "Interface" / "AddOns" / "Jiny" / "CompanionData.lua",
            wtf_account_dir=wow_dir / "WTF" / "Account",
            poll_interval_seconds=0.05,
            rag_enabled=True,
            rag_db_path=tmp_path / "classic_era_rag.db",
            rag_seed_path=DEFAULT_RAG_SEED_PATH,
            rag_top_k=3,
            oauth_client_id="cid-integration",
            oauth_token_path=tmp_path / "oauth_token.json",
            tts_enabled=True,
            overlay_enabled=False,
            overlay_theme="DarkGlass",
        )
        defaults.update(overrides)
        return CompanionConfig(**defaults)

    def test_e2e_rag_plus_api_key_provider_tts_overlay_and_no_rag_toggle(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            cfg = self._make_cfg(tmp_path, provider="gemini_api_key")
            fake_genai = _FakeGenAIClient()
            client = JinyGeminiClient(api_key="dummy-api-key", model=DEFAULT_MODEL, client=fake_genai)
            rec_tts = _RecordingTTSBackend()
            tts_mgr = TTSManager(enabled=True, backend=rec_tts)
            ov_mgr = OverlayManager(enabled=False, theme="DarkGlass")

            with mock.patch.dict(os.environ, {"GEMINI_API_KEY": ""}, clear=False):
                with mock.patch("companion.main.JinyGeminiClient", return_value=client):
                    with mock.patch("companion.main._resolve_target_paths", return_value=[cfg.dev_companion_data_path]):
                        buf = io.StringIO()
                        with contextlib.redirect_stdout(buf):
                            rc = cmd_ask(
                                cfg=cfg,
                                question="¿Dónde cae Ironfoe?",
                                locale="esES",
                                req_id="int-api-1",
                                dry_run=False,
                                write_deployed=False,
                                tts=tts_mgr,
                                overlay=ov_mgr,
                            )

                self.assertEqual(rc, 0)
                self.assertEqual(len(fake_genai.interactions.calls), 1)
                sent_input = fake_genai.interactions.calls[0]["input"]
                self.assertIn("[CLASSIC_ERA_CONTEXT]", sent_input)
                self.assertIn("Ironfoe", sent_input)
                self.assertIn("1.0%", sent_input)
                self.assertIn("Grounding rule:", sent_input)
                self.assertEqual(ov_mgr.backend.last_snapshot["status"], "online")
                self.assertIn("Grounded reply #1", ov_mgr.backend.last_snapshot["latest_reply"])
                self.assertEqual(len(rec_tts.spoken), 1)
                self.assertNotIn("[JINY_MACRO", rec_tts.spoken[0][1])
                lua_text = cfg.dev_companion_data_path.read_text(encoding="utf-8")
                self.assertIn("int-api-1", lua_text)

                # With --no-rag (no_rag=True), prompt must NOT contain [CLASSIC_ERA_CONTEXT]
                with mock.patch("companion.main.JinyGeminiClient", return_value=client):
                    with mock.patch("companion.main._resolve_target_paths", return_value=[cfg.dev_companion_data_path]):
                        with contextlib.redirect_stdout(io.StringIO()):
                            rc2 = cmd_ask(
                                cfg=cfg,
                                question="¿Dónde cae Ironfoe?",
                                locale="esES",
                                req_id="int-api-2",
                                dry_run=False,
                                write_deployed=False,
                                no_rag=True,
                                tts=tts_mgr,
                                overlay=ov_mgr,
                            )
                self.assertEqual(rc2, 0)
                self.assertEqual(fake_genai.interactions.calls[1]["input"], "¿Dónde cae Ironfoe?")

            tts_mgr.close()
            ov_mgr.close()

    def test_e2e_rag_plus_oauth_provider_bearer_and_non_classic_scope(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            cfg = self._make_cfg(tmp_path, api_key="", provider="gemini_oauth")
            seen_payloads: list[dict] = []

            def fake_http(url: str, headers: dict[str, str], body: bytes | None, timeout: float):
                payload = json.loads((body or b"{}").decode("utf-8"))
                seen_payloads.append(payload)
                return 200, json.dumps(
                    {
                        "id": f"oauth-int-{len(seen_payloads)}",
                        "output_text": "Baron Rivendare drops Deathcharger's Reins (1.0%) in Stratholme.",
                    }
                ).encode("utf-8")

            mgr = OAuthManager(
                client_id="cid-integration",
                token_path=cfg.oauth_token_path,
                http_transport=fake_http,
                clock=lambda: 1000.0,
            )
            mgr.store.save(OAuthToken(access_token="tok-live-fake", expires_at=5000.0))
            oauth_provider = GeminiOAuthProvider(
                oauth_manager=mgr,
                model=DEFAULT_MODEL,
                vertexai=False,
                http_transport=fake_http,
            )
            rec_tts = _RecordingTTSBackend()
            tts_mgr = TTSManager(enabled=True, backend=rec_tts)
            ov_mgr = OverlayManager(enabled=False, theme="DarkGlass")

            with mock.patch.dict(os.environ, {"GEMINI_API_KEY": ""}, clear=False):
                with mock.patch("companion.main._resolve_target_paths", return_value=[cfg.dev_companion_data_path]):
                    with contextlib.redirect_stdout(io.StringIO()):
                        rc1 = cmd_ask(
                            cfg=cfg,
                            question="Deathcharger's Reins drop rate?",
                            locale="enUS",
                            req_id="int-oauth-1",
                            dry_run=False,
                            write_deployed=False,
                            provider=oauth_provider,
                            tts=tts_mgr,
                            overlay=ov_mgr,
                        )
                        rc2 = cmd_ask(
                            cfg=cfg,
                            question="Where is Outland Hellfire Citadel?",
                            locale="enUS",
                            req_id="int-oauth-2",
                            dry_run=False,
                            write_deployed=False,
                            provider=oauth_provider,
                            tts=tts_mgr,
                            overlay=ov_mgr,
                        )

            tts_mgr.close()
            ov_mgr.close()
            self.assertEqual(rc1, 0)
            self.assertEqual(rc2, 0)
            self.assertEqual(len(seen_payloads), 2)
            self.assertIn("[CLASSIC_ERA_CONTEXT]", seen_payloads[0]["input"])
            self.assertIn("13335", seen_payloads[0]["input"])
            self.assertIn("Grounding rule:", seen_payloads[0]["input"])
            self.assertEqual(seen_payloads[1]["previous_interaction_id"], "oauth-int-1")
            self.assertIn("NON_CLASSIC_SCOPE", seen_payloads[1]["input"])
            self.assertIn("NO_LOCAL_RAG_MATCH", seen_payloads[1]["input"])
            self.assertEqual(len(rec_tts.spoken), 2)

    def test_e2e_rag_plus_ollama_local_http_server_cmd_ask_and_watch(self) -> None:
        received_requests: list[dict] = []

        class _MockOllamaHandler(BaseHTTPRequestHandler):
            def do_POST(self):
                length = int(self.headers.get("Content-Length", "0"))
                body = json.loads(self.rfile.read(length).decode("utf-8"))
                received_requests.append(body)
                resp = json.dumps(
                    {
                        "message": {
                            "role": "assistant",
                            "content": "Mankrik is in The Barrens (Crossroads).",
                        }
                    }
                ).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(resp)))
                self.end_headers()
                self.wfile.write(resp)

            def log_message(self, format, *args):
                return

        server = HTTPServer(("127.0.0.1", 0), _MockOllamaHandler)
        port = server.server_address[1]
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()

        try:
            with tempfile.TemporaryDirectory() as tmp:
                tmp_path = Path(tmp)
                cfg = self._make_cfg(
                    tmp_path,
                    api_key="",
                    provider="ollama",
                    ollama_base_url=f"http://127.0.0.1:{port}",
                    ollama_model="llama3.1:8b",
                )
                cfg.chat_log_path.write_text(
                    "11/21 20:31:01.000  To [Azok]: [JINY_Q#ol-1#enUS] Where is Mankrik?\n"
                    "11/21 20:31:02.000  To [Azok]: [JINY_Q#ol-2#enUS] Where is Icecrown Citadel?\n",
                    encoding="utf-8",
                )

                rec_tts = _RecordingTTSBackend()
                tts_mgr = TTSManager(enabled=True, backend=rec_tts)
                ov_mgr = OverlayManager(enabled=False, theme="DarkGlass")

                with mock.patch.dict(os.environ, {"GEMINI_API_KEY": ""}, clear=False):
                    with mock.patch("companion.main._resolve_target_paths", return_value=[cfg.dev_companion_data_path]):
                        with mock.patch("companion.main.time.sleep", side_effect=KeyboardInterrupt):
                            with contextlib.redirect_stdout(io.StringIO()):
                                rc = cmd_watch(
                                    cfg=cfg,
                                    start_from_beginning=True,
                                    tts=tts_mgr,
                                    overlay=ov_mgr,
                                )

                tts_mgr.flush(timeout=2.0)
                tts_mgr.close()
                ov_mgr.close()

                self.assertEqual(rc, 0)
                self.assertEqual(len(received_requests), 2)
                q1_user_msg = received_requests[0]["messages"][-1]["content"]
                self.assertIn("[CLASSIC_ERA_CONTEXT]", q1_user_msg)
                self.assertIn("Mankrik", q1_user_msg)
                self.assertIn("Grounding rule:", q1_user_msg)
                q2_user_msg = received_requests[1]["messages"][-1]["content"]
                self.assertIn("NON_CLASSIC_SCOPE", q2_user_msg)
                self.assertEqual(len(rec_tts.spoken), 2)
                lua_text = cfg.dev_companion_data_path.read_text(encoding="utf-8")
                self.assertIn("ol-1", lua_text)
                self.assertIn("ol-2", lua_text)
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2.0)

    def test_cli_combined_v03_and_v04_flags_offline(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            cfg_path = tmp_path / "config.json"
            lua_out = tmp_path / "CompanionData.lua"
            cfg_path.write_text(
                json.dumps(
                    {
                        "api_key": "",
                        "wow_forever_dir": str(tmp_path / "_forever_"),
                        "rag_enabled": True,
                        "rag_db_path": str(tmp_path / "cli_combined.db"),
                        "rag_seed_path": str(DEFAULT_RAG_SEED_PATH),
                        "rag_top_k": 4,
                    }
                ),
                encoding="utf-8",
            )

            with mock.patch.dict(os.environ, {"GEMINI_API_KEY": ""}, clear=False):
                buf_status = io.StringIO()
                with contextlib.redirect_stdout(buf_status):
                    rc_status = companion_main(
                        [
                            "--config",
                            str(cfg_path),
                            "--status",
                            "--provider",
                            "ollama",
                            "--tts",
                            "--overlay",
                            "--overlay-theme",
                            "DarkGlass",
                        ]
                    )
                self.assertEqual(rc_status, 0)
                out_status = buf_status.getvalue()
                self.assertIn("0.4.0", out_status)
                self.assertIn("ollama", out_status)
                self.assertIn("TTS           : ENABLED", out_status)
                self.assertIn("Overlay       : ENABLED (theme=DarkGlass", out_status)
                self.assertIn("RAG enabled   : True (Classic Era 1.15.x", out_status)

                with mock.patch("companion.main._resolve_target_paths", return_value=[lua_out]):
                    buf_ask = io.StringIO()
                    with contextlib.redirect_stdout(buf_ask):
                        rc_ask = companion_main(
                            [
                                "--config",
                                str(cfg_path),
                                "--ask",
                                "Blackrock Depths",
                                "--provider",
                                "gemini_oauth",
                                "--dry-run",
                                "--rag-type",
                                "dungeon",
                                "--rag-top-k",
                                "2",
                                "--no-tts",
                                "--no-overlay",
                            ]
                        )
                    self.assertEqual(rc_ask, 0)
                    self.assertIn("Blackrock Depths", buf_ask.getvalue())
                    self.assertIn("gemini_oauth", buf_ask.getvalue())

                    buf_norag = io.StringIO()
                    with contextlib.redirect_stdout(buf_norag):
                        rc_norag = companion_main(
                            [
                                "--config",
                                str(cfg_path),
                                "--ask",
                                "Ironfoe",
                                "--provider",
                                "ollama",
                                "--dry-run",
                                "--no-rag",
                                "--no-tts",
                                "--no-overlay",
                            ]
                        )
                    self.assertEqual(rc_norag, 0)
                    self.assertIn("RAG=DISABLED", buf_norag.getvalue())

                buf_q = io.StringIO()
                with contextlib.redirect_stdout(buf_q):
                    rc_q = companion_main(
                        [
                            "--config",
                            str(cfg_path),
                            "--rag-query",
                            "Baron Geddon",
                            "--rag-type",
                            "mob",
                            "--rag-top-k",
                            "1",
                        ]
                    )
                self.assertEqual(rc_q, 0)
                self.assertIn("Baron Geddon", buf_q.getvalue())
                self.assertIn("Left", buf_q.getvalue())

    def test_numeric_config_hardening_rejects_non_finite_and_garbage(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            cfg_path = tmp_path / "config.json"
            cfg_path.write_text(
                json.dumps(
                    {
                        "wow_forever_dir": str(tmp_path),
                        "poll_interval_seconds": "NaN",
                        "rag_top_k": "not-an-int",
                        "ollama_timeout": "inf",
                        "tts_rate": True,
                        "tts_volume": "-inf",
                        "overlay_opacity": "garbage",
                    }
                ),
                encoding="utf-8",
            )

            with mock.patch.dict(
                os.environ,
                {
                    "JINY_POLL_INTERVAL_SECONDS": "",
                    "JINY_RAG_TOP_K": "",
                    "JINY_OLLAMA_TIMEOUT": "",
                    "JINY_TTS_RATE": "",
                    "JINY_TTS_VOLUME": "",
                    "JINY_OVERLAY_OPACITY": "",
                },
                clear=False,
            ):
                cfg_json = load_config(cfg_path)

            self.assertEqual(cfg_json.poll_interval_seconds, 0.25)
            self.assertEqual(cfg_json.rag_top_k, 4)
            self.assertEqual(cfg_json.ollama_timeout, 60.0)
            self.assertEqual(cfg_json.tts_rate, 0)
            self.assertEqual(cfg_json.tts_volume, 100)
            self.assertAlmostEqual(cfg_json.overlay_opacity, 0.92)

            # Non-finite and garbage values in environment variables also fall back cleanly
            for bad_env in ("inf", "-inf", "+Infinity", "nan", "NaN", "garbage", "true"):
                with mock.patch.dict(
                    os.environ,
                    {
                        "JINY_POLL_INTERVAL_SECONDS": bad_env,
                        "JINY_RAG_TOP_K": bad_env,
                        "JINY_OLLAMA_TIMEOUT": bad_env,
                        "JINY_TTS_RATE": bad_env,
                        "JINY_TTS_VOLUME": bad_env,
                        "JINY_OVERLAY_OPACITY": bad_env,
                    },
                    clear=False,
                ):
                    cfg_env = load_config(cfg_path)
                self.assertTrue(math.isfinite(cfg_env.poll_interval_seconds))
                self.assertTrue(math.isfinite(cfg_env.ollama_timeout))
                self.assertTrue(math.isfinite(cfg_env.overlay_opacity))
                self.assertEqual(cfg_env.poll_interval_seconds, 0.25)
                self.assertEqual(cfg_env.rag_top_k, 4)
                self.assertEqual(cfg_env.ollama_timeout, 60.0)
                self.assertEqual(cfg_env.tts_rate, 0)
                self.assertEqual(cfg_env.tts_volume, 100)
                self.assertAlmostEqual(cfg_env.overlay_opacity, 0.92)

            # Valid extreme bounds clamp cleanly
            with mock.patch.dict(
                os.environ,
                {
                    "JINY_POLL_INTERVAL_SECONDS": "99",
                    "JINY_RAG_TOP_K": "99",
                    "JINY_OLLAMA_TIMEOUT": "0.1",
                    "JINY_TTS_RATE": "-50",
                    "JINY_TTS_VOLUME": "500",
                    "JINY_OVERLAY_OPACITY": "2.5",
                },
                clear=False,
            ):
                cfg_clamped = load_config(cfg_path)
            self.assertEqual(cfg_clamped.poll_interval_seconds, 5.0)
            self.assertEqual(cfg_clamped.rag_top_k, 20)
            self.assertEqual(cfg_clamped.ollama_timeout, 1.0)
            self.assertEqual(cfg_clamped.tts_rate, -10)
            self.assertEqual(cfg_clamped.tts_volume, 100)
            self.assertEqual(cfg_clamped.overlay_opacity, 1.0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
