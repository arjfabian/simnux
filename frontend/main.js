// =============================================================================
// SIMNUX Frontend - main.js
// Now supports session_id for multi-user environments
// =============================================================================

document.addEventListener("DOMContentLoaded", () => {
  const terminalOutput = document.getElementById("terminal-output");
  const backendUrl = "http://127.0.0.1:8000";
  
  let currentInput = null;
  window.SimnuxCurrentPath = "/";
  window.SimnuxSessionId = localStorage.getItem("simnux_session");

  // Helper to add text (support optional colors)
  const addLine = (text, color = "inherit") => {
    const line = document.createElement("pre");
    line.textContent = text;
    line.style.color = color;
    terminalOutput.appendChild(line);
    terminalOutput.scrollTop = terminalOutput.scrollHeight;
  };

  const addNewPrompt = (path = window.SimnuxCurrentPath) => {
    if (currentInput) currentInput.remove();

    const container = document.createElement("div");
    container.className = "input-line";
    container.innerHTML = `
      <span class="prompt">user@simnux:${path}$</span>
      <input type="text" class="terminal-input" spellcheck="false" autocomplete="off">
    `;

    terminalOutput.appendChild(container);
    currentInput = container.querySelector("input");
    currentInput.focus();
    currentInput.addEventListener("keydown", handleCommand);
  };

  async function handleCommand(e) {
    if (e.key !== "Enter") return;

    const cmd = currentInput.value.trim();
    const parent = currentInput.parentNode;
    
    // 1. "Freeze" the command on screen
    currentInput.remove();
    const cmdDisplay = document.createElement("span");
    cmdDisplay.textContent = cmd;
    parent.appendChild(cmdDisplay);

    if (!cmd) return addNewPrompt();
    if (cmd === "clear") {
      terminalOutput.innerHTML = "";
      return addNewPrompt();
    }

    try {
      // 2. Dialog with the Backend
      const res = await fetch(`${backendUrl}/execute_command`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ 
            command: cmd, 
            session_id: window.SimnuxSessionId 
        })
      });
      
      const data = await res.json();
      
      // 3. Process Output and Pointer
      if (data.output) addLine(data.output);
      window.SimnuxCurrentPath = data.current_path;

      // 4. Process Scenario Flags (Backend decides if the user won a scenario)
      if (data.status) {
        const { tasks_completed, tasks_total, scenario_solved } = data.status;
        
        if (scenario_solved) {
          addLine("\n[ OK ] SCENARIO COMPLETE.");
          addLine("Great job! Thanks for using SIMNUX.\n");
        } else if (tasks_total > 0) {
          // Optional: show current progress
          console.log(`Progreso: ${tasks_completed}/${tasks_total}`);
        }
      }

    } catch (err) {
      addLine("Error: Lost connection to the SIMNUX backend.");
    }
    
    addLine("\n");
    addNewPrompt();
  }

  // Initialization (scenario load)
  (async function init() {
    addLine("Launching SIMNUX...");
    try {
      const url = window.SimnuxSessionId 
        ? `${backendUrl}/initialize?session_id=${window.SimnuxSessionId}` 
        : `${backendUrl}/initialize`;
      
      const res = await fetch(url);
      const data = await res.json();

      window.SimnuxSessionId = data.session_id;
      localStorage.setItem("simnux_session", data.session_id);
      window.SimnuxCurrentPath = data.scenario_default_path;

      terminalOutput.innerHTML = "";
      addLine(`SIMNUX v1.0.0 - Scenario: ${data.scenario_name}\n`);
      addNewPrompt();
    } catch (e) {
      addLine("❌ FATAL: Kernel Panic. Backend is not responding.");
    }
  })();

  document.addEventListener("click", () => currentInput?.focus());
  // --- PROCESS START ---
  initializeTerminal();
});
