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


def _resolve_target_paths(cfg: CompanionConfig, include_deployed: bool) -> list[Path]:
    targets = [cfg.dev_companion_data_path]
    if include_deployed and cfg.deployed_companion_data_path.parent.exists():
        targets.append(cfg.deployed_companion_data_path)
    return targets


def _find_savedvariables_files(wtf_account_dir: Path) -> list[Path]:
    if not wtf_account_dir.exists():
        return []
    return sorted(wtf_account_dir.glob("*/SavedVariables/Jiny.lua"))


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
    return 0


def cmd_ask(
    cfg: CompanionConfig,
    question: str,
    locale: str,
    req_id: str | None,
    dry_run: bool,
    write_deployed: bool,
) -> int:
    rid = req_id or f"cli-{int(time.time())}"
    if dry_run:
        answer = (
            f"[Dry-Run {cfg.model} | {locale}] Vista previa local de respuesta "
            f"para: {question}"
        )
    else:
        client = JinyGeminiClient(api_key=cfg.api_key, model=cfg.model)
        answer = client.ask(question=question, locale=locale)

    print(f"\n[Jiny ({cfg.model})]: {answer}\n")
    replies = [{"id": rid, "lang": locale, "q": question, "a": answer, "t": int(time.time())}]
    targets = _resolve_target_paths(cfg, include_deployed=write_deployed)
    written = write_companion_data(targets, replies, status="online")
    for path in written:
        print(f"Updated: {path}")
    return 0


def cmd_watch(cfg: CompanionConfig, start_from_beginning: bool) -> int:
    client = JinyGeminiClient(api_key=cfg.api_key, model=cfg.model)
    reader = ChatLogReader(cfg.chat_log_path, start_at_end=not start_from_beginning)
    sv_files = _find_savedvariables_files(cfg.wtf_account_dir)
    replies: list[dict] = []

    print(f"Jiny Companion watching WoW Classic Forever ({cfg.model})")
    print(f"  Log file : {cfg.chat_log_path}")
    print(f"  Targets  : {[str(p) for p in _resolve_target_paths(cfg, include_deployed=True)]}")
    print("Press Ctrl+C to stop.\n")

    try:
        while True:
            pending = reader.poll()
            for sv_path in sv_files:
                pending.extend(extract_savedvariables_outbox(sv_path, reader.seen_ids))

            for req_id, locale, question in pending:
                print(f"[User #{req_id} ({locale})]: {question}")
                try:
                    answer = client.ask(question=question, locale=locale)
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
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Jiny Companion for WoW Classic Forever")
    parser.add_argument("--config", type=Path, default=None, help="Path to config.json")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--status", action="store_true", help="Inspect configuration and paths")
    group.add_argument("--watch", action="store_true", help="Watch WoWChatLog.txt in real time")
    group.add_argument("--ask", type=str, help="Send a one-off question to Gemini")
    parser.add_argument("--lang", default="esES", choices=["esES", "enUS", "itIT"], help="Response locale")
    parser.add_argument("--id", dest="req_id", default=None, help="Custom request ID for --ask")
    parser.add_argument("--dry-run", action="store_true", help="Simulate reply without calling Gemini API")
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
    if args.ask:
        return cmd_ask(
            cfg=cfg,
            question=args.ask,
            locale=args.lang,
            req_id=args.req_id,
            dry_run=args.dry_run,
            write_deployed=args.write_deployed,
        )
    if args.watch:
        return cmd_watch(cfg, start_from_beginning=args.from_start)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
