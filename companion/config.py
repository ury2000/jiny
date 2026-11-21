"""Configuration loader for Jiny Companion (WoW Classic Forever)."""

from dataclasses import dataclass
import json
import math
import os
from pathlib import Path
import warnings

DEFAULT_MODEL = "gemini-3.8-flash"
DEPRECATED_MODEL_PREFIXES = ("gemini-1.5-", "gemini-2.0-", "gemini-2.5-")

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CONFIG_PATH = Path(__file__).resolve().parent / "config.json"
DEFAULT_RAG_DB_PATH = REPO_ROOT / "companion" / "data" / "classic_era_rag.db"
DEFAULT_RAG_SEED_PATH = REPO_ROOT / "companion" / "data" / "classic_era_seed.json"
DEFAULT_RAG_TOP_K = 4
DEFAULT_TOKEN_PATH = Path(__file__).resolve().parent / "oauth_token.json"
DEFAULT_OAUTH_SCOPES: tuple[str, ...] = ("https://www.googleapis.com/auth/cloud-platform",)


def _resolve_repo_path(raw_value: str, default: Path) -> Path:
    cleaned = (raw_value or "").strip()
    if not cleaned:
        return default.resolve()
    candidate = Path(cleaned)
    if not candidate.is_absolute():
        candidate = (REPO_ROOT / candidate).resolve()
    return candidate


