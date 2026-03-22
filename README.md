# 🧱 Bytecraft

A lightweight Domain-Specific Language for scaffolding files and folders — readable by humans, executable by Python.

```bash
pip install bytecraft
```

---

## What it does

Instead of writing setup scripts in Bash or Python, you write simple instructions in a `.bc` file:

```
# My project setup

set-working-folder "my-app"

make-folder "src"
make-folder "src/utils"
make-folder "assets"

make-file "README.md" with "# My App"
make-file "src/main.py" with "print('Hello, World!')"
make-file "src/utils/helper.py"
```

Run it with:

```bash
py -m bytecraft setup.bc
```

Output:

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

### `make-file`

Creates a file. Parent directories are created automatically.

```
make-file "path/to/file.txt"
make-file "path/to/file.txt" with "content here"
```

If the file already exists, it is overwritten.

---

### `make-folder`

Creates a directory. Does nothing if it already exists.

```
make-folder "path/to/folder"
```

---

### `set-working-folder`

Sets the base directory for all subsequent relative paths. Created if it doesn't exist.

```
set-working-folder "my-project"
```

---

### Comments

Lines starting with `#` are ignored.

```
# This is a comment
```

---

## Forgiving Syntax

Bytecraft is intentionally forgiving. Quotes are optional — if they're missing, Bytecraft will try to interpret your intent anyway:

```
make-file hello.txt with Hello World
```

is treated the same as:

```
make-file "hello.txt" with "Hello World"
```

Unknown commands are skipped with a warning rather than crashing the script.

---

## Path Resolution

All relative paths are resolved against the `set-working-folder` if one has been set, otherwise against the directory where you ran the command.

Absolute paths are always used as-is.

---

## Limitations (v0.1)

- No variables
- No loops or conditionals
- No multi-line file content
- No append mode
- No imports or includes

These are planned for future versions.

---

## Roadmap

- [ ] Multi-line content blocks
- [ ] Variables and interpolation
- [ ] `append-file` command
- [ ] Strict mode
- [ ] Template support
- [ ] Import / include system

---

## License

[Server-Lab Open-Control License (SOCL) 1.0](./LICENSE)  
Copyright (c) 2025 Sourasish Das
