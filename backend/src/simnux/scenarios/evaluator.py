"""Objective evaluation engine for scenario completion detection.

Evaluates scenario completion objectives defined in scenario YAML
against live session state after command execution.
"""

from __future__ import annotations

import asyncio

from simnux.commands.dispatcher import CommandDispatcher
from simnux.commands.models import CommandContext
from simnux.commands.streams import QueueStreamWriter
from simnux.filesystem.vfs import SNXFileSystem
from simnux.runtime.models import TerminalAction
from simnux.sessions.runtime import SNXSession


# ── Trigger action mapping ──────────────────────────────────────────────

_TRIGGER_ACTION_MAP: dict[str, TerminalAction] = {
    "win_scenario": TerminalAction.WIN,
    "fail_scenario": TerminalAction.FAIL,
}


# ── Public API ──────────────────────────────────────────────────────────


async def evaluate(
    session: SNXSession,
    filesystem: SNXFileSystem,
    dispatcher: CommandDispatcher | None,
    *,
    executed_command: str | None = None,
) -> tuple[TerminalAction, str | None]:
    """Evaluate the session's triggers (or legacy objective) against state.

    When *executed_command* is provided (raw user input), ``command_output``
    conditions only run their check if the command matches the condition's
    ``target``.

    Returns ``(action_type, action_message)``.  Returns ``(NONE, None)``
    if the scenario has no triggers / objective or is already complete.
    """
    if session.tasks_completed > 0:
        return TerminalAction.NONE, None

    triggers = _collect_triggers(session.scenario)
    if not triggers:
        return TerminalAction.NONE, None

    for trigger in triggers:
        passed = await _evaluate_condition(
            trigger["condition"],
            session,
            filesystem,
            dispatcher,
            executed_command=executed_command,
        )
        if passed:
            action = _TRIGGER_ACTION_MAP.get(trigger.get("action", ""))
            if action is not None:
                return action, trigger.get("message")

    return TerminalAction.NONE, None


# ── Trigger collection (new triggers[] + legacy objective compat) ───────


def _collect_triggers(scenario) -> list[dict]:
    """Return the list of trigger dicts from the scenario.

    Supports the new ``triggers`` list and falls back to the legacy
    ``objective`` dict for backward compatibility.
    """
    triggers = getattr(scenario, "triggers", None)
    if triggers:
        return triggers

    obj = scenario.objective
    if obj:
        legacy_triggers = obj.get("triggers")
        if legacy_triggers:
            return legacy_triggers
        return [_legacy_objective_to_trigger(obj)]

    return []


def _legacy_objective_to_trigger(obj: dict) -> dict:
    """Convert a legacy single ``objective`` dict to a trigger entry."""
    ttype = obj.get("type", "")

    condition: dict = {"type": ttype}
    if ttype == "file_state":
        condition["path"] = obj.get("path")
        if "exists" in obj:
            condition["exists"] = obj["exists"]
        if "contains" in obj:
            condition["contains"] = obj["contains"]
        if "exact_match" in obj:
            condition["exact_match"] = obj["exact_match"]
    elif ttype == "command_output":
        condition["target"] = obj.get("target_command")
        for key in ("stdout_contains", "expected_output", "contains", "expected_exit_code"):
            if key in obj:
                condition[key] = obj[key]
    elif ttype == "flag_input":
        if "flag" in obj:
            condition["flag"] = obj["flag"]

    win_msg = (
        obj.get("win_message")
        or obj.get("completion_message")
        or "Scenario objective completed successfully!"
    )
    fail_msg = obj.get("fail_message") or "Scenario objective failed!"

    if obj.get("fail_trigger"):
        return {
            "condition": condition,
            "action": "fail_scenario",
            "message": fail_msg,
        }

    return {
        "condition": condition,
        "action": "win_scenario",
        "message": win_msg,
    }


# ── Condition evaluation ────────────────────────────────────────────────


