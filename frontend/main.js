const BACKEND_URL = "http://127.0.0.1:8000";

document.addEventListener("DOMContentLoaded", () => {
  const terminalOutput = document.getElementById("terminal-output");
  let currentInput = null; 
  let isSelecting = false;

  // --  HELPERS (Must be accesible to anyone)  --------------------------------
  const getSessionId = () => localStorage.getItem("session_id");
  const setSessionId = (id) => id && localStorage.setItem("session_id", id);

  const addLine = (text, defaultColor = "inherit") => {
    const line = document.createElement("div");
    line.className = "terminal-line";
    line.style.color = defaultColor;

    const tagMap = {
      "[[dir]]": '<span class="dir">',
      "[[/]]": '</span>',
      "[[file]]": '<span class="file">',
      "[[exec]]": '<span class="exec">',
      "[[error]]": '<span class="error-text">',
      "[[success]]": '<span class="success-text">',
    };

    let processedText = text;
    Object.keys(tagMap).forEach(tag => {
      processedText = processedText.split(tag).join(tagMap[tag]);
    });

    line.innerHTML = processedText.replace(/\n/g, '<br>');
    terminalOutput.appendChild(line);
    terminalOutput.scrollTop = terminalOutput.scrollHeight;
  };

  // --  GLOBAL FOCUS LOGIC  ---------------------------------------------------
  document.addEventListener("mousedown", () => isSelecting = false);
  document.addEventListener("mousemove", () => isSelecting = true);
  document.addEventListener("mouseup", () => {
    const selection = window.getSelection().toString();
    if (!selection && !isSelecting && currentInput) currentInput.focus();
  });

  document.addEventListener("keydown", (e) => {
    if (currentInput && document.activeElement !== currentInput) {
      if (!e.ctrlKey && !e.metaKey && e.key.length === 1) {
        currentInput.focus();
      }
    }
  });

  // --  CORE FUNCTIONS  -------------------------------------------------------
  const renderPrompt = (data) => {
    if (currentInput) currentInput.remove();
    if (!data?.prompt) return;

    const container = document.createElement("div");
    container.className = "input-line";
    container.innerHTML = `
      <span class="prompt">${data.prompt}</span>
      <input type="text" class="terminal-input" spellcheck="false" autocomplete="off">
    `;

    terminalOutput.appendChild(container);
    currentInput = container.querySelector("input");
    currentInput.focus();

    currentInput.addEventListener("keydown", (e) => {
      if (e.key === "Enter") handleCommand(e, data);
    });
  };

  async function handleCommand(e, lastData) {
    const cmd = currentInput.value.trim();
    const parent = currentInput.parentNode;
    
    currentInput.remove();
    const cmdDisplay = document.createElement("span");
    cmdDisplay.textContent = cmd;
    parent.appendChild(cmdDisplay);

    if (!cmd) { renderPrompt(lastData); return; }
    if (cmd === "clear") { terminalOutput.innerHTML = ""; renderPrompt(lastData); return; }

    try {
      const res = await fetch(`${BACKEND_URL}/execute_command`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ command: cmd, session_id: getSessionId() })
      });
      
      const newData = await res.json();
      setSessionId(newData.session_id);

      if (newData.output) addLine(newData.output);
      if (newData.error) addLine(newData.error, "#ff5555");
      if (newData.status?.scenario_solved) addLine("\n[ OK ] SCENARIO COMPLETE.\n", "#50fa7b");

      addLine("\n");
      renderPrompt(newData);
    } catch (err) {
      addLine("Error: Connection lost with SIMNUX Kernel.", "#ff5555");
      addLine("Details: " + err)
    }
  }

async function init() {
  try {
    // Try to recover the ID of the last session
    const storedId = localStorage.getItem("session_id");

    const setSessionId = (id) => {
      if (id) {
          console.log("Creating new Session with ID:", id);
          localStorage.setItem("session_id", id);
      } else {
          console.warn("Attempted to create a session with a null Session ID.");
      }
    };

    // 2. Use storedId (which can be null) for the URL
    const url = storedId 
      ? `${BACKEND_URL}/initialize?session_id=${storedId}` 
      : `${BACKEND_URL}/initialize`;
    
    const res = await fetch(url);
    const data = await res.json();

    // 3. Backend confirms the ID, or gives us a new one if it's expired
    setSessionId(data.session_id);
    
    terminalOutput.innerHTML = "";
    addLine(`SIMNUX v1.0.0 - Scenario: ${data.scenario_name}\n`);
    
    if (data.output) addLine(data.output);

    renderPrompt(data);
  } catch (e) {
    console.error("Detailed error:", e);
    addLine("❌ FATAL: Kernel Panic. Backend is not responding.", "#ff5555");
  }
}

  init();
});