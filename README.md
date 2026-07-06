# SIMNUX

Deterministic Linux-shell simulator for cybersecurity training and systems
simulation. Runs entirely in userspace — no containers, no VMs, no kernel
interaction.

---

## What It Is

SIMNUX is a **Python-based simulation engine** that reproduces shell semantics
inside a controlled virtual runtime. It replaces real OS processes with a
session-bound, HTTP-accessible shell runtime backed by an in-memory layered
filesystem. The frontend is a dumb terminal renderer: all state lives server-
side.

The project is designed for **scenario-based training environments** where
determinism, isolation, and reproducibility matter more than POSIX fidelity.

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
- An `SNXSession` (CWD, task progress, scenario metadata)
- An `SNXFileSystem` instance (two-layer overlay)
- A `CommandRegistry` (auto-discovered command classes)

Session identity is backend-generated (UUIDv4). The frontend retains the
opaque token for subsequent requests. No client-supplied session IDs.

### Command Pipeline

Commands are `SNXCommand` subclasses in `commands/standard/`, auto-discovered
via `pkgutil` at session init. Each command receives a `CommandContext`
(session + filesystem), reads/writes async streams, and returns an `ExitCode`:

```
raw input → pre-process operators → split on | → ParseResult
                                              ├─ single command → dispatch ─┐
                                              └─ multiple       → dispatch  │
                                                   segments        pipeline │
                                                                           ↓
                                                            CommandResult
```

Pipes (`|`) and output redirection (`>` / `>>`) are fully supported.
The shell parser handles operator tokenization, pipeline segmentation,
and redirect-path extraction before dispatch.

### API Surface

| Route | Method | Purpose |
|---|---|---|
| `/start` | GET | Create or resume a session |
| `/execute_command` | POST | Execute shell input |
| `/sessions/{id}` | GET | Session snapshot (read-only) |
| `/` | GET | Health check / runtime snapshot |
| `/debug/runtime` | GET | Unredacted runtime introspection |

### Infrastructure Contracts

- **Exit codes**: 0 (SUCCESS), 1 (ERROR), 2 (INVALID_ARGUMENT) — simplified
  from real POSIX. No SIGINT/SIGPIPE codes.
- **Error strings**: Maps to GNU coreutils conventions (`no such file or
  directory`, `is a directory`, etc.).
- **Permissions**: Stored per-node (rwxr-xr-x / rw-r--r-- defaults) but not
  enforced. Present for scenario display and future authorization.
- **Path resolution**: `~` expansion, `.`/`..` normalization, absolute path
  resolution — no symlinks.

### Observability

- Structured dual-output logging (ANSI console + plain-text file)
- Custom `OK` log level (25) for positive operational signals
- `RuntimeSnapshot` / `ShellSnapshot` dataclasses for debug endpoints

---

## Scenarios

Behavior is defined by declarative YAML files under `scenarios/<name>/`:

```yaml
name: "Hello SIMNUX"
motd: "Welcome to SIMNUX!"
difficulty: "Easy"
username: "user"
hostname: "simnux"
starting_dir: "/home/user"

filesystem:
  "/etc/hostname": "simnux-edge-01"
  "/home/user/notes.txt":
    - "TO DO:"
    - "1. Change admin password."
  "/var/log/auth.log": "Apr  2 11:30:01 simnux sshd[123]: ..."
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

- **Python ≥3.10** — single dependency: `fastapi`, `uvicorn`, `pydantic`
- **FastAPI** — async HTTP transport for shell execution
- **No ORM, no database** — all state is in-memory
- **pytest + httpx** — unit, integration, regression, and e2e test suite

### Frontend

- **Vanilla JS** — ~150 LOC, no framework
- **HTML/CSS** — single-file terminal UI

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
cd backend
. .venv/bin/activate
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

---

## License

MIT
