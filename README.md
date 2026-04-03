Project description
🧱 Bytecraft
A human-readable DSL for scaffolding files and folders.

pip install bytecraft
Bytecraft lets you describe a project structure in plain, readable instructions and execute it with a single command — no Bash, no Python boilerplate, no mental overhead. Designed with data pipelines and scaffold-heavy workflows in mind.

# pipeline.bc

load-vars "pipeline.ebv"

set-working-folder "{{project}}"

for i in 1 to {{num_partitions}}
  make-file "data/partition_{{i:03}}.parquet"
  make-file "schemas/schema_{{i:03}}.json" with "{ \"partition\": {{i}}, \"next\": {{i + 1}} }"
end-for
py -m bytecraft pipeline.bc
[Bytecraft:1] Loaded 3 variable(s) from: pipeline.ebv
[Bytecraft:3] Working folder set: my-pipeline
[Bytecraft:5] Created file: my-pipeline/data/partition_001.parquet
[Bytecraft:6] Created file: my-pipeline/schemas/schema_001.json
...
Installation
Requires Python 3.10+

pip install bytecraft
Usage
bytecraft <script.bc>                        # run a local script
bytecraft <https://example.com/script.bc>   # fetch and run a remote script
bytecraft --dry-run <script.bc>             # preview what the script would do — no files written
bytecraft --help                             # print the full language reference
bytecraft --version                          # print the current version
Running Remote Scripts
Pass a URL instead of a file path to fetch and run a .bc script directly from the internet — nothing is downloaded or saved to disk.

bytecraft https://example.com/scaffold.bc
bytecraft --dry-run https://example.com/scaffold.bc
[Bytecraft] Fetching remote script: https://example.com/scaffold.bc
[Bytecraft:1] Variable set: project = 'my-pipeline'
[Bytecraft:3] Created folder: my-pipeline/data
...
Notes:

The script is fetched over HTTP/HTTPS and executed entirely in memory.
Relative paths in the remote script resolve from your current working directory.
include is local-only — remote scripts cannot include other URLs.
If the URL is unreachable, returns a non-200 status, or times out, execution halts with a fatal error.
--dry-run works identically with remote scripts.
--dry-run
Parses and executes the entire script without writing anything to disk. All file and folder operations are printed as previews, including a content excerpt for file writes. Variables, loops, conditionals, and templates all evaluate normally. Distinguishes between creating a new file and overwriting an existing one. Works with both local and remote scripts.

[Bytecraft] *** DRY RUN — no files or folders will be written ***
[Bytecraft:5] [DRY RUN] Would create folder: my-pipeline/data
[Bytecraft:6] [DRY RUN] Would create file: my-pipeline/README.md  (42 chars: '# my-pipeline↵Version: 1.0.0')
[Bytecraft:9] [DRY RUN] Would overwrite file: my-pipeline/VERSION  (5 chars: '1.0.0')
--help
Prints the full language reference to stdout — every command, interpolation syntax, pipe transforms, arithmetic, loops, conditionals, templates, and an example script. Useful as a quick offline reference without leaving your terminal.

bytecraft --help
bytecraft -h
--version
bytecraft --version
# bytecraft 0.6.4
Commands
set-working-folder
Sets the base directory for all subsequent relative paths. Created automatically if it doesn't exist.

set-working-folder "my-project"
make-folder
Creates a directory and any missing parent directories. Does nothing if the folder already exists.

make-folder "data/raw"
make-file
Creates a file. Parent directories are created automatically. If the file already exists, it is overwritten and a warning is emitted (a fatal error in strict on mode).

# Empty file
make-file "src/__init__.py"

# Inline content
make-file "VERSION" with "1.0.0"

# Multi-line content block
make-file "README.md" with ---
# My Project

Some description here.
---
append-file
Appends content to an existing file. Creates the file if it doesn't exist. A newline is automatically inserted before the new content if the file is non-empty.

make-file "pipeline.log" with "Pipeline started"
append-file "pipeline.log" with "Stage 1 complete"
append-file "pipeline.log" with "Stage 2 complete"
Multi-line blocks work too:

append-file "README.md" with ---

## Changelog

Added in v2.
---
replace-file
Identical to make-file but always overwrites an existing file — even in strict on mode. Use this when you explicitly intend to replace a file and want to be clear about it.

