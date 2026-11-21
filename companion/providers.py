"""Unified LLM provider interface for Jiny Companion (API Key, OAuth 2.0, Ollama)."""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any, Optional

from .config import CompanionConfig, DEFAULT_MODEL, sanitize_model_name
from .oauth import (
    DEFAULT_AUTH_ENDPOINT,
    DEFAULT_OAUTH_SCOPES,
    DEFAULT_TOKEN_ENDPOINT,
    DEFAULT_TOKEN_PATH,
    HttpTransport,
    OAuthError,
    OAuthManager,
    OAuthTokenStore,
    default_http_transport,
)
from .prompts import build_system_instruction

DEFAULT_GEMINI_BASE_URL = "https://generativelanguage.googleapis.com"
DEFAULT_API_REVISION = "2026-05-20"
DEFAULT_OLLAMA_BASE_URL = "http://127.0.0.1:11434"
DEFAULT_OLLAMA_MODEL = "llama3.1:8b"

_PROVIDER_ALIASES: dict[str, str] = {
    "": "gemini_api_key",
    "gemini_api_key": "gemini_api_key",
    "gemini-api-key": "gemini_api_key",
    "gemini-api": "gemini_api_key",
    "gemini_api": "gemini_api_key",
    "gemini": "gemini_api_key",
    "api_key": "gemini_api_key",
    "api-key": "gemini_api_key",
    "ai_studio": "gemini_api_key",
    "aistudio": "gemini_api_key",
    "gemini_oauth": "gemini_oauth",
    "gemini-oauth": "gemini_oauth",
    "oauth": "gemini_oauth",
    "oauth2": "gemini_oauth",
    "gemini_oauth2": "gemini_oauth",
    "gemini-oauth2": "gemini_oauth",
    "ollama": "ollama",
    "local": "ollama",
}


class ProviderError(RuntimeError):
    """Raised when an LLM provider fails or is misconfigured."""


def normalize_provider_name(name: Optional[str]) -> str:
    """Normalize provider aliases to canonical names ('gemini_api_key', 'gemini_oauth', 'ollama')."""
    raw = (name or "").strip().lower()
    if raw in _PROVIDER_ALIASES:
        return _PROVIDER_ALIASES[raw]
    raise ProviderError(
        f"Unsupported provider '{name}'. Choose from: gemini_api_key, gemini_oauth, ollama."
    )


def compose_prompt_input(question: str, context: str | None = None) -> str:
    """Combine optional grounded context with user question cleanly."""
    if context is None or not context.strip():
        return question
    ctx = context.strip()
    if ctx.startswith("["):
        return f"{ctx}\n\n{question}"
    return f"[CONTEXT]\n{ctx}\n\n{question}"


def _extract_text_from_steps(steps: Any) -> str:
    if not isinstance(steps, list):
        return ""
    collected: list[str] = []
    for step in reversed(steps):
        step_type = step.get("type") if isinstance(step, dict) else getattr(step, "type", None)
        if step_type == "user_input":
            break
        if step_type != "model_output":
            continue
        content = step.get("content") if isinstance(step, dict) else getattr(step, "content", None)
        if not isinstance(content, list):
            continue
        step_parts: list[str] = []
        for item in content:
            item_type = item.get("type") if isinstance(item, dict) else getattr(item, "type", None)
            if item_type == "thought":
                continue
            if item_type == "text":
                text_val = item.get("text") if isinstance(item, dict) else getattr(item, "text", None)
                if text_val:
                    step_parts.append(str(text_val))
        if step_parts:
            collected.append("".join(step_parts))
    return "".join(reversed(collected)).strip()


