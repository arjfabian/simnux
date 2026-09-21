"""Integration tests for SIMNUX FastAPI HTTP API routes.

Covers all endpoints: ``/`` (root status), ``/start`` (session creation and
resume), ``/execute_command`` (command execution), and
``DELETE /sessions/{session_id}`` (session destruction). Validates response
schemas, HTTP status codes, session isolation, and state persistence across
commands.

All tests use the ``api_client`` fixture (httpx.AsyncClient) and are
marked with ``pytest.mark.asyncio``.
"""

import pytest

from tests.helpers import api_stderr_text
from tests.helpers import api_stdout_text


pytestmark = pytest.mark.asyncio


async def create_session(client) -> str:
    """Helper: start a new session and return its session_id."""
    response = await client.get("/start")
    data = response.json()
    return data["session_id"]


async def execute(client, session_id: str, command: str):
    """Helper: execute a command in the given session."""
    return await client.post(
        "/execute_command",
        json={
            "command": command,
            "session_id": session_id,
        },
    )


async def client_post_viewport(client, session_id: str, command: str, viewport_height: int):
    """Helper: execute with explicit terminal geometry (viewport_height)."""
    return await client.post(
        "/execute_command",
        json={
            "command": command,
            "session_id": session_id,
            "viewport_height": viewport_height,
        },
    )


def json_of(response) -> dict:
    """Helper: extract JSON dict from an HTTP response."""
    return response.json()


def assert_shell_response(data) -> None:
    """Assert that a response dict contains all required ShellResponse fields with correct types."""
    for field in (
        "session_id",
        "stdout",
        "stderr",
        "prompt",
        "status",
        "action_type",
    ):
        assert field in data

    assert isinstance(data["session_id"], str)
    assert isinstance(data["stdout"], list)
    assert isinstance(data["stderr"], list)
    assert isinstance(data["prompt"], str)
    assert isinstance(data["action_type"], int)
    assert data["status"] in ("ok", "error")


def assert_ok_response(response) -> None:
    """Assert that an HTTP response has status 200."""
    assert response.status_code == 200


def assert_validation_error(response) -> None:
    """Assert that an HTTP response has status 422 (validation error)."""
    assert response.status_code == 422


class TestRootEndpoint:
    """``GET /`` — root health-check endpoint."""

    async def test_root_returns_online_status(self, api_client):
        """Root endpoint returns ``status: "online"`` and runtime info."""
        resp = await api_client.get("/")

        assert_ok_response(resp)

        data = json_of(resp)

        assert data["status"] == "online"
        assert "runtime" in data
        assert "total_sessions" in data

    async def test_root_reports_zero_sessions_initially(self, api_client):
        """Fresh runtime has zero active sessions."""
        resp = await api_client.get("/")

        data = json_of(resp)

        assert data["total_sessions"] == 0


class TestStartEndpoint:
    """``GET /start`` — session creation, resume, and scenario selection."""

    async def test_start_creates_session(self, api_client):
        """Starting a new session returns a shell response with welcome motd and prompt."""
        resp = await api_client.get("/start")

        assert_ok_response(resp)

        data = json_of(resp)

        assert_shell_response(data)

        assert "session_id" in data
        assert data["scenario_name"] == "Hello SIMNUX"
        assert data["scenario_identifier"] == "hello"
        assert len(data["stdout"]) == 1
        assert "Welcome" in data["stdout"][0]
        assert data["prompt"] != ""

    async def test_start_returns_prompt(self, api_client):
        """The prompt in the start response follows the expected ``user@hostname:$ `` format."""
        resp = await api_client.get("/start")

        data = json_of(resp)

        prompt = data["prompt"]

        assert prompt.startswith("user@simnux:")
        assert prompt.endswith("$ ")

    async def test_start_resume_valid_session(self, api_client):
        """Resuming a valid session via ``?session_id=`` returns the existing session."""
        session_id = await create_session(api_client)

        resume = await api_client.get(f"/start?session_id={session_id}")

        assert resume.status_code == 200

        data = json_of(resume)

        assert data["session_id"] == session_id
        assert data["stdout"] == []
        assert data["scenario_identifier"] == "hello"

    async def test_start_invalid_session_returns_404(self, api_client):
        """Invalid session IDs return HTTP 404 instead of creating a new session."""
        resp = await api_client.get("/start?session_id=nonexistent")

        assert resp.status_code == 404

        data = json_of(resp)

        assert data["detail"] == "Session not found or expired"

    async def test_start_custom_scenario(self, api_client):
        """Starting with a custom ``?scenario_name=`` loads the requested scenario."""
        resp = await api_client.get(
            "/start",
            params={"scenario_name": "hello"},
        )

        assert_ok_response(resp)

        data = json_of(resp)

        assert data["scenario_name"] == "Hello SIMNUX"

    async def test_start_unknown_scenario_returns_404(self, api_client):
        """Requesting a nonexistent scenario returns HTTP 404."""
        resp = await api_client.get(
            "/start",
            params={"scenario_name": "nonexistent_scenario"},
        )

        assert resp.status_code == 404

        data = json_of(resp)

        assert "not found" in data["detail"]