replace-file "config.json" with "{ \"env\": \"prod\" }"

replace-file "README.md" with ---
# My Project

Updated content.
---
edit-file
Patches an existing file using line-based operations. All line numbers refer to the original file — the entire file is parsed first, then all edits are applied in one pass.

edit-file "src/main.py" with ---
l1+ # my-app v2.0
l3> import logging
l5-
l7- print('Hello, World!')
---
Operation	Example	Behaviour
l1+	l1+ new content	Replace line 1 with new content
l1-	l1-	Delete line 1 unconditionally
l1-	l1- exact text	Delete line 1 only if it matches exactly (LLM-safe)
l1>	l1> inserted line	Insert before line 1, shifting everything down
Because line numbers are resolved against the original file, deleting multiple lines is written as:

edit-file "file.txt" with ---
l1-
l2-
l3-
l4-
l5-
---
Not l1- five times — those would all refer to the same original line.

Variables and expressions are interpolated inside patch content:

set version "2.0.0"

edit-file "VERSION" with ---
l1+ {{version}}
---
edit-file warns and skips if the file doesn't exist. In strict on mode the warning becomes a fatal error.

copy-file
Copies a file or folder to a new location. Parent directories are created automatically. If copying a folder that already exists at the destination, it is replaced.

copy-file "src/app.py" to "backup/app.py"
copy-file "src" to "src_backup"
move-file
Moves a file or folder to a new location. Parent directories are created automatically.

move-file "build/output.js" to "dist/app.js"
move-file "temp" to "archive/temp"
delete-file
Deletes a file. Warns if the path doesn't exist or points to a folder.

delete-file "temp.log"
delete-file "{{build_dir}}/old_output.csv"
delete-folder
Deletes a folder and all its contents. Warns if the path doesn't exist or points to a file.

delete-folder "temp"
delete-folder "{{build_dir}}/cache"
make-zip
Creates a zip archive from one or more files or folders. Folder structure is preserved inside the zip. Pass multiple sources to bundle them into a single archive.

# Single source
make-zip "releases/v1.0.zip" from "dist"

# Multiple sources
make-zip "releases/data.zip" from "data/processed" "data/schemas" "README.md"
extract
Extracts the full contents of a zip archive to a destination folder. Parent directories are created automatically. If the destination folder already exists, contents are merged in and any conflicting files are overwritten.

extract "releases/v1.0.zip" to "dist"
extract "{{project}}-{{version}}.zip" to "{{project}}"
extract-file
Extracts a single file from inside a zip archive to a destination path. The inner path must match the zip-internal path exactly — it is case-sensitive and uses forward slashes regardless of OS. Parent directories at the destination are created automatically. Warns and skips if the specified file is not found inside the zip.

extract-file "data/schema.json" from "releases/v1.0.zip" to "schemas/schema.json"
extract-file "config/prod.json" from "{{project}}.zip" to "config/prod.json"
set
Defines a variable. Variables are referenced anywhere using {{name}} syntax — in paths, content, template calls, and loop bodies. Expressions and string operations are evaluated at assignment time. Always quote multi-word values.

set project "my-pipeline"
set version "1.0.0"
set label "{{project|upper}}"   # evaluated immediately → MY-PIPELINE

make-file "VERSION" with "{{version}}"
make-file "LABEL" with "{{label}}"
set-from-env
Loads an OS environment variable into a Bytecraft variable. Useful for CI/CD pipelines and secrets. Warns if the environment variable is not set.

set-from-env deploy_target "DEPLOY_TARGET"
set-from-env api_key "API_KEY"

make-file "config/deploy.json" with "{ \"target\": \"{{deploy_target}}\" }"
load-vars
Loads variables from an .ebv (External Bytecraft Variables) file. Useful for sharing config across multiple scripts or driving loops from external values.

load-vars "config.ebv"
config.ebv:

# Pipeline config
project = my-pipeline
version = 1.0.0
author = Sourasish Das
env = prod
num_partitions = 24
num_shards = 8
Lines starting with # are ignored. Values do not need quotes.

print
Prints a message to stdout. Supports full {{interpolation}}. Useful for progress output and debugging.

set env "prod"
print "Building {{env|upper}} release..."

