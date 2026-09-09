# Changelog

All notable changes to the SIMNUX terminal simulator project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/), and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [0.5.1] - 2026.09.09

### Added

* **Derived File Size:** `SNXNode` now exposes a derived `size` property representing the UTF-8 byte length of the node's current file content. Size is not stored independently, preventing stale or duplicated filesystem metadata.
* **`ls -l` File Size:** Long-format listings now display file size in bytes between the group and filename fields, with numeric sizes right-aligned across the listing.

### Changed

* **VFS Size Accounting:** Filesystem quota accounting now delegates byte-size calculation to `SNXNode.size`, establishing a single source of truth for file size.

### Tests

* **File Size Semantics:** Added coverage for empty files, ASCII content, multibyte UTF-8 content, content replacement, appending, copying, and quota boundary behavior.
* **`ls -l` Formatting:** Added coverage for size rendering, column alignment, directories, dot entries, and preservation of the existing timestamp boundary.

---

## [0.5.0] - 2026.09.06

### Added

* **Scenario-Local Users and Groups:** Introduced `SNXUser` and `SNXGroup` as scenario-scoped simulated Linux identities. Users and groups are owned by the scenario and are distinct from SIMNUX application/session identities.
* **Scenario Group Membership:** Added `SNXGroupMembership` for resolving scenario-local group membership independently from the identity value objects. Group membership is resolved from the scenario's group database rather than stored redundantly on `SNXUser`.
* **Account Database Bootstrapping:** The scenario loader now creates `/etc/passwd`, `/etc/group`, and `/etc/shadow` as ordinary VFS files during scenario initialization. Initial accounts are created with locked passwords (`!`); no plaintext passwords are stored.
* **Password Authentication Primitives:** Added `SNXPAM` and `SNXPasswordCredential` using PBKDF2-HMAC-SHA256 with per-credential random salts and constant-time verification.
* **`passwd` Command:** Added interactive and piped password changes using the scenario-local `/etc/passwd` and `/etc/shadow` files. Password changes update only the shadow password field and never expose or persist plaintext passwords.
* **Filesystem Ownership:** `SNXNode` now has explicit `owner` (`SNXUser`) and `group` (`SNXGroup`) references. Newly created filesystem objects inherit ownership from the acting shell user and that user's primary group.
* **Unix-Style Permissions:** Added three-class user/group/other permission flags and standard permission presets for files and directories.
* **Permission Evaluation:** Added a centralized `PermissionEvaluator` that resolves the applicable permission class for an acting user and evaluates read, write, and execute access. Root (`UID 0`) has an explicit permission bypass under the SIMNUX v0.5.0 security model.
* **Filesystem Authorization:** VFS operations now enforce permissions for reads, writes, appends, existing-file updates, directory traversal, directory listing, creation, and deletion.
* **Parent-Directory Authorization:** File and directory creation/deletion now require write and execute access on the containing directory, matching Unix directory semantics rather than relying on the target's write bit.
* **`chmod` Command:** Added numeric Unix permission changes with support for common modes such as `644`, `600`, `755`, and `000`. Only the file owner or root may change permissions.
* **`ls -l`:** Added long-format directory listing showing file type, permission bits, owner, group, and filename.

### Changed

* **Filesystem Authorization Boundary:** Permission decisions are centralized in the VFS/permission layer. Commands provide the acting shell user and invoke filesystem primitives; commands do not implement permission policy themselves.
* **Command Acting Identity:** Filesystem and command authorization consistently use `ctx.shell.user`, keeping simulated Linux identity on the shell rather than the application-level `SNXSession`.
* **Filesystem Stream Authorization:** File stream writers and command redirection now propagate the acting user into VFS operations, ensuring redirected writes are subject to the same permission enforcement as direct filesystem writes.
* **Composite File Operations:** `mv`, `rm`, `rmdir`, `mkdir`, `touch`, and shell redirection now consistently pass through the VFS authorization boundary, including the appropriate parent-directory checks.
* **`ls -l` Scope:** Long-format listing intentionally exposes only metadata currently modeled by the VFS: file type, permissions, owner, group, and name. File size and timestamps remain outside the v0.5.0 scope.

### Fixed

* **Unauthorized File Deletion:** Closing a permission-enforcement gap where files could be deleted without write/execute access on their parent directory.
* **Unauthorized Creation:** Closed VFS paths that allowed creation of files or directories inside directories where the acting user lacked the required parent-directory permissions.
* **Unauthorized Redirect Writes:** Fixed stream/redirect error handling so denied writes surface as permission errors rather than misleading `not found` failures.
* **Composite Command Authorization:** Corrected `mv`, `rm`, `rmdir`, and related command paths so their underlying filesystem mutations are subject to centralized authorization.
* **Permission Regression Coverage:** Added regression coverage for wrong-owner access, group membership, permission-class selection, parent-directory authorization, denied creation/deletion, chmod ownership restrictions, root bypass, and rollback behavior.

### Tests

* **Filesystem Authorization Matrix:** Added comprehensive VFS authorization tests covering read, write, execute, creation, deletion, directory traversal, listing, ownership, group membership, permission classes, root bypass, and parent-directory semantics.
* **Command Enforcement Tests:** Added command-level regression coverage for `cat`, `head`, `tail`, `mkdir`, `rm`, `rmdir`, `mv`, shell redirection, and related filesystem operations.
* **`ls -l` Tests:** Added coverage for file/directory type, permission rendering, owner/group display, combined flags, and explicit exclusion of size/timestamp fields.
* **Release Validation:** v0.5.0 implementation validated with the full test suite, Ruff linting, Ruff formatting, and mypy baseline comparison without introducing new type-checking errors.

