import pathlib
import re
import struct
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
ADDON_DIR = ROOT / "Jiny"
TOC_PATH = ADDON_DIR / "Jiny.toc"
TGA_PATH = ADDON_DIR / "Assets" / "JinyIcon.tga"

EXPECTED_LOCALE_KEYS = {
    "TITLE",
    "STATUS_READY",
    "STATUS_MOCK",
    "STATUS_WAITING",
    "INPUT_PLACEHOLDER",
    "BTN_SEND",
    "BTN_CLEAR",
    "BTN_SYNC",
    "BTN_LANGUAGE",
    "BTN_THEME",
    "THEME_ParchmentLight",
    "THEME_DarkGlass",
    "THEME_CHANGED",
    "HELP_THEME",
    "LANG_auto",
    "LANG_enUS",
    "LANG_esES",
    "LANG_itIT",
    "LABEL_YOU",
    "LABEL_JINY",
    "WELCOME",
    "MOCK_REPLY",
    "HISTORY_CLEARED",
    "LANG_CHANGED",
    "POSITION_RESET",
    "HELP_HEADER",
    "HELP_TOGGLE",
    "HELP_ASK",
    "HELP_LANG",
    "HELP_SCALE",
    "HELP_SYNC",
    "HELP_MODE",
    "HELP_RESET",
    "HELP_CLEAR",
    "SCALE_CHANGED",
    "SCALE_RESET",
    "SENT_TO_COMPANION",
    "SYNC_TIP",
    "MODE_CHANGED",
    "FOOTER",
    "RESIZE_TIP",
    "BTN_COPY_MACRO",
    "BTN_CREATE_MACRO",
    "BTN_COPY_CODE",
    "MACRO_CREATED",
    "MACRO_UPDATED",
    "MACRO_ERR_COMBAT",
    "MACRO_ERR_FULL",
    "MACRO_ERR_CREATE",
    "MACRO_DIALOG_TITLE",
    "MACRO_DIALOG_HINT",
}

FORBIDDEN_LUA_PATTERNS = [
    r"Interface\\+DialogFrame",
    r"Interface\\+Tooltips",
    r"\bUIPanelButtonTemplate\b",
    r"\bInputBoxTemplate\b",
    r"\bUIPanelCloseButton\b",
    r"\bSendChatMessage\b",
    r"\bio\.",
    r"\bloadfile\b",
    r"\bdofile\b",
    r"/gem\b",
    r"/gemini\b",
    r"\bWOW_PROJECT_ID\b",
    r"(?i)\bbot\b",
]


def check_utf8_no_bom(path: pathlib.Path) -> tuple[bool, str]:
    raw = path.read_bytes()
    if raw.startswith(b"\xef\xbb\xbf"):
        return False, "has UTF-8 BOM"
    try:
        raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        return False, f"invalid UTF-8: {exc}"
    return True, "OK"


def check_toc() -> list[str]:
    errors = []
    if not TOC_PATH.exists():
        return [f"Missing TOC: {TOC_PATH}"]
    ok, msg = check_utf8_no_bom(TOC_PATH)
    if not ok:
        errors.append(f"Jiny.toc: {msg}")
    content = TOC_PATH.read_text(encoding="utf-8")
    if "## Interface: 16001" not in content:
        errors.append("Jiny.toc: missing '## Interface: 16001'")
    listed_files = []
    for line in content.splitlines():
        s = line.strip()
        if not s or s.startswith("#"):
            continue
        listed_files.append(s)
        rel = pathlib.Path(*s.split("\\"))
        target = ADDON_DIR / rel
        if not target.exists():
            errors.append(f"Jiny.toc references missing file: {s}")
    if not listed_files:
        errors.append("Jiny.toc lists no Lua files")
    return errors


