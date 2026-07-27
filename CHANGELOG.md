# Changelog

All notable changes to the SIMNUX terminal simulator project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/), and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [0.4.1] - 2026.07.27

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
