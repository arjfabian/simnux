# 🐧 SIMNUX: A Logic-Based Linux Environment Simulator

**A modular, stateful Python engine designed to emulate POSIX-like shell behavior without virtualized infrastructure.**

## 📌 Project Overview

SIMNUX is a technical demonstration of a **User-Mode Shell Simulator**. Unlike traditional virtualization (VMs) or containerization (Docker), SIMNUX implements a custom **Virtual File System (VFS)** and a **Command Dispatcher** to emulate a Linux environment. It is designed for lightweight Linux education, command-line proficiency training, and security scenario modeling with zero infrastructure overhead.

## 🏗️ Technical Architecture

The project is built on a decoupled, micro-kernel inspired architecture:

### 1. Virtual File System (VFS) with Layered Logic
The VFS manages a hierarchical data structure using a **Base/Delta Layering** approach:
* **Base Layer:** A read-only snapshot provided by a YAML scenario definition.
* **Delta Layer:** A read-write overlay that captures user modifications (file creation, writes, etc.) in memory, ensuring session persistence without altering the core scenario.
* **Path Resolution:** Implements POSIX-standard path traversal (relative/absolute paths, `.` and `..` resolution) using `os.path.normpath` with a symbolic chroot to prevent escape from the virtual root.

### 2. Command Pattern & Dynamic Discovery
Every shell command is implemented as a discrete Python class, inheriting from a `SimnuxCommand` abstract base class (ABC).
* **Dynamic Loading:** Commands are discovered at runtime using `importlib.util`. This allows for hot-plugging new utilities or overriding kernel commands with scenario-specific tools without restarting the backend.
* **Dependency Injection:** Each command instance receives the active `Session` object, granting controlled access to the VFS and session state.

### 3. Asynchronous Multi-Tenant Backend
Powered by **FastAPI**, the backend manages concurrent user sessions identified by UUIDs.
* **Stateless API / Stateful Session:** While the API follows REST principles, the backend maintains isolated `SimnuxShell` instances in memory, tracking current working directories and user identity.
* **Safety & Isolation:** Each command execution is wrapped in exception handling to ensure that runtime errors in a single command do not compromise the kernel or other active sessions.

## 🛠️ Tech Stack & Patterns
* **Backend:** Python 3.10+ | FastAPI | Pydantic (Schema Validation) | PyYAML.
* **Frontend:** Vanilla JavaScript (ES6+) | CSS3.
* **Patterns:** Command Pattern, Singleton (Logger), Strategy (Scenario Loading), Layered Architecture.

---

## 🚦 Roadmap & Implementation Status

### Current v0.1.0 (MVP)
* [x] **Kernel Core:** Shell orchestrator and session management.
* [x] **VFS Implementation:** Directory traversal and read-only/read-write layering.
* [x] **Logging:** Synchronous audit trail (file + console).
* [x] **Core Utils:** `pwd`, `ls`, `cd`, `cat`.

### In Development (Q2 2026)
* **Access Control (ACL):** Implementation of `UID/GID` logic and `chmod`/`chown` bitmask validation.
* **I/O Stream Redirection:** Support for standard output redirection (`>`, `>>`).
* **Pipe Subsystem:** Inter-process communication simulation using string buffers (`|`).
* **Environment Variables:** Support for `$PATH`, `$HOME`, and custom exports.

---

## 📦 Local Development

### Prerequisites
* Python 3.10 or higher.
* Node.js (for concurrent process management).

### Setup
1.  **Clone and Install:**
    ```bash
    git clone https://git.datorum.cloud/jfabian/simnux.git
    cd simnux
    npm install
    ```
2.  **Execute Environment:**
    ```bash
    npm run dev
    ```
    *The backend will be available at `http://localhost:8000` and the terminal interface at `http://localhost:8001`.*

---

## 📝 Example: Adding a Command
The system is designed for high maintainability. Adding a `whoami` command requires only a new file in `kernel/commands/`:

```python
from kernel.command import SimnuxCommand

class Command(SimnuxCommand):
    name = "whoami"
    def execute(self, args: list) -> str:
        return self.session.username
```

-----

## 📄 License

Distributed under the **MIT License**. See `LICENSE` for more information.