async def _evaluate_condition(
    condition: dict,
    session: SNXSession,
    filesystem: SNXFileSystem,
    dispatcher: CommandDispatcher | None,
    *,
    executed_command: str | None = None,
) -> bool:
    """Evaluate a single trigger condition.  Handles all condition types."""
    ctype = condition.get("type", "")

    if ctype == "file_state":
        return _check_file_state(condition, filesystem)
    elif ctype == "command_output":
        return await _check_command_output(
            condition, session, filesystem, dispatcher, executed_command=executed_command
        )
    elif ctype == "flag_input":
        return _check_flag_input(condition, session)

    return False


def _check_file_state(
    condition: dict,
    filesystem: SNXFileSystem,
) -> bool:
    """Check whether a VFS file matches expected existence and content state.

    Supports an ``exists`` boolean in the condition:
    - ``exists: false`` — fires only when the file does **not** exist.
    - ``exists: true`` (or omitted) — fires when the file **does** exist
      and satisfies any ``contains`` / ``exact_match`` constraints.
    """
    path = condition.get("path")
    if not path:
        return False

    exists_explicit = "exists" in condition
    file_exists = filesystem.exists(path) and not filesystem.is_directory(path)

    if exists_explicit and not condition["exists"]:
        return not file_exists

    if not file_exists:
        return False

    contains = condition.get("contains")
    exact = condition.get("exact_match")

    result = filesystem.read(path)
    if result.exit_code != 0:
        return False

    content = result.node.content or ""
    if exact and content != exact:
        return False
    return not (contains and contains not in content)


async def _check_command_output(
    condition: dict,
    session: SNXSession,
    filesystem: SNXFileSystem,
    dispatcher: CommandDispatcher | None,
    *,
    executed_command: str | None = None,
) -> bool:
    """Run a check command and verify its exit code and stdout.

    Strictly gates on *executed_command* — if the user did not invoke the
    condition's ``target`` this returns ``False`` immediately.
    """
    target = condition.get("target")
    if not target or not dispatcher:
        return False

    target_normalized = target.strip()
    if executed_command is not None:
        cmd_stripped = executed_command.strip()
        if cmd_stripped != target_normalized and not cmd_stripped.startswith(
            target_normalized + " "
        ):
            return False

    expected_exit = condition.get("expected_exit_code", 0)
    stdout_contains = (
        condition.get("stdout_contains")
        or condition.get("expected_output")
        or condition.get("contains")
    )

    ctx = CommandContext(session=session, filesystem=filesystem, dispatcher=dispatcher)

    stdout_queue: asyncio.Queue[str | None] = asyncio.Queue()
    stderr_queue: asyncio.Queue[str | None] = asyncio.Queue()

    stdout_writer = QueueStreamWriter(stdout_queue)
    stderr_writer = QueueStreamWriter(stderr_queue)

    parts = target.split()
    cmd_name = parts[0]
    cmd_args = parts[1:]

    result = await dispatcher.dispatch(
        cmd_name,
        cmd_args,
        ctx,
        stdout=stdout_writer,
        stderr=stderr_writer,
    )
    stdout_writer.close()
    stderr_writer.close()

    if result.exit_code != expected_exit:
        return False

    if stdout_contains:
        stdout_lines = _drain_queue(stdout_queue)
        all_stdout = "\n".join(stdout_lines)
        if stdout_contains not in all_stdout:
            return False

    return True


def _check_flag_input(
    condition: dict,
    session: SNXSession,
) -> bool:
    """Check whether the user submitted the correct flag via ``submit``."""
    submitted = session.metadata.get("submitted_flag")
    expected = condition.get("flag")
    return submitted is not None and submitted == expected


def _drain_queue(queue: asyncio.Queue) -> list[str]:
    lines: list[str] = []
    while True:
        try:
            item = queue.get_nowait()
        except asyncio.QueueEmpty:
            break
        if item is not None:
            lines.extend(item.splitlines())
    return lines
