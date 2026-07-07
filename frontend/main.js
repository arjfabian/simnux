const BACKEND_URL = "http://127.0.0.1:8000";

document.addEventListener("DOMContentLoaded", () => {
  const terminalOutput = document.getElementById("terminal-output");
  let currentInput = null;

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
    addLine("");
  };

  const clearTerminal = () => {
    terminalOutput.innerHTML = "";
  };

  // ─────────────────────────────────────────────
  // Prompt rendering (fully backend-driven)
  // ─────────────────────────────────────────────
  const renderPrompt = (data) => {
    if (currentInput) currentInput.remove();
    if (!data?.prompt) return;

    const container = document.createElement("div");
    container.className = "input-line";

    container.innerHTML = `
      <span class="prompt">${data.prompt}</span>
      <input type="text" class="terminal-input" spellcheck="false" autocomplete="off" />
    `;

    terminalOutput.appendChild(container);

    currentInput = container.querySelector("input");
    currentInput.focus();

    currentInput.addEventListener("keydown", (e) => {
      if (e.key === "Enter") handleCommand();
    });
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
    const cmd = currentInput.value;

    // Render what user typed (like a real terminal)
    const parent = currentInput.parentNode;
    currentInput.remove();

    const echo = document.createElement("span");
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
      if (data.clear_screen) clearTerminal();

      if (data.stdout?.length) addLines(data.stdout);

      if (data.stderr?.length) {
        const hasAnsi = data.stderr.some(l => l.includes("\x1b"));
        addLines(data.stderr, hasAnsi ? null : "ansi-red");
      }

      renderPrompt(data);
    } catch (err) {
      addLine("Kernel connection lost.", "ansi-red");
      addLine(String(err), "ansi-red");
    }
  }

  // ─────────────────────────────────────────────
  // Boot sequence (ONLY session init, no logic)
  // ─────────────────────────────────────────────
  async function init() {
    try {
      const storedId = getSessionId();

      const url = storedId
        ? `${BACKEND_URL}/start?session_id=${storedId}`
        : `${BACKEND_URL}/start`;
    
      const res = await fetch(url);
      const data = await res.json();

      setSessionId(data.session_id);

      clearTerminal();

      if (data.stdout?.length) addLines(data.stdout);

      renderPrompt(data);
    } catch (e) {
      addLine("FATAL: backend unreachable.", "ansi-red");
    }
  }

  init();
});