def _extract_interaction_text(interaction: Any) -> str:
    """Extract text from Interactions API SDK objects or JSON payloads."""
    if isinstance(interaction, dict):
        output_text = interaction.get("output_text")
        if isinstance(output_text, str) and output_text.strip():
            return output_text.strip()
        steps_text = _extract_text_from_steps(interaction.get("steps"))
        if steps_text:
            return steps_text
        outputs = interaction.get("outputs")
        if isinstance(outputs, list):
            parts = [
                str(item.get("text", ""))
                for item in outputs
                if isinstance(item, dict) and item.get("type") == "text" and item.get("text")
            ]
            if parts:
                return "\n".join(parts).strip()
        return ""

    output_text = getattr(interaction, "output_text", None)
    if isinstance(output_text, str) and output_text.strip():
        return output_text.strip()

    steps_text = _extract_text_from_steps(getattr(interaction, "steps", None))
    if steps_text:
        return steps_text

    outputs = getattr(interaction, "outputs", None)
    if isinstance(outputs, list):
        parts = [
            str(getattr(item, "text", ""))
            for item in outputs
            if getattr(item, "type", None) == "text" and getattr(item, "text", None)
        ]
        if parts:
            return "\n".join(parts).strip()

    return ""


class LLMProvider(ABC):
    """Unified interface for all Jiny Companion LLM backends."""

    @property
    @abstractmethod
    def provider_name(self) -> str:
        """Canonical name of this provider."""

    @abstractmethod
    def ask(self, question: str, locale: str = "esES", context: str | None = None) -> str:
        """Send a question (with optional RAG/grounding context) and return text."""

    @abstractmethod
    def reset_session(self) -> None:
        """Clear conversational state for this provider."""

    @abstractmethod
    def health_check(self) -> dict[str, Any]:
        """Return non-secret status metadata for this provider."""


class GeminiAPIKeyProvider(LLMProvider):
    """Gemini 3.8 Flash Interactions API provider authenticated via AI Studio API key."""

    def __init__(
        self,
        api_key: str,
        model: str = DEFAULT_MODEL,
        client: Any = None,
    ) -> None:
        self.model = sanitize_model_name(model)
        self.last_interaction_id: Optional[str] = None
        if client is not None:
            self._client = client
        else:
            if not api_key:
                raise ProviderError(
                    "Missing GEMINI_API_KEY. Set GEMINI_API_KEY or 'api_key' in companion/config.json."
                )
            from google import genai

            self._client = genai.Client(api_key=api_key)

    @property
    def provider_name(self) -> str:
        return "gemini_api_key"

    def reset_session(self) -> None:
        self.last_interaction_id = None

    def ask(self, question: str, locale: str = "esES", context: str | None = None) -> str:
        kwargs: dict[str, Any] = {
            "model": self.model,
            "input": compose_prompt_input(question, context),
            "system_instruction": build_system_instruction(locale),
        }
        if self.last_interaction_id:
            kwargs["previous_interaction_id"] = self.last_interaction_id

        try:
            interaction = self._client.interactions.create(**kwargs)
        except Exception as exc:
            raise ProviderError(f"Gemini API Key request failed: {exc}") from exc

        interaction_id = getattr(interaction, "id", None)
        if interaction_id:
            self.last_interaction_id = interaction_id

        return _extract_interaction_text(interaction)

    def health_check(self) -> dict[str, Any]:
        return {
            "provider": self.provider_name,
            "ok": self._client is not None,
            "model": self.model,
            "session_active": bool(self.last_interaction_id),
        }


