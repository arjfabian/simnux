"""Tests for the scenario objective evaluator.

Covers ``file_state``, ``command_output``, and ``flag_input`` objective
types, including failure cases.
"""

import pytest

from simnux.core.commands.dispatcher import CommandDispatcher
from simnux.core.runtime.models import TerminalAction
from simnux.core.scenarios.evaluator import _check_file_state
from simnux.core.scenarios.evaluator import _check_flag_input
from simnux.core.scenarios.evaluator import evaluate
from simnux.core.scenarios.models import SNXScenario
from simnux.security.groups.models import SNXGroup
from simnux.security.users.models import SNXUser
from tests.helpers import _ROOT_EXEC


_ROOT_USER = SNXUser(0, "root")


pytestmark = pytest.mark.asyncio


def _make_scenario(objective: dict) -> SNXScenario:
    return SNXScenario(
        name="Test",
        difficulty="Easy",
        hostname="simnux",
        users={
            "root": SNXUser(0, "root"),
            "user": SNXUser(1001, "user"),
        },
        groups={
            "root": SNXGroup(0, "root"),
            "user": SNXGroup(1001, "user"),
        },
        starting_dir="/home/user",
        filesystem={},
        objective=objective,
    )


class TestFileStateObjective:
    async def test_file_state_existing_file(self, session, filesystem):
        """Existing file with no content constraints passes."""
        filesystem.touch("/home/user/config.txt", execution=_ROOT_EXEC)
        filesystem.write("/home/user/config.txt", "hello world", execution=_ROOT_EXEC)
        scenario = _make_scenario(
            {
                "type": "file_state",
                "path": "/home/user/config.txt",
            }
        )
        session.scenario = scenario
        assert _check_file_state(scenario.objective, filesystem, _ROOT_EXEC)

    async def test_file_state_nonexistent_file_fails(self, session, filesystem):
        """Missing file fails file_state check."""
        scenario = _make_scenario(
            {
                "type": "file_state",
                "path": "/home/user/missing.txt",
            }
        )
        session.scenario = scenario
        assert not _check_file_state(scenario.objective, filesystem, _ROOT_EXEC)

    async def test_file_state_contains(self, session, filesystem):
        """``contains`` sub-string constraint is enforced."""
        filesystem.touch("/home/user/secret.txt", execution=_ROOT_EXEC)
        filesystem.write("/home/user/secret.txt", "FLAG{hidden}", execution=_ROOT_EXEC)
        scenario = _make_scenario(
            {
                "type": "file_state",
                "path": "/home/user/secret.txt",
                "contains": "FLAG",
            }
        )
        session.scenario = scenario
        assert _check_file_state(scenario.objective, filesystem, _ROOT_EXEC)

    async def test_file_state_contains_fails_when_missing(self, session, filesystem):
        """``contains`` check fails when sub-string is absent."""
        filesystem.touch("/home/user/secret.txt", execution=_ROOT_EXEC)
        filesystem.write("/home/user/secret.txt", "nothing here", execution=_ROOT_EXEC)
        scenario = _make_scenario(
            {
                "type": "file_state",
                "path": "/home/user/secret.txt",
                "contains": "FLAG",
            }
        )
        session.scenario = scenario
        assert not _check_file_state(scenario.objective, filesystem, _ROOT_EXEC)

    async def test_file_state_exact_match(self, session, filesystem):
        """``exact_match`` exact-content constraint is enforced."""
        filesystem.touch("/home/user/config.txt", execution=_ROOT_EXEC)
        filesystem.write("/home/user/config.txt", "foo=bar", execution=_ROOT_EXEC)
        scenario = _make_scenario(
            {
                "type": "file_state",
                "path": "/home/user/config.txt",
                "exact_match": "foo=bar",
            }
        )
        session.scenario = scenario
        assert _check_file_state(scenario.objective, filesystem, _ROOT_EXEC)

    async def test_file_state_exact_match_fails(self, session, filesystem):
        """``exact_match`` fails when content differs."""
        filesystem.touch("/home/user/config.txt", execution=_ROOT_EXEC)
        filesystem.write("/home/user/config.txt", "foo=baz", execution=_ROOT_EXEC)
        scenario = _make_scenario(
            {
                "type": "file_state",
                "path": "/home/user/config.txt",
                "exact_match": "foo=bar",
            }
        )
        session.scenario = scenario
        assert not _check_file_state(scenario.objective, filesystem, _ROOT_EXEC)

    async def test_file_state_directory_fails(self, session, filesystem):
        """A directory path fails file_state check."""
        scenario = _make_scenario(
            {
                "type": "file_state",
                "path": "/home",
            }
        )
        session.scenario = scenario
        assert not _check_file_state(scenario.objective, filesystem, _ROOT_EXEC)

    async def test_file_state_exists_false_when_missing(self, session, filesystem):
        """``exists: false`` triggers when the file does not exist."""
        scenario = _make_scenario(
            {
                "type": "file_state",
                "path": "/home/user/deleted.txt",
                "exists": False,
            }
        )
        session.scenario = scenario
        assert _check_file_state(scenario.objective, filesystem, _ROOT_EXEC)

    async def test_file_state_exists_false_when_present(self, session, filesystem):
        """``exists: false`` does NOT trigger when the file exists."""
        filesystem.touch("/home/user/deleted.txt", execution=_ROOT_EXEC)
        scenario = _make_scenario(
            {
                "type": "file_state",
                "path": "/home/user/deleted.txt",
                "exists": False,
            }
        )
        session.scenario = scenario
        assert not _check_file_state(scenario.objective, filesystem, _ROOT_EXEC)

    async def test_file_state_exists_true_when_present(self, session, filesystem):
        """``exists: true`` triggers when the file exists."""
        filesystem.touch("/home/user/flag.txt", execution=_ROOT_EXEC)
        scenario = _make_scenario(
            {
                "type": "file_state",
                "path": "/home/user/flag.txt",
                "exists": True,
            }
        )
        session.scenario = scenario
        assert _check_file_state(scenario.objective, filesystem, _ROOT_EXEC)

    async def test_file_state_exists_true_when_missing(self, session, filesystem):
        """``exists: true`` does NOT trigger when the file is absent."""
        scenario = _make_scenario(
            {
                "type": "file_state",
                "path": "/home/user/flag.txt",
                "exists": True,
            }
        )
        session.scenario = scenario
        assert not _check_file_state(scenario.objective, filesystem, _ROOT_EXEC)


