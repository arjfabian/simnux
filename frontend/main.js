const BACKEND_URL = "http://127.0.0.1:8000";

document.addEventListener("DOMContentLoaded", () => {
  const terminalOutput = document.getElementById("terminal-output");
  const terminalContainer = document.querySelector(".terminal-container");
  let currentInput = null;

  // ─────────────────────────────────────────────
  // Client-side command history
  // ─────────────────────────────────────────────
  const commandHistory = [];
  let historyIndex = 0;

  // ─────────────────────────────────────────────
  // Global terminal focus capture
  // ─────────────────────────────────────────────
  terminalContainer.addEventListener("click", (e) => {
    if (currentInput && !window.getSelection().toString()) {
      currentInput.focus();
    }
  });

  // ─────────────────────────────────────────────
  // Session
  // ─────────────────────────────────────────────
  const getSessionId = () => localStorage.getItem("session_id");
  const setSessionId = (id) => {
    if (id) localStorage.setItem("session_id", id);
  };

  // ─────────────────────────────────────────────
  // ANSI escape parser (SGR only, safe DOM)
  // ─────────────────────────────────────────────
  const ANSI_CLASSES = {
    "1": "ansi-bold", "2": "ansi-dim", "3": "ansi-italic",
    "4": "ansi-underline", "7": "ansi-reverse",
    "30": "ansi-black", "31": "ansi-red", "32": "ansi-green",
    "33": "ansi-yellow", "34": "ansi-blue", "35": "ansi-magenta",
    "36": "ansi-cyan", "37": "ansi-white",
    "90": "ansi-bright-black", "91": "ansi-bright-red",
    "92": "ansi-bright-green", "93": "ansi-bright-yellow",
    "94": "ansi-bright-blue", "95": "ansi-bright-magenta",
    "96": "ansi-bright-cyan", "97": "ansi-bright-white",
  };

  function parseANSI(text) {
    const fragment = document.createDocumentFragment();
    const re = /\x1b\[([0-9;]*)m/g;
    let last = 0, classes = [], m;

    while ((m = re.exec(text)) !== null) {
      if (m.index > last) {
        const node = document.createTextNode(text.slice(last, m.index));
        if (classes.length) {
          const span = document.createElement("span");
          span.className = classes.join(" ");
          span.appendChild(node);
          fragment.appendChild(span);
        } else {
          fragment.appendChild(node);
        }
      }
      const codes = (m[1] || "0").split(";");
      for (const c of codes) {
        if (c === "0" || c === "") { classes = []; }
        else if (ANSI_CLASSES[c]) { classes.push(ANSI_CLASSES[c]); }
      }
      last = re.lastIndex;
    }

    if (last < text.length) {
      const node = document.createTextNode(text.slice(last));
      if (classes.length) {
        const span = document.createElement("span");
        span.className = classes.join(" ");
        span.appendChild(node);
        fragment.appendChild(span);
      } else {
        fragment.appendChild(node);
      }
    }

    return fragment;
  }

  // ─────────────────────────────────────────────
  // Rendering (NO logic, only display)
  // ─────────────────────────────────────────────
  const addLine = (text = "", extraClass = null) => {
    const line = document.createElement("div");
    line.className = "terminal-line";
    if (extraClass) line.classList.add(extraClass);

    if (text.includes("\x1b")) {
      line.appendChild(parseANSI(text));
    } else {
      line.textContent = text;
    }
    terminalOutput.appendChild(line);

    terminalOutput.scrollTop = terminalOutput.scrollHeight;
  };

  const addLines = (lines = [], extraClass = null) => {
    lines.forEach(line => addLine(line, extraClass));
  };

  const clearTerminal = () => {
    terminalOutput.innerHTML = "";
  };

  // ─────────────────────────────────────────────
  // Contenteditable input helpers
  // ─────────────────────────────────────────────
  function moveCaretToEnd(el) {
    const range = document.createRange();
    const sel = window.getSelection();
    range.selectNodeContents(el);
    range.collapse(false);
    sel.removeAllRanges();
    sel.addRange(range);
  }

  function setInputText(el, text) {
    el.textContent = text;
    moveCaretToEnd(el);
  }

  function attachInputHandlers(el) {
    el.addEventListener("keydown", (e) => {
      if (e.key === "Enter") {
        e.preventDefault();
        handleCommand();
      } else if (e.key === "ArrowUp") {
        e.preventDefault();
        if (historyIndex > 0) {
          historyIndex--;
          setInputText(el, commandHistory[historyIndex]);
        }
      } else if (e.key === "ArrowDown") {
        e.preventDefault();
        if (historyIndex < commandHistory.length - 1) {
          historyIndex++;
          setInputText(el, commandHistory[historyIndex]);
        } else {
          historyIndex = commandHistory.length;
          setInputText(el, "");
        }
      }
    });
  }

  // ─────────────────────────────────────────────
  // Prompt rendering (fully backend-driven)
  // ─────────────────────────────────────────────
  const renderPrompt = (data) => {
    if (currentInput) currentInput.remove();
    if (!data?.prompt) return;

    const container = document.createElement("div");
    container.className = "input-line";

    const prompt = document.createElement("span");
    prompt.className = "prompt";
    prompt.textContent = data.prompt;

    const input = document.createElement("span");
    input.className = "terminal-input";
    input.contentEditable = "true";
    input.spellcheck = false;

    container.appendChild(prompt);
    container.appendChild(input);
    terminalOutput.appendChild(container);

    currentInput = input;
    currentInput.focus();
    moveCaretToEnd(currentInput);
    attachInputHandlers(input);
  };

  // ─────────────────────────────────────────────
  // Input-only rendering (for awaiting_input)
  // ─────────────────────────────────────────────
  const renderInputOnly = () => {
    if (currentInput) currentInput.remove();

    const lines = terminalOutput.querySelectorAll(".terminal-line");
    const lastLine = lines.length > 0 ? lines[lines.length - 1] : null;

    const input = document.createElement("span");
    input.className = "terminal-input";
    input.contentEditable = "true";
    input.spellcheck = false;

    if (lastLine && lastLine.textContent.length > 0) {
      lastLine.appendChild(input);
      lastLine.classList.add("input-line");
    } else {
      const container = document.createElement("div");
      container.className = "input-line";
      container.appendChild(input);
      terminalOutput.appendChild(container);
    }

    currentInput = input;
    currentInput.focus();
    moveCaretToEnd(currentInput);
    attachInputHandlers(input);
  };

  // ─────────────────────────────────────────────
  // Backend communication (RAW TTY stream model)
  // ─────────────────────────────────────────────
  async function sendToBackend(payload) {
    const res = await fetch(`${BACKEND_URL}/execute_command`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });

    if (!res.ok) {
      throw new Error(`Backend error: ${res.status}`);
    }

    return await res.json();
  }

  async function handleCommand() {
    const cmd = currentInput.textContent;

    // Record command in client-side history
    if (cmd.trim()) {
      commandHistory.push(cmd);
    }
    historyIndex = commandHistory.length;

    // Render what user typed (like a real terminal)
    const parent = currentInput.parentNode;
    currentInput.remove();
    parent.className = "terminal-line command-line";

    const echo = document.createElement("span");
    echo.className = "command-text";
    echo.textContent = cmd;
    parent.appendChild(echo);

    try {
      const data = await sendToBackend({
        command: cmd,
        session_id: getSessionId(),
      });

      setSessionId(data.session_id);

      // ─────────────────────────────────────────────
      // Parse stdout/stderr from the response
      // ─────────────────────────────────────────────
      if (data.action_type === 1) clearTerminal();

      if (data.stdout?.length) addLines(data.stdout);

      if (data.stderr?.length) {
        const hasAnsi = data.stderr.some(l => l.includes("\x1b"));
        addLines(data.stderr, hasAnsi ? null : "ansi-red");
      }

      if (data.action_type === 2 && data.action_message) {
        addLine(data.action_message, "ansi-green");
      }
      if (data.action_type === 3 && data.action_message) {
        addLine(data.action_message, "ansi-red");
      }


      // ── Interactive input bridge ──────────────────────────────
      if (data.awaiting_input) {
        renderInputOnly();
      } else {
        // Add line at the end of the command output and before the new prompt
        addLine("");
        renderPrompt(data);
      }
    } catch (err) {
      addLine("Kernel connection lost.", "ansi-red");
      addLine(String(err), "ansi-red");
    }
  }

  // ─────────────────────────────────────────────
  // Boot sequence (ONLY session init, no logic)
  // ─────────────────────────────────────────────
  function scenarioFromPath() {
    const path = window.location.pathname.replace(/\/+$/, "");
    if (!path || path === "" || path.startsWith("/assets/")) return null;
    return path.replace(/^\//, "");
  }

  async function startFetch(params) {
    const qs = new URLSearchParams(params).toString();
    const res = await fetch(`${BACKEND_URL}/start?${qs}`);
    if (!res.ok && res.status === 404) return null;
    if (!res.ok) throw new Error(`Backend error: ${res.status}`);
    return res.json();
  }

  async function destroySession(id) {
    if (!id) return;
    try {
      await fetch(`${BACKEND_URL}/sessions/${id}`, { method: "DELETE" });
    } catch (_) { /* best-effort */ }
  }

  async function init() {
    try {
      const scenarioFromUrl = scenarioFromPath();
      const storedId = getSessionId();

      let data = null;

      if (scenarioFromUrl) {
        // ── Scenario deep-link (e.g. /shadow_key) ──
        if (storedId) {
          data = await startFetch({ session_id: storedId });
          if (data && data.scenario_name !== scenarioFromUrl) {
            await destroySession(storedId);
            data = null;
          }
        }
        if (!data) {
          localStorage.removeItem("session_id");
          data = await startFetch({ scenario_name: scenarioFromUrl });
        }
      } else {
        // ── Root path (/) ──
        if (storedId) {
          data = await startFetch({ session_id: storedId });
        }
        if (!data) {
          localStorage.removeItem("session_id");
          data = await startFetch({ scenario_name: "hello" });
        }
      }

      if (!data) {
        throw new Error("Backend error: 404");
      }

      setSessionId(data.session_id);

      clearTerminal();

      if (data.stdout?.length) {
        addLines(data.stdout);
        addLine("");
      }

      renderPrompt(data);
    } catch (e) {
      addLine("FATAL: backend unreachable.", "ansi-red");
    }
  }

  init();
});