"""
Bytecraft DSL Interpreter - v0.5.0
A lightweight DSL for creating files and folders.

  - Variables:         set <n> "value"
  - Interpolation:     {{name}} in any string
  - Multi-line blocks: make-file "f.txt" with ---
  - Copy:              copy-file "src" to "dst"
  - Move:              move-file "src" to "dst"
  - Zip:               make-zip "out.zip" from "folder"
  - Append:            append-file "f.txt" with "content"
  - Strict mode:       strict on / strict off
  - Templates:         define-template "name" ... end-template
                       use-template "name" key "value" ...
  - Include:           include "other.bc"
  - Loops:             for x in "a" "b" "c" ... end-for
                       for i in 1 to 5 ... end-for
  - Conditionals:      if exists / not exists "path" ... end-if
                       if "{{var}}" is / is not "value" ... end-if
  - External vars:     load-vars "file.ebv"
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

def _log(msg: str) -> None:
    print(f"[Bytecraft] {msg}")


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
        """Apply a pipe string operation: upper, lower, trim, replace:from:to"""
        op_str = op_str.strip()
        if op_str == "upper":
            return val.upper()
        if op_str == "lower":
            return val.lower()
        if op_str == "trim":
            return val.strip()
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
        _log("Strict mode enabled")
    elif val == "off":
        state["strict"] = False
        _log("Strict mode disabled")
    else:
        _warn(line_num, args, "strict requires 'on' or 'off'", state)


def _handle_set_working_folder(args: str, state: dict, line_num: int, **_) -> None:
    parts = _extract_strings(args, state)
    if not parts:
        _warn(line_num, args, "missing path for set-working-folder", state)
        return
    path = parts[0]
    os.makedirs(path, exist_ok=True)
    state["working_folder"] = path
    _log(f"Working folder set: {path}")


def _handle_make_folder(args: str, state: dict, line_num: int, **_) -> None:
    parts = _extract_strings(args, state)
    if not parts:
        _warn(line_num, args, "missing path for make-folder", state)
        return
    full_path = _resolve(parts[0], state)
    os.makedirs(full_path, exist_ok=True)
    _log(f"Created folder: {full_path}")


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
    value = _interpolate(value, state)
    state["vars"][name] = value
    _log(f"Variable set: {name} = {value!r}")


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

    _log(f"Loaded {loaded} variable(s) from: {path}")


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
    parent = os.path.dirname(full_path)
    if parent:
        os.makedirs(parent, exist_ok=True)

    if content_part is not None and content_part == "---":
        block_lines = []
        current = index
        while current < len(lines):
            raw = lines[current]
            current += 1
            stripped = raw.rstrip("\n").rstrip("\r")
            if stripped.strip() == "---":
                break
            block_lines.append(stripped)
        else:
            _warn(line_num, args, "multi-line block opened with --- but never closed", state)
        content = _interpolate("\n".join(block_lines), state)
        index = current
    else:
        content = ""
        if content_part is not None:
            content_strings = _extract_strings(content_part, state)
            content = content_strings[0] if content_strings else ""

    with open(full_path, "w", encoding="utf-8") as f:
        f.write(content)
    _log(f"Created file: {full_path}")
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
    parent = os.path.dirname(full_path)
    if parent:
        os.makedirs(parent, exist_ok=True)

    if content_part is not None and content_part == "---":
        block_lines = []
        current = index
        while current < len(lines):
            raw = lines[current]
            current += 1
            stripped = raw.rstrip("\n").rstrip("\r")
            if stripped.strip() == "---":
                break
            block_lines.append(stripped)
        else:
            _warn(line_num, args, "multi-line block opened with --- but never closed", state)
        content = _interpolate("\n".join(block_lines), state)
        index = current
    else:
        content = ""
        if content_part is not None:
            content_strings = _extract_strings(content_part, state)
            content = content_strings[0] if content_strings else ""

    # Append a newline before content if the file already exists and is non-empty
    prefix = ""
    if os.path.exists(full_path) and os.path.getsize(full_path) > 0:
        prefix = "\n"

    with open(full_path, "a", encoding="utf-8") as f:
        f.write(prefix + content)
    _log(f"Appended to file: {full_path}")
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
    dst_parent = os.path.dirname(dst)
    if dst_parent:
        os.makedirs(dst_parent, exist_ok=True)
    if os.path.isdir(src):
        if os.path.exists(dst):
            shutil.rmtree(dst)
        shutil.copytree(src, dst)
    else:
        shutil.copy2(src, dst)
    _log(f"Copied: {src} → {dst}")


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
    dst_parent = os.path.dirname(dst)
    if dst_parent:
        os.makedirs(dst_parent, exist_ok=True)
    shutil.move(src, dst)
    _log(f"Moved: {src} → {dst}")


def _handle_make_zip(args: str, state: dict, line_num: int, **_) -> None:
    from_split = re.split(r'\bfrom\b', args, maxsplit=1)
    if len(from_split) != 2:
        _warn(line_num, args, 'make-zip requires: make-zip "out.zip" from "source"', state)
        return
    zip_parts = _extract_strings(from_split[0].strip(), state)
    src_parts = _extract_strings(from_split[1].strip(), state)
    if not zip_parts or not src_parts:
        _warn(line_num, args, "make-zip missing output path or source", state)
        return
    zip_path = _resolve(zip_parts[0], state)
    src = _resolve(src_parts[0], state)
    if not os.path.exists(src):
        _warn(line_num, args, f"source does not exist: {src!r}", state)
        return
    zip_parent = os.path.dirname(zip_path)
    if zip_parent:
        os.makedirs(zip_parent, exist_ok=True)
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        if os.path.isdir(src):
            for root, _, files in os.walk(src):
                for file in files:
                    abs_path = os.path.join(root, file)
                    arc_name = os.path.relpath(abs_path, start=os.path.dirname(src))
                    zf.write(abs_path, arc_name)
        else:
            zf.write(src, os.path.basename(src))
    _log(f"Created zip: {zip_path} ← {src}")


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
    os.remove(full_path)
    _log(f"Deleted file: {full_path}")


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
    shutil.rmtree(full_path)
    _log(f"Deleted folder: {full_path}")


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
    _log(f"Template defined: {name} ({len(body)} lines)")
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
        "templates":      state["templates"],
        "vars":           {**state["vars"], **call_vars},
    }

    _log(f"Using template: {name}" + (f" with {call_vars}" if call_vars else ""))
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
    path = _resolve_include(parts[0], state)
    if not os.path.exists(path):
        _warn(line_num, args, f"included file not found: {path!r}", state)
        return
    _log(f"Including: {path}")
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
        # Value list: quoted or bare tokens
        quoted = re.findall(r'"([^"]*)"', rest)
        values = quoted if quoted else rest.split()

    for val in values:
        child_state: dict = {
            "working_folder": state["working_folder"],
            "script_dir":     state["script_dir"],
            "strict":         state["strict"],
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


# ─────────────────────────────────────────────
#  Dispatcher
# ─────────────────────────────────────────────

COMMANDS = [
    ("set-working-folder", _handle_set_working_folder),
    ("define-template",    _handle_define_template),
    ("use-template",       _handle_use_template),
    ("append-file",        _handle_append_file),
    ("make-folder",        _handle_make_folder),
    ("make-file",          _handle_make_file),
    ("make-zip",           _handle_make_zip),
    ("copy-file",          _handle_copy_file),
    ("delete-folder",      _handle_delete_folder),
    ("delete-file",        _handle_delete_file),
    ("move-file",          _handle_move_file),
    ("load-vars",          _handle_load_vars),
    ("include",            _handle_include),
    ("strict",             _handle_strict),
    ("set",                _handle_set),
    ("for",                _handle_for),
    ("if",                 _handle_if),
]

_MULTILINE_CMDS = {"make-file", "append-file", "define-template", "for", "if"}


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

def run(script_path: str) -> None:
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
        "script_dir":     os.path.dirname(os.path.abspath(script_path)),
    }

    try:
        _execute(lines, state, source_label=script_path)
    except BytecraftError as e:
        print(str(e), file=sys.stderr)
        sys.exit(1)