class TestCommandOutputObjective:
    async def test_command_output_flag_found(self, session, filesystem, populated_registry):
        """``command_output`` detects flag when matching command is executed."""
        dispatcher = CommandDispatcher(registry=populated_registry)
        filesystem.touch("/home/user/validate.sh", execution=_ROOT_EXEC)
        filesystem.write(
            "/home/user/validate.sh",
            '#!/bin/bash\necho "FLAG{found}"\n',
            execution=_ROOT_EXEC,
        )
        scenario = _make_scenario(
            {
                "type": "command_output",
                "target_command": "bash /home/user/validate.sh",
                "expected_output": "FLAG{found}",
            }
        )
        session.scenario = scenario
        action, _ = await evaluate(
            session,
            filesystem,
            dispatcher,
            executed_command="bash /home/user/validate.sh",
        )
        assert action == TerminalAction.WIN

    async def test_command_output_not_matched(self, session, filesystem, populated_registry):
        """``command_output`` fails when output does not match."""
        dispatcher = CommandDispatcher(registry=populated_registry)
        filesystem.touch("/home/user/validate.sh", execution=_ROOT_EXEC)
        filesystem.write(
            "/home/user/validate.sh",
            '#!/bin/bash\necho "wrong output"\n',
            execution=_ROOT_EXEC,
        )
        scenario = _make_scenario(
            {
                "type": "command_output",
                "target_command": "bash /home/user/validate.sh",
                "expected_output": "FLAG{something}",
            }
        )
        session.scenario = scenario
        action, _ = await evaluate(
            session,
            filesystem,
            dispatcher,
            executed_command="bash /home/user/validate.sh",
        )
        assert action == TerminalAction.NONE

    async def test_command_output_ignores_unrelated_command(
        self, session, filesystem, populated_registry
    ):
        """``command_output`` returns NONE when an unrelated command is run."""
        dispatcher = CommandDispatcher(registry=populated_registry)
        filesystem.touch("/home/user/validate.sh", execution=_ROOT_EXEC)
        filesystem.write(
            "/home/user/validate.sh",
            '#!/bin/bash\necho "FLAG{found}"\n',
            execution=_ROOT_EXEC,
        )
        scenario = _make_scenario(
            {
                "type": "command_output",
                "target_command": "bash /home/user/validate.sh",
                "expected_output": "FLAG{found}",
            }
        )
        session.scenario = scenario
        action, _ = await evaluate(
            session,
            filesystem,
            dispatcher,
            executed_command="ls",
        )
        assert action == TerminalAction.NONE

    async def test_command_output_ignores_cat_validate(
        self, session, filesystem, populated_registry
    ):
        """``command_output`` returns NONE for ``cat validate.sh`` (not the target)."""
        dispatcher = CommandDispatcher(registry=populated_registry)
        filesystem.touch("/home/user/validate.sh", execution=_ROOT_EXEC)
        filesystem.write(
            "/home/user/validate.sh",
            '#!/bin/bash\necho "FLAG{found}"\n',
            execution=_ROOT_EXEC,
        )
        scenario = _make_scenario(
            {
                "type": "command_output",
                "target_command": "bash /home/user/validate.sh",
                "expected_output": "FLAG{found}",
            }
        )
        session.scenario = scenario
        action, _ = await evaluate(
            session,
            filesystem,
            dispatcher,
            executed_command="cat validate.sh",
        )
        assert action == TerminalAction.NONE

    async def test_command_output_gate_no_executed_command(
        self, session, filesystem, populated_registry
    ):
        """Without ``executed_command`` the gate is skipped (backward compat)."""
        dispatcher = CommandDispatcher(registry=populated_registry)
        filesystem.touch("/home/user/validate.sh", execution=_ROOT_EXEC)
        filesystem.write(
            "/home/user/validate.sh",
            '#!/bin/bash\necho "FLAG{found}"\n',
            execution=_ROOT_EXEC,
        )
        scenario = _make_scenario(
            {
                "type": "command_output",
                "target_command": "bash /home/user/validate.sh",
                "expected_output": "FLAG{found}",
            }
        )
        session.scenario = scenario
        action, _ = await evaluate(session, filesystem, dispatcher)
        assert action == TerminalAction.WIN


