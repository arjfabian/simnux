import pytest

from simnux.commands.errors import CommandError
from simnux.runtime.models import ExitCode
from tests.helpers import assert_error
from tests.helpers import assert_success
from tests.helpers import stderr_text
from tests.helpers import stdout_text


pytestmark = pytest.mark.asyncio


class TestRmCommand:
    async def test_rm_existing_file(self, shell_with_commands):
        result = await shell_with_commands.execute("cat /home/user/notes.txt")
        assert_success(result)
        assert stdout_text(result) == "hello world"
        result = await shell_with_commands.execute("rm /home/user/notes.txt")
        assert_success(result)
        result = await shell_with_commands.execute("cat /home/user/notes.txt")
        assert CommandError.NOT_FOUND in stderr_text(result)

    async def test_rm_newly_created_file(self, shell_with_commands):
        result = await shell_with_commands.execute("touch newfile.txt")
        assert_success(result)

        result = await shell_with_commands.execute("rm newfile.txt")
        assert_success(result)

        result = await shell_with_commands.execute("cat newfile.txt")
        assert_error(result)
        assert CommandError.NOT_FOUND in stderr_text(result)

    async def test_rm_missing_operand(self, shell_with_commands):
        result = await shell_with_commands.execute("rm")
        assert result.exit_code == ExitCode.INVALID_ARGUMENT
        assert CommandError.MISSING_OPERAND in stderr_text(result)
        assert stdout_text(result) == ""

    async def test_rm_nonexistent_file(self, shell_with_commands):
        result = await shell_with_commands.execute("rm not-a-file.txt")
        assert CommandError.NOT_FOUND in stderr_text(result)

    async def test_rm_directory_without_delete_dir_flag(self, shell_with_commands):
        result = await shell_with_commands.execute("ls /home")
        assert_success(result)
        assert "user" in stdout_text(result)
        result = await shell_with_commands.execute("rm /home/user")
        assert_error(result)
        assert CommandError.IS_A_DIRECTORY in stderr_text(result)
        result = await shell_with_commands.execute("ls /home")
        assert_success(result)
        assert "user" in stdout_text(result)

    async def test_rm_empty_directory_without_recursive_flag(self, shell_with_commands):
        result = await shell_with_commands.execute("mkdir /testdir")
        assert_success(result)
        result = await shell_with_commands.execute("rm /testdir")
        assert_error(result)
        assert CommandError.IS_A_DIRECTORY in stderr_text(result)
        result = await shell_with_commands.execute("ls /")
        assert_success(result)
        assert "testdir" in stdout_text(result)

    async def test_rm_file_removes_from_directory_listing(self, shell_with_commands):
        result = await shell_with_commands.execute("touch /home/user/testfile")
        assert_success(result)
        result = await shell_with_commands.execute("ls /home/user")
        assert_success(result)
        assert "testfile" in stdout_text(result)
        result = await shell_with_commands.execute("rm /home/user/testfile")
        assert_success(result)
        result = await shell_with_commands.execute("ls /home/user")
        assert_success(result)
        assert "testfile" not in stdout_text(result)

    async def test_rm_file_cannot_be_read_after_delete(self, shell_with_commands):
        result = await shell_with_commands.execute("touch /home/user/testfile")
        assert_success(result)
        result = await shell_with_commands.execute("ls /home/user")
        assert_success(result)
        assert "testfile" in stdout_text(result)
        result = await shell_with_commands.execute("rm /home/user/testfile")
        assert_success(result)
        result = await shell_with_commands.execute("cat /home/user/testfile")
        assert_error(result)
        assert CommandError.NOT_FOUND in stderr_text(result)

    async def test_rm_only_removes_target_file(self, shell_with_commands):
        path = "/home/user"
        f1 = "testfile1"
        f2 = "testfile2"
        f3 = "testfile3"
        result = await shell_with_commands.execute(f"touch {path}/{f1}")
        assert_success(result)
        result = await shell_with_commands.execute(f"touch {path}/{f2}")
        assert_success(result)
        result = await shell_with_commands.execute(f"touch {path}/{f3}")
        assert_success(result)
        result = await shell_with_commands.execute(f"ls {path}")
        assert_success(result)
        for filename in [f1, f2, f3]:
            assert filename in stdout_text(result)
        result = await shell_with_commands.execute(f"rm {path}/{f1}")
        assert_success(result)
        result = await shell_with_commands.execute(f"ls {path}")
        assert f1 not in stdout_text(result)
        assert f2 in stdout_text(result)
        assert f3 in stdout_text(result)

    async def test_rm_relative_path(self, shell_with_commands):
        # Step 1 - create file in current directory
        result = await shell_with_commands.execute("touch localfile.txt")
        assert_success(result)

        # Step 2 - verify file exists
        result = await shell_with_commands.execute("ls")
        assert_success(result)
        assert "localfile.txt" in stdout_text(result)

        # Step 3 - remove using relative path
        result = await shell_with_commands.execute("rm localfile.txt")
        assert_success(result)

        # Step 4 - assert file disappeared
        result = await shell_with_commands.execute("ls")
        assert_success(result)
        assert "localfile.txt" not in stdout_text(result)

    async def test_rm_absolute_path(self, shell_with_commands):
        # Step 1 - create file
        result = await shell_with_commands.execute("touch /home/user/absfile.txt")
        assert_success(result)

        # Step 2 - verify file exists
        result = await shell_with_commands.execute("ls /home/user")
        assert_success(result)
        assert "absfile.txt" in stdout_text(result)

        # Step 3 - remove using absolute path
        result = await shell_with_commands.execute("rm /home/user/absfile.txt")
        assert_success(result)

        # Step 4 - assert file disappeared
        result = await shell_with_commands.execute("ls /home/user")
        assert_success(result)
        assert "absfile.txt" not in stdout_text(result)

    async def test_rm_home_relative_path(self, shell_with_commands):
        # Step 1 - create file in home directory
        result = await shell_with_commands.execute("touch ~/homefile.txt")
        assert_success(result)

        # Step 2 - verify file exists
        result = await shell_with_commands.execute("ls ~")
        assert_success(result)
        assert "homefile.txt" in stdout_text(result)

        # Step 3 - remove using tilde path
        result = await shell_with_commands.execute("rm ~/homefile.txt")
        assert_success(result)

        # Step 4 - assert file disappeared
        result = await shell_with_commands.execute("ls ~")
        assert_success(result)
        assert "homefile.txt" not in stdout_text(result)

    async def test_rm_deleted_file_stays_hidden(self, shell_with_commands):
        # Step 1 - create file
        result = await shell_with_commands.execute("touch hiddenfile.txt")
        assert_success(result)

        # Step 2 - remove file
        result = await shell_with_commands.execute("rm hiddenfile.txt")
        assert_success(result)

        # Step 3 - remove again
        result = await shell_with_commands.execute("rm hiddenfile.txt")
        assert_error(result)

        # Step 4 - assert NOT_FOUND returned
        assert CommandError.NOT_FOUND in stderr_text(result)

    async def test_rm_base_layer_file_creates_overlay_tombstone(self, shell_with_commands):
        # Step 1 - verify base-layer file exists
        result = await shell_with_commands.execute("cat /etc/hostname")
        assert_success(result)
        assert "simnux-edge" in stdout_text(result)

        # Step 2 - remove file
        result = await shell_with_commands.execute("rm /etc/hostname")
        assert_success(result)

        # Step 3 - assert file hidden afterwards
        result = await shell_with_commands.execute("cat /etc/hostname")
        assert_error(result)
        assert CommandError.NOT_FOUND in stderr_text(result)

    async def test_rm_preserves_other_directory_entries(self, shell_with_commands):
        # Step 1 - create sibling files
        result = await shell_with_commands.execute("touch keep1.txt")
        assert_success(result)

        result = await shell_with_commands.execute("touch keep2.txt")
        assert_success(result)

        result = await shell_with_commands.execute("touch remove.txt")
        assert_success(result)

        # Step 2 - remove one file
        result = await shell_with_commands.execute("rm remove.txt")
        assert_success(result)

        # Step 3 - list directory contents
        result = await shell_with_commands.execute("ls")
        assert_success(result)

        # Step 4 - assert only target disappeared
        output = stdout_text(result)

        assert "remove.txt" not in output
        assert "keep1.txt" in output
        assert "keep2.txt" in output

    async def test_rm_root_directory_rejected(self, shell_with_commands):
        # Step 1 - execute rm on root
        result = await shell_with_commands.execute("rm /")

        # Step 2 - assert error returned
        assert_error(result)

        # Step 3 - assert directory error message
        assert CommandError.IS_A_DIRECTORY in stderr_text(result)

        # Step 4 - assert root still accessible
        result = await shell_with_commands.execute("ls /")
        assert_success(result)

    async def test_rm_directory_with_children_rejected(self, shell_with_commands):
        # Step 1 - create directory structure
        result = await shell_with_commands.execute("mkdir testdir")
        assert_success(result)

        result = await shell_with_commands.execute("touch testdir/file.txt")
        assert_success(result)

        # Step 2 - attempt removing directory
        result = await shell_with_commands.execute("rm testdir")

        # Step 3 - assert failure
        assert_error(result)

        # Step 4 - assert directory still exists
        result = await shell_with_commands.execute("ls")
        assert_success(result)
        assert "testdir" in stdout_text(result)

        result = await shell_with_commands.execute("ls testdir")
        assert_success(result)
        assert "file.txt" in stdout_text(result)

    async def test_rm_returns_empty_stdout_on_success(self, shell_with_commands):
        # Step 1 - create file
        result = await shell_with_commands.execute("touch stdoutcheck.txt")
        assert_success(result)

        # Step 2 - remove file
        result = await shell_with_commands.execute("rm stdoutcheck.txt")

        # Step 3 - assert stdout/stderr empty
        assert result.stdout == []
        assert result.stderr == []

    async def test_rm_returns_empty_stdout_on_failure(self, shell_with_commands):
        result = await shell_with_commands.execute("rm not-a-file.txt")
        assert result.stdout == []
        assert result.exit_code == ExitCode.ERROR
        assert CommandError.NOT_FOUND in stderr_text(result)
