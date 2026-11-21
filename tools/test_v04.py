"""Offline unit and integration tests for Jiny v0.4 (DarkGlass, Auth/Providers, TTS, Overlay)."""

from __future__ import annotations

import base64
import contextlib
import hashlib
import io
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import threading
import time
import types
import unittest
from unittest import mock
import urllib.error
import urllib.parse
import urllib.request

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import companion
from companion.config import CompanionConfig, DEFAULT_MODEL, load_config
from companion.gemini_client import JinyGeminiClient
from companion.main import build_parser, cmd_ask, cmd_oauth_login, cmd_status, cmd_watch, main as cli_main
from companion.oauth import (
    OAuthError,
    OAuthManager,
    OAuthToken,
    OAuthTokenStore,
    compute_code_challenge,
    generate_code_verifier,
    load_client_secrets_file,
)
from companion.overlay import (
    OVERLAY_THEMES,
    HeadlessOverlayBackend,
    OverlayController,
    OverlayManager,
    TkOverlayBackend,
)
from companion.providers import (
    GeminiAPIKeyProvider,
    GeminiOAuthProvider,
    LLMProvider,
    OllamaProvider,
    ProviderError,
    create_provider,
    normalize_provider_name,
    probe_provider_status,
)
from companion.tts import (
    NullTTSBackend,
    Pyttsx3Backend,
    TTSBackend,
    TTSError,
    TTSManager,
    WindowsSAPIBackend,
    create_tts_backend,
    sanitize_tts_text,
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
        return _FakeInteraction(f"int-{idx}", f"Reply #{idx}: {kwargs['input']}")


class _FakeGenAIClient:
    def __init__(self) -> None:
        self.interactions = _FakeInteractionsAPI()


class TestAddonV04Static(unittest.TestCase):
    def test_toc_and_check_addon_pass(self) -> None:
        toc = (ROOT / "Jiny" / "Jiny.toc").read_text(encoding="utf-8")
        self.assertIn("## Interface: 16001", toc)
        self.assertIn("## Version: 0.4.0", toc)

        sys.path.insert(0, str(ROOT / "tools"))
        import check_addon

        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc = check_addon.main()
        self.assertEqual(rc, 0, msg=buf.getvalue())

    def test_themes_core_ui_and_locales_darkglass_support(self) -> None:
        themes_lua = (ROOT / "Jiny" / "Themes.lua").read_text(encoding="utf-8")
        for token in (
            'Themes.default = "ParchmentLight"',
            "Themes.order",
            "DarkGlass",
            "function Themes:Resolve",
            "function Themes:Next",
            "macroBorder",
            "codeBody",
        ):
            self.assertIn(token, themes_lua)

        core_lua = (ROOT / "Jiny" / "Core.lua").read_text(encoding="utf-8")
        self.assertIn('lowerCmd == "theme"', core_lua)
        self.assertIn("HELP_THEME", core_lua)
        self.assertIn("Themes:Resolve", core_lua)

        ui_lua = (ROOT / "Jiny" / "UI.lua").read_text(encoding="utf-8")
        self.assertIn("function UI:SetTheme", ui_lua)
        self.assertIn("function UI:RenderHistory", ui_lua)
        self.assertIn("footerRow1", ui_lua)
        self.assertIn("footerRow2", ui_lua)
        self.assertIn("self.themeBtn", ui_lua)
        self.assertNotIn("|cffffd100", ui_lua)
        self.assertNotIn("|cff81e6d9", ui_lua)

        for code in ("enUS", "esES", "itIT"):
            loc = (ROOT / "Jiny" / "Locales" / f"{code}.lua").read_text(encoding="utf-8")
            self.assertIn('FOOTER = "v0.4 • Forever"', loc)
            for key in ("BTN_THEME", "THEME_ParchmentLight", "THEME_DarkGlass", "THEME_CHANGED", "HELP_THEME"):
                self.assertIn(key, loc)
            self.assertIsNone(re.search(r"\bbot\b", loc, flags=re.IGNORECASE))

    def test_darkglass_palette_contrast(self) -> None:
        dg = OVERLAY_THEMES["DarkGlass"]

        def _rel_lum(hex_str: str) -> float:
            h = hex_str.lstrip("#")
            rgb = [int(h[i : i + 2], 16) / 255.0 for i in (0, 2, 4)]
            lin = [c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4 for c in rgb]
            return 0.2126 * lin[0] + 0.7152 * lin[1] + 0.0722 * lin[2]

        bg_l = _rel_lum(dg["bg"])
        fg_l = _rel_lum(dg["text"])
        ratio = (max(bg_l, fg_l) + 0.05) / (min(bg_l, fg_l) + 0.05)
        self.assertGreater(ratio, 10.0)


class TestConfigAndVersion(unittest.TestCase):
    def test_version_and_example_config(self) -> None:
        self.assertEqual(companion.__version__, "0.4.0")
        example_path = ROOT / "companion" / "config.example.json"
        raw = json.loads(example_path.read_text(encoding="utf-8"))
        self.assertEqual(raw["api_key"], "")
        self.assertEqual(raw["oauth_client_secret"], "")
        self.assertEqual(raw["provider"], "gemini_api_key")
        self.assertIn("tts_enabled", raw)
        self.assertIn("overlay_theme", raw)

    def test_load_config_defaults_and_env_overrides(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            cfg_path = Path(tmp) / "config.json"
            cfg_path.write_text(
                json.dumps(
                    {
                        "api_key": "file-key",
                        "model": "gemini-3.8-flash",
                        "wow_forever_dir": tmp,
                        "poll_interval_seconds": 0.5,
                    }
                ),
                encoding="utf-8",
            )
            with mock.patch.dict(
                os.environ,
                {
                    "GEMINI_API_KEY": "",
                    "JINY_GEMINI_MODEL": "",
                    "JINY_WOW_FOREVER_DIR": "",
                    "JINY_PROVIDER": "ollama",
                    "JINY_OLLAMA_BASE_URL": "http://127.0.0.1:11435",
                    "JINY_OLLAMA_MODEL": "mistral:7b",
                    "JINY_OLLAMA_TIMEOUT": "45",
                    "JINY_OAUTH_CLIENT_ID": "cid-123",
                    "JINY_VERTEXAI": "true",
                    "JINY_GCP_PROJECT": "wow-proj",
                    "JINY_GCP_LOCATION": "europe-west1",
                    "JINY_TTS_ENABLED": "1",
                    "JINY_TTS_BACKEND": "sapi",
                    "JINY_TTS_RATE": "3",
                    "JINY_TTS_VOLUME": "85",
                    "JINY_OVERLAY_ENABLED": "yes",
                    "JINY_OVERLAY_THEME": "ParchmentLight",
                    "JINY_OVERLAY_OPACITY": "0.85",
                    "JINY_OVERLAY_ALWAYS_ON_TOP": "false",
                },
                clear=False,
            ):
                cfg = load_config(cfg_path)

            self.assertEqual(cfg.api_key, "file-key")
            self.assertEqual(cfg.model, DEFAULT_MODEL)
            self.assertEqual(cfg.poll_interval_seconds, 0.5)
            self.assertEqual(cfg.provider, "ollama")
            self.assertEqual(cfg.ollama_base_url, "http://127.0.0.1:11435")
            self.assertEqual(cfg.ollama_model, "mistral:7b")
            self.assertEqual(cfg.ollama_timeout, 45.0)
            self.assertEqual(cfg.oauth_client_id, "cid-123")
            self.assertTrue(cfg.vertexai)
            self.assertEqual(cfg.gcp_project, "wow-proj")
            self.assertEqual(cfg.gcp_location, "europe-west1")
            self.assertTrue(cfg.tts_enabled)
            self.assertEqual(cfg.tts_backend, "sapi")
            self.assertEqual(cfg.tts_rate, 3)
            self.assertEqual(cfg.tts_volume, 85)
            self.assertTrue(cfg.overlay_enabled)
            self.assertEqual(cfg.overlay_theme, "ParchmentLight")
            self.assertAlmostEqual(cfg.overlay_opacity, 0.85)
            self.assertFalse(cfg.overlay_always_on_top)

    def test_load_config_empty_numeric_env_and_json_null_or_zero(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            cfg_path = Path(tmp) / "config.json"
            cfg_path.write_text(
                json.dumps(
                    {
                        "wow_forever_dir": tmp,
                        "tts_rate": None,
                        "tts_volume": None,
                        "overlay_opacity": None,
                    }
                ),
                encoding="utf-8",
            )
            with mock.patch.dict(
                os.environ,
                {
                    "JINY_TTS_RATE": "",
                    "JINY_TTS_VOLUME": "   ",
                    "JINY_OVERLAY_OPACITY": "",
                },
                clear=False,
            ):
                cfg = load_config(cfg_path)
            self.assertEqual(cfg.tts_rate, 0)
            self.assertEqual(cfg.tts_volume, 100)
            self.assertAlmostEqual(cfg.overlay_opacity, 0.92)

            # Explicit 0 in JSON must not be coerced to 100
            cfg_path.write_text(
                json.dumps({"wow_forever_dir": tmp, "tts_rate": 0, "tts_volume": 0}),
                encoding="utf-8",
            )
            with mock.patch.dict(
                os.environ,
                {"JINY_TTS_RATE": "", "JINY_TTS_VOLUME": "", "JINY_OVERLAY_OPACITY": ""},
                clear=False,
            ):
                cfg_zero = load_config(cfg_path)
            self.assertEqual(cfg_zero.tts_rate, 0)
            self.assertEqual(cfg_zero.tts_volume, 0)


class TestProvidersOffline(unittest.TestCase):
    def _base_cfg(self, tmp: str, **overrides) -> CompanionConfig:
        base = dict(
            api_key="test-api-key",
            model=DEFAULT_MODEL,
            wow_forever_dir=Path(tmp),
            chat_log_path=Path(tmp) / "WoWChatLog.txt",
            dev_companion_data_path=Path(tmp) / "CompanionData.lua",
            deployed_companion_data_path=Path(tmp) / "Deployed" / "CompanionData.lua",
            wtf_account_dir=Path(tmp) / "WTF" / "Account",
            oauth_client_id="client-id-1",
            oauth_token_path=Path(tmp) / "oauth_token.json",
        )
        base.update(overrides)
        return CompanionConfig(**base)

    def test_provider_normalization_and_factory(self) -> None:
        self.assertEqual(normalize_provider_name("gemini-api"), "gemini_api_key")
        self.assertEqual(normalize_provider_name("gemini_api_key"), "gemini_api_key")
        self.assertEqual(normalize_provider_name("oauth"), "gemini_oauth")
        self.assertEqual(normalize_provider_name("gemini-oauth"), "gemini_oauth")
        self.assertEqual(normalize_provider_name("ollama"), "ollama")
        with self.assertRaises(ProviderError):
            normalize_provider_name("unknown-llm")

        with tempfile.TemporaryDirectory() as tmp:
            cfg = self._base_cfg(tmp)
            p1 = create_provider(cfg, provider="gemini-api", client=_FakeGenAIClient())
            self.assertIsInstance(p1, GeminiAPIKeyProvider)
            self.assertIsInstance(p1, LLMProvider)

            p2 = create_provider(cfg, provider="gemini-oauth", client=_FakeGenAIClient())
            self.assertIsInstance(p2, GeminiOAuthProvider)

            p3 = create_provider(cfg, provider="ollama")
            self.assertIsInstance(p3, OllamaProvider)

            with self.assertRaises(ProviderError):
                create_provider(cfg, provider="bad-provider")

    def test_gemini_api_key_provider_and_client_compat(self) -> None:
        with self.assertRaises(ValueError):
            JinyGeminiClient(api_key="", model=DEFAULT_MODEL, client=None)
        with self.assertRaises(ProviderError):
            GeminiAPIKeyProvider(api_key="", model=DEFAULT_MODEL, client=None)

        fake = _FakeGenAIClient()
        provider = GeminiAPIKeyProvider(api_key="k", model=DEFAULT_MODEL, client=fake)
        r1 = provider.ask("Donde esta Hogger?", locale="esES", context="[CLASSIC_ERA_CONTEXT]\nElwynn Forest")
        self.assertIn("Reply #1", r1)
        self.assertIn("[CLASSIC_ERA_CONTEXT]", fake.interactions.calls[0]["input"])
        self.assertEqual(provider.last_interaction_id, "int-1")

        r2 = provider.ask("Nivel recomendado?", locale="esES")
        self.assertIn("Reply #2", r2)
        self.assertEqual(fake.interactions.calls[1]["previous_interaction_id"], "int-1")

        provider.reset_session()
        self.assertIsNone(provider.last_interaction_id)
        self.assertTrue(provider.health_check()["ok"])

        compat = JinyGeminiClient(api_key="k", client=_FakeGenAIClient())
        self.assertIn("Reply #1", compat.ask("Hi", locale="enUS", context="ctx"))

    def test_oauth_pkce_store_refresh_and_secret_safety(self) -> None:
        verifier = generate_code_verifier()
        expected = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode("ascii")).digest()).rstrip(b"=").decode("ascii")
        self.assertEqual(compute_code_challenge(verifier), expected)

        with tempfile.TemporaryDirectory() as tmp:
            secrets_file = Path(tmp) / "client_secret.json"
            secrets_file.write_text(
                json.dumps({"installed": {"client_id": "cid-abc", "client_secret": "sec-xyz"}}),
                encoding="utf-8",
            )
            loaded_sec = load_client_secrets_file(secrets_file)
            self.assertEqual(loaded_sec["client_id"], "cid-abc")

            token_path = Path(tmp) / "oauth_token.json"
            now = [1000.0]
            requests_seen: list[tuple[str, bytes | None]] = []

            def fake_http(url: str, headers: dict[str, str], body: bytes | None, timeout: float):
                requests_seen.append((url, body))
                body_str = (body or b"").decode("utf-8")
                if "grant_type=authorization_code" in body_str:
                    return 200, json.dumps(
                        {
                            "access_token": "tok-initial-secret",
                            "refresh_token": "ref-keep-secret",
                            "expires_in": 120,
                            "token_type": "Bearer",
                        }
                    ).encode("utf-8")
                if "grant_type=refresh_token" in body_str:
                    return 200, json.dumps(
                        {
                            "access_token": "tok-refreshed-secret",
                            "expires_in": 3600,
                        }
                    ).encode("utf-8")
                return 400, b'{"error":"invalid_request"}'

            mgr = OAuthManager(
                client_id="cid-abc",
                client_secret="sec-xyz",
                token_path=token_path,
                http_transport=fake_http,
                clock=lambda: now[0],
            )
            tok = mgr.exchange_code("auth-code-1", "http://127.0.0.1:9999/callback", verifier)
            self.assertEqual(tok.access_token, "tok-initial-secret")
            self.assertTrue(token_path.exists())
            self.assertFalse(token_path.with_suffix(".json.tmp").exists())

            status = mgr.get_token_status()
            self.assertTrue(status["has_token"])
            self.assertTrue(status["has_refresh_token"])
            self.assertFalse(status["expired"])
            status_dump = json.dumps(status)
            self.assertNotIn("tok-initial-secret", status_dump)
            self.assertNotIn("ref-keep-secret", status_dump)
            self.assertNotIn("sec-xyz", status_dump)
            self.assertNotIn("tok-initial-secret", repr(tok))

            # Advance clock past expiry -> auto-refresh should trigger and preserve refresh_token
            now[0] = 1200.0
            refreshed = mgr.get_access_token()
            self.assertEqual(refreshed, "tok-refreshed-secret")
            reloaded = OAuthTokenStore(token_path).load()
            self.assertIsNotNone(reloaded)
            self.assertEqual(reloaded.refresh_token, "ref-keep-secret")

            # Manual fallback interactive flow with state check
            mgr_manual = OAuthManager(
                client_id="cid-abc",
                token_path=token_path,
                http_transport=fake_http,
                clock=lambda: now[0],
            )
            with contextlib.redirect_stdout(io.StringIO()):
                tok2 = mgr_manual.authorize_interactive(
                    port=-1,
                    open_browser=False,
                    manual_fallback=True,
                    input_fn=lambda _prompt: "manual-code-xyz",
                )
            self.assertEqual(tok2.access_token, "tok-initial-secret")

    def test_oauth_corrupted_non_utf8_bad_expires_at_and_favicon_loopback(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            bad_secret = Path(tmp) / "client_secret.json"
            bad_secret.write_bytes(b"\xff\xfe\x00\x81invalid-utf8")
            with self.assertRaises(OAuthError):
                load_client_secrets_file(bad_secret)

            bad_token = Path(tmp) / "oauth_token.json"
            bad_token.write_bytes(b"\xff\xfe\x00\x81invalid-utf8")
            with self.assertRaises(OAuthError):
                OAuthTokenStore(bad_token).load()

            mgr = OAuthManager(client_id="cid-test", token_path=bad_token)
            status = mgr.get_token_status()
            self.assertFalse(status["has_token"])
            self.assertIn("error", status)

            cfg = self._base_cfg(tmp, provider="gemini_oauth", oauth_token_path=bad_token)
            probe = probe_provider_status(cfg)
            self.assertFalse(probe["ready"])
            self.assertIn("token store error", probe["detail"])

            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                rc = cmd_status(cfg)
            self.assertEqual(rc, 0)

            with self.assertRaises(OAuthError):
                mgr._token_from_response({"access_token": "tok", "expires_at": "not-a-float"})
            with self.assertRaises(OAuthError):
                mgr._token_from_response({"access_token": "tok", "expires_at": {"bad": 1}})

            # Loopback server ignores /favicon.ico (404) without failing real /callback
            token_ok = Path(tmp) / "oauth_ok.json"

            def fake_http(url: str, headers: dict[str, str], body: bytes | None, timeout: float):
                return 200, json.dumps({"access_token": "tok-loopback", "expires_in": 600}).encode("utf-8")

            mgr_loop = OAuthManager(client_id="cid-loop", token_path=token_ok, http_transport=fake_http)
            favicon_status: list[int] = []
            callback_status: list[int] = []
            client_errors: list[BaseException] = []

            def fake_open_browser(auth_url: str) -> bool:
                parsed = urllib.parse.urlparse(auth_url)
                qs = urllib.parse.parse_qs(parsed.query)
                redirect_uri = qs["redirect_uri"][0]
                state = qs["state"][0]
                r_parsed = urllib.parse.urlparse(redirect_uri)
                favicon_url = f"{r_parsed.scheme}://{r_parsed.netloc}/favicon.ico"
                cb_url = f"{redirect_uri}?code=auth-after-favicon&state={urllib.parse.quote(state)}"

                def _send_requests() -> None:
                    try:
                        try:
                            with urllib.request.urlopen(favicon_url, timeout=2.0) as resp:
                                favicon_status.append(resp.status)
                        except urllib.error.HTTPError as err:
                            favicon_status.append(err.code)
                        with urllib.request.urlopen(cb_url, timeout=2.0) as resp2:
                            callback_status.append(resp2.status)
                    except BaseException as exc:  # pragma: no cover
                        client_errors.append(exc)

                threading.Thread(target=_send_requests, daemon=True).start()
                return True

            with mock.patch("companion.oauth.webbrowser.open", side_effect=fake_open_browser):
                with contextlib.redirect_stdout(io.StringIO()):
                    tok = mgr_loop.authorize_interactive(
                        port=0,
                        timeout_seconds=5.0,
                        open_browser=True,
                        manual_fallback=False,
                    )
            self.assertEqual(client_errors, [])
            self.assertEqual(favicon_status, [404])
            self.assertEqual(callback_status, [200])
            self.assertEqual(tok.access_token, "tok-loopback")

    def test_oauth_provider_bearer_and_vertex_modes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            token_path = Path(tmp) / "oauth_token.json"
            OAuthTokenStore(token_path).save(
                OAuthToken(access_token="access-1", refresh_token="refresh-1", expires_at=None)
            )
            calls: list[tuple[str, dict[str, str], dict]] = []
            attempt = [0]

            def fake_http(url: str, headers: dict[str, str], body: bytes | None, timeout: float):
                if "oauth2.googleapis.com/token" in url:
                    return 200, json.dumps({"access_token": "access-2", "expires_in": 3600}).encode("utf-8")
                attempt[0] += 1
                calls.append((url, headers, json.loads((body or b"{}").decode("utf-8"))))
                if attempt[0] == 1:
                    return 401, json.dumps({"error": {"message": "expired"}}).encode("utf-8")
                return 200, json.dumps(
                    {
                        "id": "oauth-int-1",
                        "status": "completed",
                        "steps": [
                            {
                                "type": "model_output",
                                "content": [
                                    {"type": "thought", "text": "hidden"},
                                    {"type": "text", "text": "Mankrik is in Barrens."},
                                ],
                            }
                        ],
                    }
                ).encode("utf-8")

            mgr = OAuthManager(client_id="cid", token_path=token_path, http_transport=fake_http)
            provider = GeminiOAuthProvider(oauth_manager=mgr, vertexai=False, http_transport=fake_http)
            answer = provider.ask("Where is Mankrik?", locale="enUS", context="Barrens (52, 31)")
            self.assertEqual(answer, "Mankrik is in Barrens.")
            self.assertEqual(len(calls), 2)
            self.assertEqual(calls[0][1]["Authorization"], "Bearer access-1")
            self.assertEqual(calls[1][1]["Authorization"], "Bearer access-2")
            self.assertEqual(calls[1][1]["Api-Revision"], "2026-05-20")
            self.assertEqual(provider.last_interaction_id, "oauth-int-1")

            # Vertex requires gcp_project when client is not injected
            with self.assertRaises(ProviderError):
                GeminiOAuthProvider(oauth_manager=mgr, vertexai=True, gcp_project="")

            fake_vertex = _FakeGenAIClient()
            v_provider = GeminiOAuthProvider(
                oauth_manager=mgr,
                vertexai=True,
                gcp_project="my-gcp-proj",
                client=fake_vertex,
            )
            v_ans = v_provider.ask("Hello Vertex", locale="enUS")
            self.assertIn("Reply #1", v_ans)

    def test_ollama_provider_history_health_and_errors(self) -> None:
        calls: list[tuple[str, dict | None]] = []

        def fake_ollama(url: str, headers: dict[str, str], body: bytes | None, timeout: float):
            payload = json.loads(body.decode("utf-8")) if body else None
            calls.append((url, payload))
            if url.endswith("/api/tags"):
                return 200, json.dumps({"models": [{"name": "llama3.1:8b"}]}).encode("utf-8")
            if url.endswith("/api/chat"):
                idx = len([c for c in calls if c[0].endswith("/api/chat")])
                return 200, json.dumps({"message": {"role": "assistant", "content": f"Ollama #{idx}"}}).encode("utf-8")
            return 404, b"{}"

        ollama = OllamaProvider(base_url="http://127.0.0.1:11434", model="llama3.1:8b", http_transport=fake_ollama)
        hc = ollama.health_check()
        self.assertTrue(hc["ok"])
        self.assertTrue(hc["model_available"])

        a1 = ollama.ask("Hola", locale="esES", context="Deadmines level 18-22")
        self.assertEqual(a1, "Ollama #1")
        a2 = ollama.ask("Segundo turno", locale="esES")
        self.assertEqual(a2, "Ollama #2")
        second_msgs = calls[-1][1]["messages"]
        self.assertEqual([m["role"] for m in second_msgs], ["system", "user", "assistant", "user"])

        ollama.reset_session()
        ollama.ask("Turno nuevo", locale="esES")
        reset_msgs = calls[-1][1]["messages"]
        self.assertEqual([m["role"] for m in reset_msgs], ["system", "user"])

        def failing_ollama(url: str, headers: dict[str, str], body: bytes | None, timeout: float):
            raise OAuthError("Connection refused")

        bad_ollama = OllamaProvider(http_transport=failing_ollama)
        with self.assertRaises(ProviderError):
            bad_ollama.ask("Test")
        bad_hc = bad_ollama.health_check()
        self.assertFalse(bad_hc["ok"])


class TestTTSModule(unittest.TestCase):
    def test_sanitize_tts_text_strips_wow_and_macro_markup(self) -> None:
        raw = (
            "|cff00ff00Hola|r |Hitem:19019:0:0:0|h[Thunderfury]|h!\n"
            '[JINY_MACRO name="Burst"]\n#showtooltip\n/cast Fireball\n[/JINY_MACRO]\n'
            "```lua\nprint('hi')\n```\n"
            "Usa `/cast Frostbolt` cerca de (45, 32)."
        )
        cleaned = sanitize_tts_text(raw)
        self.assertEqual(cleaned, "Hola [Thunderfury]! Usa /cast Frostbolt cerca de (45, 32).")
        self.assertEqual(sanitize_tts_text('[JINY_MACRO]/cast Blink[/JINY_MACRO]'), "")

    def test_tts_manager_disabled_and_async_resilience(self) -> None:
        spoken: list[tuple[str, str]] = []

        class RecordingBackend(TTSBackend):
            name = "rec"

            def is_available(self) -> bool:
                return True

            def speak(self, text: str, locale: str = "esES") -> None:
                if "FAIL" in text:
                    raise TTSError("simulated audio failure")
                spoken.append((text, locale))

        disabled_mgr = TTSManager(enabled=False, backend=RecordingBackend())
        self.assertFalse(disabled_mgr.speak("Hello"))
        self.assertIsNone(disabled_mgr._worker)
        disabled_mgr.close()

        with TTSManager(enabled=True, backend=RecordingBackend()) as mgr:
            self.assertFalse(mgr.speak("```lua\nx=1\n```"))
            self.assertTrue(mgr.speak("FAIL once", locale="enUS"))
            self.assertTrue(mgr.speak("Recovered message", locale="esES"))
            self.assertTrue(mgr.flush(timeout=3.0))
            self.assertEqual(mgr.last_error, "simulated audio failure")
            self.assertEqual(spoken, [("Recovered message", "esES")])
            mgr.stop()
            mgr.close()  # idempotent

    def test_windows_sapi_injection_safety_and_pyttsx3_lazy(self) -> None:
        captured: list[tuple[list[str], dict, bool]] = []

        def fake_runner(cmd, env=None, shell=True, **kwargs):
            captured.append((cmd, env, shell))
            return types.SimpleNamespace(returncode=0, stderr="")

        payload = '"; calc.exe; $(whoami) | Invoke-Expression'
        sapi = WindowsSAPIBackend(rate=2, volume=90, runner=fake_runner)
        sapi.speak(payload, locale="esES")
        self.assertEqual(len(captured), 1)
        cmd, env, shell = captured[0]
        self.assertFalse(shell)
        self.assertNotIn("calc.exe", " ".join(cmd))
        self.assertEqual(env["JINY_TTS_TEXT"], payload)
        self.assertEqual(env["JINY_TTS_LOCALE"], "esES")
        self.assertEqual(env["JINY_TTS_RATE"], "2")
        self.assertEqual(env["JINY_TTS_VOLUME"], "90")

        def failing_runner(cmd, **kwargs):
            return types.SimpleNamespace(returncode=1, stderr="SAPI err")

        with self.assertRaises(TTSError):
            WindowsSAPIBackend(runner=failing_runner).speak("hello")

        # Pyttsx3 absent -> safe False, no crash
        with mock.patch.dict(sys.modules, {"pyttsx3": None}):
            py3 = Pyttsx3Backend()
            self.assertFalse(py3.is_available())
            py3.speak("ignored")

        # Pyttsx3 present -> mocked engine invoked
        calls: list[str] = []
        fake_engine = types.SimpleNamespace(
            getProperty=lambda _k: 180,
            setProperty=lambda _k, _v: None,
            say=lambda txt: calls.append(txt),
            runAndWait=lambda: calls.append("<RUN>"),
        )
        fake_pyttsx3 = types.SimpleNamespace(init=lambda: fake_engine)
        with mock.patch.dict(sys.modules, {"pyttsx3": fake_pyttsx3}):
            py3_ok = Pyttsx3Backend()
            self.assertTrue(py3_ok.is_available())
            py3_ok.speak("Hola Azeroth")
        self.assertEqual(calls, ["Hola Azeroth", "<RUN>"])

        self.assertIsInstance(create_tts_backend("null"), NullTTSBackend)


class TestOverlayModule(unittest.TestCase):
    def test_overlay_does_not_import_tkinter_at_import_time(self) -> None:
        proc = subprocess.run(
            [
                sys.executable,
                "-c",
                "import sys; import companion.overlay; print('tkinter' in sys.modules)",
            ],
            cwd=str(ROOT),
            capture_output=True,
            text=True,
            check=True,
        )
        self.assertEqual(proc.stdout.strip(), "False")

    def test_overlay_themes_match_lua_and_controller_state(self) -> None:
        self.assertEqual(OVERLAY_THEMES["DarkGlass"]["bg"], "#10141f")
        self.assertEqual(OVERLAY_THEMES["DarkGlass"]["title"], "#ffd100")
        self.assertEqual(OVERLAY_THEMES["ParchmentLight"]["bg"], "#e8d5a8")
        self.assertEqual(OVERLAY_THEMES["ParchmentLight"]["title"], "#4a2508")

        ctrl = OverlayController(theme="DarkGlass")
        ctrl.set_status("watching", provider="ollama")
        ctrl.set_question("Where is Hogger?")
        ctrl.set_reply("Where is Hogger?", "Elwynn Forest (27, 86)")
        snap = ctrl.snapshot()
        self.assertEqual(snap["status"], "watching")
        self.assertEqual(snap["provider"], "ollama")
        self.assertEqual(snap["latest_reply"], "Elwynn Forest (27, 86)")
        ctrl.set_theme("ParchmentLight")
        snap2 = ctrl.snapshot()
        self.assertEqual(snap2["theme"], "ParchmentLight")
        self.assertEqual(snap2["palette"]["bg"], "#e8d5a8")

    def test_overlay_manager_headless_and_tclerror_fallback(self) -> None:
        with OverlayManager(enabled=False, theme="DarkGlass") as mgr:
            self.assertIsInstance(mgr.backend, HeadlessOverlayBackend)
            mgr.show_reply("Q1", "A1")
            self.assertEqual(mgr.backend.last_snapshot["latest_reply"], "A1")

        # Simulate tk.Tk() raising TclError on headless CI -> graceful fallback to HeadlessOverlayBackend
        fake_tk = types.ModuleType("tkinter")

        class FakeTclError(Exception):
            pass

        def boom():
            raise FakeTclError("no display name and no $DISPLAY")

        fake_tk.TclError = FakeTclError
        fake_tk.Tk = boom

        with mock.patch.dict(sys.modules, {"tkinter": fake_tk}):
            mgr_tk = OverlayManager(enabled=True, theme="DarkGlass", backend_name="tk")
            backend = mgr_tk.start()
            self.assertIsInstance(backend, HeadlessOverlayBackend)
            self.assertIn("no display", mgr_tk.fallback_reason or "")
            mgr_tk.close()
            mgr_tk.close()  # idempotent

    def test_tk_overlay_backend_close_empty_saturated_and_external_destroy(self) -> None:
        class FakeTclError(Exception):
            pass

        def _make_fake_tk(fail_on_configure: bool = False):
            fake_tk = types.ModuleType("tkinter")
            fake_tk.TclError = FakeTclError
            created_roots: list[object] = []

            class FakeWidget:
                def __init__(self, master=None, **kwargs) -> None:
                    self.master = master
                    self.kwargs = kwargs

                def pack(self, **kwargs) -> None:
                    return

                def configure(self, **kwargs) -> None:
                    if fail_on_configure:
                        raise FakeTclError("invalid command name")

                def delete(self, *args) -> None:
                    return

                def insert(self, *args) -> None:
                    return

            class FakeStringVar:
                def __init__(self, value: str = "") -> None:
                    self.value = value

                def set(self, value: str) -> None:
                    self.value = value

            class FakeRoot:
                def __init__(self) -> None:
                    self._cond = threading.Condition()
                    self._scheduled: list[tuple[float, object]] = []
                    self._running = True
                    self.destroyed = False
                    self.quit_called = False
                    created_roots.append(self)

                def title(self, _t: str) -> None:
                    return

                def geometry(self, _g: str) -> None:
                    return

                def minsize(self, _w: int, _h: int) -> None:
                    return

                def attributes(self, *_args) -> None:
                    return

                def protocol(self, _name: str, _fn) -> None:
                    return

                def configure(self, **kwargs) -> None:
                    if self.destroyed or fail_on_configure:
                        raise FakeTclError("application has been destroyed")

                def after(self, ms: int, fn) -> None:
                    if self.destroyed:
                        raise FakeTclError("application has been destroyed")
                    with self._cond:
                        self._scheduled.append((time.monotonic() + (ms / 1000.0), fn))
                        self._cond.notify_all()

                def quit(self) -> None:
                    self.quit_called = True
                    with self._cond:
                        self._running = False
                        self._cond.notify_all()

                def destroy(self) -> None:
                    self.destroyed = True
                    with self._cond:
                        self._running = False
                        self._cond.notify_all()

                def mainloop(self) -> None:
                    while True:
                        due: list[object] = []
                        with self._cond:
                            if not self._running or self.destroyed:
                                return
                            now = time.monotonic()
                            remaining: list[tuple[float, object]] = []
                            next_deadline = None
                            for run_at, fn in self._scheduled:
                                if run_at <= now:
                                    due.append(fn)
                                else:
                                    remaining.append((run_at, fn))
                                    if next_deadline is None or run_at < next_deadline:
                                        next_deadline = run_at
                            self._scheduled = remaining
                            if not due:
                                wait_for = 0.05 if next_deadline is None else max(0.005, min(0.05, next_deadline - now))
                                self._cond.wait(timeout=wait_for)
                                continue
                        for fn in due:
                            fn()

            fake_tk.Tk = FakeRoot
            fake_tk.Frame = FakeWidget
            fake_tk.Label = FakeWidget
            fake_tk.Text = FakeWidget
            fake_tk.StringVar = FakeStringVar
            return fake_tk, created_roots

        # 1) Empty queue close
        fake_tk_1, roots_1 = _make_fake_tk()
        with mock.patch.dict(sys.modules, {"tkinter": fake_tk_1}):
            b1 = TkOverlayBackend()
            b1.start()
            t0 = time.monotonic()
            b1.close()
            dt = time.monotonic() - t0
            self.assertLess(dt, 1.0)
            self.assertEqual(len(roots_1), 1)
            self.assertTrue(roots_1[0].destroyed)
            self.assertTrue(roots_1[0].quit_called)
            self.assertFalse(b1._thread.is_alive())

        # 2) Saturated queue close (maxsize=64)
        fake_tk_2, roots_2 = _make_fake_tk()
        with mock.patch.dict(sys.modules, {"tkinter": fake_tk_2}):
            b2 = TkOverlayBackend()
            b2.start()
            snap = OverlayController().snapshot()
            for i in range(100):
                b2.render({**snap, "latest_reply": f"msg-{i}"})
            t0 = time.monotonic()
            b2.close()
            dt = time.monotonic() - t0
            self.assertLess(dt, 1.0)
            self.assertEqual(len(roots_2), 1)
            self.assertTrue(roots_2[0].destroyed)
            self.assertFalse(b2._thread.is_alive())

        # 3) External root destroy / TclError during _apply_snapshot exits UI thread cleanly
        fake_tk_3, roots_3 = _make_fake_tk(fail_on_configure=True)
        with mock.patch.dict(sys.modules, {"tkinter": fake_tk_3}):
            b3 = TkOverlayBackend()
            b3.start()
            b3.render(OverlayController().snapshot())
            b3._thread.join(timeout=1.0)
            self.assertFalse(b3._thread.is_alive())
            self.assertTrue(roots_3[0].destroyed)


class TestMainWiring(unittest.TestCase):
    def _make_cfg(self, tmp: str, **overrides) -> CompanionConfig:
        defaults = dict(
            api_key="",
            model=DEFAULT_MODEL,
            wow_forever_dir=Path(tmp),
            chat_log_path=Path(tmp) / "WoWChatLog.txt",
            dev_companion_data_path=Path(tmp) / "CompanionData.lua",
            deployed_companion_data_path=Path(tmp) / "Deployed" / "CompanionData.lua",
            wtf_account_dir=Path(tmp) / "WTF" / "Account",
            poll_interval_seconds=0.1,
            oauth_token_path=Path(tmp) / "oauth_token.json",
        )
        defaults.update(overrides)
        return CompanionConfig(**defaults)

    def test_parser_and_offline_status_for_all_providers(self) -> None:
        parser = build_parser()
        args = parser.parse_args(
            ["--ask", "Hi", "--provider", "ollama", "--tts", "--overlay", "--overlay-theme", "DarkGlass"]
        )
        self.assertEqual(args.provider, "ollama")
        self.assertTrue(args.tts_override)
        self.assertTrue(args.overlay_override)
        self.assertEqual(args.overlay_theme, "DarkGlass")

        args_off = parser.parse_args(["--status", "--no-tts", "--no-overlay"])
        self.assertFalse(args_off.tts_override)
        self.assertFalse(args_off.overlay_override)

        args_oauth = parser.parse_args(["--oauth-login"])
        self.assertTrue(args_oauth.oauth_login)

        with tempfile.TemporaryDirectory() as tmp:
            for prov in ("gemini_api_key", "gemini_oauth", "ollama"):
                cfg = self._make_cfg(tmp, provider=prov)
                buf = io.StringIO()
                with contextlib.redirect_stdout(buf):
                    rc = cmd_status(cfg)
                self.assertEqual(rc, 0)
                self.assertIn("0.4.0", buf.getvalue())

    def test_cmd_ask_dry_run_and_provider_error(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            cfg = self._make_cfg(tmp, tts_enabled=True, overlay_enabled=False)
            spoken: list[str] = []

            class RecTTS(TTSBackend):
                name = "rec"

                def is_available(self) -> bool:
                    return True

                def speak(self, text: str, locale: str = "esES") -> None:
                    spoken.append(text)

            tts_mgr = TTSManager(enabled=True, backend=RecTTS())
            ov_mgr = OverlayManager(enabled=False)
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                rc = cmd_ask(
                    cfg=cfg,
                    question="Test?",
                    locale="esES",
                    req_id="req-1",
                    dry_run=True,
                    write_deployed=False,
                    tts=tts_mgr,
                    overlay=ov_mgr,
                )
            tts_mgr.close()
            ov_mgr.close()
            self.assertEqual(rc, 0)
            self.assertTrue(cfg.dev_companion_data_path.exists())
            self.assertTrue(len(spoken) == 1)

            # ProviderError returns 1 cleanly without crashing
            class BrokenProvider(LLMProvider):
                @property
                def provider_name(self) -> str:
                    return "ollama"

                def ask(self, question: str, locale: str = "esES", context: str | None = None) -> str:
                    raise ProviderError("daemon offline")

                def reset_session(self) -> None:
                    return

                def health_check(self) -> dict:
                    return {"ok": False}

            buf_err = io.StringIO()
            with contextlib.redirect_stdout(buf_err):
                rc_err = cmd_ask(
                    cfg=self._make_cfg(tmp, provider="ollama"),
                    question="Q",
                    locale="esES",
                    req_id=None,
                    dry_run=False,
                    write_deployed=False,
                    provider=BrokenProvider(),
                )
            self.assertEqual(rc_err, 1)
            self.assertIn("daemon offline", buf_err.getvalue())

    def test_cmd_watch_survives_provider_error_and_updates_outputs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            cfg = self._make_cfg(tmp, provider="ollama", tts_enabled=True, overlay_enabled=False)
            cfg.chat_log_path.write_text(
                "11/21 20:31:01.000  To [Azok]: [JINY_Q#1-1#esES] First fails\n"
                "11/21 20:31:02.000  To [Azok]: [JINY_Q#1-2#esES] Second works\n",
                encoding="utf-8",
            )

            class FlakyProvider(LLMProvider):
                @property
                def provider_name(self) -> str:
                    return "ollama"

                def ask(self, question: str, locale: str = "esES", context: str | None = None) -> str:
                    if "First" in question:
                        raise ProviderError("transient failure")
                    return "Recovered reply"

                def reset_session(self) -> None:
                    return

                def health_check(self) -> dict:
                    return {"ok": True}

            spoken: list[str] = []

            class RecTTS(TTSBackend):
                name = "rec"

                def is_available(self) -> bool:
                    return True

                def speak(self, text: str, locale: str = "esES") -> None:
                    spoken.append(text)

            tts_mgr = TTSManager(enabled=True, backend=RecTTS())
            ov_mgr = OverlayManager(enabled=False)

            sleep_calls = [0]

            def stop_after_one_poll(_sec: float) -> None:
                sleep_calls[0] += 1
                if sleep_calls[0] >= 1:
                    raise KeyboardInterrupt()

            buf = io.StringIO()
            with mock.patch("companion.main.time.sleep", side_effect=stop_after_one_poll):
                with contextlib.redirect_stdout(buf):
                    rc = cmd_watch(
                        cfg=cfg,
                        start_from_beginning=True,
                        provider=FlakyProvider(),
                        tts=tts_mgr,
                        overlay=ov_mgr,
                    )
            tts_mgr.flush(timeout=2.0)
            tts_mgr.close()
            ov_mgr.close()
            self.assertEqual(rc, 0)
            self.assertIn("transient failure", buf.getvalue())
            self.assertEqual(spoken, ["Recovered reply"])
            self.assertIn("Recovered reply", cfg.dev_companion_data_path.read_text(encoding="utf-8"))

    def test_cmd_oauth_login_success_and_error(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            cfg = self._make_cfg(tmp)
            with mock.patch("companion.main.run_oauth_login", return_value=cfg.oauth_token_path):
                with contextlib.redirect_stdout(io.StringIO()):
                    self.assertEqual(cmd_oauth_login(cfg), 0)

            with mock.patch("companion.main.run_oauth_login", side_effect=OAuthError("bad client")):
                with contextlib.redirect_stdout(io.StringIO()):
                    self.assertEqual(cmd_oauth_login(cfg), 1)

            # Unknown provider on CLI returns exit code 1 cleanly
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(cli_main(["--status", "--provider", "invalid-x"]), 1)


if __name__ == "__main__":
    unittest.main(verbosity=2)