class TestFlagInputObjective:
    async def test_flag_input_correct(self, session):
        """Correct flag via metadata passes flag_input check."""
        scenario = _make_scenario(
            {
                "type": "flag_input",
                "flag": "s3cr3t",
            }
        )
        session.scenario = scenario
        session.metadata["submitted_flag"] = "s3cr3t"
        assert _check_flag_input(scenario.objective, session)

    async def test_flag_input_wrong(self, session):
        """Wrong flag fails flag_input check."""
        scenario = _make_scenario(
            {
                "type": "flag_input",
                "flag": "s3cr3t",
            }
        )
        session.scenario = scenario
        session.metadata["submitted_flag"] = "wrong"
        assert not _check_flag_input(scenario.objective, session)

    async def test_flag_input_not_submitted(self, session):
        """No submitted flag fails flag_input check."""
        scenario = _make_scenario(
            {
                "type": "flag_input",
                "flag": "s3cr3t",
            }
        )
        session.scenario = scenario
        assert not _check_flag_input(scenario.objective, session)


class TestEvaluateTopLevel:
    async def test_evaluate_no_objective(self, session):
        """Sessions without an objective return (NONE, None)."""
        action, msg = await evaluate(session, None, None)
        assert action == TerminalAction.NONE
        assert msg is None

    async def test_evaluate_already_completed(self, session):
        """Sessions already marked complete return (NONE, None)."""
        session.tasks_completed = 1
        scenario = _make_scenario(
            {
                "type": "file_state",
                "path": "/home/user/notes.txt",
            }
        )
        session.scenario = scenario
        action, msg = await evaluate(session, None, None)
        assert action == TerminalAction.NONE
        assert msg is None

    async def test_evaluate_unknown_type(self, session):
        """Unknown objective type returns (NONE, None)."""
        scenario = _make_scenario(
            {
                "type": "unknown_type",
            }
        )
        session.scenario = scenario
        action, msg = await evaluate(session, None, None)
        assert action == TerminalAction.NONE
        assert msg is None

    async def test_evaluate_win_message_default(self, session, filesystem):
        """Default win_message is used when objective omits it."""
        filesystem.touch("/home/user/flag.txt", execution=_ROOT_EXEC)
        filesystem.write("/home/user/flag.txt", "win", execution=_ROOT_EXEC)
        scenario = _make_scenario(
            {
                "type": "file_state",
                "path": "/home/user/flag.txt",
            }
        )
        session.scenario = scenario
        action, msg = await evaluate(session, filesystem, None)
        assert action == TerminalAction.WIN
        assert msg == "Scenario objective completed successfully!"


