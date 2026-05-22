"""Regression tests for filesystem path resolution and normalization.

Covers deeply nested path resolution, tilde+dotdot combinations, and
chroot-safety clamping that prevents traversal above root.
"""

class TestRegressionFileSystemPathResolution:
    """Path resolution: deeply nested paths and tilde+dotdot composition."""

    def test_deeply_nested_path_resolution(self, create_filesystem):
        """Deep relative path resolves correctly from a starting directory."""
        fs = create_filesystem()
        result = fs.resolve_path("/", "a/b/c/d", "/home/user")
        assert result == "/a/b/c/d"

    def test_relative_path_with_tilde_and_dotdot(self, create_filesystem):
        """``~/../other`` goes up from home then into sibling directory."""
        fs = create_filesystem()
        result = fs.resolve_path("/home/user", "~/../other", "/home/user")
        assert result == "/home/other"


class TestRegressionPathNormalization:
    """Path normalization: chroot-safety prevents traversal above root."""

    def test_path_resolution_never_escapes_root(self, create_filesystem):
        """``../../../../etc`` from ``/`` clamps to ``/etc`` — root-escape prevention."""
        fs = create_filesystem()

        result = fs.resolve_path(
            "/",
            "../../../../etc",
            "/",
        )

        assert result == "/etc"
