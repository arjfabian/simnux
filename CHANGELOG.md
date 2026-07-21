# Changelog

All notable changes to the SIMNUX terminal simulator project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/), and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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
