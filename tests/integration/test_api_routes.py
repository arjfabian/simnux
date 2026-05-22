"""Integration tests for SIMNUX FastAPI HTTP API routes.

Covers all endpoints: ``/`` (root status), ``/start`` (session creation),
``/execute_command`` (command execution), ``/sessions/{id}`` (snapshot
retrieval), and ``/debug/runtime``. Validates response schemas, HTTP
status codes, session isolation, and state persistence across commands.

All tests use the ``api_client`` fixture (httpx.AsyncClient) and are
marked with ``pytest.mark.asyncio``.
"""

import pytest
import pytest_asyncio

from tests.helpers import (
    api_stderr_text,
    api_stdout_text,
)

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
    ):
        assert field in data

    assert isinstance(data["session_id"], str)
    assert isinstance(data["stdout"], list)
    assert isinstance(data["stderr"], list)
    assert isinstance(data["prompt"], str)
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

        resume = await api_client.get(
            f"/start?session_id={session_id}"
        )

        assert resume.status_code == 200

        data = json_of(resume)

        assert data["session_id"] == session_id
        assert data["stdout"] == []

    async def test_start_invalid_session_creates_new_session(self, api_client):
        """Requesting a nonexistent session ID creates a fresh session instead."""
        resp = await api_client.get(
            "/start?session_id=nonexistent"
        )

        assert_ok_response(resp)

        data = json_of(resp)

        assert data["session_id"] != "nonexistent"
        assert len(data["stdout"]) == 1

    async def test_start_custom_scenario(self, api_client):
        """Starting with a custom ``?scenario_name=`` loads the requested scenario."""
        resp = await api_client.get(
            "/start",
            params={"scenario_name": "hello"},
        )

        assert_ok_response(resp)

        data = json_of(resp)

        assert data["scenario_name"] == "Hello SIMNUX"


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


class TestSessionEndpoint:
    """``GET /sessions/{session_id}`` — session snapshot retrieval."""

    async def test_get_session_not_found(self, api_client):
        """Requesting a nonexistent session returns HTTP 404."""
        resp = await api_client.get(
            "/sessions/nonexistent"
        )

        assert resp.status_code == 404

    async def test_get_session_returns_snapshot(self, api_client):
        """An existing session returns its snapshot with filesystem and commands."""
        sid = await create_session(api_client)

        resp = await api_client.get(
            f"/sessions/{sid}"
        )

        assert_ok_response(resp)

        data = json_of(resp)

        assert data["session_id"] == sid
        assert "filesystem" in data
        assert "loaded_commands" in data
        assert "current_path" in data
        assert data["current_path"] == "/home/user"

    async def test_sessions_are_isolated(self, api_client):
        """Files created in one session do not appear in another session's snapshot."""
        sid1 = await create_session(api_client)
        sid2 = await create_session(api_client)

        await execute(
            api_client,
            sid1,
            "touch /tmp/isolated-file",
        )

        snapshot = await api_client.get(f"/sessions/{sid2}")

        data = snapshot.json()

        assert "/tmp/isolated-file" not in data["filesystem"]


class TestDebugRuntimeEndpoint:
    """``GET /debug/runtime`` — runtime diagnostic endpoint."""

    async def test_debug_runtime(self, api_client):
        """Debug endpoint returns active sessions and session count."""
        await create_session(api_client)

        resp = await api_client.get("/debug/runtime")

        assert_ok_response(resp)

        data = json_of(resp)

        assert "active_sessions" in data
        assert "total_sessions" in data
        assert data["total_sessions"] >= 1


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