"""Command execution endpoint for SIMNUX.

Bridges HTTP requests to the internal shell runtime.
This layer is intentionally thin to keep protocol logic separate from execution
logic.
"""

import asyncio

from fastapi import APIRouter
from fastapi import HTTPException
from fastapi import Request

from simnux.api.models.contracts import CommandRequest
from simnux.api.models.contracts import ShellResponse
from simnux.commands.streams import QueueStreamReader
from simnux.runtime.models import TerminalAction
from simnux.scenarios.evaluator import evaluate


router = APIRouter()


@router.post("/execute_command", response_model=ShellResponse)
async def execute(
    request: CommandRequest,
    http_request: Request,
) -> ShellResponse:
    """Dispatch raw shell input to the session-bound shell runtime.

    When the session is ``awaiting_input`` the user's text is fed as stdin
    to the suspended command rather than being parsed as a new command.
    """

    runtime = http_request.app.state.runtime

    if not runtime.exists(request.session_id):
        raise HTTPException(
            status_code=404,
            detail="Session not found",
        )

    shell = runtime.get_session(request.session_id)
    session = shell.session

    # ── Interactive input resume ─────────────────────────────────────
    if session.awaiting_input and session.pending_command:
        stdin_queue: asyncio.Queue = asyncio.Queue()
        stdin_queue.put_nowait(request.command + "\n")
        stdin_queue.put_nowait(None)
        resume_stdin = QueueStreamReader(stdin_queue)

        result = await shell.execute_resume(
            session.pending_command,
            resume_stdin,
        )
    else:
        result = await shell.execute(request.command)

    action_type = result.action_type
    action_message: str | None = None

    if action_type == TerminalAction.NONE:
        try:
            eval_action, eval_message = await evaluate(
                session,
                shell.filesystem,
                shell.dispatcher,
                executed_command=request.command,
            )
            if eval_action in (TerminalAction.WIN, TerminalAction.FAIL):
                action_type = eval_action
                action_message = eval_message
                if eval_action == TerminalAction.WIN:
                    session.tasks_completed = 1
        except Exception:
            pass
    else:
        action_message = None

    return ShellResponse(
        session_id=request.session_id,
        scenario_name=session.scenario.name,
        stdout=result.stdout,
        stderr=result.stderr,
        prompt="" if session.awaiting_input else shell.render_prompt(),
        action_type=action_type,
        action_message=action_message,
        awaiting_input=session.awaiting_input,
        status="ok",
    )
