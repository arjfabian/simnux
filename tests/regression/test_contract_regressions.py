"""Regression tests for API and model contracts.

Ensures that ShellResponse and CommandResult maintain their expected
field types and structural invariants (e.g., stdout is always a list,
None values are preserved).
"""

from simnux.runtime.models import CommandResult


class TestRegressionResponseContracts:
    """ShellResponse and CommandResult structural contract validation.

    Ensures response objects maintain correct field types (list, str, None)
    and default values, preventing API contract breakage.
    """

    def test_execute_response_has_all_fields(self):
        """ShellResponse initializes with all expected fields and default values."""
        from simnux.api.models.contracts import ShellResponse
        resp = ShellResponse(session_id="test")
        assert resp.session_id == "test"
        assert resp.stdout == []
        assert resp.stderr == []
        assert resp.prompt == ""
        assert resp.status == "ok"

    def test_shell_response_stdout_list_normalization(self):
        """ShellResponse normalizes string stdout into a list (single-element)."""
        from simnux.api.models.contracts import ShellResponse

        cmd_result = CommandResult(stdout="single line")
        resp = ShellResponse(
            session_id="s1",
            stdout=cmd_result.stdout,
            stderr=cmd_result.stderr,
            status="ok",
        )
        assert isinstance(resp.stdout, list)
        assert resp.stdout == ["single line"]

    def test_command_result_string_normalization(self):
        """CommandResult normalizes a string stdout into a list."""
        r = CommandResult(stdout="line1")
        assert isinstance(r.stdout, list)
        assert r.stdout == ["line1"]

    def test_command_result_none_stays_none(self):
        """CommandResult preserves ``None`` stdout (defensive: no false normalization)."""
        r = CommandResult(stdout=None)
        assert r.stdout is None