---

## [0.4.6] - 2026.09.05

### Added

* **`SNXSession` Shell Router:** `SNXSession` (`core/sessions/runtime.py`) is now a pure application-level session: it owns only the session token and the set of attached `SNXShell` instances (`shells`, `add_shell`/`get_shell`/`remove_shell`/`active_shells`) and carries no simulated-world interaction state. The structure `SNXSession 1 -> N SNXShell 1 -> 1 SNXScenario` is now realised internally.
* **`CommandRequest.scenario_name` Selector:** The execute-command contract gains an optional `scenario_name` field so a request can target a specific shell in a multi-shell session. When absent, the session's first/default shell is used. The public routing still keys a request by `session_id`; scenario/shell selection is now an explicit, opt-in field rather than an implicit coupling.

### Changed

* **Interaction State Moved to `SNXShell`:** All mutable per-scenario interaction state — current Linux user, current working directory, environment, command history, pending/suspended input, and task progress — now lives on `SNXShell` (`core/shell/runtime.py`). `CommandContext` now carries a `shell` reference (replacing the session reference that previously leaked interaction state), and commands/prompt rendering read `ctx.shell.user`/`ctx.shell.current_directory` instead of session-bound state (e.g. `whoami`, `pwd`, `cd`, `history`, `read`, `sh`, `ls`, `more`).
* **Runtime Session Semantics:** `SNXRuntime.create_session(scenario_name, session_id)` now returns the `SNXShell` and attaches it to the app-level `SNXSession` identified by `session_id`. Reusing `session_id` with a **different** scenario adds a second shell, preserving the first (both remain routable via `runtime.get_shell(session_id, scenario_name)`); reusing the same `session_id` **and** scenario replaces that scenario's shell (last-wins). `GET /api/sessions/{session_id}` and `GET /start` resume resolve the session's shell by `scenario_name` (falling back to the first shell), keeping the public API response contract unchanged.
* **Snapshot & Config Models Moved to `core`:** `ShellSnapshot`/`RuntimeSnapshot` now live in `core/runtime/observability.py` (produced by `SNXShell.get_snapshot()`/`SNXRuntime.get_snapshot()`) and `RuntimeConfig`/`LimitsConfig` in `core/runtime/config.py`. `infrastructure/observability/snapshots.py` and `boot/config.py` re-export them at their boundaries so no import-level behavior changes.
* **Package Reorganization:** Reorganized the SIMNUX backend under `backend/src/simnux/` into layered namespaces for clearer separation of concerns: `boot/` (application startup & composition — previously `init/`), `core/` (commands, filesystem, runtime, scenarios, sessions, shell, scripting), and `infrastructure/` (api, observability). This is a purely mechanical package reorganization; behavior is unchanged. Key namespace changes:
  * `simnux.init.*` → `simnux.boot.*` (e.g., `simnux.init.app_factory` → `simnux.boot.app_factory`)
  * `simnux.api.*` → `simnux.infrastructure.api.*`
  * `simnux.observability.*` → `simnux.infrastructure.observability.*`
  * `simnux.commands.*`, `simnux.filesystem.*`, `simnux.runtime.*`, `simnux.scenarios.*`, `simnux.sessions.*`, `simnux.shell.*`, `simnux.scripting.*` → `simnux.core.<package>.*`
* **Updated Entrypoints & Discovery:** Updated the uvicorn factory strings in `backend/src/simnux/cli.py` and `backend/Dockerfile` (now `simnux.boot.app_factory:create_app`), and updated the metadata-driven loaders (`core/commands/loader.py`, `boot/routes.py`) to discover modules from their new namespaces. The `simnux` console script (`simnux.cli:main`) is unchanged.

### Fixed

* **Session Snapshot Tests (`GET /api/sessions/{session_id}`):** `TestSessionEndpoint` was still hitting the pre-0.4.5 path `/sessions/{id}`, which only exposes a `DELETE` handler — GET returned `405 Method Not Allowed`. Updated the tests to use the relocated `/api/sessions/{id}` public route.
* **Removed Stale Debug Endpoint Test:** Deleted `TestDebugRuntimeEndpoint`, which asserted on `GET /debug/runtime` after that router was intentionally removed in 0.4.5.
* **API Performance/Integration Test Rate-Limit Flakiness:** The process-wide `slowapi` limiter (30/min per IP) is shared across the whole pytest run, so the aggregate requests in the API integration suite exhausted the quota and later tests spuriously failed with HTTP 429. Added an autouse conftest fixture that resets the limiter before each test — production rate limiting is unchanged.
* **`test_session_state_persistence` Scenario Expectation:** The e2e test issued `cd /var/log` and asserted on `/var/log/test.log`, but the `hello` scenario filesystem has no `/var/log`. Switched the test to `/tmp`, which the scenario defines.

### Tests

* **Session/Shell Routing & Isolation:** Added a session-ownership boundary test (an `SNXSession` exposes no scenario, acting-user, `current_directory`, `history`, or `environment` fields), runtime tests covering `session_id` reuse across two scenarios preserving both shells and their independent interaction state, per-shell snapshot generation for a multi-scenario session, and shell-isolation tests (independent cwd, history, environment, pending input, and task progress per shell in one session).

---

## [0.4.5] - 2026-08-27

### Added