class GeminiOAuthProvider(LLMProvider):
    """Gemini Interactions API provider authenticated via OAuth 2.0 (Vertex AI or Bearer REST)."""

    def __init__(
        self,
        oauth_manager: OAuthManager,
        model: str = DEFAULT_MODEL,
        vertexai: bool = False,
        gcp_project: str = "",
        gcp_location: str = "us-central1",
        client: Any = None,
        http_transport: Optional[HttpTransport] = None,
        base_url: str = DEFAULT_GEMINI_BASE_URL,
        timeout: float = 60.0,
    ) -> None:
        self.model = sanitize_model_name(model)
        self._oauth_manager = oauth_manager
        self.vertexai = bool(vertexai)
        self.gcp_project = (gcp_project or "").strip()
        self.gcp_location = (gcp_location or "us-central1").strip()
        self._injected_client = client
        self._client = client
        self._last_token: Optional[str] = None
        self._http_transport: HttpTransport = http_transport or default_http_transport
        self.base_url = (base_url or DEFAULT_GEMINI_BASE_URL).rstrip("/")
        self.timeout = max(1.0, float(timeout))
        self.last_interaction_id: Optional[str] = None

        if self.vertexai and self._injected_client is None and not self.gcp_project:
            raise ProviderError(
                "Vertex AI OAuth mode requires 'gcp_project' (JINY_GCP_PROJECT / GOOGLE_CLOUD_PROJECT)."
            )

    @property
    def provider_name(self) -> str:
        return "gemini_oauth"

    def reset_session(self) -> None:
        self.last_interaction_id = None

    def _get_vertex_client(self, force_refresh: bool = False) -> Any:
        if self._injected_client is not None:
            return self._injected_client

        try:
            token = self._oauth_manager.get_access_token(force_refresh=force_refresh)
            stored = self._oauth_manager.store.load()
        except OAuthError as exc:
            raise ProviderError(f"OAuth token unavailable: {exc}") from exc

        if self._client is None or token != self._last_token:
            from google import genai
            from google.oauth2.credentials import Credentials

            expiry = None
            if stored and stored.expires_at is not None:
                expiry = datetime.fromtimestamp(stored.expires_at, tz=timezone.utc).replace(tzinfo=None)

            creds = Credentials(
                token=token,
                refresh_token=stored.refresh_token if stored else None,
                token_uri=self._oauth_manager.token_endpoint,
                client_id=self._oauth_manager.client_id,
                client_secret=self._oauth_manager.client_secret or None,
                scopes=list(self._oauth_manager.scopes),
                expiry=expiry,
            )
            self._client = genai.Client(
                vertexai=True,
                credentials=creds,
                project=self.gcp_project,
                location=self.gcp_location,
            )
            self._last_token = token

        return self._client

    def _ask_vertex(self, question: str, locale: str, context: str | None) -> str:
        client = self._get_vertex_client()
        kwargs: dict[str, Any] = {
            "model": self.model,
            "input": compose_prompt_input(question, context),
            "system_instruction": build_system_instruction(locale),
        }
        if self.last_interaction_id:
            kwargs["previous_interaction_id"] = self.last_interaction_id
        try:
            interaction = client.interactions.create(**kwargs)
        except Exception as exc:
            raise ProviderError(f"Gemini OAuth (Vertex AI) request failed: {exc}") from exc

        interaction_id = getattr(interaction, "id", None)
        if interaction_id:
            self.last_interaction_id = interaction_id
        return _extract_interaction_text(interaction)

    def _ask_bearer_rest(self, question: str, locale: str, context: str | None) -> str:
        try:
            token = self._oauth_manager.get_access_token()
        except OAuthError as exc:
            raise ProviderError(f"OAuth token unavailable: {exc}") from exc

        url = f"{self.base_url}/v1beta/interactions"
        body_dict: dict[str, Any] = {
            "model": self.model,
            "input": compose_prompt_input(question, context),
            "system_instruction": build_system_instruction(locale),
        }
        if self.last_interaction_id:
            body_dict["previous_interaction_id"] = self.last_interaction_id
        body_bytes = json.dumps(body_dict).encode("utf-8")

        def _send(access_token: str) -> tuple[int, bytes]:
            headers = {
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "application/json",
                "Api-Revision": DEFAULT_API_REVISION,
            }
            try:
                return self._http_transport(url, headers, body_bytes, self.timeout)
            except OAuthError as exc:
                raise ProviderError(f"Gemini OAuth HTTP error: {exc}") from exc

        status, raw = _send(token)
        if status == 401:
            token_status = self._oauth_manager.get_token_status()
            if token_status.get("has_refresh_token"):
                try:
                    token = self._oauth_manager.get_access_token(force_refresh=True)
                except OAuthError as exc:
                    raise ProviderError(f"Gemini OAuth refresh after 401 failed: {exc}") from exc
                status, raw = _send(token)

        try:
            payload = json.loads(raw.decode("utf-8")) if raw else {}
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ProviderError(f"Gemini OAuth endpoint returned invalid JSON (HTTP {status}).") from exc

        if status >= 400:
            err_msg = ""
            if isinstance(payload, dict):
                err_obj = payload.get("error")
                if isinstance(err_obj, dict):
                    err_msg = str(err_obj.get("message", "")).strip()
                elif err_obj:
                    err_msg = str(err_obj).strip()
            detail = f": {err_msg}" if err_msg else ""
            raise ProviderError(f"Gemini OAuth API error (HTTP {status}){detail}")

        if isinstance(payload, dict) and payload.get("id"):
            self.last_interaction_id = str(payload["id"])

        return _extract_interaction_text(payload)

    def ask(self, question: str, locale: str = "esES", context: str | None = None) -> str:
        if self.vertexai or self._injected_client is not None:
            return self._ask_vertex(question, locale, context)
        return self._ask_bearer_rest(question, locale, context)

    def health_check(self) -> dict[str, Any]:
        token_status = self._oauth_manager.get_token_status()
        has_token = bool(token_status.get("has_token")) or (self._injected_client is not None)
        vertex_ok = (not self.vertexai) or bool(self.gcp_project) or (self._injected_client is not None)
        return {
            "provider": self.provider_name,
            "ok": has_token and vertex_ok,
            "mode": "vertexai" if self.vertexai else "bearer_interactions",
            "model": self.model,
            "vertexai": self.vertexai,
            "gcp_project": self.gcp_project,
            "gcp_location": self.gcp_location,
            "session_active": bool(self.last_interaction_id),
            **token_status,
        }


