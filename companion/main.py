"""CLI entry point for Jiny Companion (WoW Classic Forever)."""

from __future__ import annotations

import argparse
from dataclasses import replace
import importlib.util
from pathlib import Path
import sys
import time
from typing import Optional

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from companion import __version__
from companion.config import CompanionConfig, load_config
from companion.gemini_client import JinyGeminiClient
from companion.log_reader import ChatLogReader, extract_savedvariables_outbox
from companion.lua_writer import write_companion_data
from companion.oauth import OAuthError, run_oauth_login
from companion.overlay import OverlayManager, resolve_overlay_theme
from companion.prompts import format_rag_context
from companion.providers import (
    LLMProvider,
    ProviderError,
    create_provider,
    normalize_provider_name,
    probe_provider_status,
)
from companion.rag_schema import CLASSIC_ERA_VERSION, VALID_ENTITY_TYPES
from companion.rag_store import ClassicRagStore
from companion.tts import TTSManager, create_tts_backend


def _resolve_target_paths(cfg: CompanionConfig, include_deployed: bool) -> list[Path]:
    targets = [cfg.dev_companion_data_path]
    if include_deployed and cfg.deployed_companion_data_path.parent.exists():
        targets.append(cfg.deployed_companion_data_path)
    return targets


def _find_savedvariables_files(wtf_account_dir: Path) -> list[Path]:
    if not wtf_account_dir.exists():
        return []
    return sorted(wtf_account_dir.glob("*/SavedVariables/Jiny.lua"))


def _open_rag_store(cfg: CompanionConfig, auto_build: bool = True) -> ClassicRagStore:
    return ClassicRagStore(
        db_path=cfg.rag_db_path,
        seed_path=cfg.rag_seed_path,
        auto_build=auto_build,
    )


def _apply_cli_overrides(cfg: CompanionConfig, args: argparse.Namespace) -> CompanionConfig:
    updates: dict[str, object] = {}
    if getattr(args, "provider", None) is not None:
        updates["provider"] = normalize_provider_name(args.provider)
    if getattr(args, "tts_override", None) is not None:
        updates["tts_enabled"] = bool(args.tts_override)
    if getattr(args, "overlay_override", None) is not None:
        updates["overlay_enabled"] = bool(args.overlay_override)
    if getattr(args, "overlay_theme", None) is not None:
        updates["overlay_theme"] = resolve_overlay_theme(args.overlay_theme)
    if getattr(args, "no_rag", False):
        updates["rag_enabled"] = False
    if getattr(args, "rag_top_k", None) is not None:
        updates["rag_top_k"] = max(1, min(20, int(args.rag_top_k)))
    return replace(cfg, **updates) if updates else cfg


def _instantiate_provider(cfg: CompanionConfig, provider: Optional[LLMProvider] = None) -> LLMProvider:
    if provider is not None:
        return provider
    canonical = normalize_provider_name(cfg.provider)
    if canonical == "gemini_api_key":
        return JinyGeminiClient(api_key=cfg.api_key, model=cfg.model)
    return create_provider(cfg)


def _answer_question(
    provider: LLMProvider,
    cfg: CompanionConfig,
    question: str,
    locale: str,
    context: str | None = None,
) -> str:
    """Single answer hook feeding grounded Classic Era RAG context into active provider."""
    _ = cfg
    return provider.ask(question=question, locale=locale, context=context)


def cmd_status(cfg: CompanionConfig) -> int:
    try:
        import google.genai as genai_mod

        sdk_ver = getattr(genai_mod, "__version__", "installed")
    except ImportError:
        sdk_ver = "NOT INSTALLED (run: py -m pip install -U google-genai)"

    probe = probe_provider_status(cfg)
    tts_backend = create_tts_backend(cfg.tts_backend, rate=cfg.tts_rate, volume=cfg.tts_volume)
    tk_available = importlib.util.find_spec("tkinter") is not None

    print(f"Jiny Companion Status v{__version__} (WoW Classic Forever)")
    print(f"  Provider      : {probe['provider']} ({probe['detail']})")
    print(f"  Model         : {probe['model']}")
    print(f"  google-genai  : {sdk_ver}")
    print(
        f"  TTS           : {'ENABLED' if cfg.tts_enabled else 'disabled'} "
        f"(backend={cfg.tts_backend}, resolved={tts_backend.name})"
    )
    print(
        f"  Overlay       : {'ENABLED' if cfg.overlay_enabled else 'disabled'} "
        f"(theme={resolve_overlay_theme(cfg.overlay_theme)}, tkinter={'available' if tk_available else 'unavailable'})"
    )
    print(f"  _forever_ dir : {cfg.wow_forever_dir} ({'OK' if cfg.wow_forever_dir.exists() else 'NOT FOUND'})")
    print(f"  WoWChatLog    : {cfg.chat_log_path} ({'EXISTS' if cfg.chat_log_path.exists() else 'waiting for /chatlog'})")
    print(f"  Dev Lua data  : {cfg.dev_companion_data_path}")
    deployed_dir_exists = cfg.deployed_companion_data_path.parent.exists()
    print(
        f"  Deployed data : {cfg.deployed_companion_data_path} "
        f"({'addon folder present' if deployed_dir_exists else 'not deployed yet'})"
    )
    print(f"  RAG enabled   : {cfg.rag_enabled} (Classic Era {CLASSIC_ERA_VERSION}, top_k={cfg.rag_top_k})")
    print(f"  RAG DB        : {cfg.rag_db_path} ({'EXISTS' if cfg.rag_db_path.exists() else 'will auto-seed'})")
    print(f"  RAG seed      : {cfg.rag_seed_path} ({'OK' if cfg.rag_seed_path.exists() else 'MISSING'})")
    if cfg.rag_db_path.exists():
        with _open_rag_store(cfg, auto_build=False) as store:
            counts = store.stats()
        print(
            "  RAG counts    : "
            f"quests={counts['quests']}, mobs={counts['mobs']}, "
            f"items={counts['items']}, dungeons={counts['dungeons']}, total={counts['total']}"
        )
    return 0


