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
  // Rendering (NO logic, only display)
  // ─────────────────────────────────────────────
  const addLine = (text = "", color = "inherit") => {
    const line = document.createElement("div");
    line.className = "terminal-line";
    line.style.color = color;

    line.textContent = text;
    terminalOutput.appendChild(line);

    terminalOutput.scrollTop = terminalOutput.scrollHeight;
  };

  const addLines = (lines = [], color = "inherit") => {
    lines.forEach(line => addLine(line, color));
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
      if (data.stderr?.length) addLines(data.stderr);
      // if (data.stdout?.length) {
      //   data.stdout.forEach(line => addLine(line));
      //   addLine("");
      // }

      // if (data.stderr?.length) {
      //   data.stderr.forEach(line => addLine(line, "#ff5555"));
      //   addLine("");
      // }

      renderPrompt(data);
    } catch (err) {
      addLine("Kernel connection lost.", "#ff5555");
      addLine(String(err), "#ff5555");
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
      addLine("FATAL: backend unreachable.", "#ff5555");
    }
  }

  init();
});