* **Full-Screen Pager (`less`):** New `less [-N] FILE` command providing a full-screen file viewer with buffered navigation. Supports Space/f (next page), b (previous page), j/k or ArrowDown/ArrowUp (single-line scroll), g/G (top/bottom), numeric `<N>G` line jumps, and regex search (`/pattern`, `n` next match, `N` previous match). `-N` prepends width-padded right-aligned line numbers. Unknown keys are silently ignored; `q` quits. Piped input (`echo x | less`) dumps stdin without entering pager mode.
* **Forward-Only Pager (`more`):** New `more FILE` command mirroring classic forward-only paging: Space/f advance a page, j scrolls one line, backward navigation (`b`, `k`) writes `more: cannot go backward` to stderr while staying open, and unsupported operations (`g`, `G`, `/`) write `more: unsupported operation`. Rejects all options. Matches POSIX auto-exit semantics: an advance that reaches (or passes) the end of file — including Space/Enter pressed while already showing the last page — terminates the pager automatically and returns to the shell prompt.
* **`PagerState` Session Model:** New dataclass in `simnux.commands.models` encapsulating the complete pager viewport state — buffered content, filename, scroll position, viewport height (24 lines), and search bookkeeping (`search_pattern`, `search_positions`, `search_index`). Provides clamped position mutation (`advance`/`rewind`/`jump_top`/`jump_bottom`), forward/backward regex search with wrap-around indexing, and viewport projection helpers (`current_page()`, `at_bottom()`, `percent_shown()`).
* **Generic Suspension Slot:** `SNXSession` gains a single generic `pending_state: Any | None` field for any command that suspends mid-execution. Pager commands store their `PagerState` here on suspend and clear it (together with `awaiting_input`/`pending_command`) on exit — no pager-specific attributes leak into the session model.
* **`TerminalAction.PAGER`:** New action type value (4) signalling the frontend that the response carries a full-screen pager overlay instead of streamed terminal output.
* **Pager Program Discriminator & Status Projection:** `PagerState` records its owning program (`program: "less" | "more"`). The API projects a preformatted `pager_status` field for `more` — the POSIX `--More--(NN%)` indicator computed via `percent_shown()` — while `less` leaves it absent so the frontend composes its interactive `filename lines X-Y/Z (END)` status bar requiring `q` to quit. `renderPager()` prefers the backend-provided string when present.
* **Dynamic Terminal Viewport:** `CommandRequest` gains an optional `viewport_height` field (1–200 lines) reported by the frontend on every execution and pager-resume turn. It flows through `SNXShell.execute()`/`execute_resume()` into a new generic `CommandContext.viewport_height` field. Pager commands initialize `PagerState.viewport` from it (fallback: 24) and re-clamp the scroll position against fresh geometry before slicing each resume turn, so resizing the browser window immediately reshapes the pager view.
* **`MAX_PAGER_FILE_SIZE` Read Limit:** New `MAX_PAGER_FILE_SIZE` constant (1MB) in `simnux.commands.models` guarding file-reading commands (`less`, `cat`, `head`, `tail`, `grep`, `diff`). Files exceeding the cap are rejected with an explicit stderr error (`<cmd>: <file>: file too large (max 1MB)`) before any content is processed, preventing oversized files from being buffered into memory or handed to the frontend. `cat` additionally returns a proper "not found" error when a node has no content.
* **Configurable Backend URL & CORS Policy:** The frontend's `BACKEND_URL` is now read at runtime from `window.SIMNUX_CONFIG` (populated by a `config.js` script loaded from `index.html`) instead of being hardcoded, so a single build can target any backend. The backend no longer hardcodes its CORS allow-list to localhost; it now reads the comma-separated `ALLOWED_ORIGINS` environment variable (defaulting to the local dev origins) at startup. This decouples the backend and frontend endpoint addresses from the codebase, letting each be deployed and pointed independently.
* **API Rate Limiting:** The backend now applies per-client-IP request rate limiting (30 requests/minute by default) via `slowapi`. Added `ProxyHeadersMiddleware` (trusting Fly's proxy headers) so client IPs resolve correctly behind a reverse proxy, and a `slowapi` runtime dependency. Because client-side paging no longer issues per-keystroke `POST /execute_command` calls, interactive paging preserves rate-limit headroom for real command execution.

### Changed

* **Pager HTTP Contract Projection:** `/execute_command` projects suspended `PagerState` onto `ShellResponse` via optional fields — `pager_lines` (current viewport slice), `pager_position`, `pager_total`, `pager_eof`, `pager_filename`. Projection only occurs when `session.pending_state` is a `PagerState`; scenario evaluation is suppressed during active paging so keystrokes cannot accidentally trigger objective evaluation.
* **Resume Path History Isolation:** `SNXShell._resume_impl()` skips `add_history` when `session.pending_state` is set, keeping pager keystrokes (Space, j/k, `/pattern`) out of command history.
* **Frontend Dumb-Terminal Pager Protocol:** The frontend maps keys to minimal resume payloads — Space/f → `""`, b → `"b"`, Up/Down → `"k"`/`"j"`, g/G/n/N/q/Q/Escape pass through, and `/` opens a native prompt whose input resumes as `"/<pattern>"`. Responses with `action_type == 4` swap in a full-screen pager view with a sticky status bar (`filename lines X-Y/Z (END)` / percentage); any non-pager response exits the overlay and restores normal terminal flow. Keystrokes are captured globally while the pager is active; click-to-focus is suppressed.
* **Frontend Viewport Measurement:** Every `/execute_command` payload now carries a dynamically computed `viewport_height` — terminal line capacity derived from the outer `.terminal-container` height (falling back to `window.innerHeight`) divided by the computed line height, minus chrome padding (minimum 5 lines). Applies uniformly to normal command execution and pager keystroke resumes; calculation steps are traced via `console.debug("[SIMNUX]", ...)`. While a pager is active, prompt lines are hidden and restored on exit so only the pager view is visible.
* **Client-Side `less` Pager Protocol:** `less` was refactored from the suspended, backend-buffered pager into a client-side (non-suspended) viewer. On execution it returns the full file once through new `is_pager`/`pager_content` response fields; the frontend stores the lines locally and performs all navigation (Space/f page-forward, b page-back, j/k line scroll, g/G top/bottom, `/pattern` search, q quit) with zero further backend round trips. Piped input (`echo x | less`) still dumps stdin without entering pager mode. This replaces the per-keystroke resume flow for `less` described above, and keeps pager traffic out of the request rate limiter. `more` retains its suspended, backend-driven paging behavior.
* **Scenario & Session Route Paths:** Public route prefixes were normalized — `GET /scenarios` (was `/api/scenarios`) and resumed sessions at `GET /api/sessions/{session_id}` (was `/sessions/{session_id}`).
* **Removed Debug Router:** Deleted the `simnux.api.routes.debug` module (and its `/debug/runtime` raw runtime introspection endpoint), leaving only the stable public API surface exposed.

### Fixed

* **Local Pager Key Bleed:** Turning off the client-side `less` pager with `q`/`Q`/`Escape` (and other intercepted pager keys) no longer leaks the keystroke into the terminal's input buffer. All captured pager keys are `preventDefault()`ed (with the input buffer cleared on exit), so quitting a file never leaves a stray character queued for the next command.

---

## [0.4.2] - 2026-08-24

### Added

* **Dynamic Package Versioning:** Added dynamic version resolution (`setuptools.dynamic`) tied directly to `simnux.__version__`.
* **New Mission Scenario:** Added "Mission 1" scenario to demonstrate state-driven VFS completion triggers and victory handling.

### Changed

* **Scenario Reorganization:** Extracted test/demo shell scripts from the "Hello SIMNUX" scenario into a dedicated scenario ("SIMNUX Tests").
* **MOTD ASCII Alignment:** Applied YAML literal block scalar explicit indentation (`|2`) across scenario MOTDs to preserve ASCII art margins cleanly.

### Fixed

* **Auto-versioning for FastAPI App & Health Endpoint:** OpenAPI schema metadata and system status routes now dynamically consume `__version__` instead of relying on hardcoded strings.
* **Terminal Prompt Line Spacing:** Added explicit newline padding after stdout stream flushes in the frontend terminal renderer (`main.js`).

---

## [0.4.1] - 2026-07-27

### Added

* **POSIX History Expansion Engine:** Introduced `CommandHistory` class in `simnux/scripting/history.py` supporting bash-style history tokens: `!!` (repeat last command), `!n` (1-indexed history number), `!-n` (relative past command), and `!string` (most recent command starting with prefix). Expansions are performed before command tokenization. Expands multiple tokens per line and writes the expanded command to stdout before execution (POSIX behavior).
* **Frontend Arrow-Key History Navigation:** Client-side command history with `ArrowUp`/`ArrowDown` key support. Non-empty commands are recorded on submission; navigating past the end clears the input. History is session-scoped and resets on page reload.
* **Frontend Global Terminal Focus Capture:** Clicking anywhere inside the `.terminal-container` focuses the active prompt input, unless text is actively selected.
* **Frontend Word Wrapping:** Terminal output lines now use `white-space: pre-wrap; word-break: break-all;` to wrap long lines cleanly without clipping.
* **Frontend Contenteditable Input:** Active prompt input is now a `<span contenteditable="true">` instead of `<textarea>`. Typed and pasted text flows inline after the prompt and wraps natively to column 0 on line 2, matching submitted command appearance identically. Includes `moveCaretToEnd()` helper for history navigation.

### Changed

* **`SNXShell` History Expansion Integration:** `SNXShell._execute_impl()` now runs POSIX history expansion before parsing. Expanded commands are echoed to stdout before dispatch. Invalid expansion tokens (e.g. `!!` with empty history) return a clean `ValueError` error message via stderr.
* **`CommandHistory` Constructor:** Accepts a reference to the session's `history` list directly, avoiding duplication. The class is stateless beyond the shared list reference.
* **Terminal Prompt Line Layout:** Prompt, active input, and submitted command all share the same block layout (`display: block; white-space: pre-wrap; word-break: break-all`). The prompt, active contenteditable input, and submitted command text are all inline elements. This ensures wrapped lines always return to column 0, whether the user is typing or viewing a submitted command. Active input uses `caret-color: #d1d1d1` for visible cursor.
* **Ruff Lint Compliance:** Addressed remaining Ruff rules across backend and tests — `B007` (unused loop variable in `vfs.py`), `SIM103` (boolean simplification in `evaluator.py`), `SIM108` (ternary assignments in `history.py`), `SIM102` (compound guard statements in `runner.py`), `F841` (dead variable removal in `evaluator.py` and `parser.py`), `B904` (explicit exception chaining in `parser.py`). Suppressed `SIM113` in `_execute_while` manual iteration counter.
* **Formatting Pass:** Ran `ruff format` across all backend and test files. Adjusted `pyproject.toml` per-file ignores for `E402` module-level imports in test fixtures.

### Fixed

* **Legacy Objective Fail Trigger:** Fixed `_legacy_objective_to_trigger` in `evaluator.py` where `fail_trigger` was incorrectly returning `action: "win_scenario"` and ignoring `fail_msg`. Now correctly returns `action: "fail_scenario"` with the failure message.

### Tests

* **History Expansion Tests:** Added 25 tests in `tests/unit/test_history.py` across 7 classes:
  * `TestHistoryBangBang` — `!!` repeats the most recent command; empty history raises.
  * `TestHistoryBangN` — `!n` index lookup with 1-based numbering; out-of-range raises.
  * `TestHistoryBangMinusN` — `!-n` relative indexing from end of history.
  * `TestHistoryBangString` — `!prefix` finds most recent matching command.
  * `TestHistoryNoExpansion` — commands without `!` pass through unchanged.
  * `TestHistoryMultiExpansion` — multiple tokens in a single line expand correctly.
  * `TestHistoryEdgeCases` — suffix expansion, bare `!`, read-only `entries` view.

---

## [0.4.0] - 2026-07-24

### Added

* **Resource Limits Configuration:** Introduced `config/limits.yaml` with a typed `LimitsConfig` Pydantic model (`simnux.init.config`). Covers VFS byte caps (`max_file_bytes`, `max_total_bytes`) and script execution bounds (`max_loop_iterations`, `max_execution_time_seconds`, `max_lines`). Missing file or partial YAML falls back to safe defaults. `config/limits.yaml` is git-ignored; `config/limits.yaml.example` ships with the repo.
* **VFS Byte Caps:** `SNXFileSystem` now enforces `max_file_bytes` (per-file) and `max_total_bytes` (session-wide) during `write()` and `append()`. Exceeding either limit returns `DISK_QUOTA_EXCEEDED`. A value of `0` disables the corresponding check.
* **Logical Operators (`&&`, `||`):** Shell supports `&&` (AND) and `||` (OR) with short-circuit evaluation — `&&` executes the next segment only if the previous succeeded; `||` executes only if the previous failed. Both operators compose with pipelines and redirections. Implemented in `ShellParser.parse_logical()` and `SNXShell._execute_logical()`.
* **`test` / `[` Command:** POSIX conditional expression evaluator supporting file tests (`-f`, `-d`, `-e`), string tests (`-z`, `-n`, `=`, `!=`), integer comparisons (`-eq`, `-ne`, `-gt`, `-ge`, `-lt`, `-le`), and negation (`!`). Registered as `[` with `test` as alias; bracket invocation enforces trailing `]` requirement. Uses `_invoked_name` for dispatch-time alias detection.
* **`CommandRegistry.register()` Alias Support:** Commands with `aliases` list are automatically registered under each alias name, enabling dispatch by alternate names (e.g. `test` → `[`).
* **Scripting Module (`simnux/scripting/runner.py`):** Dedicated `ScriptRunner` class encapsulates VFS script resolution and line-by-line execution. `CommandDispatcher` now delegates all script handling to `ScriptRunner`, keeping the dispatcher focused on command routing and stream wiring.
* **`while` / `for` Loop Syntax in Scripts:** `ScriptRunner` supports POSIX-style `while COND; do ... done` and `for VAR in WORDS; do ... done` constructs. Condition evaluation reuses the existing command registry (e.g. `[ -f file ]`). Loop variables are stored in `session.environment` and accessible via `$VAR`.
* **Script Variable Expansion:** `ScriptRunner` expands `$var`, `${var}`, and `$((expr))` in command arguments, conditions, and pipeline segments. Variables are resolved from `session.environment` at dispatch time.
* **Script Variable Assignment:** Lines matching `VAR=VALUE` are handled as variable assignments inside script bodies and loops. The value is expanded for `$((expr))` and `$var` references before storage.
* **Arithmetic Expansion:** `$((expr))` is evaluated with support for `+`, `-`, `*`, `/`, `%`, parentheses, and variable references. Bare identifiers in arithmetic contexts are resolved from the environment. Division by zero returns 0.
* **Script Execution Bounds:** Script line count (`max_lines`), loop iteration count (`max_loop_iterations`), and wall-clock time (`max_execution_time_seconds`) are enforced in `ScriptRunner.execute()`. Exceeding any bound writes a diagnostic to stderr and returns `ExitCode.ERROR`.
* **Script Exception Handling:** Unhandled exceptions in `_execute_body`, `_eval_condition`, and `_execute_while` are now caught and written to stderr as clean error messages instead of propagating as "Internal runtime error".
* **`DISK_QUOTA_EXCEEDED` Error Constant:** Added to `CommandError` enum for VFS byte-cap violations.
* **`read` Standard Command:** Implemented POSIX-style `read` for interactive input — supports `-p "<prompt>"` for prompt output, stores input into a named shell variable (or `REPLY` by default) via `session.environment`. Returns `ExitCode.ERROR` on unexpected EOF.
* **`sh` / `bash` Standard Commands:** Added `sh.py` (and `bash` alias) for explicit script invocation via `sh <path>` mirroring POSIX semantics.
* **`CommandContext.dispatcher` Reference:** Added an optional `dispatcher` field to `CommandContext` so registered commands can delegate script execution back to the dispatcher.
* **Scenario Objective Evaluation Engine:** Introduced `scenarios/evaluator.py` with `evaluate()` supporting three objective types: `file_state`, `command_output`, and `flag_input`. Evaluates scenario completion against live VFS state and command output after every `/execute_command` call.
* **Command Output Gating:** The evaluator now strictly gates ``command_output`` checks — the objective only runs when the user's command matches the objective's ``target_command``. Arbitrary commands like ``ls`` or ``cat validate.sh`` no longer prematurely trigger WIN.
* **`ScenarioLoader.list_available()`:** New classmethod returns sorted list of valid scenario directory names from `scenarios/<name>/scenario.yaml`.
* **`GET /api/scenarios` Endpoint:** Exposes `list_available()` over HTTP so the frontend can dynamically enumerate scenario choices.
* **`ScenarioNotFoundError`:** Dedicated exception subclassing `FileNotFoundError` for missing scenario directories.
* **`win_message` Contract Default:** The loader now applies a default `win_message` (`"Scenario objective completed successfully!"`) when the objective has no explicit message.
* **`file_state` `exists` Condition:** The evaluator now supports an `exists` boolean in `file_state` conditions — `exists: false` fires only when the target file is absent, enabling tamper-detection triggers (e.g. key file deletion).
* **`DELETE /sessions/{id}` Endpoint:** Idempotent session destruction endpoint for the frontend to clean up stale sessions when switching scenarios, preventing runtime session leaks.
* **`echo` Command Flags (`-n`, `-e`, `-E`):** POSIX-style `echo` now supports `-n` (suppress trailing newline), `-e` (interpret backslash escapes: `\n`, `\t`, `\\`, `\0nnn`, `\xHH`, `\uHHHH`, `\UHHHHHHHH`), and `-E` (disable escape interpretation). Flags are parsed before positional arguments; non-flag tokens end flag parsing. Default behavior now includes a trailing newline.
* **Limits Propagation Chain:** `LimitsConfig` is now threaded end-to-end: `SNXRuntime` accepts `limits`, passes `vfs_limits` to `SNXFileSystem` and `limits` to `SNXShell`, which passes it through `CommandDispatcher` to `ScriptRunner`. All resource limits originate from a single `config/limits.yaml` load at startup.
* **`FileStreamWriter.last_error`:** After `close()`, the writer captures any VFS rejection message (e.g. `DISK_QUOTA_EXCEEDED`) in a public `last_error: str | None` attribute. All six dispatch points — `ScriptRunner.execute()`, `_execute_body()`, `_execute_logical_line()`, `_dispatch_pipeline()`, `CommandDispatcher.dispatch()`, and `CommandDispatcher.dispatch_pipeline()` — check this attribute and write the error message to stderr before setting `ExitCode.ERROR`.
* **Script-Level Logical Operators:** `ScriptRunner` handles `&&` and `||` operators within script bodies via its own `_execute_logical_line()` method, using `ShellParser.parse_logical()`. This complements the existing `SNXShell._execute_logical()` for interactive shell usage.
* **`_KEYWORDS` Shell Keyword Skip Set:** Stray shell keywords (`done`, `fi`, `then`, `else`, `elif`, `do`, `in`) at the top level of script execution are silently skipped instead of triggering "command not found" errors.
* **`_collect_do_done()` Nested Block Tracking:** Loop body collection tracks `do`/`done` nesting depth and detects inline `for/while ... ; do` on a single line via regex, enabling correct parsing of single-line loop constructs.

### Changed

* **Frontend Terminal Rendering for `awaiting_input`:** When `read` suspends for interactive input, the prompt text (e.g. `"Input: "`) and the input cursor now render inline on the same line instead of as separate DOM elements, and `renderInputOnly` attaches the `<input>` directly to the last terminal-line div. User input echo appears on the same line as the prompt; normal prompt resumes on the next line once `awaiting_input` clears.
* **Script Execution Refactored:** Script resolution (`_resolve_script`) and line-by-line execution (`execute_script`) extracted from `CommandDispatcher` into `ScriptRunner` (`simnux/scripting/runner.py`). `CommandDispatcher` retains thin delegation wrappers for backward compatibility with `sh`/`bash` commands.
* **Frontend Session Cleanup:** When switching scenario URLs, the frontend now calls `DELETE /sessions/{id}` to destroy the stale backend session before creating a new one, preventing abandoned session accumulation in runtime memory.
* **Scenario Directory Restructure:** Scenario YAML files moved from `backend/src/simnux/scenarios/<name>/scenario.yml` to `scenarios/<name>/scenario.yaml` at the project root — decoupling scenario assets from Python package layout.
* **Unified `TerminalAction` State Enum:** Extracted all terminal side-effect signals into a single `TerminalAction` enum (`runtime/models.py`) — `NONE` (0), `CLEAR_SCREEN` (1), `WIN` (2), `FAIL` (3). Replaces the previous `clear_screen: bool`, `completed: bool` / `completion_message: str` fields in both `CommandResult` and `ShellResponse` with `action_type: int` and `action_message: str | None`.
* **Dispatcher Action Propagation:** `CommandResult.action_type` is now set from `command.action_type` (gated on `SUCCESS` exit code) instead of computing a boolean `clear_screen`. Pipeline dispatch mirrors the same pattern.
* **`clear` Command Refactored:** `clear.py` sets `action_type = TerminalAction.CLEAR_SCREEN` instead of `clear_screen = True`.
* **Evaluator Returns `TerminalAction`:** `evaluate()` now returns `(TerminalAction, message)` instead of `(bool, str | None)`. Objective keys renamed: `completion_message` → `win_message` (with backward-compatible fallback), added `fail_message`. Default `win_message` is `"Scenario objective completed successfully!"`.
* **Frontend Response Handling:** `main.js` now reads `data.action_type` / `data.action_message` for clear-screen, win, and fail signals instead of the legacy `clear_screen` boolean.
* **Dispatcher Error Handling:** Dispatching an unregistered command now returns a `CommandResult` with exit code `ERROR` (1) instead of raising `ValueError`. This enables script-path fallback without breaking the pipeline.
* **Shell Pre-validation:** Commands containing `/` or starting with `~` are no longer eagerly rejected as "command not found" — the dispatcher resolves them as potential script paths at dispatch time.
* **Scenario Loader Refactored:** `ScenarioLoader.load()` now resolves scenarios from `scenarios/<name>/scenario.yaml` relative to the project root. Raises `ScenarioNotFoundError` (subclass of `FileNotFoundError`) on miss. Provides sensible defaults: `username` → `"user"`, `hostname` → `"simnux"`, `starting_dir` → `"/home/user"`.
* **Invalid Session Resume Returns 404:** `GET /start?session_id=<unknown>` now returns HTTP 404 instead of silently creating a new session.
* **Unknown Scenario Returns 404:** `GET /start?scenario_name=<unknown>` returns HTTP 404 instead of a 500 stack trace.
* **Frontend Session Expiry Recovery:** The frontend boot sequence now handles 404 from the start endpoint — it logs a warning, clears the stale `session_id` from `localStorage`, and automatically re-issues `GET /start` without a session parameter to bootstrap a fresh session.
* **Frontend Scenario Deep-Linking:** The frontend boot sequence now parses `window.location.pathname` to extract a scenario name. When a scenario is specified in the URL, resume is attempted first; if the resumed session belongs to a different scenario, the stale session is discarded and a fresh session is created for the URL-specified scenario via `GET /start?scenario_name=<name>`. Root path (`/`) defaults to `scenario_name=hello`.
* **SPA-Aware Dev Server:** Replaced bare `python -m http.server` with `frontend/server.py` — a custom handler that serves `index.html` for any path that doesn't correspond to an existing file, enabling scenario deep-links (e.g. `/my_scenario`) to work without a router.
* **POSIX `ls` Dotfile Filtering:** `ls` now filters out names starting with `.` by default. Added `-a`/`--all` (include `.`, `..`, and hidden files) and `-A`/`--almost-all` (include hidden files but omit `.` and `..`). Output is guaranteed sorted alphabetically.
* **MOTD Loading from VFS:** Removed the top-level `motd` field from the scenario YAML schema and `SNXScenario` model. The welcome banner is now read directly from `/etc/motd` in the session's virtual filesystem at boot time, falling back to empty string if the file does not exist. Scenario YAML files now place the welcome message inside `filesystem["/etc/motd"]` instead of a standalone `motd:` key.
* **`SNXFileSystem` Constructor Accepts `vfs_limits`:** `SNXFileSystem.__init__` now accepts a `vfs_limits: VfsLimits | None` parameter for centralized limits configuration. The previous `max_file_bytes` / `max_total_bytes` integer kwargs are retained for backward compatibility.
* **`CommandDispatcher` Accepts `limits`:** `CommandDispatcher.__init__` now takes a `limits: LimitsConfig` parameter and passes it to `ScriptRunner`, completing the limits propagation chain from runtime to script execution.
* **`test_cmd.py` Renamed to `condition.py`:** The production `[`/`test` command class moved from `test_cmd.py` to `condition.py` to prevent pytest from collecting it as a test module. A `pytest_configure` hook suppresses the resulting `PytestCollectionWarning`.

### Fixed

* **`file_state` `exists: false` Never Fired:** The evaluator previously returned `False` for any missing file regardless of the `exists` field, so `exists: false` tamper-detection triggers could never activate. Now correctly returns `True` when the file is absent.
* **Scenario Session Leak:** Switching scenarios in the frontend previously created new backend sessions without destroying the old one, causing `SNXRuntime.shells` to grow unboundedly. Now cleaned up via explicit `DELETE` on scenario switch.
* **Scenario File Not Found:** `ScenarioLoader.load()` now raises `FileNotFoundError` when the scenario YAML does not exist, which is caught by the API layer and mapped to a proper HTTP 404 response.
* **ScriptRunner `_invoked_name` Missing in Script Context:** `ScriptRunner` was not setting `command._invoked_name = cmd_name` before executing commands, causing `[` to always fail inside scripts (bracket invocation was never detected, so `]` wasn't stripped). Fixed in all three execution paths: `execute()`, `_execute_logical_line()`, and `_dispatch_pipeline()`.
* **`test` / `[` Prefix Negation:** The `[ ! -f file ]` form with a single sub-expression was failing because negation was only handled when it preceded the entire expression. Added prefix negation recursion so `!` at `args[0]` correctly inverts the result of the remaining arguments.
* **`load_limits_config()` Path Resolution:** The config loader walked 4 `.parent` calls from `config.py` but needed 5 to reach the project root, causing it to resolve to `backend/` instead. `config/limits.yaml` was never found; safe defaults were always used. Fixed to 5 `.parent` calls.
* **`_collect_do_done()` Inline `do` Detection:** Single-line loop constructs like `for i in 1 2 3; do echo $i; done` were not detected because `_collect_do_done()` only matched bare `do` tokens. Fixed with regex `r";\s*do\s*$"` to handle `for/while ... ; do` on a single line.
* **`_execute_body()` Rewrite:** The loop body executor was rewritten from recursive line advancement to index-based `while idx < len(body):` iteration with explicit `_next_line_idx` advancement, fixing several loop progression bugs.
* **`_execute_logical_line()` Stream Close:** `cmd_stdout.close()` was inside the `except Exception` block, meaning `FileStreamWriter` streams were never closed on successful command execution. Moved to outside the try/except so streams are always properly flushed.
* **VFS Error Messages Written to stderr:** `FileStreamWriter.last_error` was previously only used to set the exit code silently. All six dispatch points now write the error message to stderr before setting `ExitCode.ERROR`, making VFS quota violations visible to the user.
* **`ScriptRunner.execute()` Top-Level Redirect Error Check:** Top-level stdout redirects (`> file`) in `ScriptRunner.execute()` were missing the `FileStreamWriter.last_error` check after `close()`, causing VFS write errors to be silently swallowed. Added the propagation check.

### Tests

* **Resource Limits Tests:** Added 25 tests in `tests/unit/test_resource_limits.py` across 9 classes:
  * `TestVfsFileByteLimit` — single-file byte cap enforcement in `write()` and `append()`.
  * `TestVfsTotalByteLimit` — session-wide total byte cap tracking across multiple files.
  * `TestScriptLoopIterations` — `while`/`for` loops bounded by `max_loop_iterations`.
  * `TestScriptExecutionTime` — script execution bounded by `max_execution_time_seconds`.
  * `TestScriptLineLimit` — script line count bounded by `max_lines`, including pre-execution rejection.
  * `TestInfiniteWhileLoopWithTestCmd` — verifies `while [ 1 -eq 1 ]` halts on iteration cap with the real `[` command.
  * `TestVfsQuotaBreachViaLoopAppend` — runs `for` loops appending via `>>` until `max_total_bytes` is reached; asserts `DISK_QUOTA_EXCEEDED`, original file content preserved, and byte tracking accuracy.
  * `TestLimitsConfigLoader` — `load_limits_config()` with safe defaults, partial YAML, invalid YAML, and project-root resolution.
  * `TestFileStreamWriterQuotaError` — `FileStreamWriter` captures VFS errors in `last_error`, propagates to stderr in script context.
* **Script Loop Variable Tests:** Added 32 tests in `tests/unit/test_script_loops.py` across 8 classes:
  * `TestForLoopVariableExpansion` — `$i` and `${item}` expand correctly inside for-loop bodies.
  * `TestWhileLoopVariableExpansion` — while loops with `i=1`, `i=$((i+1))`, and `$i` in conditions run to completion without internal errors.
  * `TestStandaloneAssignment` — `VAR=VALUE` and subsequent `echo $VAR` work outside loops.
  * `TestScriptErrorHandling` — unknown commands and malformed redirects produce clean POSIX errors, not "Internal runtime error".
  * `TestExpandVars` / `TestEvalArithmetic` — unit tests for `_expand_vars` and `_eval_arithmetic` helpers.
  * `TestNestedForLoop` — nested `for` loops execute inner and outer bodies correctly; unclosed inner loops don't leak into outer scope.
  * `TestKeywordsSkip` — stray shell keywords (`done`, `fi`, `then`, `do`, `in`) at top level are silently skipped.

---

## [0.3.1] - 2026-07-20

### Added

* **Command History Framework:** Added `SNXSession.history` with a deterministic 1000-entry capacity ring buffer, capturing parseable shell inputs automatically post-parse.
* **POSIX `history` Command:** Implemented `history` with right-aligned 4-digit line indexing, support for `history N`, argument validation (rejecting `0` and out-of-range bounds), and `history -c` to flush buffer state.
* **Observability Snapshot Extension:** Integrated `recent_history` and `history_count` into `ShellSnapshot` for continuous session tracking.

### Changed

* **GNU `head` Compliance:** Added multi-file banner headers (`==> filename <==`), stream hyphen (`-`) operand handling, and safe async stream exhaustion to prevent unconsumed pipe locks.
* **GNU `tail` Compliance:** Aligned `tail` to `head` standards, including multi-file banners, newline section spacing, zero-line slice safety, and stream caching for multiple standard input (`-`) operations.
* **GNU `diff` Compliance:** Re-mapped exit codes (0 = identical, 1 = differences, 2 = error) and implemented cached `stdin` buffering for double-stdin comparisons (`diff - -`).
* **ANSI Engine Refactoring:** Compressed `commands/ansi.py` SGR escape sequence generators using PEP 562 module-level `__getattr__`.

---

## [0.3.0] - 2026-07-07

### Added

* **Declarative Parameter Parser:** Introduced framework-level `argument_parser.py` supporting flags, positional arguments, and shorthand expansion hooks (`normalize_args`).
* **Backend ANSI escape Engine (`commands/ansi.py`):** Added SGR colorization utilities for terminal rendering.
* **Safe Frontend DOM Parser:** Implemented an ANSI state-machine on the client to parse raw escape sequences into styled DOM nodes safely without `innerHTML`.
* **Enhanced Visual Utilities:** Added date highlighting to `cal` and file-type colorization logic to `ls`.

### Fixed

* Fixed cross-browser CSS font rendering glitches, trailing character padding artifacts, and asset caching quirks.

---

## [0.2.0] - 2026-03-15

### Added

* **Stream-based Reactive Runtime:** Replaced monolithic synchronous execution with an asynchronous, event-driven process pipeline model using FastAPI and Python `asyncio`.
* **Async I/O Primitives:** Implemented non-blocking stream abstraction layers (`AsyncStreamReader` and `AsyncStreamWriter`) supporting piped commands (`|`).
* **Stateless VFS Architecture:** Introduced immutable Virtual File System (VFS) tree operations with deterministic path resolution and memory-efficient node reads.
* **Standard Command Suite:** Introduced base implementations for core shell utilities (`cat`, `ls`, `cd`, `pwd`, `echo`, `mkdir`, `rm`, `cp`, `mv`, `grep`, `clear`).

### Changed

* Refactored command dispatching mechanism to route input queues through asynchronous pipelines instead of block-and-return strings.

---

## [0.1.0] - 2026-01-10

### Added

* **Monolithic Baseline Engine:** Initial proof-of-concept release for the SIMNUX terminal engine.
* **Basic Web Console UI:** Lightweight HTML/CSS/JS frontend interface mimicking a dark-mode Unix terminal prompt.
* **In-Memory File System:** Primitive file tree dictionary mapping basic file reads and directory navigation.
* **Core Command Evaluation:** Single-pass string parser for basic command inputs.
