# SIMNUX

**A lightweight, browser-based Linux CLI simulator built for general training,**
**CTFs, and interactive tutorials. Runs entirely in userspace — no containers,**
**no VMs, no kernel interaction.**

---

## What It Is

SIMNUX is a **Python-based simulation engine** that reproduces Linux shell
semantics inside a controlled virtual runtime. It replaces real OS processes
with a session-bound, HTTP-accessible shell backed by an in-memory layered
filesystem. The browser frontend is a thin terminal renderer — all state
lives server-side.

Built for **scenario-based training environments** where determinism,
isolation, and reproducibility matter more than full POSIX fidelity.

---

## Architecture

### Layered Virtual Filesystem (VFS)

```
base_layer  ← immutable, scenario-defined (YAML)
delta_layer ← per-session mutations (copy-on-write)
```

Reads merge both layers (delta wins). Writes always target `delta_layer` —
the base is never mutated. Deletion is a tombstone in the overlay, not a
destructive operation. This gives session isolation without cloning the
filesystem tree.

### Session Model

Each client gets an isolated `SNXShell` bound to:
- An `SNXSession` (CWD, command history, scenario metadata, interactive input state)
- An `SNXFileSystem` instance (two-layer overlay)
- A `CommandRegistry` (auto-discovered command classes)

Session identity is backend-generated (UUIDv4). The frontend retains the
opaque token for subsequent requests. No client-supplied session IDs.

### Command Pipeline

Commands are `SNXCommand` subclasses in `commands/standard/`, auto-discovered
via `pkgutil` at session init. Each command receives a `CommandContext`
(session + filesystem), reads/writes async streams, and returns an `ExitCode`.

Logical operators `&&` (AND) and `||` (OR) compose with pipelines and
redirections, using short-circuit evaluation — `&&` runs the next segment
only if the previous succeeded; `||` runs only if it failed.

```
raw input → parse logical (&&/||) → split on | → ParseResult
                                                  ├─ single command → dispatch
                                                  └─ multiple       → pipeline
```

Commands can also emit **terminal actions** (clear-screen, scenario win/fail)
via a `TerminalAction` enum, allowing the evaluator to trigger side effects
on the frontend.

**22 built-in commands**: `cat`, `cd`, `cal`, `clear`, `cp`, `diff`, `echo`,
`grep`, `head`, `history`, `ls`, `mkdir`, `mv`, `pwd`, `read`, `rm`, `rmdir`,
`sh` (alias: `bash`), `tail`, `test` (alias: `[`), `touch`, `whoami`.

### Interactive Input

The `read` command suspends the shell and returns an `awaiting_input` signal
to the frontend. The user types input inline; on submit, the shell resumes
with the captured value stored in a shell variable (or `REPLY` by default).

### Script Execution

`sh` and `bash` commands load and execute VFS-hosted scripts line by line
via the `ScriptRunner`, supporting logical operators (`&&`, `||`),
pipelines, redirections, and loop constructs (`while ... done`,
`for ... done`) within scripts.

### History Expansion

Interactive commands support POSIX history expansion tokens before
tokenization:
- `!!` — repeat the most recent command
- `!n` — 1-indexed history number
- `!-n` — relative past command (n lines back)
- `!string` — most recent command starting with `string`

Multiple tokens per line are supported. Expanded commands are echoed to
stdout before execution, matching standard shell behavior. Invalid
expansion references (e.g. `!!` with empty history) return a clean error
via stderr.

### Resource Limits

VFS byte caps and script execution bounds are configurable via
`config/limits.yaml` (git-ignored; copy `config/limits.yaml.example`).
Defaults: 1 MB per file, 10 MB total, 10 000 loop iterations, 30 s
wall-clock, 5 000 lines per script. Setting any value to `0` disables
that check.

### Scenario Objective Evaluation

The evaluator checks objective conditions (`file_state`, `command_output`,
`flag_input`) after every command execution and emits terminal actions
(`WIN` / `FAIL`) when conditions are met.

### API Surface

| Route | Method | Purpose |
|---|---|---|
| `/start` | GET | Create or resume a session (accepts optional `session_id` and `scenario_name` query params) |
| `/execute_command` | POST | Execute shell input |
| `/sessions/{id}` | GET | Session snapshot (read-only) |
| `/sessions/{id}` | DELETE | Destroy a session |
| `/api/scenarios` | GET | List available scenario names |
| `/` | GET | Health check / runtime snapshot |
| `/debug/runtime` | GET | Unredacted runtime introspection |

### Infrastructure Contracts

