"""
Bytecraft DSL Interpreter - v0.6.1
A lightweight DSL for creating files and folders.

  - Variables:         set <n> "value"
  - Env variables:     set-from-env <n> "ENV_VAR"
  - Interpolation:     {{name}} in any string
  - Pipe ops:          {{name|upper|lower|trim|capitalize|len|replace:a:b}}
  - Multi-line blocks: make-file "f.txt" with ---
  - Copy:              copy-file "src" to "dst"
  - Move:              move-file "src" to "dst"
  - Zip:               make-zip "out.zip" from "folder" ["folder2" ...]
  - Extract:           extract "archive.zip" to "dest/"
  - Extract file:      extract-file "inner/file" from "archive.zip" to "dest/file"
  - Append:            append-file "f.txt" with "content"
  - Strict mode:       strict on / strict off
  - Print:             print "message"
  - Templates:         define-template "name" ... end-template
                       use-template "name" key "value" ...
  - Include:           include "other.bc"
  - Loops:             for x in "a" "b" "c" ... end-for
                       for i in 1 to 5 ... end-for
  - Conditionals:      if exists / not exists "path" ... end-if
                       if "{{var}}" is / is not "value" ... end-if
                       else-if / else supported
  - External vars:     load-vars "file.ebv"
  - Replace file:      replace-file "f.txt" with "content"
  - Patch file:        edit-file "f.txt" with --- l1+ line l2- l3> insert ---
"""

import os
import re
import shutil
import sys
import zipfile


# ─────────────────────────────────────────────
#  Errors
# ─────────────────────────────────────────────

class BytecraftError(RuntimeError):
    pass


# ─────────────────────────────────────────────
#  Logging
# ─────────────────────────────────────────────

def _log(msg: str, line_num: int | None = None) -> None:
    prefix = f"[Bytecraft:{line_num}]" if line_num is not None else "[Bytecraft]"
    print(f"{prefix} {msg}")


def _warn(line_num: int, line: str, reason: str, state: dict) -> None:
    msg = f"[Bytecraft] WARNING (line {line_num}): {reason} → skipping: {line!r}"
    if state.get("strict"):
        raise BytecraftError(msg.replace("WARNING", "ERROR (strict mode)"))
    print(msg, file=sys.stderr)


# ─────────────────────────────────────────────
#  Variable interpolation
# ─────────────────────────────────────────────

def _interpolate(text: str, state: dict) -> str:
    variables = state["vars"]

    def _apply_fmt(val: str, fmt: str | None) -> str:
        """Apply a Python format spec to a string value."""
        if not fmt:
            return val
        try:
            return format(int(val), fmt)
        except (ValueError, TypeError):
            try:
                return format(val, fmt)
            except (ValueError, TypeError):
                return val

    def _apply_string_op(val: str, op_str: str) -> str:
        """Apply a pipe string operation: upper, lower, trim, capitalize, len, replace:from:to"""
        op_str = op_str.strip()
        if op_str == "upper":
            return val.upper()
        if op_str == "lower":
            return val.lower()
        if op_str == "trim":
            return val.strip()
        if op_str == "capitalize":
            return val.capitalize()
        if op_str == "len":
            return str(len(val))
        if op_str.startswith("replace:"):
            parts = op_str.split(":", 2)
            if len(parts) == 3:
                return val.replace(parts[1], parts[2])
        return val

    def _eval_arithmetic(expr: str) -> tuple[bool, str]:
        """
        Try to evaluate a simple binary arithmetic expression.
        Operands may be variable names or numeric literals.
        Returns (success, result_string).
        """
        m = re.match(r'^(.+?)\s*([+\-*/])\s*(.+)$', expr.strip())
        if not m:
            return False, ""
        left_s, op, right_s = m.group(1).strip(), m.group(2), m.group(3).strip()
        left_v  = variables.get(left_s,  left_s)
        right_v = variables.get(right_s, right_s)
        try:
            l, r = float(left_v), float(right_v)
        except ValueError:
            return False, ""
        if op == "+" : result = l + r
        elif op == "-": result = l - r
        elif op == "*": result = l * r
        elif op == "/":
            if r == 0:
                return False, ""
            result = l / r
        else:
            return False, ""
        # Return as int string if whole number
        return True, str(int(result)) if result == int(result) else str(result)

    def replacer(match):
        expr = match.group(1).strip()

        # ── 1. String pipe operations: {{name|upper}}, {{name|replace:_:-}} ──
        if "|" in expr:
            pipe_idx = expr.index("|")
            var_part = expr[:pipe_idx].strip()
            op_part  = expr[pipe_idx + 1:].strip()
            if var_part not in variables:
                msg = f"undefined variable '{{{{{var_part}}}}}'"
                if state.get("strict"):
                    raise BytecraftError(f"[Bytecraft] ERROR (strict mode): {msg}")
                _log(f"WARNING: {msg}")
                return match.group(0)
            return _apply_string_op(variables[var_part], op_part)

        # ── 2. Split trailing format spec: {{i + 1:03}} or {{var:02}} ──
        #    Heuristic: colon followed only by valid format spec characters
        fmt: str | None = None
        fmt_m = re.search(r':([0-9<>^+\-#0dfsxobegEFGX%_.]+)$', expr)
        if fmt_m:
            fmt  = fmt_m.group(1)
            expr = expr[:fmt_m.start()].strip()

        # ── 3. Arithmetic: {{i + 1}}, {{count * 2}}, {{total / 4}} ──
        if re.search(r'\s*[+\-*/]\s*', expr):
            ok, result = _eval_arithmetic(expr)
            if ok:
                return _apply_fmt(result, fmt)
            # Fall through to plain variable (handles e.g. negative-prefixed names)

        # ── 4. Plain variable lookup ──
        if expr in variables:
            return _apply_fmt(variables[expr], fmt)

        msg = f"undefined variable '{{{{{expr}}}}}'"
        if state.get("strict"):
            raise BytecraftError(f"[Bytecraft] ERROR (strict mode): {msg}")
        _log(f"WARNING: {msg}")
        return match.group(0)

    return re.sub(r'\{\{(.+?)\}\}', replacer, text)


