"""Tests for the CommandRegistry in-memory command map.

Covers registration, lookup, overwrite semantics, and listing of
registered commands.
"""


class _DummyCommand:
    name = "dummy"


class _AnotherCommand:
    name = "another"


class _OverwriteCommand:
    name = "dummy"


class TestCommandRegistryRegistration:
    """Command registration scenarios.

    Verifies that commands can be registered, retrieved, and that
    registering a command with an existing name overwrites the
    previous entry (last-write-wins).
    """

    def test_register_and_get(self, registry):
        """Register a command and retrieve it by name — identity is preserved."""
        command = _DummyCommand()

        registry.register(command)

        assert registry.get("dummy") is command

    def test_register_overwrites_existing_command(self, registry):
        """Registering a second command with the same name replaces the first (last-wins)."""
        first = _DummyCommand()
        second = _OverwriteCommand()

        registry.register(first)
        registry.register(second)

        assert registry.get("dummy") is second

    def test_register_multiple_commands(self, registry):
        """Multiple distinct commands can coexist in the registry."""
        dummy = _DummyCommand()
        another = _AnotherCommand()

        registry.register(dummy)
        registry.register(another)

        assert registry.get("dummy") is dummy
        assert registry.get("another") is another


class TestCommandRegistryLookup:
    """Lookup and existence-check scenarios for the registry."""

    def test_get_nonexistent_returns_none(self, registry):
        """Requesting an unregistered name returns ``None``, never raises."""
        assert registry.get("nonexistent") is None

    def test_exists(self, registry):
        """``exists()`` returns ``True`` for registered names, ``False`` otherwise."""
        registry.register(_DummyCommand())

        assert registry.exists("dummy") is True
        assert registry.exists("missing") is False


class TestCommandRegistryListing:
    """Command listing and enumeration scenarios."""

    def test_list_commands_sorted(self, registry):
        """``list_commands()`` returns registered names in alphabetical order."""
        registry.register(_DummyCommand())
        registry.register(_AnotherCommand())

        assert registry.list_commands() == [
            "another",
            "dummy",
        ]

    def test_list_commands_empty(self, registry):
        """An empty registry returns an empty list from ``list_commands()``."""
        assert registry.list_commands() == []