def cmd_rag_rebuild(cfg: CompanionConfig) -> int:
    with _open_rag_store(cfg, auto_build=False) as store:
        counts = store.rebuild(cfg.rag_seed_path)
    print(f"Rebuilt Classic Era {CLASSIC_ERA_VERSION} RAG index: {cfg.rag_db_path}")
    print(f"  Seed   : {cfg.rag_seed_path}")
    print(
        "  Counts : "
        f"quests={counts['quests']}, mobs={counts['mobs']}, "
        f"items={counts['items']}, dungeons={counts['dungeons']}, total={counts['total']}"
    )
    return 0


def cmd_rag_stats(cfg: CompanionConfig) -> int:
    with _open_rag_store(cfg, auto_build=True) as store:
        counts = store.stats()
    print(f"Jiny Classic Era {CLASSIC_ERA_VERSION} RAG Stats")
    print(f"  DB path  : {cfg.rag_db_path}")
    print(f"  Seed     : {cfg.rag_seed_path}")
    print(f"  Quests   : {counts['quests']}")
    print(f"  Mobs     : {counts['mobs']}")
    print(f"  Items    : {counts['items']}")
    print(f"  Dungeons : {counts['dungeons']}")
    print(f"  Total    : {counts['total']}")
    return 0


def cmd_rag_query(
    cfg: CompanionConfig,
    query: str,
    locale: str,
    entity_type: str | None = None,
    top_k: int | None = None,
) -> int:
    effective_k = max(1, min(20, top_k if top_k is not None else cfg.rag_top_k))
    with _open_rag_store(cfg, auto_build=True) as store:
        hits = store.retrieve(query, top_k=effective_k, entity_type=entity_type)
    print(format_rag_context(hits, locale=locale, query=query))
    return 0


def cmd_oauth_login(cfg: CompanionConfig) -> int:
    try:
        token_path = run_oauth_login(cfg)
    except (OAuthError, ProviderError, ValueError) as exc:
        print(f"[Error (oauth)]: {exc}")
        return 1
    print(f"OAuth token stored safely at: {token_path}")
    return 0