# ─────────────────────────────────────────────
#  String extraction
# ─────────────────────────────────────────────

def _extract_strings(text: str, state: dict) -> list[str]:
    quoted = re.findall(r'"([^"]*)"', text)
    if quoted:
        return [_interpolate(s, state) for s in quoted]
    tokens = text.strip().split()
    return [_interpolate(t, state) for t in tokens]


# ─────────────────────────────────────────────
#  Path resolution
# ─────────────────────────────────────────────

def _resolve(path: str, state: dict) -> str:
    working = state.get("working_folder")
    if working and not os.path.isabs(path):
        return os.path.join(working, path)
    return path


def _is_dry(state: dict) -> bool:
    return state.get("dry_run", False)


def _resolve_include(path: str, state: dict) -> str:
    if os.path.isabs(path):
        return path
    return os.path.join(state.get("script_dir", "."), path)


# ─────────────────────────────────────────────
#  Block collector
#  Collects lines between an opener and a closer keyword,
#  respecting nesting of the same opener keyword.
# ─────────────────────────────────────────────

def _collect_block(
    lines: list[str],
    index: int,
    opener_pattern: str,
    closer: str,
    line_num: int,
    state: dict,
) -> tuple[list[str], int]:
    """
    Collect lines until `closer` is found, handling nested openers.
    Returns (block_lines, new_index).
    """
    body: list[str] = []
    depth = 1
    opener_re = re.compile(opener_pattern, re.IGNORECASE)

    while index < len(lines):
        raw = lines[index]
        index += 1
        stripped = raw.strip()

        if opener_re.match(stripped):
            depth += 1
        elif stripped.lower() == closer:
            depth -= 1
            if depth == 0:
                return body, index

        body.append(raw.rstrip("\n").rstrip("\r"))

    _warn(line_num, closer, f"block opened but '{closer}' never found", state)
    return body, index


# ─────────────────────────────────────────────
#  Core execution engine
# ─────────────────────────────────────────────

def _execute(lines: list[str], state: dict, source_label: str = "<script>") -> None:
    index = 0
    while index < len(lines):
        line = lines[index]
        line_num = index + 1
        index += 1
        index = _dispatch(line, state, line_num, lines, index, source_label)


# ─────────────────────────────────────────────
#  Command handlers
# ─────────────────────────────────────────────

def _handle_strict(args: str, state: dict, line_num: int, **_) -> None:
    val = args.strip().lower()
    if val == "on":
        state["strict"] = True
        _log("Strict mode enabled", line_num)
    elif val == "off":
        state["strict"] = False
        _log("Strict mode disabled", line_num)
    else:
        _warn(line_num, args, "strict requires 'on' or 'off'", state)


def _handle_set_working_folder(args: str, state: dict, line_num: int, **_) -> None:
    parts = _extract_strings(args, state)
    if not parts:
        _warn(line_num, args, "missing path for set-working-folder", state)
        return
    path = parts[0]
    if _is_dry(state):
        _log(f"[DRY RUN] Would set working folder: {path}", line_num)
        state["working_folder"] = path  # still set so path resolution works
        return
    os.makedirs(path, exist_ok=True)
    state["working_folder"] = path
    _log(f"Working folder set: {path}", line_num)


def _handle_make_folder(args: str, state: dict, line_num: int, **_) -> None:
    parts = _extract_strings(args, state)
    if not parts:
        _warn(line_num, args, "missing path for make-folder", state)
        return
    full_path = _resolve(parts[0], state)
    if _is_dry(state):
        _log(f"[DRY RUN] Would create folder: {full_path}", line_num)
        return
    os.makedirs(full_path, exist_ok=True)
    _log(f"Created folder: {full_path}", line_num)


def _handle_set(args: str, state: dict, line_num: int, **_) -> None:
    match = re.match(r'(\w+)\s+"([^"]*)"', args.strip())
    if match:
        name, value = match.group(1), match.group(2)
    else:
        tokens = args.strip().split(maxsplit=1)
        if len(tokens) < 2:
            _warn(line_num, args, "set requires a name and a value", state)
            return
        name, value = tokens[0], tokens[1].strip('"')
        # Warn if the value looks like multiple unquoted words
        if ' ' in value and not value.startswith('"'):
            _warn(line_num, args, f"unquoted multi-word value for '{name}' — wrap in quotes to be explicit", state)
    value = _interpolate(value, state)
    state["vars"][name] = value
    _log(f"Variable set: {name} = {value!r}", line_num)