class OllamaProvider(LLMProvider):
    """Local Ollama provider using stdlib urllib HTTP transport."""

    def __init__(
        self,
        base_url: str = DEFAULT_OLLAMA_BASE_URL,
        model: str = DEFAULT_OLLAMA_MODEL,
        timeout: float = 60.0,
        http_transport: Optional[HttpTransport] = None,
    ) -> None:
        self.base_url = (base_url or DEFAULT_OLLAMA_BASE_URL).rstrip("/")
        self.model = (model or DEFAULT_OLLAMA_MODEL).strip()
        self.timeout = max(1.0, float(timeout))
        self._http_transport: HttpTransport = http_transport or default_http_transport
        self._history: list[dict[str, str]] = []

    @property
    def provider_name(self) -> str:
        return "ollama"

    def reset_session(self) -> None:
        self._history.clear()

    def ask(self, question: str, locale: str = "esES", context: str | None = None) -> str:
        messages: list[dict[str, str]] = [
            {"role": "system", "content": build_system_instruction(locale)},
            *self._history,
            {"role": "user", "content": compose_prompt_input(question, context)},
        ]
        body_bytes = json.dumps(
            {"model": self.model, "messages": messages, "stream": False}
        ).encode("utf-8")
        url = f"{self.base_url}/api/chat"
        headers = {"Content-Type": "application/json"}

        try:
            status, raw = self._http_transport(url, headers, body_bytes, self.timeout)
        except OAuthError as exc:
            raise ProviderError(f"Ollama connection failed ({self.base_url}): {exc}") from exc
        except Exception as exc:
            raise ProviderError(f"Ollama transport error ({self.base_url}): {exc}") from exc

        try:
            payload = json.loads(raw.decode("utf-8")) if raw else {}
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ProviderError(f"Ollama returned invalid JSON (HTTP {status}).") from exc

        if not isinstance(payload, dict):
            raise ProviderError(f"Ollama returned unexpected response (HTTP {status}).")

        if status >= 400 or payload.get("error"):
            err = payload.get("error") or f"HTTP {status}"
            raise ProviderError(f"Ollama error: {err}")

        answer = ""
        msg = payload.get("message")
        if isinstance(msg, dict) and msg.get("content") is not None:
            answer = str(msg["content"]).strip()
        elif payload.get("response") is not None:
            answer = str(payload["response"]).strip()

        if not answer:
            raise ProviderError("Ollama returned an empty response.")

        self._history.append({"role": "user", "content": question})
        self._history.append({"role": "assistant", "content": answer})
        return answer

    def health_check(self) -> dict[str, Any]:
        url = f"{self.base_url}/api/tags"
        probe_timeout = min(self.timeout, 5.0)
        try:
            status, raw = self._http_transport(url, {"Accept": "application/json"}, None, probe_timeout)
            payload = json.loads(raw.decode("utf-8")) if raw else {}
        except Exception as exc:
            return {
                "provider": self.provider_name,
                "ok": False,
                "base_url": self.base_url,
                "model": self.model,
                "models": [],
                "model_available": False,
                "error": str(exc),
            }

        if status >= 400 or not isinstance(payload, dict):
            return {
                "provider": self.provider_name,
                "ok": False,
                "base_url": self.base_url,
                "model": self.model,
                "models": [],
                "model_available": False,
                "error": f"HTTP {status}",
            }

        models = [
            str(m.get("name"))
            for m in payload.get("models", [])
            if isinstance(m, dict) and m.get("name")
        ]
        model_available = self.model in models or any(
            m.split(":", 1)[0] == self.model.split(":", 1)[0] for m in models
        )
        return {
            "provider": self.provider_name,
            "ok": True,
            "base_url": self.base_url,
            "model": self.model,
            "models": models,
            "model_available": model_available,
        }