class TestExecuteCommandEndpoint:
    """``POST /execute_command`` — command execution via HTTP."""

    async def test_execute_valid_command(self, api_client):
        """Executing a valid command (``pwd``) returns the expected output."""
        session_id = await create_session(api_client)

        resp = await execute(
            api_client,
            session_id,
            "pwd",
        )

        assert_ok_response(resp)

        data = json_of(resp)

        assert data["session_id"] == session_id
        assert "/home/user" in api_stdout_text(data)
        assert data["status"] == "ok"

    async def test_execute_with_unknown_session(self, api_client):
        """Executing a command against an unknown session returns HTTP 404."""
        resp = await execute(
            api_client,
            "invalid-session",
            "pwd",
        )

        assert resp.status_code == 404

    async def test_execute_invalid_command(self, api_client):
        """Executing an invalid command returns the error in stderr (HTTP 200, shell error)."""
        session_id = await create_session(api_client)

        resp = await execute(
            api_client,
            session_id,
            "nonexistent",
        )

        assert_ok_response(resp)

        data = json_of(resp)

        assert "command not found" in api_stderr_text(data)

        # HTTP layer succeeded; shell command failed internally.
        assert data["status"] == "ok"

    async def test_execute_mutates_fs_and_affects_prompt(self, api_client):
        """Executing ``cd`` via the API mutates the session's CWD for subsequent commands."""
        session_id = await create_session(api_client)

        await execute(
            api_client,
            session_id,
            "cd /etc",
        )

        resp = await execute(
            api_client,
            session_id,
            "pwd",
        )

        assert "/etc" in api_stdout_text(json_of(resp))

    async def test_execute_response_schema(self, api_client):
        """The execute response conforms to the ``ShellResponse`` schema."""
        session_id = await create_session(api_client)

        resp = await execute(
            api_client,
            session_id,
            "echo test",
        )

        data = json_of(resp)

        assert_shell_response(data)

    async def test_consecutive_commands_persist_state(self, api_client):
        """State (CWD) persists across consecutive API calls within the same session."""
        sid = await create_session(api_client)

        await execute(
            api_client,
            sid,
            "cd /home/user",
        )

        resp = await execute(
            api_client,
            sid,
            "pwd",
        )

        assert "/home/user" in api_stdout_text(json_of(resp))


class TestDestroySessionEndpoint:
    """``DELETE /sessions/{session_id}`` — session destruction."""

    async def test_destroy_returns_200(self, api_client):
        """Deleting an existing session returns 200 with ok status."""
        sid = await create_session(api_client)

        resp = await api_client.delete(f"/sessions/{sid}")

        assert_ok_response(resp)
        assert json_of(resp)["status"] == "ok"

    async def test_destroy_removes_session(self, api_client):
        """After deletion, the session can no longer be resumed."""
        sid = await create_session(api_client)

        await api_client.delete(f"/sessions/{sid}")

        resp = await api_client.get(f"/start?session_id={sid}")
        assert resp.status_code == 404

    async def test_destroy_is_idempotent(self, api_client):
        """Deleting a non-existent session still returns 200."""
        resp = await api_client.delete("/sessions/ghost-id")

        assert_ok_response(resp)
        assert json_of(resp)["status"] == "ok"

    async def test_destroy_does_not_affect_other_sessions(self, api_client):
        """Destroying one session leaves other sessions intact."""
        sid1 = await create_session(api_client)
        sid2 = await create_session(api_client)

        await api_client.delete(f"/sessions/{sid1}")

        resp = await api_client.get(f"/start?session_id={sid2}")
        assert resp.status_code == 200
        assert json_of(resp)["session_id"] == sid2


class TestResponseContract:
    """Response contract: execute endpoint output conforms to ShellResponse schema."""

    async def test_shell_response_contract(self, api_client):
        """``POST /execute_command`` response includes all required ShellResponse fields."""
        sid = await create_session(api_client)

        resp = await execute(
            api_client,
            sid,
            "echo hello",
        )

        assert_ok_response(resp)

        data = json_of(resp)

        assert_shell_response(data)

        assert data["session_id"]
        assert data["scenario_identifier"] == "hello"


class TestValidationErrors:
    """Input validation: Pydantic rejections for missing or blank fields."""

    async def test_execute_command_missing_session_id(self, api_client):
        """Missing ``session_id`` triggers HTTP 422 validation error."""
        resp = await api_client.post(
            "/execute_command",
            json={"command": "pwd"},
        )

        assert_validation_error(resp)

    async def test_execute_command_blank_command(self, api_client):
        """A blank command (whitespace-only) returns empty stdout/stderr (not an error)."""
        session_id = await create_session(api_client)

        resp = await execute(
            api_client,
            session_id,
            "   ",
        )

        assert_ok_response(resp)

        data = resp.json()

        assert data["stdout"] == []
        assert data["stderr"] == []

    async def test_execute_command_missing_command(self, api_client):
        """Missing ``command`` field triggers HTTP 422 validation error."""
        resp = await api_client.post(
            "/execute_command",
            json={"session_id": "abc"},
        )
        assert_validation_error(resp)


