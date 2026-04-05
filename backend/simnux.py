import os
import sys
import uuid

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from typing import Optional, Dict

DEFAULT_SCENARIO = "hello"

# ==============================================================================

# SYSTEM PATH SETUP  -----------------------------------------------------------

# Path setup and injection
BASE_PATH = os.path.dirname(__file__)                   # Root folder (backend/)
KERNEL_PATH = os.path.join(BASE_PATH, "kernel")                 # Kernel modules
SCENARIOS_PATH = os.path.join(BASE_PATH, "scenarios")     # Scenario definitions

# Kernel dependency injection
sys.path.insert(0, KERNEL_PATH)
from kernel import filesystem, shell
from kernel.shell import SimnuxShell
from kernel.logger import Logger

# FastAPI initialization
app = FastAPI(title="SIMNUX Kernel", version="0.2.0")
logger = Logger()

# CORS setup (for communication from port 8001)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:8001", "http://127.0.0.1:8001"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ==============================================================================

# COMMUNICATION CONTRACTS  -----------------------------------------------------

class CommandRequest(BaseModel):
    command: str
    session_id: str

class CommandResponse(BaseModel):
    output: str
    error: Optional[str] = None
    prompt: str
    session_id: str
    status: dict

# SESSION MANAGEMENT: Stores active SimnuxShell instances  ---------------------
active_sessions: Dict[str, SimnuxShell] = {}

# ==============================================================================

# ENDPOINTS  -------------------------------------------------------------------

@app.get("/")
async def root():
    # Build the list of sessions with its internal details
    sessions_detail = []
    # Get the details for each active session    
    for s_id, s_shell in active_sessions.items():
        sessions_detail.append({
            "id": str(s_id),
            "scenario_name": getattr(s_shell.scenario, 'name', "Unknown"),
            "loaded_commands": list(s_shell.commands.keys()),
            "current_path": str(s_shell.current_path)
        })
    # Return the complete list
    return {
        "status": "online",
        "kernel": "SIMNUX v0.0.1",
        "active_sessions": sessions_detail
    }

@app.get("/initialize")
async def initialize(session_id: Optional[str]=None, scenario: str=DEFAULT_SCENARIO):
    """
    Loads a scenario and returns the first prompt.
    """
    if not session_id or session_id not in active_sessions:
        logger.add(f"Session ID {session_id} not found or invalid. Initializing.")
        new_id = str(uuid.uuid4())
        scenario_path = os.path.join(os.getcwd(), "scenarios", scenario)
        logger.add(f"Loading scenario {scenario_path}...")
        shell = SimnuxShell(
            session_id=new_id,
            scenario_path=scenario_path,
            logger=logger)
        active_sessions[new_id] = shell
        session_id = new_id
        logger.add(f"Scenario initialized successfully for ID {current_id}.")
    else:
        shell = active_sessions[session_id]

    # 2. Get the MOTD (this returns the prompt and the session_id)
    response = shell.get_motd()
    response["scenario_name"] = shell.scenario.name
    response["session_id"] = current_id
    
    logger.add(f"Session {current_id} initialized.")
    return response

@app.post("/execute_command", response_model=CommandResponse)
async def execute(request: CommandRequest):
    """
    The execution pipeline: Input -> Shell -> Commndos -> Output
    """
    if request.session_id not in active_sessions:
        raise HTTPException(status_code = 440, detail = "Kernel Session Expired")

    shell = active_sessions[request.session_id]
    
    # The Shell processes the raw command and returns a structured response
    result = shell.dispatch(request.command)
    
    return CommandResponse(
        output = result["output"],
        error = result.get("error"),
        prompt = shell.get_prompt(),
        session_id = request.session_id,
        status = shell.get_status()
    )

@app.get("/inspect_vfs")
async def inspect_vfs(session_id: str):
    if session_id not in active_sessions:
        return {"error": "Session not found"}
    
    shell = active_sessions[session_id]
    return {
        "session_id": session_id,
        "current_path": shell.current_path,
        "deltas": shell.vfs.deltas,
        "base_keys": list(shell.vfs.base_state.keys())
    }

@app.on_event("shutdown")
def cleanup():
    active_sessions.clear()