- **Exit codes**: 0 (SUCCESS), 1 (ERROR), 2 (INVALID_ARGUMENT) — simplified
  from real POSIX. No SIGINT/SIGPIPE codes.
- **Error strings**: Map to GNU coreutils conventions (`no such file or
  directory`, `is a directory`, etc.).
- **Permissions**: Stored per-node (rwxr-xr-x / rw-r--r-- defaults) but not
  enforced. Present for scenario display and future authorization.
- **Path resolution**: `~` expansion, `.`/`..` normalization, absolute path
  resolution — no symlinks.

### Observability

- Structured dual-output logging (ANSI-colored console + plain-text file)
- Custom `OK` log level (25) for positive operational signals
- `RuntimeSnapshot` / `ShellSnapshot` dataclasses for debug endpoints

---

## Scenarios

Behavior is defined by declarative YAML files under `scenarios/<name>/`:

```yaml
name: "Hello SIMNUX"
difficulty: "Easy"
username: "user"
hostname: "simnux"
starting_dir: "/home/user"

filesystem:
  "/etc/hostname": "simnux-edge-01"
  "/etc/motd": |
    Welcome to SIMNUX!
    This is the default scenario.
  "/home/user/notes.txt":
    - "TO DO:"
    - "1. Change admin password."
    - "2. Close port 8080."
  "/var/log/auth.log": "Apr  2 11:30:01 simnux sshd[123]: Accepted password for user..."
  "/bin/sh": "__BINARY_PLACEHOLDER__"
  "/home/user/.config/": ""
```

Content can be a string or a YAML list (joined with newlines). The
`ScenarioLoader` auto-creates parent directories and maps flat path
declarations into the VFS node tree. No database, no migration —
filesystem state is the scenario.

---

## What It Is Not

- **Not a Linux distribution** — no kernel, no syscalls, no binary execution
- **Not a container runtime** — no cgroups, no namespaces, no OCI images
- **Not a process emulator** — commands run as Python coroutines, not real
  processes
- **Not an SSH client** — the frontend is an HTTP consumer, not a terminal
  emulator
- **Not POSIX-compliant** — intentionally simplified exit codes, no signals,
  no fork/exec, no real processes

The goal is **behavioral fidelity at the UX layer**, not system-level
compatibility.

---

## Tech Stack

### Backend

- **Python >=3.10** — FastAPI, Uvicorn, Pydantic, PyYAML
- **FastAPI** — async HTTP transport for shell execution
- **No ORM, no database** — all state is in-memory
- **pytest + pytest-asyncio + httpx** — unit, integration, regression, and
  e2e test suite with 85% coverage threshold; includes resource-limit stress
  tests (infinite-loop halting, script line cap, VFS quota breach via `>>`)
  and POSIX history expansion tests
- **Ruff** — linting and formatting
- **mypy** — static type checking

### Frontend

- **Vanilla JavaScript** — ~350 LOC, no framework, no build step
- **HTML/CSS** — single-page terminal UI with ANSI color rendering
- **Contenteditable input** — active prompt uses `<span contenteditable>` for native inline text flow and line wrapping
- **Arrow-key history** — client-side command history with `ArrowUp`/`ArrowDown` navigation
- **Click-to-focus** — clicking anywhere in the terminal focuses the active input

### CI/CD

- **Forgejo Actions** — lint, format, type-check, test with coverage gate

---

## Local Development

```bash
python dev.py
```

| Service | URL |
|---|---|
| Backend (FastAPI) | `http://localhost:8000` |
| Frontend (static) | `http://localhost:8001` |

Environment variable `SIMNUX_RELOAD=true` enables uvicorn hot-reload.

### Running Tests

```bash
pytest                           # all tests
pytest tests/unit                # unit tests only
pytest tests/e2e                 # end-to-end shell flows
pytest tests/integration         # API route + overlay integrity
pytest tests/regression          # regression suite
```

---

## Design Constraints

1. **No real processes** — commands are Python coroutines mutating in-memory
   state. There is no `fork()`, `exec()`, or PID tree.
2. **Deterministic by construction** — no I/O scheduling, no race conditions
   in the VFS, no external dependencies at runtime.
3. **Session isolation via composition** — each session gets its own
   filesystem, registry, and shell instance. No shared mutable state.
4. **Frontend is a view layer** — the prompt string is rendered server-side;
   the browser just appends it to the DOM.
5. **Scenarios are the deployment unit** — a SIMNUX deployment defines a set
   of scenarios; no DB migrations or schema changes are required to add new
   training content.
6. **No permission model** — there is no file-permission or ownership logic.
   `sh` executes any file as a script regardless of mode bits; every VFS node
   is readable, writable, and executable by any session.

---

## License

MIT