def cmd_ask(
    cfg: CompanionConfig,
    question: str,
    locale: str,
    req_id: str | None,
    dry_run: bool,
    write_deployed: bool,
    no_rag: bool = False,
    rag_top_k: int | None = None,
    rag_type: str | None = None,
    provider: Optional[LLMProvider] = None,
    tts: Optional[TTSManager] = None,
    overlay: Optional[OverlayManager] = None,
) -> int:
    rid = req_id or f"cli-{int(time.time())}"
    use_rag = cfg.rag_enabled and not no_rag
    effective_k = max(1, min(20, rag_top_k if rag_top_k is not None else cfg.rag_top_k))
    hits = []
    rag_context: str | None = None

    active_overlay = overlay or OverlayManager.from_config(cfg)
    active_tts = tts or TTSManager.from_config(cfg)

    active_overlay.start()
    try:
        active_overlay.update_status("thinking", provider=cfg.provider)
        active_overlay.show_question(question)

        if use_rag:
            with _open_rag_store(cfg, auto_build=True) as store:
                hits = store.retrieve(question, top_k=effective_k, entity_type=rag_type)
            rag_context = format_rag_context(hits, locale=locale, query=question)

        if dry_run:
            if use_rag and hits:
                rag_summary = f" | RAG hits={len(hits)} ({hits[0].name}: {hits[0].snippet})"
            elif use_rag:
                rag_summary = " | RAG=NO_LOCAL_RAG_MATCH"
            else:
                rag_summary = " | RAG=DISABLED"
            active_model = cfg.ollama_model if normalize_provider_name(cfg.provider) == "ollama" else cfg.model
            answer = (
                f"[Dry-Run {cfg.provider} / {active_model} | {locale}] Vista previa local de respuesta "
                f"para: {question}{rag_summary}"
            )
            if rag_context:
                print(rag_context)
        else:
            active_provider = _instantiate_provider(cfg, provider=provider)
            active_provider_name = getattr(active_provider, "provider_name", cfg.provider)
            active_overlay.update_status("thinking", provider=active_provider_name)
            answer = _answer_question(
                active_provider,
                cfg,
                question=question,
                locale=locale,
                context=rag_context,
            )

        active_overlay.show_reply(question, answer)
        active_overlay.update_status("online", provider=cfg.provider)
        active_tts.speak(answer, locale=locale)
        if active_tts.enabled:
            active_tts.flush(timeout=15.0)
    except (ProviderError, OAuthError, ValueError) as exc:
        active_overlay.show_error(str(exc))
        print(f"[Error ({cfg.provider})]: {exc}")
        return 1
    finally:
        if tts is None:
            active_tts.close()
        if overlay is None:
            active_overlay.close()

    print(f"\n[Jiny ({cfg.provider})]: {answer}\n")
    replies = [{"id": rid, "lang": locale, "q": question, "a": answer, "t": int(time.time())}]
    targets = _resolve_target_paths(cfg, include_deployed=write_deployed)
    written = write_companion_data(targets, replies, status="online")
    for path in written:
        print(f"Updated: {path}")
    return 0


