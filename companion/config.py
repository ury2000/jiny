"""Configuration loader for Jiny Companion (WoW Classic Forever)."""

from dataclasses import dataclass
import json
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


def _resolve_repo_path(raw_value: str, default: Path) -> Path:
    cleaned = (raw_value or "").strip()
    if not cleaned:
        return default.resolve()
    candidate = Path(cleaned)
    if not candidate.is_absolute():
        candidate = (REPO_ROOT / candidate).resolve()
    return candidate


def _parse_bool(value: object, default: bool = True) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    text = str(value or "").strip().lower()
    if not text:
        return default
    if text in {"1", "true", "yes", "on"}:
        return True
    if text in {"0", "false", "no", "off"}:
        return False
    return default


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
    rag_enabled: bool = True
    rag_db_path: Path = DEFAULT_RAG_DB_PATH
    rag_seed_path: Path = DEFAULT_RAG_SEED_PATH
    rag_top_k: int = DEFAULT_RAG_TOP_K


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

    poll_interval = float(raw.get("poll_interval_seconds", 0.25) or 0.25)
    poll_interval = max(0.1, min(5.0, poll_interval))

    env_rag_enabled = os.environ.get("JINY_RAG_ENABLED", "").strip()
    rag_enabled = _parse_bool(
        env_rag_enabled if env_rag_enabled else raw.get("rag_enabled", True),
        default=True,
    )

    raw_rag_db = os.environ.get("JINY_RAG_DB", "").strip() or str(
        raw.get("rag_db_path") or ""
    ).strip()
    rag_db_path = _resolve_repo_path(raw_rag_db, DEFAULT_RAG_DB_PATH)

    raw_rag_seed = os.environ.get("JINY_RAG_SEED", "").strip() or str(
        raw.get("rag_seed_path") or ""
    ).strip()
    rag_seed_path = _resolve_repo_path(raw_rag_seed, DEFAULT_RAG_SEED_PATH)

    raw_top_k = os.environ.get("JINY_RAG_TOP_K", "").strip() or raw.get(
        "rag_top_k", DEFAULT_RAG_TOP_K
    )
    try:
        rag_top_k = int(raw_top_k)
    except (TypeError, ValueError):
        rag_top_k = DEFAULT_RAG_TOP_K
    rag_top_k = max(1, min(20, rag_top_k))

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
    )
