const BACKEND_URL = window.SIMNUX_CONFIG?.BACKEND_URL;

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
  // Full-screen pager state (less / more)
  // ─────────────────────────────────────────────
  const PAGER_ACTION = 4; // TerminalAction.PAGER
  let pagerActive = false;

  // Client-side pager state (non-suspended ``less``): the full file is stored
  // locally and navigated without further backend roundtrips.
  let localPager = null; // { lines, position, filename, promptData }
  let localPagerMode = false;

  // ─────────────────────────────────────────────
  // Global terminal focus capture
  // ─────────────────────────────────────────────
  terminalContainer.addEventListener("click", (e) => {
    if (pagerActive) return;
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
  // Full-screen pager (less / more)
  // Dumb-terminal protocol: capture keys, map to payloads.
  // ─────────────────────────────────────────────
  function promptSearch() {
    return prompt("/") || "";
  }

  async function sendPagerCommand(cmd) {
    try {
      const data = await sendToBackend({
        command: cmd,
        session_id: getSessionId(),
      });
      setSessionId(data.session_id);

      if (data.action_type === PAGER_ACTION) {
        renderPager(data);
      } else {
        exitPager();
        if (data.stdout?.length) addLines(data.stdout);
        if (data.stderr?.length) {
          const hasAnsi = data.stderr.some(l => l.includes("\x1b"));
          addLines(data.stderr, hasAnsi ? null : "ansi-red");
        }
        addLine("");
        renderPrompt(data);
      }
    } catch (err) {
      exitPager();
      addLine("Kernel connection lost.", "ansi-red");
      addLine(String(err), "ansi-red");
    }
  }

  function pagerKeyHandler(e) {
    let cmd;
    switch (e.key) {
      case " ":
      case "f":
        cmd = "";
        break;
      case "b": cmd = "b"; break;
      case "j":
      case "ArrowDown":
        cmd = "j";
        break;
      case "k":
      case "ArrowUp":
        cmd = "k";
        break;
      case "g": cmd = "g"; break;
      case "G": cmd = "G"; break;
      case "n": cmd = "n"; break;
      case "N": cmd = "N"; break;
      case "q":
      case "Q":
      case "Escape":
        cmd = "q";
        break;
      case "/":
        e.preventDefault();
        cmd = "/" + promptSearch();
        break;
      default:
        return; // unmapped keys pass through untouched
    }

    console.debug("[SIMNUX] Pager key:", JSON.stringify(e.key), "->", JSON.stringify(cmd));
    e.preventDefault();
    sendPagerCommand(cmd);
  }

  function renderPager(data) {
    pagerActive = true;

    // Hide any active prompt lines while the pager owns the screen.
    if (currentInput) currentInput.blur();
    document.querySelectorAll(".input-line").forEach((el) => {
      el.style.display = "none";
    });

    terminalOutput.innerHTML = "";

    if (data.pager_lines?.length) {
      data.pager_lines.forEach(line => addLine(line.replace(/\n$/, "")));
      console.debug(
        "[SIMNUX] Pager render:",
        data.pager_filename,
        `lines ${data.pager_position + 1}-${Math.min(data.pager_position + data.pager_lines.length, data.pager_total)}/${data.pager_total}`,
      );
    } else {
      addLine("");
    }

    // Status bar — backend may send a preformatted indicator (more's
    // "--More--(N%)"); otherwise compose the interactive less-style one.
    const status = document.createElement("div");
    status.className = "pager-status";
    if (data.stderr?.length) {
      status.textContent = data.stderr[data.stderr.length - 1];
      status.classList.add("pager-error");
    } else if (data.pager_status) {
      status.textContent = data.pager_status;
    } else {
      const parts = [];
      if (data.pager_filename) parts.push(data.pager_filename);
      if (data.pager_position != null && data.pager_total != null && data.pager_total > 0) {
        const end = Math.min(data.pager_position + data.pager_lines.length, data.pager_total);
        parts.push(`lines ${data.pager_position + 1}-${end}/${data.pager_total}`);
      }
      if (data.pager_eof) parts.push("(END)");
      status.textContent = parts.join("  ");
    }
    terminalOutput.appendChild(status);

    terminalOutput.scrollTop = terminalOutput.scrollHeight;
  }

  function exitPager() {
    pagerActive = false;
    document.removeEventListener("keydown", pagerKeyHandler);

    // Restore any prompt lines hidden while the pager was active.
    document.querySelectorAll(".input-line").forEach((el) => {
      el.style.display = "";
    });
    console.debug("[SIMNUX] Pager exited");
  }

  // ─────────────────────────────────────────────
  // Client-side pager (non-suspended ``less``)
  // All navigation handled locally — no POST /execute_command roundtrips.
  // ─────────────────────────────────────────────
  function enterLocalPager(data) {
    const lines = (data.pager_content || []).map((l) => l.replace(/\n$/, ""));
    localPager = {
      lines,
      position: 0,
      filename: data.pager_filename || "",
      promptData: data,
    };
    pagerActive = true;
    localPagerMode = true;

    // Hide any active prompt lines while the pager owns the screen.
    if (currentInput) currentInput.blur();
    document.querySelectorAll(".input-line").forEach((el) => {
      el.style.display = "none";
    });

    renderLocalPager();
    document.addEventListener("keydown", localPagerKeyHandler);
    console.debug("[SIMNUX] Local pager entered:", localPager.filename, `${lines.length} lines`);
  }

  function renderLocalPager() {
    const p = localPager;
    const viewport = computeViewportHeight();
    const total = p.lines.length;
    const end = Math.min(p.position + viewport, total);

    terminalOutput.innerHTML = "";
    for (let i = p.position; i < end; i++) {
      addLine(p.lines[i]);
    }
    if (end <= p.position) addLine("");

    // Compose the interacive less-style status bar, fully client-side.
    const status = document.createElement("div");
    status.className = "pager-status";
    const parts = [];
    if (p.filename) parts.push(p.filename);
    if (total > 0) parts.push(`lines ${p.position + 1}-${end}/${total}`);
    if (p.position + viewport >= total) parts.push("(END)");
    status.textContent = parts.join("  ");
    terminalOutput.appendChild(status);

    terminalOutput.scrollTop = terminalOutput.scrollHeight;
  }

  function localPagerKeyHandler(e) {
    const p = localPager;
    if (!p) return;

    // Fully swallow every intercepted key so it can never leak into the
    // terminal input buffer (e.g. pre-filling the prompt with 'q').
    if (isPagerNavigationKey(e.key)) {
      e.preventDefault();
      e.stopPropagation();
    }

    const viewport = computeViewportHeight();

    const pageDown = () => { p.position = Math.min(p.position + viewport, Math.max(0, p.lines.length - viewport)); };
    const pageUp = () => { p.position = Math.max(0, p.position - viewport); };

    switch (e.key) {
      case "ArrowDown":
      case "j":
        p.position = Math.min(p.position + 1, Math.max(0, p.lines.length - viewport));
        renderLocalPager();
        break;
      case "ArrowUp":
      case "k":
        p.position = Math.max(0, p.position - 1);
        renderLocalPager();
        break;
      case "PageDown":
      case " ":
      case "f":
        pageDown();
        renderLocalPager();
        break;
      case "PageUp":
      case "b":
        pageUp();
        renderLocalPager();
        break;
      case "q":
      case "Q":
      case "Escape":
        exitLocalPager();
        break;
      default:
        break; // unmapped keys pass through untouched
    }
  }

  function isPagerNavigationKey(key) {
    switch (key) {
      case "ArrowDown":
      case "ArrowUp":
      case "PageDown":
      case "PageUp":
      case " ":
      case "j":
      case "k":
      case "b":
      case "f":
      case "q":
      case "Q":
      case "Escape":
        return true;
      default:
        return false;
    }
  }

  function exitLocalPager() {
    if (!pagerActive || !localPagerMode) return;
    const promptData = localPager ? localPager.promptData : null;

    // Detach the listener first so no further keystrokes are captured and the
    // freshly-restored prompt input can't be reached by lingering events.
    document.removeEventListener("keydown", localPagerKeyHandler);
    pagerActive = false;
    localPagerMode = false;
    localPager = null;

    // Remove any pager viewport/prompt remnants and restore a clean prompt.
    terminalOutput.querySelectorAll(".input-line").forEach((el) => el.remove());
    renderPrompt(promptData || { prompt: "" });

    // Defensively wipe any text that may have leaked into the fresh input
    // buffer, then put the caret at a clean empty end and refocus.
    if (currentInput) {
      setInputText(currentInput, "");
      currentInput.focus();
      moveCaretToEnd(currentInput);
    }

    console.debug("[SIMNUX] Local pager exited");
  }

  // ─────────────────────────────────────────────
  // Backend communication (RAW TTY stream model)
  // ─────────────────────────────────────────────
  function computeViewportHeight() {
    const linePixelHeight =
      parseFloat(window.getComputedStyle(terminalOutput).lineHeight) || 20;
    // Measure outer container height instead of inner output element
    const containerHeight = terminalContainer.clientHeight || window.innerHeight;
    const lines = Math.max(5, Math.floor(containerHeight / linePixelHeight) - 2);
    console.debug("[SIMNUX] Calculated viewport height:", lines, "lines (container:", containerHeight, "px)");
    return lines;
  }

  async function sendToBackend(payload) {
    payload.viewport_height = computeViewportHeight();
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

      // ── Full-screen pager entry ───────────────────────────────
      if (data.action_type === PAGER_ACTION) {
        if (data.is_pager) {
          // ``less`` client-side pager: render locally, navigate locally.
          enterLocalPager(data);
        } else {
          // ``more`` legacy suspended pager: backend-driven dumb terminal.
          renderPager(data);
          document.addEventListener("keydown", pagerKeyHandler);
        }
        return;
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
          if (data && data.scenario_identifier !== scenarioFromUrl) {
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