def cmd_watch(
    cfg: CompanionConfig,
    start_from_beginning: bool,
    no_rag: bool = False,
    dry_run: bool = False,
    provider: Optional[LLMProvider] = None,
    tts: Optional[TTSManager] = None,
    overlay: Optional[OverlayManager] = None,
) -> int:
    active_provider: Optional[LLMProvider] = None
    if not dry_run:
        try:
            active_provider = _instantiate_provider(cfg, provider=provider)
        except (ProviderError, OAuthError, ValueError) as exc:
            print(f"[Error ({cfg.provider})]: {exc}")
            return 1
        active_provider_name = getattr(active_provider, "provider_name", cfg.provider)
    else:
        active_provider_name = cfg.provider

    use_rag = cfg.rag_enabled and not no_rag
    rag_store = _open_rag_store(cfg, auto_build=True) if use_rag else None
    active_overlay = overlay or OverlayManager.from_config(cfg)
    active_tts = tts or TTSManager.from_config(cfg)
    active_overlay.start()
    active_overlay.update_status("watching", provider=active_provider_name)

    reader = ChatLogReader(cfg.chat_log_path, start_at_end=not start_from_beginning)
    sv_files = _find_savedvariables_files(cfg.wtf_account_dir)
    replies: list[dict] = []

    print(f"Jiny Companion v{__version__} watching WoW Classic Forever ({active_provider_name})")
    print(f"  Log file : {cfg.chat_log_path}")
    print(f"  RAG      : {'ENABLED' if rag_store is not None else 'DISABLED'}")
    print(f"  Targets  : {[str(p) for p in _resolve_target_paths(cfg, include_deployed=True)]}")
    print("Press Ctrl+C to stop.\n")

    try:
        while True:
            pending = reader.poll()
            for sv_path in sv_files:
                pending.extend(extract_savedvariables_outbox(sv_path, reader.seen_ids))

            for req_id, locale, question in pending:
                print(f"[User #{req_id} ({locale})]: {question}")
                rag_context: str | None = None
                if rag_store is not None:
                    try:
                        hits = rag_store.retrieve(question, top_k=cfg.rag_top_k)
                        rag_context = format_rag_context(hits, locale=locale, query=question)
                    except Exception as rag_exc:
                        print(f"[Jiny] RAG warning: {rag_exc}")
                        rag_context = None

                active_overlay.update_status("thinking", provider=active_provider_name)
                active_overlay.show_question(question)
                try:
                    if dry_run or active_provider is None:
                        answer = f"[Dry-Run {cfg.model} | {locale}] {question}"
                    else:
                        answer = _answer_question(
                            active_provider,
                            cfg,
                            question=question,
                            locale=locale,
                            context=rag_context,
                        )
                except Exception as exc:
                    print(f"[Error ({active_provider_name})]: {exc}")
                    active_overlay.show_error(str(exc))
                    continue

                print(f"[Jiny]: {answer}\n")
                active_overlay.show_reply(question, answer)
                active_overlay.update_status("online", provider=active_provider_name)
                active_tts.speak(answer, locale=locale)

                replies.append(
                    {
                        "id": req_id,
                        "lang": locale,
                        "q": question,
                        "a": answer,
                        "t": int(time.time()),
                    }
                )
                targets = _resolve_target_paths(cfg, include_deployed=True)
                write_companion_data(targets, replies, status="online")

            time.sleep(cfg.poll_interval_seconds)
    except KeyboardInterrupt:
        print("\nJiny Companion stopped.")
    finally:
        if rag_store is not None:
            rag_store.close()
        if tts is None:
            active_tts.stop(drain=False)
        if overlay is None:
            active_overlay.close()
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Jiny Companion for WoW Classic Forever")
    parser.add_argument("--config", type=Path, default=None, help="Path to config.json")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--status", action="store_true", help="Inspect configuration and paths")
    group.add_argument("--watch", action="store_true", help="Watch WoWChatLog.txt in real time")
    group.add_argument("--ask", type=str, help="Send a one-off question to the active LLM provider")
    group.add_argument("--oauth-login", action="store_true", help="Authenticate via OAuth 2.0 PKCE flow")
    group.add_argument("--rag-rebuild", action="store_true", help="Rebuild local Classic Era RAG SQLite index")
    group.add_argument("--rag-stats", action="store_true", help="Show Classic Era RAG index counts")
    group.add_argument("--rag-query", type=str, help="Query local Classic Era RAG store offline")

    parser.add_argument(
        "--provider",
        type=str,
        default=None,
        help="Override LLM provider (gemini_api_key, gemini_oauth, ollama)",
    )

    tts_group = parser.add_mutually_exclusive_group()
    tts_group.add_argument("--tts", dest="tts_override", action="store_const", const=True, default=None, help="Enable TTS output")
    tts_group.add_argument("--no-tts", dest="tts_override", action="store_const", const=False, help="Disable TTS output")

    overlay_group = parser.add_mutually_exclusive_group()
    overlay_group.add_argument(
        "--overlay",
        dest="overlay_override",
        action="store_const",
        const=True,
        default=None,
        help="Enable lightweight overlay window",
    )
    overlay_group.add_argument(
        "--no-overlay",
        dest="overlay_override",
        action="store_const",
        const=False,
        help="Disable lightweight overlay window",
    )
    parser.add_argument(
        "--overlay-theme",
        choices=["DarkGlass", "ParchmentLight"],
        default=None,
        help="Override overlay theme",
    )

    parser.add_argument("--lang", default="esES", choices=["esES", "enUS", "itIT"], help="Response locale")
    parser.add_argument("--id", dest="req_id", default=None, help="Custom request ID for --ask")
    parser.add_argument("--dry-run", action="store_true", help="Simulate reply without calling LLM API")
    parser.add_argument("--no-rag", action="store_true", help="Disable local RAG context injection")
    parser.add_argument(
        "--rag-type",
        default=None,
        choices=list(VALID_ENTITY_TYPES),
        help="Optional entity type filter for RAG queries",
    )
    parser.add_argument(
        "--rag-top-k",
        type=int,
        default=None,
        help="Override number of RAG results retrieved",
    )
    parser.add_argument(
        "--write-deployed",
        action="store_true",
        help="Also write CompanionData.lua into _forever_ if deployed",
    )
    parser.add_argument(
        "--from-start",
        action="store_true",
        help="Read existing WoWChatLog.txt from offset 0 on --watch startup",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    cfg = load_config(args.config)
    try:
        cfg = _apply_cli_overrides(cfg, args)
    except ProviderError as exc:
        print(f"[Error]: {exc}")
        return 1

    if args.status:
        return cmd_status(cfg)
    if args.oauth_login:
        return cmd_oauth_login(cfg)
    if args.rag_rebuild:
        return cmd_rag_rebuild(cfg)
    if args.rag_stats:
        return cmd_rag_stats(cfg)
    if args.rag_query is not None:
        return cmd_rag_query(
            cfg=cfg,
            query=args.rag_query,
            locale=args.lang,
            entity_type=args.rag_type,
            top_k=args.rag_top_k,
        )
    if args.ask is not None:
        return cmd_ask(
            cfg=cfg,
            question=args.ask,
            locale=args.lang,
            req_id=args.req_id,
            dry_run=args.dry_run,
            write_deployed=args.write_deployed,
            no_rag=args.no_rag,
            rag_top_k=args.rag_top_k,
            rag_type=args.rag_type,
        )
    if args.watch:
        return cmd_watch(
            cfg,
            start_from_beginning=args.from_start,
            no_rag=args.no_rag,
            dry_run=args.dry_run,
        )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())