def create_provider(config: CompanionConfig, **overrides: Any) -> LLMProvider:
    """Instantiate the configured LLMProvider from CompanionConfig and optional test overrides."""
    canonical = normalize_provider_name(overrides.get("provider") or config.provider)

    if canonical == "gemini_api_key":
        return GeminiAPIKeyProvider(
            api_key=config.api_key,
            model=config.model,
            client=overrides.get("client"),
        )

    if canonical == "gemini_oauth":
        oauth_manager = overrides.get("oauth_manager")
        if oauth_manager is None:
            oauth_manager = OAuthManager(
                client_id=config.oauth_client_id,
                client_secret=config.oauth_client_secret,
                token_path=config.oauth_token_path,
                scopes=config.oauth_scopes,
                auth_endpoint=config.oauth_auth_endpoint,
                token_endpoint=config.oauth_token_endpoint,
                http_transport=overrides.get("http_transport"),
            )
        return GeminiOAuthProvider(
            oauth_manager=oauth_manager,
            model=config.model,
            vertexai=config.vertexai,
            gcp_project=config.gcp_project,
            gcp_location=config.gcp_location,
            client=overrides.get("client"),
            http_transport=overrides.get("http_transport"),
            base_url=overrides.get("base_url", DEFAULT_GEMINI_BASE_URL),
            timeout=float(overrides.get("timeout", 60.0)),
        )

    return OllamaProvider(
        base_url=config.ollama_base_url,
        model=config.ollama_model,
        timeout=config.ollama_timeout,
        http_transport=overrides.get("http_transport"),
    )


def probe_provider_status(config: CompanionConfig) -> dict[str, Any]:
    """Offline-safe, non-throwing provider status probe for CLI --status."""
    try:
        canonical = normalize_provider_name(config.provider)
    except ProviderError as exc:
        return {
            "provider": str(config.provider),
            "ready": False,
            "model": config.model,
            "detail": str(exc),
        }

    if canonical == "gemini_api_key":
        has_key = bool(config.api_key)
        return {
            "provider": canonical,
            "ready": has_key,
            "model": config.model,
            "detail": "API key SET" if has_key else "MISSING (set GEMINI_API_KEY)",
        }

    if canonical == "gemini_oauth":
        store = OAuthTokenStore(Path(config.oauth_token_path))
        try:
            token = store.load()
            has_token = token is not None
            expired = token.is_expired() if token is not None else True
            has_refresh = bool(token and token.refresh_token)
        except OAuthError as exc:
            return {
                "provider": canonical,
                "ready": False,
                "model": config.model,
                "detail": f"token store error ({exc})",
            }
        mode = f"vertexai ({config.gcp_project or 'missing project'})" if config.vertexai else "bearer_interactions"
        ready = has_token and ((not expired) or has_refresh) and ((not config.vertexai) or bool(config.gcp_project))
        token_msg = "token READY" if has_token and not expired else ("token EXPIRED (refreshable)" if has_token and has_refresh else "token MISSING (run --oauth-login)")
        return {
            "provider": canonical,
            "ready": ready,
            "model": config.model,
            "detail": f"{mode}; {token_msg}; client_id={'SET' if config.oauth_client_id else 'MISSING'}",
        }

    return {
        "provider": canonical,
        "ready": True,
        "model": config.ollama_model,
        "detail": f"local endpoint {config.ollama_base_url} (offline check, not probed)",
    }
