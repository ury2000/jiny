"""CLI entry point for Jiny Companion (WoW Classic Forever)."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys
import time

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from companion.config import CompanionConfig, load_config
from companion.gemini_client import JinyGeminiClient
from companion.log_reader import ChatLogReader, extract_savedvariables_outbox
from companion.lua_writer import write_companion_data
from companion.prompts import format_rag_context
from companion.rag_schema import CLASSIC_ERA_VERSION, VALID_ENTITY_TYPES
from companion.rag_store import ClassicRagStore


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


def cmd_status(cfg: CompanionConfig) -> int:
    try:
        import google.genai as genai_mod

        sdk_ver = getattr(genai_mod, "__version__", "installed")
    except ImportError:
        sdk_ver = "NOT INSTALLED (run: py -m pip install -U google-genai)"

    print("Jiny Companion Status (WoW Classic Forever)")
    print(f"  Model         : {cfg.model}")
    print(f"  API Key       : {'SET' if cfg.api_key else 'MISSING (set GEMINI_API_KEY)'}")
    print(f"  google-genai  : {sdk_ver}")
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
) -> int:
    rid = req_id or f"cli-{int(time.time())}"
    use_rag = cfg.rag_enabled and not no_rag
    effective_k = max(1, min(20, rag_top_k if rag_top_k is not None else cfg.rag_top_k))
    hits = []
    rag_context: str | None = None
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
        answer = (
            f"[Dry-Run {cfg.model} | {locale}] Vista previa local de respuesta "
            f"para: {question}{rag_summary}"
        )
        if rag_context:
            print(rag_context)
    else:
        client = JinyGeminiClient(api_key=cfg.api_key, model=cfg.model)
        answer = client.ask(question=question, locale=locale, context=rag_context)

    print(f"\n[Jiny ({cfg.model})]: {answer}\n")
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
) -> int:
    client = None if dry_run else JinyGeminiClient(api_key=cfg.api_key, model=cfg.model)
    use_rag = cfg.rag_enabled and not no_rag
    rag_store = _open_rag_store(cfg, auto_build=True) if use_rag else None
    reader = ChatLogReader(cfg.chat_log_path, start_at_end=not start_from_beginning)
    sv_files = _find_savedvariables_files(cfg.wtf_account_dir)
    replies: list[dict] = []

    print(f"Jiny Companion watching WoW Classic Forever ({cfg.model})")
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
                try:
                    if dry_run or client is None:
                        answer = f"[Dry-Run {cfg.model} | {locale}] {question}"
                    else:
                        answer = client.ask(question=question, locale=locale, context=rag_context)
                except Exception as exc:
                    print(f"[Error Gemini API]: {exc}")
                    continue

                print(f"[Jiny]: {answer}\n")
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
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Jiny Companion for WoW Classic Forever")
    parser.add_argument("--config", type=Path, default=None, help="Path to config.json")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--status", action="store_true", help="Inspect configuration and paths")
    group.add_argument("--watch", action="store_true", help="Watch WoWChatLog.txt in real time")
    group.add_argument("--ask", type=str, help="Send a one-off question to Gemini")
    group.add_argument("--rag-rebuild", action="store_true", help="Rebuild local Classic Era RAG SQLite index")
    group.add_argument("--rag-stats", action="store_true", help="Show Classic Era RAG index counts")
    group.add_argument("--rag-query", type=str, help="Query local Classic Era RAG store offline")
    parser.add_argument("--lang", default="esES", choices=["esES", "enUS", "itIT"], help="Response locale")
    parser.add_argument("--id", dest="req_id", default=None, help="Custom request ID for --ask")
    parser.add_argument("--dry-run", action="store_true", help="Simulate reply without calling Gemini API")
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

    if args.status:
        return cmd_status(cfg)
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