for i in 1 to 5
  print "  Processing partition {{i}} of 5"
  make-file "data/part_{{i}}.parquet"
end-for

print "Done."
for
Loops over a list of values or an integer range. The loop variable is available inside the body via {{name}}. Range bounds can be variables. Loops can be nested. Bare-word value lists are interpolated.

# Quoted value list
for env in "dev" "staging" "prod"
  make-file "config/{{env}}.json" with "{ \"env\": \"{{env}}\" }"
end-for

# Bare-word value list (also works, values are interpolated)
for env in dev staging prod
  make-file "config/{{env}}.json"
end-for

# Integer range
for i in 1 to 10
  make-file "logs/day_{{i}}.log"
end-for

# Variable range bounds (driven by .ebv)
load-vars "pipeline.ebv"
for i in 1 to {{num_partitions}}
  make-file "data/partition_{{i:03}}.parquet"
end-for
if / else-if / else
Conditionally executes a block. Supports file existence checks and variable comparisons. Supports else-if and else chains. Can be nested inside loops and other if blocks.

# File existence
if exists "data/processed"
  make-folder "data/archive"
end-if

if not exists "dist"
  make-folder "dist"
end-if

# Variable comparison with else-if / else
if "{{env}}" is "prod"
  make-file "config.json" with "{ \"debug\": false, \"strict\": true }"
else-if "{{env}}" is "staging"
  make-file "config.json" with "{ \"debug\": true, \"strict\": true }"
else
  make-file "config.json" with "{ \"debug\": true, \"strict\": false }"
end-if

# Negation
if "{{env}}" is not "dev"
  include "hardening.bc"
end-if
define-template / use-template
Templates let you define reusable scaffolding blocks and stamp them out with different values. Variables passed to use-template are local to that call and do not leak back into the outer script.

define-template "dataset"
  make-folder "data/{{name}}/raw"
  make-folder "data/{{name}}/processed"
  make-file "data/{{name}}/README.md" with "# {{name}} dataset"
end-template

use-template "dataset" name "customers"
use-template "dataset" name "orders"
use-template "dataset" name "products"
include
Runs another .bc file inline with fully shared state. Variables, templates, the working folder, and strict mode all carry across in both directions. Paths are resolved relative to the calling script's directory. Remote URLs are not supported — include is local-only.

include "base.bc"
include "templates/data-pipeline.bc"
strict on / strict off
In strict mode, warnings become fatal errors — undefined variables, unknown commands, and missing source files all halt execution immediately. Can be toggled on and off within the same script.

strict on

make-file "VERSION" with "{{version}}"   # fine if version is set
make-file "bad.txt" with "{{typo}}"      # ERROR: halts execution

strict off
Comments
Lines starting with # are ignored.

# This is a comment
Expressions
Variables support arithmetic and string operations directly inside {{ }}.

Arithmetic
All four operations are supported. Operands can be variable names or numeric literals.

{{i + 1}}
{{total - 2}}
{{count * 3}}
{{total / 4}}
Arithmetic composes with format specs:

for i in 1 to {{count}}
  make-file "part_{{i:02}}_of_{{count + 0:02}}.csv" with "next={{i + 1}}"
end-for
# → part_01_of_05.csv, part_02_of_05.csv, ...
String operations
String operations use a pipe | syntax.

Operation	Syntax	Example output
Uppercase	{{name|upper}}	MY_DATASET
Lowercase	{{name|lower}}	my_dataset
Capitalize	{{name|capitalize}}	My_dataset
Trim whitespace	{{name|trim}}	my_dataset
Length	{{name|len}}	10
Replace	{{name|replace:_:-}}	my-dataset
set name "my_dataset"

make-file "{{name|upper}}.txt"           # MY_DATASET.txt
make-file "{{name|capitalize}}.txt"      # My_dataset.txt
make-file "{{name|replace:_:-}}.txt"     # my-dataset.txt
print "name is {{name|len}} characters"  # name is 10 characters
String ops work in paths, content, and set values:

set tag "{{name|upper}}"
make-folder "datasets/{{name|replace:_:/}}"   # datasets/my/dataset/
Format specs
Numeric variables and arithmetic results support Python-style format specs using {{var:fmt}}.

