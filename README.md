# 🧱 Bytecraft

> A human-readable DSL for scaffolding files and folders.

```
pip install bytecraft
```

---

Bytecraft lets you describe a project structure in plain, readable instructions and execute it with a single command — no Bash, no Python boilerplate, no mental overhead.

```
# bootstrap.bc

set-working-folder "my-app"

make-folder "src"
make-folder "src/utils"
make-folder "assets"

make-file "README.md" with "# my-app"
make-file "src/main.py" with "print('Hello, World!')"
make-file "src/utils/helper.py"
```

```bash
py -m bytecraft bootstrap.bc
```

```
[Bytecraft] Working folder set: my-app
[Bytecraft] Created folder: my-app/src
[Bytecraft] Created folder: my-app/src/utils
[Bytecraft] Created folder: my-app/assets
[Bytecraft] Created file: my-app/README.md
[Bytecraft] Created file: my-app/src/main.py
[Bytecraft] Created file: my-app/src/utils/helper.py
```

---

## Installation

Requires Python 3.10+

```bash
pip install bytecraft
```

---

## Commands

### `set-working-folder`

Sets the base directory for all subsequent relative paths. Created automatically if it doesn't exist.

```
set-working-folder "my-project"
```

---

### `make-folder`

Creates a directory and any missing parent directories. Does nothing if the folder already exists.

```
make-folder "src/utils"
```

---

### `make-file`

Creates a file. Parent directories are created automatically. Overwrites if the file already exists.

```
# Empty file
make-file "src/__init__.py"

# With inline content
make-file "VERSION" with "1.0.0"

# With a multi-line block
make-file "README.md" with ---
# My Project

Some description here.
---
```

---

### `set`

Defines a variable. Variables can be referenced anywhere using `{{name}}` syntax.

```
set project "my-app"
set version "1.0.0"

make-file "VERSION" with "{{version}}"
make-file "src/main.py" with "# {{project}} v{{version}}"
```

Variables also interpolate inside multi-line blocks:

```
set author "Sourasish Das"

make-file "README.md" with ---
# {{project}}

Maintained by {{author}}.
---
```

---

### Comments

Lines starting with `#` are ignored.

```
# This is a comment
```

---

## Forgiving Syntax

Bytecraft is intentionally forgiving. Quotes are optional — if they're missing, Bytecraft will try to recover and interpret your intent:

```
make-file hello.txt with Hello World
```

is treated the same as:

```
make-file "hello.txt" with "Hello World"
```

Unknown commands print a warning and are skipped rather than crashing the whole script.

---

## Full Example

```
# Project scaffold

set project "dashboard"
set author "Sourasish Das"
set version "0.1.0"

set-working-folder "{{project}}"

make-folder "src"
make-folder "src/components"
make-folder "src/utils"
make-folder "tests"
make-folder "assets"

make-file "VERSION" with "{{version}}"

make-file "src/main.py" with "# Entry point for {{project}}"

make-file "README.md" with ---
# {{project}}

Version: {{version}}
Author: {{author}}
---

make-file "tests/test_main.py" with ---
import unittest

class TestMain(unittest.TestCase):
    def test_placeholder(self):
        self.assertTrue(True)
---
```

---

## Limitations (v0.1.1)

- No loops or conditionals
- No append mode
- No imports or includes
- No strict mode

These are planned for future versions.

---

## Roadmap

- [ ] `append-file` command
- [ ] Loops and conditionals
- [ ] Strict mode
- [ ] Import / include system
- [ ] Template support

---

## License

[Server-Lab Open-Control License (SOCL) 1.0](./LICENSE)  
Copyright (c) 2025 Sourasish Das