def check_locales() -> list[str]:
    errors = []
    locales_dir = ADDON_DIR / "Locales"
    for code in ("enUS", "esES", "itIT"):
        path = locales_dir / f"{code}.lua"
        if not path.exists():
            errors.append(f"Missing locale file: {path}")
            continue
        text = path.read_text(encoding="utf-8")
        keys = set(re.findall(r'^\s*([A-Za-z0-9_]+)\s*=\s*"', text, flags=re.MULTILINE))
        missing = sorted(EXPECTED_LOCALE_KEYS - keys)
        extra = sorted(keys - EXPECTED_LOCALE_KEYS)
        if missing:
            errors.append(f"{code}.lua missing keys: {missing}")
        if extra:
            errors.append(f"{code}.lua extra keys: {extra}")
        for fmt_key in ("MOCK_REPLY", "LANG_CHANGED", "SCALE_CHANGED", "MODE_CHANGED", "THEME_CHANGED"):
            m = re.search(rf'^\s*{fmt_key}\s*=\s*"((?:[^"\\]|\\.)*)"', text, flags=re.MULTILINE)
            if not m or "%s" not in m.group(1):
                errors.append(f"{code}.lua key {fmt_key} missing '%s' placeholder")
        if re.search(r"\bbot\b", text, flags=re.IGNORECASE):
            errors.append(f"{code}.lua contains forbidden word 'bot'")
    return errors


def check_lua_files() -> list[str]:
    errors = []
    lua_files = sorted(ADDON_DIR.rglob("*.lua"))
    if not lua_files:
        return ["No .lua files found"]
    for path in lua_files:
        rel = path.relative_to(ADDON_DIR)
        ok, msg = check_utf8_no_bom(path)
        if not ok:
            errors.append(f"{rel}: {msg}")
            continue
        text = path.read_text(encoding="utf-8")
        first_line = text.splitlines()[0].strip() if text.splitlines() else ""
        if not re.match(r"^local\s+ADDON\s*,\s*ns\s*=\s*\.\.\.", first_line):
            errors.append(f"{rel}: first line must be 'local ADDON, ns = ...'")
        for pat in FORBIDDEN_LUA_PATTERNS:
            if pat == r"\bSendChatMessage\b" and rel.as_posix() == "Transport.lua":
                continue
            if re.search(pat, text):
                errors.append(f"{rel}: matches forbidden pattern '{pat}'")
    return errors


def check_tga() -> list[str]:
    if not TGA_PATH.exists():
        return [f"Missing TGA icon: {TGA_PATH}"]
    raw = TGA_PATH.read_bytes()
    if len(raw) < 18:
        return ["TGA file too small (< 18 bytes)"]
    (
        id_len,
        cmap_type,
        img_type,
        _cmap_first,
        _cmap_len,
        _cmap_bpp,
        _x_origin,
        _y_origin,
        width,
        height,
        bpp,
        descriptor,
    ) = struct.unpack("<BBBHHBHHHHBB", raw[:18])
    errors = []
    if img_type != 2:
        errors.append(f"TGA image type expected 2 (uncompressed true-color), got {img_type}")
    if width != 64 or height != 64:
        errors.append(f"TGA dimensions expected 64x64, got {width}x{height}")
    if bpp != 32:
        errors.append(f"TGA bpp expected 32, got {bpp}")
    if (descriptor & 0x20) != 0:
        errors.append(f"TGA descriptor expected bottom-left origin (bit 5 = 0), got 0x{descriptor:02x}")
    expected_size = 18 + id_len + (64 * 64 * 4)
    if len(raw) != expected_size:
        errors.append(f"TGA size expected {expected_size} bytes, got {len(raw)}")
    return errors


def check_text_utf8() -> list[str]:
    errors = []
    for path in list(ROOT.glob("*.md")) + list((ROOT / "tools").glob("*")) + [ADDON_DIR / "Assets" / "JinyIcon.svg"]:
        if path.is_file():
            ok, msg = check_utf8_no_bom(path)
            if not ok:
                errors.append(f"{path.relative_to(ROOT)}: {msg}")
    return errors


def main() -> int:
    checks = [
        ("TOC", check_toc),
        ("Locales", check_locales),
        ("Lua files", check_lua_files),
        ("TGA icon", check_tga),
        ("UTF-8 no BOM", check_text_utf8),
    ]
    all_errors = []
    for label, fn in checks:
        errs = fn()
        if errs:
            print(f"[FAIL] {label}:")
            for e in errs:
                print(f"  - {e}")
            all_errors.extend(errs)
        else:
            print(f"[OK] {label}")
    return 1 if all_errors else 0


if __name__ == "__main__":
    sys.exit(main())