class TestPagerProjection:
    """Full-screen pager (less/more) contract projection over HTTP."""

    async def test_less_invocation_projects_client_pager(self, api_client):
        """``less`` returns action_type=4 with is_pager + full content.

        ``less`` is a client-side pager: it returns the entire file so the
        frontend can page locally; no backend suspension occurs.
        """
        session_id = await create_session(api_client)

        resp = await execute(api_client, session_id, "less lipsum.txt")
        assert_ok_response(resp)

        data = resp.json()
        assert data["action_type"] == 4
        assert data["is_pager"] is True
        assert data["awaiting_input"] is False
        # The client-side pager does not suspend the backend, so a prompt is
        # still rendered (the frontend hides it while the local pager is open).
        assert data["prompt"] != ""
        # Full file returned (not a viewport slice).
        assert len(data["pager_content"]) > 24
        assert data["pager_content"][0]
        assert data["pager_filename"] == "lipsum.txt"
        # No legacy suspended-pager projection for the client-side protocol.
        assert data["pager_lines"] is None

    async def test_less_ignores_viewport_for_content(self, api_client):
        """``less`` returns the full file regardless of viewport_height."""
        session_id = await create_session(api_client)

        resp = await client_post_viewport(
            api_client,
            session_id,
            "less /etc/motd",
            viewport_height=5,
        )
        data = resp.json()
        assert data["action_type"] == 4
        assert data["is_pager"] is True
        # All 9 lines are handed to the client, not a 5-line slice.
        assert len(data["pager_content"]) == 9
        assert data["pager_filename"] == "/etc/motd"

    async def test_less_size_limit_over_http(self, api_client):
        """``less`` rejects a file larger than MAX_PAGER_FILE_SIZE."""
        from simnux.core.commands.models import MAX_PAGER_FILE_SIZE

        session_id = await create_session(api_client)
        await execute(api_client, session_id, "touch big.txt")
        await execute(
            api_client,
            session_id,
            f"echo {'x' * (MAX_PAGER_FILE_SIZE + 1)} > big.txt",
        )

        resp = await execute(api_client, session_id, "less big.txt")
        data = resp.json()
        assert data["action_type"] == 0
        assert data["is_pager"] is False
        assert any("file too large (max 1MB)" in line for line in data["stderr"])

    async def test_more_projects_posix_status_indicator(self, api_client):
        """``more`` carries a preformatted --More--(NN%) status string."""
        session_id = await create_session(api_client)

        resp = await client_post_viewport(
            api_client,
            session_id,
            "more /etc/motd",
            viewport_height=5,
        )
        data = resp.json()
        assert data["action_type"] == 4
        # 5 of 9 lines shown -> round(5 * 100 / 9) = 56.
        assert data["pager_status"] == "--More--(56%)"

    async def test_more_auto_exits_at_eof_over_http(self, api_client):
        """Advancing past the last page returns to the normal prompt."""
        session_id = await create_session(api_client)
        await execute(api_client, session_id, "more lipsum.txt")

        # Default 24-line viewport: first Space shows lines 25-48, second
        # reaches EOF and exits automatically.
        resp = await execute(api_client, session_id, "")
        assert resp.json()["action_type"] == 4

        resp = await execute(api_client, session_id, "")
        data = resp.json()
        assert data["action_type"] == 0
        assert data["awaiting_input"] is False
        assert data["pager_lines"] is None
        assert data["prompt"] != ""

    async def test_pager_navigation_updates_projection(self, api_client):
        """Keystroke payloads resume the ``more`` pager with refreshed fields."""
        session_id = await create_session(api_client)
        await execute(api_client, session_id, "more lipsum.txt")

        # Advance: Space on a multi-page file stays in the pager and moves.
        resp = await execute(api_client, session_id, "")
        data = resp.json()
        assert data["action_type"] == 4
        assert data["pager_position"] == 24  # default 24-line viewport

        # Quit returns to normal prompt.
        resp = await execute(api_client, session_id, "q")
        data = resp.json()
        assert data["action_type"] == 0
        assert data["pager_lines"] is None

    async def test_quit_restores_normal_prompt(self, api_client):
        """After ``q`` the ``more`` pager exits back to a normal prompt."""
        session_id = await create_session(api_client)
        await execute(api_client, session_id, "more lipsum.txt")

        resp = await execute(api_client, session_id, "q")
        data = resp.json()
        assert data["action_type"] == 0
        assert data["awaiting_input"] is False
        assert data["pager_lines"] is None
        assert data["prompt"] != ""

        # Session usable normally afterwards.
        resp = await execute(api_client, session_id, "pwd")
        data = resp.json()
        assert_ok_response(resp)
        assert data["stdout"] == ["/home/user"]