class TestTriggersEvaluation:
    async def test_triggers_win_file_state(self, session, filesystem):
        """``triggers`` with a matching file_state condition returns WIN."""
        filesystem.touch("/home/user/.solved", execution=_ROOT_EXEC)
        scenario = _make_scenario({})
        scenario.triggers = [
            {
                "condition": {"type": "file_state", "path": "/home/user/.solved"},
                "action": "win_scenario",
                "message": "You solved it!",
            },
        ]
        session.scenario = scenario
        action, msg = await evaluate(session, filesystem, None)
        assert action == TerminalAction.WIN
        assert msg == "You solved it!"

    async def test_triggers_fail_file_state(self, session, filesystem):
        """A failing condition with ``fail_scenario`` action returns FAIL."""
        filesystem.touch("/home/user/.bomb", execution=_ROOT_EXEC)
        scenario = _make_scenario({})
        scenario.triggers = [
            {
                "condition": {"type": "file_state", "path": "/home/user/.bomb"},
                "action": "fail_scenario",
                "message": "Game over!",
            },
        ]
        session.scenario = scenario
        action, msg = await evaluate(session, filesystem, None)
        assert action == TerminalAction.FAIL
        assert msg == "Game over!"

    async def test_triggers_first_match_wins(self, session, filesystem):
        """When multiple triggers match, the first one wins."""
        filesystem.touch("/home/user/flag.txt", execution=_ROOT_EXEC)
        scenario = _make_scenario({})
        scenario.triggers = [
            {
                "condition": {"type": "file_state", "path": "/home/user/flag.txt"},
                "action": "win_scenario",
                "message": "Winner!",
            },
            {
                "condition": {"type": "file_state", "path": "/home/user/flag.txt"},
                "action": "fail_scenario",
                "message": "Should not reach",
            },
        ]
        session.scenario = scenario
        action, msg = await evaluate(session, filesystem, None)
        assert action == TerminalAction.WIN
        assert msg == "Winner!"

    async def test_triggers_no_match_returns_none(self, session, filesystem):
        """When no trigger matches, returns (NONE, None)."""
        scenario = _make_scenario({})
        scenario.triggers = [
            {
                "condition": {"type": "file_state", "path": "/home/user/missing.txt"},
                "action": "win_scenario",
                "message": "Won't trigger",
            },
        ]
        session.scenario = scenario
        action, msg = await evaluate(session, filesystem, None)
        assert action == TerminalAction.NONE
        assert msg is None

    async def test_triggers_command_output_gated(self, session, filesystem, populated_registry):
        """``triggers`` with command_output condition gates on executed_command."""
        dispatcher = CommandDispatcher(registry=populated_registry)
        filesystem.touch("/home/user/check.sh", execution=_ROOT_EXEC)
        filesystem.write("/home/user/check.sh", '#!/bin/bash\necho "PASS"\n', execution=_ROOT_EXEC)
        scenario = _make_scenario({})
        scenario.triggers = [
            {
                "condition": {
                    "type": "command_output",
                    "target": "bash /home/user/check.sh",
                    "stdout_contains": "PASS",
                },
                "action": "win_scenario",
                "message": "Check passed!",
            },
        ]
        session.scenario = scenario
        action, msg = await evaluate(
            session,
            filesystem,
            dispatcher,
            executed_command="bash /home/user/check.sh",
        )
        assert action == TerminalAction.WIN
        assert msg == "Check passed!"

    async def test_triggers_legacy_objective_backward_compat(self, session, filesystem):
        """Legacy ``objective`` dict still triggers WIN via backward compat."""
        filesystem.touch("/home/user/flag.txt", execution=_ROOT_EXEC)
        filesystem.write("/home/user/flag.txt", "secret", execution=_ROOT_EXEC)
        scenario = _make_scenario(
            {
                "type": "file_state",
                "path": "/home/user/flag.txt",
                "win_message": "Old style works!",
            }
        )
        session.scenario = scenario
        action, msg = await evaluate(session, filesystem, None)
        assert action == TerminalAction.WIN
        assert msg == "Old style works!"

    async def test_triggers_fail_on_file_deleted(self, session, filesystem):
        """``exists: false`` trigger fires FAIL when file is absent."""
        scenario = _make_scenario({})
        scenario.triggers = [
            {
                "condition": {
                    "type": "file_state",
                    "path": "/var/log/.hidden_key",
                    "exists": False,
                },
                "action": "fail_scenario",
                "message": "Key file deleted!",
            },
        ]
        session.scenario = scenario
        action, msg = await evaluate(session, filesystem, None)
        assert action == TerminalAction.FAIL
        assert msg == "Key file deleted!"

    async def test_triggers_exists_false_no_fire_when_present(self, session, filesystem):
        """``exists: false`` trigger does NOT fire when file still exists."""
        filesystem.touch("/var/log/.hidden_key", execution=_ROOT_EXEC)
        scenario = _make_scenario({})
        scenario.triggers = [
            {
                "condition": {
                    "type": "file_state",
                    "path": "/var/log/.hidden_key",
                    "exists": False,
                },
                "action": "fail_scenario",
                "message": "Key file deleted!",
            },
        ]
        session.scenario = scenario
        action, msg = await evaluate(session, filesystem, None)
        assert action == TerminalAction.NONE
        assert msg is None
