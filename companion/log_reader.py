"""Privacy-filtered incremental reader for WoWChatLog.txt and Jiny SavedVariables."""

from __future__ import annotations

from pathlib import Path
import re

QUERY_RE = re.compile(r"\[JINY_Q#([A-Za-z0-9_-]+)#([A-Za-z]+)\]\s+(.+?)\s*$")
SV_ENTRY_RE = re.compile(
    r'\{\s*(?=[^}]*\["id"\]\s*=\s*"([^"]+)")'
    r'(?=[^}]*\["q"\]\s*=\s*"((?:[^"\\]|\\.)*)")'
    r'(?=[^}]*\["lang"\]\s*=\s*"([^"]+)")'
    r'[^}]*\}',
    re.DOTALL,
)


def parse_query_line(line: str) -> tuple[str, str, str] | None:
    """Return (req_id, locale, question) only if line matches Jiny's explicit prefix."""
    match = QUERY_RE.search(line)
    if not match:
        return None
    req_id, locale, question = match.group(1), match.group(2), match.group(3).strip()
    if not question:
        return None
    return req_id, locale, question


class ChatLogReader:
    """Incremental byte-offset reader for WoWChatLog.txt with strict privacy filtering."""

    def __init__(self, log_path: Path, start_at_end: bool = True) -> None:
        self.log_path = Path(log_path)
        self.seen_ids: set[str] = set()
        self.offset: int = 0
        self._remainder: str = ""
        if start_at_end and self.log_path.exists():
            self.offset = self.log_path.stat().st_size

    def poll(self) -> list[tuple[str, str, str]]:
        """Read newly appended bytes and return unique (req_id, locale, question) tuples."""
        if not self.log_path.exists():
            return []

        size = self.log_path.stat().st_size
        if size < self.offset:
            # File was rotated or truncated
            self.offset = 0
            self._remainder = ""

        if size == self.offset:
            return []

        with self.log_path.open("rb") as fh:
            fh.seek(self.offset)
            chunk = fh.read()
            self.offset = fh.tell()

        text = self._remainder + chunk.decode("utf-8", errors="replace")
        lines = text.splitlines(keepends=True)
        self._remainder = ""
        if lines and not lines[-1].endswith(("\n", "\r")):
            self._remainder = lines.pop()

        results: list[tuple[str, str, str]] = []
        for raw_line in lines:
            parsed = parse_query_line(raw_line)
            if parsed is None:
                continue
            req_id, locale, question = parsed
            if req_id in self.seen_ids:
                continue
            self.seen_ids.add(req_id)
            results.append((req_id, locale, question))
        return results


def _unescape_lua_string(raw: str) -> str:
    return (
        raw.replace('\\"', '"')
        .replace("\\n", "\n")
        .replace("\\r", "\r")
        .replace("\\t", "\t")
        .replace("\\\\", "\\")
    )


def _extract_brace_block(text: str, start_brace_idx: int) -> str | None:
    """Extract balanced {...} content starting at start_brace_idx, respecting strings."""
    depth = 0
    in_string = False
    escaped = False
    i = start_brace_idx
    n = len(text)
    while i < n:
        ch = text[i]
        if in_string:
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == '"':
                in_string = False
        else:
            if ch == '"':
                in_string = True
            elif ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    return text[start_brace_idx + 1 : i]
        i += 1
    return None


def extract_savedvariables_outbox(
    sv_path: Path,
    seen_ids: set[str],
) -> list[tuple[str, str, str]]:
    """Optional fallback reader for JinyDB['outbox'] inside SavedVariables/Jiny.lua."""
    if not sv_path.exists():
        return []
    text = sv_path.read_text(encoding="utf-8", errors="replace")
    outbox_match = re.search(r'\["outbox"\]\s*=\s*\{', text)
    if not outbox_match:
        return []

    block = _extract_brace_block(text, outbox_match.end() - 1)
    if block is None:
        return []

    results: list[tuple[str, str, str]] = []
    for match in SV_ENTRY_RE.finditer(block):
        req_id = match.group(1)
        if req_id in seen_ids:
            continue
        question = _unescape_lua_string(match.group(2)).strip()
        locale = match.group(3)
        if not question:
            continue
        seen_ids.add(req_id)
        results.append((req_id, locale, question))
    return results
