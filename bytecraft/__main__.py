"""
Entry point for: python -m bytecraft file.bc

Usage:
  bytecraft <script.bc>             Run a local script
  bytecraft <https://...>           Fetch and run a remote .bc script
  bytecraft --dry-run <script.bc>   Preview what the script would do (no writes)
  bytecraft --help                  Show language reference
  bytecraft --version               Show version
"""

import sys
from .interpreter import run, run_from_url

VERSION = "0.6.4"

HELP_TEXT = """
╔══════════════════════════════════════════════════════════════╗
║            Bytecraft DSL  ·  Language Reference              ║
║                        v0.6.4                                ║
╚══════════════════════════════════════════════════════════════╝

USAGE
  bytecraft [--dry-run] <script.bc>
  bytecraft [--dry-run] <https://example.com/script.bc>
  bytecraft --help
  bytecraft --version

  --dry-run   Preview all operations without writing anything to disk.
              Works with both local and remote scripts.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
REMOTE SCRIPTS
  Pass a URL instead of a file path to fetch and run a .bc script
  directly from the internet — no download required.

  bytecraft https://example.com/scaffold.bc
  bytecraft --dry-run https://example.com/scaffold.bc

  Notes:
  · The script is fetched over HTTP/HTTPS and executed in memory.
  · Relative paths in the script resolve from your current directory.
  · include is local-only — remote scripts cannot include other URLs.
  · If the URL is unreachable or returns an error, execution halts.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
COMMENTS
  # This is a comment

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
VARIABLES
  set <n> "value"
      Assign a variable. Value supports interpolation.
      Example:  set app "myapp"

  set-from-env <n> "ENV_VAR"
      Load an environment variable into a bytecraft variable.
      Example:  set-from-env token "GITHUB_TOKEN"

  load-vars "file.ebv"
      Load key = value pairs from an external vars file.
      Example:  load-vars "config.ebv"
      File format:
        name = myapp
        version = 1.0

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
INTERPOLATION
  Use {{name}} anywhere in a string to substitute a variable.

  Pipe transforms:
    {{name|upper}}          -> "MYAPP"
    {{name|lower}}          -> "myapp"
    {{name|capitalize}}     -> "Myapp"
    {{name|trim}}           -> strips whitespace
    {{name|len}}            -> character count as string
    {{name|replace:_:-}}    -> replace underscores with hyphens

  Arithmetic:
    {{i + 1}}               -> integer addition
    {{count * 2}}           -> multiply
    {{total / 4}}           -> divide
    {{score - 1}}           -> subtract

  Format specs:
    {{i:03}}                -> zero-padded integer, e.g. "007"

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
FILES AND FOLDERS
  make-folder "path"
      Create a directory (and any missing parents).
      Example:  make-folder "src/utils"

  make-file "path" with "content"
      Create a file with inline content.
      Example:  make-file "VERSION" with "1.0.0"

  make-file "path" with ---
      Multi-line file content block.
      Example:
        make-file "README.md" with ---
        # {{project}}
        Welcome to {{project}}.
        ---

  append-file "path" with "content"
      Append to a file (creates it if missing). Also supports --- blocks.

  replace-file "path" with "content"
      Overwrite a file unconditionally — no overwrite warning, even in
      strict mode. Use when intentional replacement is the expected
      behaviour. Also supports --- multi-line blocks.
      Example:  replace-file "config.json" with "{ \"env\": \"prod\" }"

  copy-file "src" to "dst"
      Copy a file or directory tree.

  move-file "src" to "dst"
      Move a file or directory.

  delete-file "path"
      Delete a file.

  delete-folder "path"
      Delete a folder and all its contents.

  make-zip "out.zip" from "folder" ["folder2" ...]
      Create a zip archive from one or more files/folders.

  extract "archive.zip" to "dest/"
      Extract all contents of a zip archive to a folder.
      If the destination exists, contents are merged in and
      conflicting files are overwritten.

  extract-file "inner/file" from "archive.zip" to "dest/file"
      Extract a single file from inside a zip archive.
      Warns and skips if the file is not found inside the zip.

  set-working-folder "path"
      Set a base directory. All subsequent relative paths resolve
      against it. Creates the folder if it does not exist.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
LOOPS
  for <var> in "a" "b" "c"
    ...
  end-for

  for <var> in 1 to 5
    ...
  end-for

  Variable bounds also work:
    set count "3"
    for i in 1 to {{count}}
      print "Step {{i}}"
    end-for

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
CONDITIONALS
  if exists "path"
  if not exists "path"
  if "{{var}}" is "value"
  if "{{var}}" is not "value"

  else-if and else are supported:
    if "{{env}}" is "prod"
      make-file "config.toml" with "env = production"
    else-if "{{env}}" is "staging"
      make-file "config.toml" with "env = staging"
    else
      make-file "config.toml" with "env = development"
    end-if

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
TEMPLATES
  define-template "name"
    ...
  end-template

  use-template "name" key "value" key2 "value2"

  Example:
    define-template "service"
      make-folder "services/{{name}}"
      make-file "services/{{name}}/index.py" with "# {{name}} service"
    end-template

    use-template "service" name "auth"
    use-template "service" name "billing"

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
INCLUDES
  include "other.bc"
      Execute another .bc file inline. Paths resolve relative to
      the including file. Remote URLs are not supported in include.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
START NEW SCAFFOLD
  start-new "other.bc"
  start-new "https://example.com/other.bc"
      Run a separate .bc script with a completely clean state —
      no variables, no templates, no working folder carried over.
      Use this to split large scaffolds across multiple files
      without hitting file size limits.

      Supports both local paths and remote URLs. If the file is
      missing or the URL fails, execution halts with a fatal error.

      Local paths resolve relative to the calling script's directory.
      Remote scripts resolve relative paths from the current working
      directory, same as running them directly from the CLI.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
OUTPUT AND MODES
  print "message"
      Write a message to stdout. Supports interpolation.

  strict on
  strict off
      In strict mode, warnings become errors and halt execution.
      Recommended for CI pipelines.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
EXAMPLE SCRIPT
  set project "my-app"
  set author "Alice"

  make-folder "{{project}}/src"
  make-folder "{{project}}/tests"

  make-file "{{project}}/README.md" with ---
  # {{project|capitalize}}
  By {{author}}.
  ---

  for env in "dev" "staging" "prod"
    make-file "{{project}}/config.{{env}}.toml" with ---
    [env]
    name = "{{env}}"
    ---
  end-for

  print "Done -- {{project}} scaffolded."
"""


def main() -> None:
    args = sys.argv[1:]

    if not args or args[0] in ("--help", "-h"):
        print(HELP_TEXT)
        sys.exit(0)

    if args[0] in ("--version", "-v"):
        print(f"bytecraft {VERSION}")
        sys.exit(0)

    dry_run = False
    if args[0] == "--dry-run":
        dry_run = True
        args = args[1:]

    if not args:
        print("Error: no script file or URL provided.")
        print("Usage: bytecraft [--dry-run] <script.bc>")
        print("       bytecraft [--dry-run] <https://example.com/script.bc>")
        print("       bytecraft --help")
        sys.exit(1)

    script = args[0]

    if script.startswith("http://") or script.startswith("https://"):
        run_from_url(script, dry_run=dry_run)
    else:
        run(script, dry_run=dry_run)


if __name__ == "__main__":
    main()