def _parse_bool(value: object, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        if isinstance(value, float) and not math.isfinite(value):
            return default
        return bool(value)
    text = str(value).strip().lower()
    if text in ("1", "true", "yes", "on"):
        return True
    if text in ("0", "false", "no", "off"):
        return False
    return default


def _parse_scopes(value: object) -> tuple[str, ...]:
    if not value:
        return DEFAULT_OAUTH_SCOPES
    if isinstance(value, (list, tuple)):
        items = [str(s).strip() for s in value if str(s).strip()]
        return tuple(items) if items else DEFAULT_OAUTH_SCOPES
    text = str(value).strip()
    if not text:
        return DEFAULT_OAUTH_SCOPES
    parts = [p.strip() for p in text.replace(",", " ").split() if p.strip()]
    return tuple(parts) if parts else DEFAULT_OAUTH_SCOPES


def sanitize_model_name(model_name: str | None) -> str:
    """Replace deprecated Gemini model IDs with the current default."""
    candidate = (model_name or "").strip()
    if not candidate:
        return DEFAULT_MODEL
    lower = candidate.lower()
    if any(lower.startswith(prefix) for prefix in DEPRECATED_MODEL_PREFIXES):
        warnings.warn(
            f"Model '{candidate}' is deprecated; substituting '{DEFAULT_MODEL}'.",
            stacklevel=2,
        )
        return DEFAULT_MODEL
    return candidate


@dataclass(frozen=True)
class CompanionConfig:
    api_key: str
    model: str
    wow_forever_dir: Path
    chat_log_path: Path
    dev_companion_data_path: Path
    deployed_companion_data_path: Path
    wtf_account_dir: Path
    poll_interval_seconds: float = 0.25
    # v0.3 Classic Era RAG
    rag_enabled: bool = True
    rag_db_path: Path = DEFAULT_RAG_DB_PATH
    rag_seed_path: Path = DEFAULT_RAG_SEED_PATH
    rag_top_k: int = DEFAULT_RAG_TOP_K
    # v0.4 Providers & OAuth 2.0
    provider: str = "gemini_api_key"
    ollama_base_url: str = "http://127.0.0.1:11434"
    ollama_model: str = "llama3.1:8b"
    ollama_timeout: float = 60.0
    oauth_client_id: str = ""
    oauth_client_secret: str = ""
    oauth_token_path: Path = DEFAULT_TOKEN_PATH
    oauth_scopes: tuple[str, ...] = DEFAULT_OAUTH_SCOPES
    oauth_auth_endpoint: str = "https://accounts.google.com/o/oauth2/v2/auth"
    oauth_token_endpoint: str = "https://oauth2.googleapis.com/token"
    vertexai: bool = False
    gcp_project: str = ""
    gcp_location: str = "us-central1"
    # v0.4 Modular Outputs (TTS & Overlay)
    tts_enabled: bool = False
    tts_backend: str = "auto"
    tts_rate: int = 0
    tts_volume: int = 100
    overlay_enabled: bool = False
    overlay_theme: str = "DarkGlass"
    overlay_opacity: float = 0.92
    overlay_always_on_top: bool = True


def _pick_numeric(env_name: str, raw_value: object, default: int | float) -> object:
    env_val = os.environ.get(env_name, "").strip()
    if env_val:
        return env_val
    if raw_value is None:
        return default
    if isinstance(raw_value, str):
        stripped = raw_value.strip()
        return stripped if stripped else default
    return raw_value


def _pick_bool(env_name: str, raw_value: object, default: bool) -> bool:
    env_val = os.environ.get(env_name, "").strip()
    if env_val:
        return _parse_bool(env_val, default=_parse_bool(raw_value, default=default))
    return _parse_bool(raw_value, default=default)


<<<<<<< HEAD
def _parse_finite_float(
    value: object,
    default: float,
    min_val: float | None = None,
    max_val: float | None = None,
) -> float:
    if isinstance(value, bool) or value is None:
        return default
    if isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            return default
        try:
            parsed = float(stripped)
        except ValueError:
            return default
    elif isinstance(value, (int, float)):
        parsed = float(value)
    else:
        return default
    if not math.isfinite(parsed):
        return default
    if min_val is not None:
        parsed = max(min_val, parsed)
    if max_val is not None:
        parsed = min(max_val, parsed)
    return parsed


def _parse_bounded_int(
    value: object,
    default: int,
    min_val: int,
    max_val: int,
) -> int:
    if isinstance(value, bool) or value is None:
        return default
    if isinstance(value, int):
        parsed = value
    elif isinstance(value, float):
        if not math.isfinite(value):
            return default
        parsed = int(value)
    elif isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            return default
        try:
            parsed = int(stripped)
        except ValueError:
            return default
    else:
        return default
    return max(min_val, min(max_val, parsed))


=======
>>>>>>> b206aed (fix(v0.4): reject non-finite OAuth expiry and empty boolean env overrides)
def load_config(config_path: Path | None = None) -> CompanionConfig:
    path = config_path or DEFAULT_CONFIG_PATH
    raw: dict = {}
    if path.exists():
        raw = json.loads(path.read_text(encoding="utf-8"))

    env_key = os.environ.get("GEMINI_API_KEY", "").strip()
    file_key = str(raw.get("api_key", "")).strip()
    api_key = env_key or file_key

    env_model = os.environ.get("JINY_GEMINI_MODEL", "").strip()
    file_model = str(raw.get("model", "")).strip()
    model = sanitize_model_name(env_model or file_model or DEFAULT_MODEL)

    raw_wow_dir = os.environ.get("JINY_WOW_FOREVER_DIR", "").strip() or str(
        raw.get("wow_forever_dir", "")
    ).strip()
    if raw_wow_dir:
        wow_path = Path(raw_wow_dir)
        if not wow_path.is_absolute():
            wow_path = (REPO_ROOT / wow_path).resolve()
    else:
        wow_path = (REPO_ROOT.parent / "_forever_").resolve()

    poll_interval = _parse_finite_float(
        _pick_numeric("JINY_POLL_INTERVAL_SECONDS", raw.get("poll_interval_seconds"), 0.25),
        default=0.25,
        min_val=0.05,
        max_val=5.0,
    )

    rag_enabled = _pick_bool("JINY_RAG_ENABLED", raw.get("rag_enabled"), default=True)

    raw_rag_db = os.environ.get("JINY_RAG_DB", "").strip() or str(
        raw.get("rag_db_path") or ""
    ).strip()
    rag_db_path = _resolve_repo_path(raw_rag_db, DEFAULT_RAG_DB_PATH)

    raw_rag_seed = os.environ.get("JINY_RAG_SEED", "").strip() or str(
        raw.get("rag_seed_path") or ""
    ).strip()
    rag_seed_path = _resolve_repo_path(raw_rag_seed, DEFAULT_RAG_SEED_PATH)

    rag_top_k = _parse_bounded_int(
        _pick_numeric("JINY_RAG_TOP_K", raw.get("rag_top_k"), DEFAULT_RAG_TOP_K),
        default=DEFAULT_RAG_TOP_K,
        min_val=1,
        max_val=20,
    )

    provider = (
        os.environ.get("JINY_PROVIDER", "").strip()
        or str(raw.get("provider", "gemini_api_key")).strip()
        or "gemini_api_key"
    )

    ollama_base_url = (
        os.environ.get("JINY_OLLAMA_BASE_URL", "").strip()
        or os.environ.get("OLLAMA_HOST", "").strip()
        or str(raw.get("ollama_base_url", "http://127.0.0.1:11434")).strip()
        or "http://127.0.0.1:11434"
    )
    ollama_model = (
        os.environ.get("JINY_OLLAMA_MODEL", "").strip()
        or str(raw.get("ollama_model", "llama3.1:8b")).strip()
        or "llama3.1:8b"
    )
    ollama_timeout = _parse_finite_float(
        _pick_numeric("JINY_OLLAMA_TIMEOUT", raw.get("ollama_timeout"), 60.0),
        default=60.0,
        min_val=1.0,
    )

    oauth_client_id = (
        os.environ.get("JINY_OAUTH_CLIENT_ID", "").strip()
        or str(raw.get("oauth_client_id", "")).strip()
    )
    oauth_client_secret = (
        os.environ.get("JINY_OAUTH_CLIENT_SECRET", "").strip()
        or str(raw.get("oauth_client_secret", "")).strip()
    )
    raw_token_path = os.environ.get("JINY_OAUTH_TOKEN_PATH", "").strip() or str(
        raw.get("oauth_token_path", "")
    ).strip()
    if raw_token_path:
        oauth_token_path = Path(raw_token_path)
        if not oauth_token_path.is_absolute():
            oauth_token_path = (REPO_ROOT / oauth_token_path).resolve()
    else:
        oauth_token_path = DEFAULT_TOKEN_PATH

    raw_scopes = os.environ.get("JINY_OAUTH_SCOPES", "").strip() or raw.get("oauth_scopes")
    oauth_scopes = _parse_scopes(raw_scopes)
    oauth_auth_endpoint = (
        os.environ.get("JINY_OAUTH_AUTH_ENDPOINT", "").strip()
        or str(raw.get("oauth_auth_endpoint", "https://accounts.google.com/o/oauth2/v2/auth")).strip()
        or "https://accounts.google.com/o/oauth2/v2/auth"
    )
    oauth_token_endpoint = (
        os.environ.get("JINY_OAUTH_TOKEN_ENDPOINT", "").strip()
        or str(raw.get("oauth_token_endpoint", "https://oauth2.googleapis.com/token")).strip()
        or "https://oauth2.googleapis.com/token"
    )

    vertexai = _pick_bool("JINY_VERTEXAI", raw.get("vertexai"), default=False)
    gcp_project = (
        os.environ.get("JINY_GCP_PROJECT", "").strip()
        or os.environ.get("GOOGLE_CLOUD_PROJECT", "").strip()
        or str(raw.get("gcp_project", "")).strip()
    )
    gcp_location = (
        os.environ.get("JINY_GCP_LOCATION", "").strip()
        or os.environ.get("GOOGLE_CLOUD_LOCATION", "").strip()
        or str(raw.get("gcp_location", "us-central1")).strip()
        or "us-central1"
    )

    tts_enabled = _pick_bool("JINY_TTS_ENABLED", raw.get("tts_enabled"), default=False)
    tts_backend = (
        os.environ.get("JINY_TTS_BACKEND", "").strip()
        or str(raw.get("tts_backend", "auto")).strip()
        or "auto"
    )
    tts_rate = _parse_bounded_int(
        _pick_numeric("JINY_TTS_RATE", raw.get("tts_rate"), 0),
        default=0,
        min_val=-10,
        max_val=10,
    )
    tts_volume = _parse_bounded_int(
        _pick_numeric("JINY_TTS_VOLUME", raw.get("tts_volume"), 100),
        default=100,
        min_val=0,
        max_val=100,
    )

    overlay_enabled = _pick_bool("JINY_OVERLAY_ENABLED", raw.get("overlay_enabled"), default=False)
    overlay_theme = (
        os.environ.get("JINY_OVERLAY_THEME", "").strip()
        or str(raw.get("overlay_theme", "DarkGlass")).strip()
        or "DarkGlass"
    )
    overlay_opacity = _parse_finite_float(
        _pick_numeric("JINY_OVERLAY_OPACITY", raw.get("overlay_opacity"), 0.92),
        default=0.92,
        min_val=0.3,
        max_val=1.0,
    )
    overlay_always_on_top = _pick_bool(
        "JINY_OVERLAY_ALWAYS_ON_TOP",
        raw.get("overlay_always_on_top"),
        default=True,
    )

    return CompanionConfig(
        api_key=api_key,
        model=model,
        wow_forever_dir=wow_path,
        chat_log_path=wow_path / "Logs" / "WoWChatLog.txt",
        dev_companion_data_path=REPO_ROOT / "Jiny" / "CompanionData.lua",
        deployed_companion_data_path=wow_path / "Interface" / "AddOns" / "Jiny" / "CompanionData.lua",
        wtf_account_dir=wow_path / "WTF" / "Account",
        poll_interval_seconds=poll_interval,
        rag_enabled=rag_enabled,
        rag_db_path=rag_db_path,
        rag_seed_path=rag_seed_path,
        rag_top_k=rag_top_k,
        provider=provider,
        ollama_base_url=ollama_base_url,
        ollama_model=ollama_model,
        ollama_timeout=ollama_timeout,
        oauth_client_id=oauth_client_id,
        oauth_client_secret=oauth_client_secret,
        oauth_token_path=oauth_token_path,
        oauth_scopes=oauth_scopes,
        oauth_auth_endpoint=oauth_auth_endpoint,
        oauth_token_endpoint=oauth_token_endpoint,
        vertexai=vertexai,
        gcp_project=gcp_project,
        gcp_location=gcp_location,
        tts_enabled=tts_enabled,
        tts_backend=tts_backend,
        tts_rate=tts_rate,
        tts_volume=tts_volume,
        overlay_enabled=overlay_enabled,
        overlay_theme=overlay_theme,
        overlay_opacity=overlay_opacity,
        overlay_always_on_top=overlay_always_on_top,
    )