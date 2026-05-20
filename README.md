# 🐧 SIMNUX

A lightweight Linux-like environment simulator built around a controlled virtual runtime instead of real system processes.

---

## Overview

SIMNUX is a backend-driven shell simulation designed to reproduce the *feel* and behavioral logic of a UNIX-like environment without relying on containers, virtual machines, or direct operating system access.

The project does **not** aim to replace Linux, emulate a full kernel, or provide binary compatibility. Instead, it focuses on recreating a coherent command-line experience through a controlled virtual filesystem, stateful sessions, and modular command execution.

At its core, SIMNUX is a simulation engine — not a terminal skin over a real machine.

---

## Design Goals

* Provide a realistic shell-like experience.
* Keep the runtime deterministic and fully controlled.
* Avoid infrastructure overhead such as Docker or VMs.
* Separate frontend rendering from backend logic.
* Make commands modular and easy to extend.
* Enable scenario-based environments for training and experimentation.

---

## Architecture

SIMNUX is built around a few core concepts:

### Virtual Filesystem (VFS)

The filesystem is fully virtual and exists entirely in memory.

It uses a layered model:

* **Base Layer** → immutable scenario state.
* **Delta Layer** → session-specific modifications.

This allows users to interact with files and directories naturally while preserving isolation between sessions.

---

### Stateful Shell Sessions

Each connected client receives an isolated shell session identified by a UUID.

The backend maintains:

* current working directory,
* filesystem state,
* loaded commands,
* session context.

The frontend acts only as a renderer for terminal output.

---

### Modular Commands

Commands are implemented as independent Python classes.

Each command interacts with the environment exclusively through controlled filesystem and session primitives, which keeps the runtime predictable and easier to secure.

Current MVP commands include:

* `ls`
* `cd`
* `pwd`
* `cat`
* `touch`
* `echo`

---

## What SIMNUX Is *Not*

SIMNUX intentionally avoids becoming:

* a Linux distribution,
* a container platform,
* a process emulator,
* a browser-based SSH client,
* or a full POSIX implementation.

Many Linux behaviors are simplified by design.

The goal is consistency and controllability, not complete system fidelity.

---

## Current Status

SIMNUX is currently in MVP stage.

Implemented features include:

* Stateful shell runtime
* Virtual layered filesystem
* Session persistence
* Path resolution (`~`, `.`, `..`)
* Command registry and dynamic loading
* Browser-based terminal frontend
* In-memory isolated sessions

---

## Tech Stack

### Backend

* Python
* FastAPI

### Frontend

* Vanilla JavaScript
* HTML/CSS

---

## Local Development

### Requirements

* Python 3.10+
* Node.js

### Run

```bash
python dev.py
```

By default:

* Backend → `http://localhost:8000`
* Frontend → `http://localhost:8001`

---

## Philosophy

SIMNUX is built around a simple idea:

> emulate behavior, not infrastructure.

Instead of executing real system commands inside isolated environments, the runtime reproduces shell semantics through controlled internal logic.

This keeps the environment lightweight, deterministic, and easier to reason about while still preserving a familiar command-line experience.

---

## License

MIT License.
