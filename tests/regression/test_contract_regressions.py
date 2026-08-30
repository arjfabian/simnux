"""Regression tests for API and model contracts.

Ensures that ShellResponse and CommandResult maintain their expected
field types and structural invariants (e.g., stdout is always a list).
"""

from simnux.core.runtime.models import CommandResult


class TestRegressionResponseContracts:
    """ShellResponse and CommandResult structural contract validation.

    Ensures response objects maintain correct field types (list, str, None)
    and default values, preventing API contract breakage.
    """

    def test_execute_response_has_all_fields(self):
        """ShellResponse initializes with all expected fields and default values."""
        from simnux.infrastructure.api.models.contracts import ShellResponse

        resp = ShellResponse(session_id="test")
        assert resp.session_id == "test"
        assert resp.stdout == []
        assert resp.stderr == []
        assert resp.prompt == ""
        assert resp.status == "ok"

    def test_command_result_defaults(self):
        """CommandResult defaults to empty lists for stdout/stderr."""
        from simnux.core.runtime.models import ExitCode

        r = CommandResult()
        assert isinstance(r.stdout, list)
        assert r.stdout == []
        assert isinstance(r.stderr, list)
        assert r.stderr == []
        assert r.exit_code == ExitCode.SUCCESS

    def test_command_result_list_stdout(self):
        """CommandResult accepts list[str] for stdout."""
        r = CommandResult(stdout=["line1", "line2"])
        assert isinstance(r.stdout, list)
        assert r.stdout == ["line1", "line2"]

    def test_command_result_empty_list_default(self):
        """CommandResult omitting fields uses empty list defaults."""
        r = CommandResult()
        assert r.stdout == []
        assert r.stderr == []