def _handle_load_vars(args: str, state: dict, line_num: int, **_) -> None:
    """load-vars "file.ebv" — load key = value pairs into state."""
    parts = _extract_strings(args, state)
    if not parts:
        _warn(line_num, args, "load-vars requires a file path", state)
        return

    path = _resolve_include(parts[0], state)
    if not os.path.exists(path):
        _warn(line_num, args, f"ebv file not found: {path!r}", state)
        return

    try:
        with open(path, "r", encoding="utf-8") as f:
            ebv_lines = f.readlines()
    except OSError as e:
        _warn(line_num, args, f"could not read ebv file: {e}", state)
        return

    loaded = 0
    for i, ebv_line in enumerate(ebv_lines, start=1):
        stripped = ebv_line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        m = re.match(r'(\w+)\s*=\s*(.+)', stripped)
        if not m:
            _warn(i, stripped, f"invalid ebv syntax in {path}", state)
            continue
        key = m.group(1)
        value = m.group(2).strip().strip('"')
        state["vars"][key] = value
        loaded += 1

    _log(f"Loaded {loaded} variable(s) from: {path}", line_num)


def _handle_make_file(
    args: str, state: dict, line_num: int, lines: list[str], index: int, **_
) -> int:
    with_split = re.split(r'\bwith\b', args, maxsplit=1)
    path_part = with_split[0].strip()
    content_part = with_split[1].strip() if len(with_split) > 1 else None

    path_strings = _extract_strings(path_part, state)
    if not path_strings:
        _warn(line_num, args, "missing path for make-file", state)
        return index

    full_path = _resolve(path_strings[0], state)

    if content_part is not None and content_part == "---":
        block_lines = []
        current = index
        closed = False
        while current < len(lines):
            raw = lines[current]
            current += 1
            stripped = raw.rstrip("\n").rstrip("\r")
            if stripped.strip() == "---":
                closed = True
                break
            block_lines.append(stripped)
        if not closed:
            _warn(line_num, args, "multi-line block opened with --- but never closed", state)
        content = _interpolate("\n".join(block_lines), state)
        index = current
    else:
        content = ""
        if content_part is not None:
            content_strings = _extract_strings(content_part, state)
            content = content_strings[0] if content_strings else ""

    if _is_dry(state):
        action = "Would overwrite" if os.path.exists(full_path) else "Would create"
        preview = content[:60].replace("\n", "↵") + ("..." if len(content) > 60 else "")
        _log(f"[DRY RUN] {action} file: {full_path}  ({len(content)} chars: {preview!r})", line_num)
        return index

    if os.path.exists(full_path):
        _warn(line_num, args, f"overwriting existing file: {full_path!r}", state)

    parent = os.path.dirname(full_path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    with open(full_path, "w", encoding="utf-8") as f:
        f.write(content)
    _log(f"Created file: {full_path}", line_num)
    return index


def _handle_append_file(
    args: str, state: dict, line_num: int, lines: list[str], index: int, **_
) -> int:
    """append-file "path" with "content" — appends to a file, creates if missing."""
    with_split = re.split(r'\bwith\b', args, maxsplit=1)
    path_part = with_split[0].strip()
    content_part = with_split[1].strip() if len(with_split) > 1 else None

    path_strings = _extract_strings(path_part, state)
    if not path_strings:
        _warn(line_num, args, "missing path for append-file", state)
        return index

    full_path = _resolve(path_strings[0], state)

    if content_part is not None and content_part == "---":
        block_lines = []
        current = index
        closed = False
        while current < len(lines):
            raw = lines[current]
            current += 1
            stripped = raw.rstrip("\n").rstrip("\r")
            if stripped.strip() == "---":
                closed = True
                break
            block_lines.append(stripped)
        if not closed:
            _warn(line_num, args, "multi-line block opened with --- but never closed", state)
        content = _interpolate("\n".join(block_lines), state)
        index = current
    else:
        content = ""
        if content_part is not None:
            content_strings = _extract_strings(content_part, state)
            content = content_strings[0] if content_strings else ""

    if _is_dry(state):
        preview = content[:60].replace("\n", "↵") + ("..." if len(content) > 60 else "")
        _log(f"[DRY RUN] Would append to file: {full_path}  ({len(content)} chars: {preview!r})", line_num)
        return index

    parent = os.path.dirname(full_path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    # Append a newline before content if the file already exists and is non-empty
    prefix = ""
    if os.path.exists(full_path) and os.path.getsize(full_path) > 0:
        prefix = "\n"
    with open(full_path, "a", encoding="utf-8") as f:
        f.write(prefix + content)
    _log(f"Appended to file: {full_path}", line_num)
    return index


def _handle_copy_file(args: str, state: dict, line_num: int, **_) -> None:
    to_split = re.split(r'\bto\b', args, maxsplit=1)
    if len(to_split) != 2:
        _warn(line_num, args, 'copy-file requires: copy-file "src" to "dst"', state)
        return
    src_parts = _extract_strings(to_split[0].strip(), state)
    dst_parts = _extract_strings(to_split[1].strip(), state)
    if not src_parts or not dst_parts:
        _warn(line_num, args, "copy-file missing source or destination", state)
        return
    src = _resolve(src_parts[0], state)
    dst = _resolve(dst_parts[0], state)
    if not os.path.exists(src):
        _warn(line_num, args, f"source does not exist: {src!r}", state)
        return
    if _is_dry(state):
        _log(f"[DRY RUN] Would copy: {src} → {dst}", line_num)
        return
    dst_parent = os.path.dirname(dst)
    if dst_parent:
        os.makedirs(dst_parent, exist_ok=True)
    if os.path.isdir(src):
        if os.path.exists(dst):
            shutil.rmtree(dst)
        shutil.copytree(src, dst)
    else:
        shutil.copy2(src, dst)
    _log(f"Copied: {src} → {dst}", line_num)


def _handle_move_file(args: str, state: dict, line_num: int, **_) -> None:
    to_split = re.split(r'\bto\b', args, maxsplit=1)
    if len(to_split) != 2:
        _warn(line_num, args, 'move-file requires: move-file "src" to "dst"', state)
        return
    src_parts = _extract_strings(to_split[0].strip(), state)
    dst_parts = _extract_strings(to_split[1].strip(), state)
    if not src_parts or not dst_parts:
        _warn(line_num, args, "move-file missing source or destination", state)
        return
    src = _resolve(src_parts[0], state)
    dst = _resolve(dst_parts[0], state)
    if not os.path.exists(src):
        _warn(line_num, args, f"source does not exist: {src!r}", state)
        return
    if _is_dry(state):
        _log(f"[DRY RUN] Would move: {src} → {dst}", line_num)
        return
    dst_parent = os.path.dirname(dst)
    if dst_parent:
        os.makedirs(dst_parent, exist_ok=True)
    shutil.move(src, dst)
    _log(f"Moved: {src} → {dst}", line_num)


def _handle_make_zip(args: str, state: dict, line_num: int, **_) -> None:
    from_split = re.split(r'\bfrom\b', args, maxsplit=1)
    if len(from_split) != 2:
        _warn(line_num, args, 'make-zip requires: make-zip "out.zip" from "source" ["source2" ...]', state)
        return
    zip_parts = _extract_strings(from_split[0].strip(), state)
    src_parts = _extract_strings(from_split[1].strip(), state)
    if not zip_parts or not src_parts:
        _warn(line_num, args, "make-zip missing output path or source(s)", state)
        return
    zip_path = _resolve(zip_parts[0], state)
    sources = [_resolve(s, state) for s in src_parts]

    missing = [s for s in sources if not os.path.exists(s)]
    if missing:
        for m in missing:
            _warn(line_num, args, f"source does not exist: {m!r}", state)
        return

    src_label = ", ".join(sources)
    if _is_dry(state):
        _log(f"[DRY RUN] Would create zip: {zip_path} ← {src_label}", line_num)
        return

    zip_parent = os.path.dirname(zip_path)
    if zip_parent:
        os.makedirs(zip_parent, exist_ok=True)
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for src in sources:
            if os.path.isdir(src):
                for root, _, files in os.walk(src):
                    for file in files:
                        abs_path = os.path.join(root, file)
                        arc_name = os.path.relpath(abs_path, start=os.path.dirname(src))
                        zf.write(abs_path, arc_name)
            else:
                zf.write(src, os.path.basename(src))
    _log(f"Created zip: {zip_path} ← {src_label}", line_num)


def _handle_extract(args: str, state: dict, line_num: int, **_) -> None:
    """extract \"archive.zip\" to \"dest/\" — extracts all contents, merging into dest if it exists."""
    to_split = re.split(r'\bto\b', args, maxsplit=1)
    if len(to_split) != 2:
        _warn(line_num, args, 'extract requires: extract "archive.zip" to "dest/"', state)
        return
    zip_parts = _extract_strings(to_split[0].strip(), state)
    dst_parts = _extract_strings(to_split[1].strip(), state)
    if not zip_parts or not dst_parts:
        _warn(line_num, args, "extract missing zip path or destination", state)
        return
    zip_path = _resolve(zip_parts[0], state)
    dst = _resolve(dst_parts[0], state)
    if not os.path.exists(zip_path):
        _warn(line_num, args, f"zip file does not exist: {zip_path!r}", state)
        return
    if not zipfile.is_zipfile(zip_path):
        _warn(line_num, args, f"not a valid zip file: {zip_path!r}", state)
        return
    if _is_dry(state):
        _log(f"[DRY RUN] Would extract zip: {zip_path} → {dst}", line_num)
        return
    os.makedirs(dst, exist_ok=True)
    with zipfile.ZipFile(zip_path, "r") as zf:
        zf.extractall(dst)
    _log(f"Extracted zip: {zip_path} → {dst}", line_num)


def _handle_extract_file(args: str, state: dict, line_num: int, **_) -> None:
    """extract-file \"inner/file.csv\" from \"archive.zip\" to \"output/file.csv\" — extracts a single file."""
    from_split = re.split(r'\bfrom\b', args, maxsplit=1)
    if len(from_split) != 2:
        _warn(line_num, args, 'extract-file requires: extract-file "inner/path" from "archive.zip" to "dest"', state)
        return
    inner_parts = _extract_strings(from_split[0].strip(), state)
    rest = from_split[1].strip()

    to_split = re.split(r'\bto\b', rest, maxsplit=1)
    if len(to_split) != 2:
        _warn(line_num, args, 'extract-file requires: extract-file "inner/path" from "archive.zip" to "dest"', state)
        return
    zip_parts = _extract_strings(to_split[0].strip(), state)
    dst_parts = _extract_strings(to_split[1].strip(), state)

    if not inner_parts or not zip_parts or not dst_parts:
        _warn(line_num, args, "extract-file missing inner path, zip path, or destination", state)
        return

    inner_path = inner_parts[0]
    zip_path = _resolve(zip_parts[0], state)
    dst = _resolve(dst_parts[0], state)

    if not os.path.exists(zip_path):
        _warn(line_num, args, f"zip file does not exist: {zip_path!r}", state)
        return
    if not zipfile.is_zipfile(zip_path):
        _warn(line_num, args, f"not a valid zip file: {zip_path!r}", state)
        return

    with zipfile.ZipFile(zip_path, "r") as zf:
        if inner_path not in zf.namelist():
            _warn(line_num, args, f"file not found inside zip: {inner_path!r}", state)
            return
        if _is_dry(state):
            _log(f"[DRY RUN] Would extract file: {inner_path} from {zip_path} → {dst}", line_num)
            return
        dst_parent = os.path.dirname(dst)
        if dst_parent:
            os.makedirs(dst_parent, exist_ok=True)
        with zf.open(inner_path) as src_f, open(dst, "wb") as dst_f:
            dst_f.write(src_f.read())
    _log(f"Extracted file: {inner_path} from {zip_path} → {dst}", line_num)


def _handle_delete_file(args: str, state: dict, line_num: int, **_) -> None:
    """delete-file "path" — deletes a file. Warns if it doesn't exist."""
    parts = _extract_strings(args, state)
    if not parts:
        _warn(line_num, args, "missing path for delete-file", state)
        return
    full_path = _resolve(parts[0], state)
    if not os.path.exists(full_path):
        _warn(line_num, args, f"file does not exist: {full_path!r}", state)
        return
    if os.path.isdir(full_path):
        _warn(line_num, args, f"path is a folder, use delete-folder: {full_path!r}", state)
        return
    if _is_dry(state):
        _log(f"[DRY RUN] Would delete file: {full_path}", line_num)
        return
    os.remove(full_path)
    _log(f"Deleted file: {full_path}", line_num)


def _handle_delete_folder(args: str, state: dict, line_num: int, **_) -> None:
    """delete-folder "path" — deletes a folder and all its contents. Warns if it doesn't exist."""
    parts = _extract_strings(args, state)
    if not parts:
        _warn(line_num, args, "missing path for delete-folder", state)
        return
    full_path = _resolve(parts[0], state)
    if not os.path.exists(full_path):
        _warn(line_num, args, f"folder does not exist: {full_path!r}", state)
        return
    if not os.path.isdir(full_path):
        _warn(line_num, args, f"path is a file, use delete-file: {full_path!r}", state)
        return
    if _is_dry(state):
        _log(f"[DRY RUN] Would delete folder: {full_path}", line_num)
        return
    shutil.rmtree(full_path)
    _log(f"Deleted folder: {full_path}", line_num)


def _handle_define_template(
    args: str, state: dict, line_num: int, lines: list[str], index: int, **_
) -> int:
    name_parts = _extract_strings(args, state)
    if not name_parts:
        _warn(line_num, args, "define-template requires a name", state)
        while index < len(lines):
            if lines[index].strip().lower() == "end-template":
                index += 1
                break
            index += 1
        return index

    name = name_parts[0]
    body, index = _collect_block(lines, index, r'define-template\b', "end-template", line_num, state)
    state["templates"][name] = body
    _log(f"Template defined: {name} ({len(body)} lines)", line_num)
    return index


def _handle_use_template(args: str, state: dict, line_num: int, **_) -> None:
    name_match = re.match(r'\s*"([^"]+)"\s*(.*)', args) or re.match(r'\s*(\S+)\s*(.*)', args)
    if not name_match:
        _warn(line_num, args, "use-template requires a template name", state)
        return

    name = _interpolate(name_match.group(1), state)
    rest = name_match.group(2).strip()

    if name not in state["templates"]:
        _warn(line_num, args, f"undefined template: '{name}'", state)
        return

    call_vars: dict[str, str] = {}
    for m in re.finditer(r'(\w+)\s+"([^"]*)"', rest):
        call_vars[m.group(1)] = _interpolate(m.group(2), state)

    child_state: dict = {
        "working_folder": state["working_folder"],
        "script_dir":     state["script_dir"],
        "strict":         state["strict"],
        "dry_run":        state.get("dry_run", False),
        "templates":      state["templates"],
        "vars":           {**state["vars"], **call_vars},
    }

    _log(f"Using template: {name}" + (f" with {call_vars}" if call_vars else ""), line_num)
    _execute(
        [line + "\n" for line in state["templates"][name]],
        child_state,
        source_label=f"<template:{name}>",
    )
    state["working_folder"] = child_state["working_folder"]


def _handle_include(args: str, state: dict, line_num: int, **_) -> None:
    parts = _extract_strings(args, state)
    if not parts:
        _warn(line_num, args, "include requires a file path", state)
        return
    path = parts[0]
    # Remote includes are not supported — include is local-only
    if path.startswith("http://") or path.startswith("https://"):
        _warn(line_num, args, "include does not support remote URLs — use a local path", state)
        return
    path = _resolve_include(path, state)
    if not os.path.exists(path):
        _warn(line_num, args, f"included file not found: {path!r}", state)
        return
    _log(f"Including: {path}", line_num)
    try:
        with open(path, "r", encoding="utf-8") as f:
            included_lines = f.readlines()
    except OSError as e:
        _warn(line_num, args, f"could not read included file: {e}", state)
        return
    prev_script_dir = state["script_dir"]
    state["script_dir"] = os.path.dirname(os.path.abspath(path))
    _execute(included_lines, state, source_label=path)
    state["script_dir"] = prev_script_dir


def _handle_for(
    args: str, state: dict, line_num: int, lines: list[str], index: int, **_
) -> int:
    """
    for <var> in "a" "b" "c"   — value list
    for <var> in 1 to 5         — integer range (inclusive)
    """
    # Collect the loop body first
    body, index = _collect_block(lines, index, r'for\b', "end-for", line_num, state)

    # Parse: for <var> in ...
    m = re.match(r'(\w+)\s+in\s+(.*)', args.strip(), re.IGNORECASE)
    if not m:
        _warn(line_num, args, "for syntax: for <var> in <values> OR for <var> in <n> to <m>", state)
        return index

    var_name = m.group(1)
    rest = m.group(2).strip()

    # Range: "1 to 5" or "1 to {{count}}" (variable bounds)
    range_m = re.match(r'^(.+?)\s+to\s+(.+)$', rest, re.IGNORECASE)
    if range_m:
        start_str = _interpolate(range_m.group(1).strip(), state)
        end_str   = _interpolate(range_m.group(2).strip(), state)
        try:
            start, end = int(start_str), int(end_str)
            values = [str(i) for i in range(start, end + 1)]
        except ValueError:
            _warn(line_num, args, f"range bounds must be integers, got {start_str!r} and {end_str!r}", state)
            return index
    else:
        # Value list: quoted or bare tokens (bare tokens are interpolated)
        quoted = re.findall(r'"([^"]*)"', rest)
        if quoted:
            values = quoted
        else:
            values = [_interpolate(t, state) for t in rest.split()]

    for val in values:
        child_state: dict = {
            "working_folder": state["working_folder"],
            "script_dir":     state["script_dir"],
            "strict":         state["strict"],
            "dry_run":        state.get("dry_run", False),
            "templates":      state["templates"],
            "vars":           {**state["vars"], var_name: _interpolate(val, state)},
        }
        _execute([line + "\n" for line in body], child_state, source_label=f"<for:{var_name}={val}>")
        # Propagate working_folder changes out of the loop body
        state["working_folder"] = child_state["working_folder"]

    return index


def _split_if_block(body: list[str]) -> list[tuple[str | None, list[str]]]:
    """
    Split a collected if-body into segments:
        [(condition_or_None, lines), ...]
    The first segment's condition is None (it was the original if condition).
    else-if segments have a condition string.
    else segment has condition None.
    Handles nesting by tracking depth.
    """
    segments: list[tuple] = []
    current: list[str] = []
    current_cond: str | None = "__initial__"
    depth = 0

    for line in body:
        stripped = line.strip().lower()

        if re.match(r'if\b', stripped):
            depth += 1
            current.append(line)
        elif stripped == "end-if":
            if depth > 0:
                depth -= 1
                current.append(line)
            # else: shouldn't happen since _collect_block consumed the outer end-if
        elif depth == 0 and re.match(r'else-if\b', stripped):
            segments.append((current_cond, current))
            # Extract the condition from "else-if <condition>"
            current_cond = line.strip()[len("else-if"):].strip()
            current = []
        elif depth == 0 and stripped == "else":
            segments.append((current_cond, current))
            current_cond = None   # None = unconditional else
            current = []
        else:
            current.append(line)

    segments.append((current_cond, current))
    return segments


def _handle_if(
    args: str, state: dict, line_num: int, lines: list[str], index: int, **_
) -> int:
    """
    if <condition>
      ...
    else-if <condition>
      ...
    else
      ...
    end-if
    """
    body, index = _collect_block(lines, index, r'if\b', "end-if", line_num, state)

    # Build the chain: [(condition, body_lines), ...]
    # First entry uses the original if condition
    segments = _split_if_block(body)

    for seg_idx, (cond, seg_body) in enumerate(segments):
        if seg_idx == 0:
            # First segment: use the original if condition
            result = _evaluate_condition(args.strip(), state, line_num)
        elif cond is None:
            # else block — always executes if we get here
            result = True
        else:
            result = _evaluate_condition(cond, state, line_num)

        if result:
            _execute([line + "\n" for line in seg_body], state, source_label="<if>")
            break   # short-circuit: only execute the first matching branch

    return index


def _evaluate_condition(condition: str, state: dict, line_num: int) -> bool:
    """Evaluate an if condition and return True or False."""

    # if exists "path" / if not exists "path"
    m = re.match(r'^(not\s+)?exists\s+"([^"]*)"$', condition, re.IGNORECASE)
    if m:
        negate = bool(m.group(1))
        path = _resolve(_interpolate(m.group(2), state), state)
        result = os.path.exists(path)
        return not result if negate else result

    # if "{{var}}" is "value" / if "{{var}}" is not "value"
    m = re.match(r'^"([^"]*)"\s+is(\s+not)?\s+"([^"]*)"$', condition, re.IGNORECASE)
    if m:
        lhs = _interpolate(m.group(1), state)
        negate = bool(m.group(2))
        rhs = _interpolate(m.group(3), state)
        result = lhs == rhs
        return not result if negate else result

    # Forgiving: bare word comparison without quotes
    m = re.match(r'^(\S+)\s+is(\s+not)?\s+(\S+)$', condition, re.IGNORECASE)
    if m:
        lhs = _interpolate(m.group(1), state)
        negate = bool(m.group(2))
        rhs = _interpolate(m.group(3), state)
        result = lhs == rhs
        return not result if negate else result

    _warn(line_num, condition, "unrecognised if condition", state)
    return False


def _handle_print(args: str, state: dict, line_num: int, **_) -> None:
    """print "message" — outputs a message to stdout."""
    parts = _extract_strings(args, state)
    msg = parts[0] if parts else _interpolate(args.strip(), state)
    print(msg)


def _handle_set_from_env(args: str, state: dict, line_num: int, **_) -> None:
    """set-from-env <name> "ENV_VAR" — loads an environment variable into state."""
    match = re.match(r'(\w+)\s+"([^"]*)"', args.strip()) or re.match(r'(\w+)\s+(\S+)', args.strip())
    if not match:
        _warn(line_num, args, 'set-from-env requires: set-from-env <name> "ENV_VAR"', state)
        return
    name, env_key = match.group(1), match.group(2)
    value = os.environ.get(env_key)
    if value is None:
        _warn(line_num, args, f"environment variable {env_key!r} is not set", state)
        return
    state["vars"][name] = value
    _log(f"Variable set from env: {name} = {value!r}", line_num)



def _handle_replace_file(
    args: str, state: dict, line_num: int, lines: list[str], index: int, **_
) -> int:
    """replace-file — same as make-file but always overwrites, even in strict mode."""
    with_split = re.split(r'\bwith\b', args, maxsplit=1)
    path_part = with_split[0].strip()
    content_part = with_split[1].strip() if len(with_split) > 1 else None

    path_strings = _extract_strings(path_part, state)
    if not path_strings:
        _warn(line_num, args, "missing path for replace-file", state)
        return index

    full_path = _resolve(path_strings[0], state)

    if content_part is not None and content_part == "---":
        block_lines = []
        current = index
        closed = False
        while current < len(lines):
            raw = lines[current]
            current += 1
            stripped = raw.rstrip("\n").rstrip("\r")
            if stripped.strip() == "---":
                closed = True
                break
            block_lines.append(stripped)
        if not closed:
            _warn(line_num, args, "multi-line block opened with --- but never closed", state)
        content = _interpolate("\n".join(block_lines), state)
        index = current
    else:
        content = ""
        if content_part is not None:
            content_strings = _extract_strings(content_part, state)
            content = content_strings[0] if content_strings else ""

    if _is_dry(state):
        action = "Would overwrite" if os.path.exists(full_path) else "Would create"
        preview = content[:60].replace("\n", "↵") + ("..." if len(content) > 60 else "")
        _log(f"[DRY RUN] {action} file (replace): {full_path}  ({len(content)} chars: {preview!r})", line_num)
        return index

    parent = os.path.dirname(full_path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    with open(full_path, "w", encoding="utf-8") as f:
        f.write(content)
    _log(f"Replaced file: {full_path}", line_num)
    return index


def _parse_patch(patch_lines: list[str], state: dict) -> list[tuple]:
    """
    Parse patch instructions into operations:
        ("replace", line_num, content)    — l1+ new content
        ("delete",  line_num, guard)      — l1- [exact match guard]
        ("insert",  line_num, content)    — l1> insert before line N

    Line numbers are 1-based and refer to the ORIGINAL file.
    """
    ops = []
    for raw in patch_lines:
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        m = re.match(r'l(\d+)([+\->])(.*)', line)
        if not m:
            continue
        lnum    = int(m.group(1))
        op      = m.group(2)
        payload = m.group(3).strip() if m.group(3).strip() else None
        payload = _interpolate(payload, state) if payload else None

        if op == "+":
            ops.append(("replace", lnum, payload or ""))
        elif op == "-":
            ops.append(("delete",  lnum, payload))
        elif op == ">":
            ops.append(("insert",  lnum, payload or ""))
    return ops


def _apply_patch(
    original_lines: list[str], ops: list[tuple], state: dict, line_num: int
) -> list[str]:
    """
    Apply patch ops to original_lines.
    All line numbers refer to the ORIGINAL file (1-based).
    Parsed first, then applied in one pass.
    """
    replacements: dict[int, str]        = {}
    deletions:    set[int]              = set()
    insertions:   dict[int, list[str]]  = {}

    for op_type, lnum, payload in ops:
        if op_type == "replace":
            replacements[lnum] = payload
        elif op_type == "delete":
            orig = (
                original_lines[lnum - 1].rstrip("\n").rstrip("\r")
                if lnum <= len(original_lines) else None
            )
            if payload is None or orig == payload:
                deletions.add(lnum)
            else:
                _warn(line_num, f"l{lnum}- {payload}",
                      f"line {lnum} mismatch — expected {payload!r}, got {orig!r}", state)
        elif op_type == "insert":
            insertions.setdefault(lnum, []).append(payload)

    result: list[str] = []
    for i, orig_line in enumerate(original_lines, start=1):
        for ins in insertions.get(i, []):
            result.append(ins + "\n")
        if i in deletions:
            continue
        if i in replacements:
            result.append(replacements[i] + "\n")
        else:
            result.append(orig_line if orig_line.endswith("\n") else orig_line + "\n")

    # Handle ops beyond end of file
    beyond = sorted(set(
        list({n for n in replacements if n > len(original_lines)}) +
        list({n for n in insertions   if n > len(original_lines)})
    ))
    for n in beyond:
        for ins in insertions.get(n, []):
            result.append(ins + "\n")
        if n in replacements:
            result.append(replacements[n] + "\n")

    return result


def _handle_edit_file(
    args: str, state: dict, line_num: int, lines: list[str], index: int, **_
) -> int:
    """
    edit-file "path" with ---
    l1+ replacement line
    l2> insert before line 2
    l3-
    l5- exact match guard
    ---
    """
    with_split = re.split(r'\bwith\b', args, maxsplit=1)
    path_part    = with_split[0].strip()
    content_part = with_split[1].strip() if len(with_split) > 1 else None

    path_strings = _extract_strings(path_part, state)
    if not path_strings:
        _warn(line_num, args, "missing path for edit-file", state)
        return index

    if content_part != "---":
        _warn(line_num, args, "edit-file requires a --- patch block", state)
        return index

    # Collect patch block
    patch_raw: list[str] = []
    current = index
    closed = False
    while current < len(lines):
        raw = lines[current]
        current += 1
        if raw.strip() == "---":
            closed = True
            break
        patch_raw.append(raw.rstrip("\n").rstrip("\r"))
    if not closed:
        _warn(line_num, args, "edit-file patch block opened with --- but never closed", state)
    index = current

    full_path = _resolve(path_strings[0], state)

    if not os.path.exists(full_path):
        _warn(line_num, args, f"edit-file: file does not exist: {full_path!r}", state)
        return index

    ops = _parse_patch(patch_raw, state)

    if _is_dry(state):
        _log(f"[DRY RUN] Would edit file: {full_path} ({len(ops)} operation(s))", line_num)
        return index

    try:
        with open(full_path, "r", encoding="utf-8") as f:
            original_lines = f.readlines()
    except OSError as e:
        _warn(line_num, args, f"edit-file: could not read file: {e}", state)
        return index

    result = _apply_patch(original_lines, ops, state, line_num)

    with open(full_path, "w", encoding="utf-8") as f:
        f.writelines(result)

    _log(f"Edited file: {full_path} ({len(ops)} operation(s))", line_num)
    return index


# ─────────────────────────────────────────────
#  Dispatcher
# ─────────────────────────────────────────────

COMMANDS = [
    ("set-working-folder", _handle_set_working_folder),
    ("set-from-env",       _handle_set_from_env),
    ("define-template",    _handle_define_template),
    ("use-template",       _handle_use_template),
    ("replace-file",       _handle_replace_file),
    ("edit-file",          _handle_edit_file),
    ("append-file",        _handle_append_file),
    ("make-folder",        _handle_make_folder),
    ("make-file",          _handle_make_file),
    ("make-zip",           _handle_make_zip),
    ("extract-file",       _handle_extract_file),
    ("extract",            _handle_extract),
    ("copy-file",          _handle_copy_file),
    ("delete-folder",      _handle_delete_folder),
    ("delete-file",        _handle_delete_file),
    ("move-file",          _handle_move_file),
    ("load-vars",          _handle_load_vars),
    ("include",            _handle_include),
    ("strict",             _handle_strict),
    ("print",              _handle_print),
    ("set",                _handle_set),
    ("for",                _handle_for),
    ("if",                 _handle_if),
]

_MULTILINE_CMDS = {"make-file", "replace-file", "edit-file", "append-file", "define-template", "for", "if"}


def _dispatch(
    line: str, state: dict, line_num: int,
    lines: list[str], index: int, source_label: str = "<script>",
) -> int:
    stripped = line.strip()
    if not stripped or stripped.startswith("#"):
        return index

    lower = stripped.lower()
    for cmd, handler in COMMANDS:
        if lower.startswith(cmd):
            # Ensure it's a whole word match (not e.g. "set-working-folder" matching "set")
            rest = stripped[len(cmd):]
            if rest and rest[0].isalnum():
                continue
            args = rest.strip()
            if cmd in _MULTILINE_CMDS:
                index = handler(args, state, line_num, lines=lines, index=index)
            else:
                handler(args, state, line_num)
            return index

    _warn(line_num, stripped, "unknown command", state)
    return index


# ─────────────────────────────────────────────
#  Public entry point
# ─────────────────────────────────────────────

def run(script_path: str, dry_run: bool = False) -> None:
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
        "vars":           {},
        "templates":      {},
        "strict":         False,
        "dry_run":        dry_run,
        "script_dir":     os.path.dirname(os.path.abspath(script_path)),
    }

    if dry_run:
        print("[Bytecraft] *** DRY RUN — no files or folders will be written ***")

    try:
        _execute(lines, state, source_label=script_path)
    except BytecraftError as e:
        print(str(e), file=sys.stderr)
        sys.exit(1)


def run_from_url(url: str, dry_run: bool = False) -> None:
    import urllib.request
    import urllib.error

    _log(f"Fetching remote script: {url}")
    try:
        with urllib.request.urlopen(url, timeout=15) as response:
            source = response.read().decode("utf-8")
    except urllib.error.HTTPError as e:
        print(f"[Bytecraft] ERROR: HTTP {e.code} fetching {url!r}", file=sys.stderr)
        sys.exit(1)
    except urllib.error.URLError as e:
        print(f"[Bytecraft] ERROR: Could not reach {url!r} — {e.reason}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"[Bytecraft] ERROR: Failed to fetch {url!r} — {e}", file=sys.stderr)
        sys.exit(1)

    lines = source.splitlines(keepends=True)

    state: dict = {
        "working_folder": None,
        "vars":           {},
        "templates":      {},
        "strict":         False,
        "dry_run":        dry_run,
        "script_dir":     os.getcwd(),
    }

    if dry_run:
        print("[Bytecraft] *** DRY RUN — no files or folders will be written ***")

    try:
        _execute(lines, state, source_label=url)
    except BytecraftError as e:
        print(str(e), file=sys.stderr)
        sys.exit(1)
