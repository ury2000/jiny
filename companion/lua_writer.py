"""Atomic Lua data writer for Jiny/CompanionData.lua."""

from __future__ import annotations

import os
from pathlib import Path
import time

MAX_REPLIES = 50


def escape_lua_string(value: str) -> str:
    """Escape a Python string into a safe double-quoted Lua literal."""
    out: list[str] = []
    for ch in value:
        if ch == "\\":
            out.append("\\\\")
        elif ch == '"':
            out.append('\\"')
        elif ch == "\n":
            out.append("\\n")
        elif ch == "\r":
            out.append("\\r")
        elif ch == "\t":
            out.append("\\t")
        elif ord(ch) < 32:
            out.append(f"\\{ord(ch):03d}")
        else:
            out.append(ch)
    return "".join(out)


def render_companion_lua(
    replies: list[dict],
    status: str = "online",
    updated_at: int | None = None,
) -> str:
    """Render CompanionData.lua content using addon namespace contract."""
    ts = int(updated_at if updated_at is not None else time.time())
    trimmed = replies[-MAX_REPLIES:]
    lines = [
        "local ADDON, ns = ...",
        "",
        "ns.CompanionData = {",
        f"    updatedAt = {ts},",
        f'    companionStatus = "{escape_lua_string(status)}",',
        "    replies = {",
    ]
    for item in trimmed:
        req_id = escape_lua_string(str(item.get("id", "")))
        q = escape_lua_string(str(item.get("q", "")))
        a = escape_lua_string(str(item.get("a", "")))
        lang = escape_lua_string(str(item.get("lang", "esES")))
        item_t = int(item.get("t", ts))
        lines.extend(
            [
                "        {",
                f'            id = "{req_id}",',
                f'            lang = "{lang}",',
                f'            q = "{q}",',
                f'            a = "{a}",',
                f"            t = {item_t},",
                "        },",
            ]
        )
    lines.extend(["    },", "}", ""])
    return "\n".join(lines)


def write_companion_data(
    paths: list[Path],
    replies: list[dict],
    status: str = "online",
    updated_at: int | None = None,
) -> list[Path]:
    """Atomically write CompanionData.lua (UTF-8 without BOM) to each target path."""
    content = render_companion_lua(replies=replies, status=status, updated_at=updated_at)
    written: list[Path] = []
    for target in paths:
        target = Path(target)
        target.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = target.with_suffix(".lua.tmp")
        tmp_path.write_bytes(content.encode("utf-8"))
        os.replace(tmp_path, target)
        written.append(target)
    return written
