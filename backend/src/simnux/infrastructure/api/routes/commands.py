"""Command execution endpoint for SIMNUX.

Bridges HTTP requests to the internal shell runtime.
This layer is intentionally thin to keep protocol logic separate from execution
logic.
"""

import asyncio

from fastapi import APIRouter
from fastapi import HTTPException
from fastapi import Request

from simnux.core.commands.models import PagerState
from simnux.core.commands.streams import QueueStreamReader
from simnux.core.runtime.models import TerminalAction
from simnux.core.scenarios.evaluator import evaluate
from simnux.infrastructure.api.models.contracts import CommandRequest
from simnux.infrastructure.api.models.contracts import ShellResponse


router = APIRouter()


@router.post("/execute_command", response_model=ShellResponse)
async def execute(
    payload: CommandRequest,
    request: Request,
) -> ShellResponse:
    """Dispatch raw shell input to the session's target shell runtime.

    When the shell is ``awaiting_input`` the user's text is fed as stdin to
    the suspended command rather than being parsed as a new command.
    """

    runtime = request.app.state.runtime

    session = runtime.get_session(payload.session_id)
    if session is None or not session.shells:
        raise HTTPException(
            status_code=404,
            detail="Session not found",
        )

    shell = session.get_shell(payload.scenario_name) if payload.scenario_name else None
    if shell is None:
        shell = session.active_shells[0]

    # ── Interactive input resume ─────────────────────────────────────
    if shell.awaiting_input and shell.pending_command:
        stdin_queue: asyncio.Queue = asyncio.Queue()
        stdin_queue.put_nowait(payload.command + "\n")
        stdin_queue.put_nowait(None)
        resume_stdin = QueueStreamReader(stdin_queue)

        result = await shell.execute_resume(
            shell.pending_command,
            resume_stdin,
            viewport_height=payload.viewport_height,
        )
    else:
        result = await shell.execute(
            payload.command,
            viewport_height=payload.viewport_height,
        )

    action_type = result.action_type
    action_message: str | None = None

    pager_active = isinstance(shell.pending_state, PagerState)

    if action_type == TerminalAction.NONE and not pager_active:
        try:
            eval_action, eval_message = await evaluate(
                shell,
                shell.filesystem,
                shell.dispatcher,
                executed_command=payload.command,
            )
            if eval_action in (TerminalAction.WIN, TerminalAction.FAIL):
                action_type = eval_action
                action_message = eval_message
                if eval_action == TerminalAction.WIN:
                    shell.tasks_completed = 1
        except Exception:
            pass
    else:
        action_message = None

    # ── Pager projection ─────────────────────────────────────────────
    pager_fields: dict = {}
    if result.pager_payload is not None:
        # Non-suspended client-side pager (``less``): hand the full lines to
        # the frontend so it pages locally without further roundtrips.
        pager_fields = {
            "is_pager": True,
            "pager_content": result.pager_payload.get("lines") or [],
            "pager_filename": result.pager_payload.get("filename"),
        }
    elif isinstance(shell.pending_state, PagerState):
        # Legacy suspended pager (``more``): project the live viewport.
        ps = shell.pending_state
        pager_fields = {
            "pager_lines": ps.current_page(),
            "pager_position": ps.position,
            "pager_total": ps.total,
            "pager_eof": ps.at_bottom(),
            "pager_filename": ps.filename,
        }
        if ps.program == "more":
            # POSIX indicator: --More--(NN%)
            pager_fields["pager_status"] = f"--More--({ps.percent_shown()}%)"

    return ShellResponse(
        session_id=payload.session_id,
        scenario_name=shell.scenario.name,
        scenario_identifier=shell.identifier,
        stdout=result.stdout,
        stderr=result.stderr,
        prompt="" if shell.awaiting_input else shell.render_prompt(),
        action_type=action_type,
        action_message=action_message,
        awaiting_input=shell.awaiting_input,
        **pager_fields,
        status="ok",
    )
