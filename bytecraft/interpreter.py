"""
Bytecraft DSL Interpreter - v0.1.1
A lightweight DSL for creating files and folders.

New in v0.2:
  - Variables:         set <name> "value"
  - Interpolation:     {{name}} in any string
  - Multi-line blocks: make-file "f.txt" with ---
"""

import os
import re
import sys


# ─────────────────────────────────────────────
#  Logging
# ─────────────────────────────────────────────

def _log(msg: str) -> None:
    print(f"[Bytecraft] {msg}")


def _warn(line_num: int, line: str, reason: str) -> None:
    print(f"[Bytecraft] WARNING (line {line_num}): {reason} → skipping: {line!r}", file=sys.stderr)


# ─────────────────────────────────────────────
#  Variable interpolation
# ─────────────────────────────────────────────

def _interpolate(text: str, variables: dict) -> str:
    """Replace {{var}} placeholders with their values from state."""
    def replacer(match):
        key = match.group(1).strip()
        if key in variables:
            return variables[key]
        _log(f"WARNING: undefined variable '{{{{{key}}}}}'")
        return match.group(0)  # leave as-is if not found

    return re.sub(r'\{\{(.+?)\}\}', replacer, text)


# ─────────────────────────────────────────────
#  String extraction
# ─────────────────────────────────────────────

def _extract_strings(text: str, variables: dict) -> list[str]:
    """
    Extract quoted strings from text, with variable interpolation.
    Falls back to whitespace splitting (forgiving parser).
    """
    quoted = re.findall(r'"([^"]*)"', text)
    if quoted:
        return [_interpolate(s, variables) for s in quoted]

    tokens = text.strip().split()
    return [_interpolate(t, variables) for t in tokens]


# ─────────────────────────────────────────────
#  Path resolution
# ─────────────────────────────────────────────

def _resolve(path: str, state: dict) -> str:
    """Resolve a path against the current working folder."""
    working = state.get("working_folder")
    if working and not os.path.isabs(path):
        return os.path.join(working, path)
    return path


# ─────────────────────────────────────────────
#  Command handlers
# ─────────────────────────────────────────────

def _handle_set_working_folder(args: str, state: dict, line_num: int, **_) -> None:
    parts = _extract_strings(args, state["vars"])
    if not parts:
        _warn(line_num, args, "missing path for set-working-folder")
        return

    path = parts[0]
    os.makedirs(path, exist_ok=True)
    state["working_folder"] = path
    _log(f"Working folder set: {path}")


def _handle_make_folder(args: str, state: dict, line_num: int, **_) -> None:
    parts = _extract_strings(args, state["vars"])
    if not parts:
        _warn(line_num, args, "missing path for make-folder")
        return

    full_path = _resolve(parts[0], state)
    os.makedirs(full_path, exist_ok=True)
    _log(f"Created folder: {full_path}")


def _handle_set(args: str, state: dict, line_num: int, **_) -> None:
    """set <name> "value"  — define a variable."""
    match = re.match(r'(\w+)\s+"([^"]*)"', args.strip())
    if match:
        name, value = match.group(1), match.group(2)
    else:
        # Forgiving: split on whitespace
        tokens = args.strip().split(maxsplit=1)
        if len(tokens) < 2:
            _warn(line_num, args, "set requires a name and a value")
            return
        name, value = tokens[0], tokens[1].strip('"')

    # Interpolate in case it references other variables
    value = _interpolate(value, state["vars"])
    state["vars"][name] = value
    _log(f"Variable set: {name} = {value!r}")


def _handle_make_file(
    args: str,
    state: dict,
    line_num: int,
    lines: list[str],
    index: int,
) -> int:
    """
    Returns the new line index after consumption.
    For single-line content this is unchanged.
    For multi-line blocks (---) it advances past the closing ---.
    """
    with_split = re.split(r'\bwith\b', args, maxsplit=1)

    path_part = with_split[0].strip()
    content_part = with_split[1].strip() if len(with_split) > 1 else None

    path_strings = _extract_strings(path_part, state["vars"])
    if not path_strings:
        _warn(line_num, args, "missing path for make-file")
        return index

    full_path = _resolve(path_strings[0], state)

    parent = os.path.dirname(full_path)
    if parent:
        os.makedirs(parent, exist_ok=True)

    # ── Multi-line block ──────────────────────
    if content_part is not None and content_part == "---":
        block_lines = []
        current = index  # already points to the next line

        while current < len(lines):
            raw = lines[current]
            current += 1
            stripped = raw.rstrip("\n").rstrip("\r")
            if stripped.strip() == "---":
                break
            block_lines.append(stripped)
        else:
            _warn(line_num, args, "multi-line block opened with --- but never closed")

        content = _interpolate("\n".join(block_lines), state["vars"])
        index = current  # advance past the closing ---

    # ── Inline / no content ───────────────────
    else:
        content = ""
        if content_part is not None:
            content_strings = _extract_strings(content_part, state["vars"])
            content = content_strings[0] if content_strings else ""

    with open(full_path, "w", encoding="utf-8") as f:
        f.write(content)

    _log(f"Created file: {full_path}")
    return index


# ─────────────────────────────────────────────
#  Dispatcher
# ─────────────────────────────────────────────

# Longer prefixes must come first to avoid false matches (e.g. "set" vs "set-working-folder")
COMMANDS = [
    ("set-working-folder", _handle_set_working_folder),
    ("make-folder",        _handle_make_folder),
    ("make-file",          _handle_make_file),
    ("set",                _handle_set),
]


def _dispatch(line: str, state: dict, line_num: int, lines: list[str], index: int) -> int:
    """
    Dispatch a single line. Returns the (possibly advanced) line index
    to support multi-line block consumption.
    """
    stripped = line.strip()

    if not stripped or stripped.startswith("#"):
        return index

    lower = stripped.lower()
    for cmd, handler in COMMANDS:
        if lower.startswith(cmd):
            args = stripped[len(cmd):].strip()
            if cmd == "make-file":
                index = handler(args, state, line_num, lines=lines, index=index)
            else:
                handler(args, state, line_num)
            return index

    _warn(line_num, stripped, "unknown command")
    return index


# ─────────────────────────────────────────────
#  Public entry point
# ─────────────────────────────────────────────

def run(script_path: str) -> None:
    """Parse and execute a .bc script file."""
    try:
        with open(script_path, "r", encoding="utf-8") as f:
            lines = f.readlines()
    except FileNotFoundError:
        print(f"[Bytecraft] ERROR: File not found: {script_path!r}", file=sys.stderr)
        sys.exit(1)
    except OSError as e:
        print(f"[Bytecraft] ERROR: Could not read file: {e}", file=sys.stderr)
        sys.exit(1)

    state: dict = {
        "working_folder": None,
        "vars": {},
    }

    index = 0
    while index < len(lines):
        line = lines[index]
        line_num = index + 1
        index += 1
        index = _dispatch(line, state, line_num, lines, index)
