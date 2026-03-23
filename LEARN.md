# Learn Bytecraft

This guide walks you through Bytecraft from scratch — no prior experience needed. By the end you'll be writing scripts that scaffold full project structures, drive data pipelines, and package releases.

---

## 1. Your first script

Create a file called `hello.bc`:

```
make-file "hello.txt" with "Hello, Bytecraft!"
```

Run it:

```bash
py -m bytecraft hello.bc
```

You'll see:

```
[Bytecraft] Created file: hello.txt
```

Open `hello.txt` — it contains `Hello, Bytecraft!`. That's it. One line, one file.

---

## 2. Creating folders

```
make-folder "src"
make-folder "src/utils"
make-folder "assets"
```

Bytecraft creates all missing parent directories automatically. `src/utils` works even if `src` doesn't exist yet.

---

## 3. Setting a working folder

Instead of typing the same prefix on every path, set a working folder once:

```
set-working-folder "my-app"

make-folder "src"
make-file "README.md" with "# my-app"
```

Every path after `set-working-folder` is relative to `my-app/`. So `src` becomes `my-app/src` and `README.md` becomes `my-app/README.md`.

---

## 4. Multi-line file content

For longer content, use a `---` block:

```
make-file "README.md" with ---
# My Project

A short description.

## Usage

Run the app with `python main.py`.
---
```

Everything between the two `---` markers is written to the file exactly as typed.

---

## 5. Variables

Define a variable with `set`, reference it with `{{name}}`:

```
set project "dashboard"
set version "1.0.0"

set-working-folder "{{project}}"

make-file "VERSION" with "{{version}}"
make-file "src/main.py" with "# {{project}} v{{version}}"
```

Variables work in paths, content, and anywhere else a string appears.

---

## 6. Loading variables from a file

For larger configs, or to share values across multiple scripts, use a `.ebv` file:

**`config.ebv`:**
```
project = my-app
version = 1.0.0
author = Sourasish Das
env = prod
```

**`setup.bc`:**
```
load-vars "config.ebv"

set-working-folder "{{project}}"
make-file "VERSION" with "{{version}}"
```

Lines starting with `#` are comments. Values don't need quotes.

---

## 7. Arithmetic

Do simple math directly inside `{{ }}`:

```
set count "5"

make-file "info.txt" with ---
count     = {{count}}
count + 1 = {{count + 1}}
count * 2 = {{count * 2}}
---
```

Supported operators: `+`, `-`, `*`, `/`. Both sides can be variable names or numbers.

---

## 8. String operations

Transform variable values using the pipe `|` syntax:

```
set name "my_dataset"

make-file "{{name|upper}}.txt"        # MY_DATASET.txt
make-file "{{name|replace:_:-}}.txt"  # my-dataset.txt
```

Available operations:

| Operation | Example | Result |
|---|---|---|
| `\|upper` | `{{name\|upper}}` | `MY_DATASET` |
| `\|lower` | `{{name\|lower}}` | `my_dataset` |
| `\|trim` | `{{name\|trim}}` | strips whitespace |
| `\|replace:from:to` | `{{name\|replace:_:-}}` | `my-dataset` |

---

## 9. Format specs

Add `:fmt` to a variable for Python-style formatting — most useful for zero-padding numbers:

```
set i "7"

make-file "part_{{i:02}}.csv"   # part_07.csv
make-file "part_{{i:03}}.csv"   # part_007.csv
```

Combines with arithmetic too:

```
make-file "part_{{i:02}}_next_{{i + 1:02}}.csv"   # part_07_next_08.csv
```

---

## 10. Loops

### Value list

```
for env in "dev" "staging" "prod"
  make-file "config/{{env}}.json" with "{ \"env\": \"{{env}}\" }"
end-for
```

### Integer range

```
for i in 1 to 5
  make-file "logs/day_{{i}}.log"
end-for
```

### Variable range bounds

```
set num_shards "8"

for i in 1 to {{num_shards}}
  make-file "shards/shard_{{i:03}}.csv"
end-for
```

The loop variable is available as `{{i}}` (or whatever name you choose) inside the body. Loops can be nested inside each other.

---

## 11. Conditionals

### Existence check

```
if exists "dist"
  delete-folder "dist"
end-if

if not exists "output"
  make-folder "output"
end-if
```

### Variable comparison

```
set env "prod"

if "{{env}}" is "prod"
  make-file "config.json" with "{ \"debug\": false }"
else-if "{{env}}" is "staging"
  make-file "config.json" with "{ \"debug\": true, \"strict\": true }"
else
  make-file "config.json" with "{ \"debug\": true }"
end-if
```

`if` blocks can be nested inside loops, and loops can be nested inside `if` blocks.

---

## 12. Copying, moving, and deleting

```
# Copy a file
copy-file "src/app.py" to "backup/app.py"

# Copy a whole folder
copy-file "src" to "src_backup"

# Move a file
move-file "build/output.js" to "dist/app.js"

# Delete a file
delete-file "temp.log"

# Delete a folder and everything in it
delete-folder "temp"
```

---

## 13. Zipping

```
make-zip "releases/v1.0.zip" from "dist"
make-zip "releases/data.zip" from "data/processed"
```

Folder structure is preserved inside the zip. Works with variables:

```
make-zip "releases/{{project}}-{{version}}.zip" from "dist"
```

---

## 14. Templates

Templates let you define a reusable block of commands and stamp it out with different values:

```
define-template "module"
  make-folder "src/{{name}}"
  make-file "src/{{name}}/__init__.py"
  make-file "src/{{name}}/main.py" with "# {{name}} module"
end-template

use-template "module" name "auth"
use-template "module" name "api"
use-template "module" name "db"
```