Syntax	Example output
{{i:02}}	01, 02, ... 10
{{i:03}}	001, 002, ... 100
{{i:>5}}	1 (right-aligned, width 5)
Forgiving Syntax
Bytecraft is intentionally forgiving. Quotes are optional — if they're missing, Bytecraft will recover and interpret your intent:

make-file hello.txt with Hello World
is treated the same as:

make-file "hello.txt" with "Hello World"
Unknown commands print a warning and are skipped rather than crashing the script. Use strict on if you want the opposite behaviour.

Full Example
# Data pipeline scaffold

strict on

load-vars "pipeline.ebv"
set-from-env deploy_target "DEPLOY_TARGET"

set-working-folder "{{project}}"
set project_upper "{{project|upper}}"

print "Scaffolding {{project_upper}} ({{env}})..."

# Dataset template
define-template "dataset"
  make-folder "data/{{name}}/raw"
  make-folder "data/{{name}}/processed"
  make-folder "data/{{name}}/archive"
  make-file "data/{{name}}/README.md" with "# {{name|upper}} — {{project}}"
end-template

use-template "dataset" name "customers"
use-template "dataset" name "orders"
use-template "dataset" name "products"

# Generate partitioned output files
for i in 1 to {{num_partitions}}
  make-file "output/partition_{{i:03}}_of_{{num_partitions:03}}.parquet"
end-for

print "Created {{num_partitions}} partitions."

# Per-environment configs
for env in "dev" "staging" "prod"
  if "{{env}}" is "prod"
    make-file "config/{{env}}.json" with "{ \"debug\": false, \"strict\": true }"
  else-if "{{env}}" is "staging"
    make-file "config/{{env}}.json" with "{ \"debug\": true, \"strict\": true }"
  else
    make-file "config/{{env}}.json" with "{ \"debug\": true, \"strict\": false }"
  end-if
end-for

# Build log
make-file "pipeline.log" with "Scaffold started for {{project_upper}}"
append-file "pipeline.log" with "Datasets created"
append-file "pipeline.log" with "{{num_partitions}} partitions generated"
append-file "pipeline.log" with "Configs written"

# Package for release in prod only
if "{{env}}" is "prod"
  copy-file "output" to "dist/output"
  make-zip "releases/{{project}}-{{version}}.zip" from "dist" "pipeline.log"
  append-file "pipeline.log" with "Release packaged → {{deploy_target}}"
  print "Release zipped to releases/{{project}}-{{version}}.zip"
end-if
pipeline.ebv:

project = my-pipeline
version = 1.0.0
author = Sourasish Das
env = prod
num_partitions = 24
Roadmap
 Variables and interpolation
 Multi-line file content blocks
 copy-file and move-file
 make-zip (single and multiple sources)
 append-file
 Templates (define-template / use-template)
 include
 Strict mode
 for loops (value lists and ranges)
 Variable range bounds
 Zero-padding and format specs ({{i:03}})
 if / else-if / else
 .ebv external variable files
 delete-file and delete-folder
 Arithmetic expressions ({{i + 1}}, {{count * 2}})
 String operations ({{name|upper}}, {{name|capitalize}}, {{name|len}}, {{name|replace:_:-}})
 print command
 set-from-env for environment variable injection
 --dry-run CLI flag — now fully side-effect free (no directories created on disk)
 Line numbers in all log output
 --help / -h — full language reference in the terminal
 --version / -v
 Overwrite warning on make-file (fatal in strict mode)
 extract — extract full zip contents to a folder (merge/overwrite if destination exists)
 extract-file — extract a single file from a zip by its internal path
 Remote script execution — bytecraft https://example.com/script.bc fetches and runs in memory
 replace-file — explicit overwrite, bypasses strict mode overwrite guard
 edit-file — line-based file patching (l1+ replace, l1- delete, l1> insert before)
Project Status
Bytecraft has reached its intended feature set. The core language is complete — variables, loops, conditionals, templates, zip operations, file patching, remote execution, and everything in between are all shipped and working.

Future updates will prioritize stability, bug fixes, and reliability over new features. The DSL syntax and existing commands are considered stable and will not have breaking changes.

License
Server-Lab Open-Control License (SOCL) 1.0
Copyright (c) 2025 Sourasish Das