Variables passed to `use-template` are local — they don't affect the outer script. Global variables (like `{{project}}`) are still accessible inside the template body.

Combine with a loop to stamp out many instances at once:

```
for name in "auth" "api" "db" "admin"
  use-template "module" name "{{name}}"
end-for
```

---

## 15. Including other scripts

Split large scripts into smaller reusable files:

**`folders.bc`:**
```
make-folder "src"
make-folder "tests"
make-folder "docs"
make-folder "assets"
```

**`main.bc`:**
```
set-working-folder "my-app"
include "folders.bc"
make-file "README.md" with "# my-app"
```

The included file runs with fully shared state — variables, templates, and the working folder all carry across in both directions. Paths in `include` are always relative to the calling script's location.

---

## 16. Strict mode

By default, Bytecraft is forgiving — unknown commands and undefined variables print a warning and continue. Turn on strict mode when you want errors to stop execution:

```
strict on

set version "1.0.0"
make-file "VERSION" with "{{version}}"      # fine
make-file "bad.txt" with "{{undefined}}"    # ERROR: stops here

strict off
make-file "this_runs.txt" with "ok"         # runs normally again
```

Use `strict on` at the top of production scripts to catch mistakes early.

---

## 17. Appending to files

Use `append-file` to add content to an existing file without overwriting it:

```
make-file "build.log" with "Build started"
append-file "build.log" with "Compiling..."
append-file "build.log" with "Done"
```

A newline is automatically added before each appended entry. Multi-line blocks work too:

```
append-file "CHANGELOG.md" with ---

## v1.1.0

- Added new feature
- Fixed bug
---
```

If the file doesn't exist yet, `append-file` creates it.

---

## 18. Putting it all together

Here's a complete data pipeline scaffold using everything covered in this guide:

```
# Full data pipeline scaffold
# Usage: py -m bytecraft pipeline.bc

strict on

load-vars "pipeline.ebv"

set-working-folder "{{project}}"
set project_label "{{project|upper}} v{{version}}"

# ── Dataset template ─────────────────────────
define-template "dataset"
  make-folder "data/{{name}}/raw"
  make-folder "data/{{name}}/processed"
  make-file "data/{{name}}/README.md" with "# {{name|upper}} dataset"
end-template

for ds in "customers" "orders" "products"
  use-template "dataset" name "{{ds}}"
end-for

# ── Partition files ──────────────────────────
for i in 1 to {{num_partitions}}
  make-file "output/partition_{{i:03}}_of_{{num_partitions:03}}.parquet"
end-for

# ── Environment configs ──────────────────────
for env in "dev" "staging" "prod"
  if "{{env}}" is "prod"
    make-file "config/{{env}}.json" with "{ \"debug\": false, \"strict\": true }"
  else-if "{{env}}" is "staging"
    make-file "config/{{env}}.json" with "{ \"debug\": true, \"strict\": true }"
  else
    make-file "config/{{env}}.json" with "{ \"debug\": true, \"strict\": false }"
  end-if
end-for

# ── Build log ────────────────────────────────
make-file "pipeline.log" with "{{project_label}} — scaffold started"
append-file "pipeline.log" with "Datasets: customers, orders, products"
append-file "pipeline.log" with "Partitions: {{num_partitions}}"
append-file "pipeline.log" with "Configs: dev, staging, prod"

# ── Release package (prod only) ──────────────
if "{{env}}" is "prod"
  copy-file "output" to "dist/output"
  make-zip "releases/{{project}}-{{version}}.zip" from "dist"
  append-file "pipeline.log" with "Release packaged"
end-if
```

**`pipeline.ebv`:**
```
project = my-pipeline
version = 1.0.0
author = Sourasish Das
env = prod
num_partitions = 24
```

---

## Quick reference

| Command | What it does |
|---|---|
| `set-working-folder "path"` | Set base directory for all paths |
| `make-folder "path"` | Create a directory |
| `make-file "path"` | Create an empty file |
| `make-file "path" with "content"` | Create a file with content |
| `make-file "path" with ---` | Create a file with a multi-line block |
| `append-file "path" with "content"` | Append to a file |
| `copy-file "src" to "dst"` | Copy a file or folder |
| `move-file "src" to "dst"` | Move a file or folder |
| `delete-file "path"` | Delete a file |
| `delete-folder "path"` | Delete a folder and its contents |
| `make-zip "out.zip" from "src"` | Create a zip archive |
| `set name "value"` | Define a variable |
| `load-vars "file.ebv"` | Load variables from a file |
| `for x in "a" "b" "c"` | Loop over a value list |
| `for i in 1 to 10` | Loop over an integer range |
| `if exists "path"` | Check if a path exists |
| `if "{{x}}" is "value"` | Compare a variable |
| `else-if "{{x}}" is "value"` | Additional branch |
| `else` | Fallback branch |
| `define-template "name"` | Define a reusable block |
| `use-template "name" key "val"` | Stamp out a template |
| `include "file.bc"` | Run another script inline |
| `strict on` / `strict off` | Toggle strict mode |
| `# comment` | Ignored line |

| Expression | What it does |
|---|---|
| `{{var}}` | Variable value |
| `{{var:03}}` | Zero-padded to 3 digits |
| `{{i + 1}}` | Arithmetic |
| `{{name\|upper}}` | Uppercase |
| `{{name\|lower}}` | Lowercase |
| `{{name\|trim}}` | Strip whitespace |
| `{{name\|replace:_:-}}` | Replace characters |
