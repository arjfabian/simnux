"""Identity-state backbone tests.

Covers the invariant chain:

    IdentityState
        -> IdentityManager
           -> SNXGroupMembership
              -> ExecutionCredentials

and the requirement that membership is explicit and never depends on user/
group identifiers matching.
"""

import pytest

from simnux.core.scenarios.identity import IdentityManager
from simnux.core.scenarios.identity import IdentityState
from simnux.security.execution.models import ExecutionContext
from simnux.security.groups.models import SNXGroup
from simnux.security.users.models import SNXUser


_ROOT_USER = SNXUser(0, "root")
_ROOT_GROUP = SNXGroup(0, "root")
_ALICE = SNXUser(1001, "alice")
_STAFF = SNXGroup(2001, "staff")
_OPS = SNXGroup(2002, "ops")


def _root_manager() -> IdentityManager:
    manager = IdentityManager(IdentityState())
    manager.seed_group(_ROOT_GROUP)
    manager.seed_user(_ROOT_USER, primary_group=_ROOT_GROUP)
    return manager


class TestIdentityStateResolution:
    """Numeric-id and identifier lookups for users and groups."""

    def test_user_and_group_resolution_by_both_axes(self):
        state = IdentityState()
        state.register_user(_ALICE)
        state.register_group(_STAFF)

        assert state.user_by_id(1001) is _ALICE
        assert state.user_by_identifier("alice") is _ALICE
        assert state.group_by_id(2001) is _STAFF
        assert state.group_by_identifier("staff") is _STAFF

    def test_missing_lookups_return_none(self):
        state = IdentityState()
        assert state.user_by_id(1) is None
        assert state.user_by_identifier("ghost") is None
        assert state.group_by_id(1) is None
        assert state.group_by_identifier("ghost") is None

    def test_iteration_and_order(self):
        state = IdentityState()
        state.register_user(_ROOT_USER)
        state.register_user(_ALICE)
        state.register_group(_ROOT_GROUP)
        state.register_group(_STAFF)

        assert state.all_users() == (_ROOT_USER, _ALICE)
        assert state.all_groups() == (_ROOT_GROUP, _STAFF)


class TestIdentityStateRegistration:
    """Duplicate and cross-axis collisions are rejected."""

    def test_duplicate_user_id_rejected(self):
        state = IdentityState()
        state.register_user(_ALICE)
        with pytest.raises(ValueError, match="already registered"):
            state.register_user(SNXUser(1001, "alice2"))

    def test_duplicate_user_identifier_rejected(self):
        state = IdentityState()
        state.register_user(_ALICE)
        with pytest.raises(ValueError, match="already registered"):
            state.register_user(SNXUser(2002, "alice"))

    def test_duplicate_group_rejected_by_id_and_identifier(self):
        state = IdentityState()
        state.register_group(_STAFF)
        with pytest.raises(ValueError, match="already registered"):
            state.register_group(SNXGroup(2001, "staff2"))
        with pytest.raises(ValueError, match="already registered"):
            state.register_group(SNXGroup(2003, "staff"))

    def test_membership_requires_registered_ids(self):
        state = IdentityState()
        state.register_user(_ALICE)
        state.register_group(_STAFF)
        with pytest.raises(ValueError, match="unknown user"):
            state.add_membership(999, 2001)
        with pytest.raises(ValueError, match="unknown group"):
            state.add_membership(1001, 999)

    def test_membership_cardinality(self):
        state = IdentityState()
        state.register_user(_ALICE)
        state.register_group(_STAFF)
        state.register_group(_OPS)
        state.add_membership(1001, 2001)
        state.add_membership(1001, 2002)
        assert state.member_group_ids(1001) == frozenset({2001, 2002})

    def test_primary_group_implies_membership(self):
        state = IdentityState()
        state.register_user(_ALICE)
        state.register_group(_STAFF)
        state.set_primary_group(1001, 2001)
        assert state.primary_group_id(1001) == 2001
        assert state.primary_group(1001) is _STAFF
        assert state.member_group_ids(1001) == frozenset({2001})


class TestMembershipExplicitNotNameMatched:
    """Membership never depends on user/group identifiers matching."""

    def test_membership_view_is_explicit_despite_name_mismatch(self):
        manager = _root_manager()
        manager.seed_group(_STAFF)
        manager.seed_user(_ALICE, primary_group=_STAFF)

        assert manager.group_by_identifier("alice") is None

        membership = manager.membership_view()
        assert membership.is_member(1001, 2001) is True
        assert membership.group_ids_of(_ALICE) == frozenset({2001})
        assert membership.primary_group(_ALICE) is _STAFF

    def test_primary_group_resolved_from_state_not_name(self):
        manager = _root_manager()
        alice = SNXUser(1001, "alice")
        staff = SNXGroup(2001, "staff")
        manager.seed_group(staff)
        manager.seed_user(alice, primary_group=staff)

        membership = manager.membership_view()
        assert membership.primary_group(alice) is staff
        assert membership.primary_group(_ROOT_USER) is _ROOT_GROUP


class TestIdentityChain:
    """IdentityState -> IdentityManager -> SNXGroupMembership -> Credentials."""

    def _manager(self) -> IdentityManager:
        manager = _root_manager()
        manager.seed_group(_STAFF)
        manager.seed_group(_OPS)
        manager.seed_user(_ALICE, primary_group=_STAFF, groups=[_OPS])
        return manager

    def test_credentials_built_from_explicit_view(self):
        membership = self._manager().membership_view()

        context = ExecutionContext.for_user(_ALICE, membership)
        creds = context.credentials

        assert creds.real_user is _ALICE
        assert creds.effective_user is _ALICE
        assert creds.primary_group is _STAFF
        assert creds.supplementary_groups == (_OPS,)
        assert set(creds.groups) == {_STAFF, _OPS}

    def test_root_privilege_does_not_leak_to_plain_user(self):
        membership = self._manager().membership_view()
        creds = ExecutionContext.for_user(_ALICE, membership).credentials
        assert _ROOT_GROUP not in creds.groups
        assert creds.primary_group is not _ROOT_GROUP

    def test_view_is_a_snapshot_of_state(self):
        manager = self._manager()
        membership = manager.membership_view()
        assert membership.is_member(1001, 2001) is True
        assert membership.is_member(1001, 2002) is True

        # Later mutation does not leak into the previously built view.
        manager.add_user_to_group(_ALICE, _ROOT_GROUP)
        assert membership.is_member(1001, 0) is False
        assert manager.membership_view().is_member(1001, 0) is True

    def test_execution_context_is_a_frozen_snapshot(self):
        manager = self._manager()
        context = ExecutionContext.for_user(_ALICE, manager.membership_view())

        manager.add_user_to_group(_ALICE, _OPS)
        manager.add_user_to_group(_ALICE, _ROOT_GROUP)

        assert set(context.credentials.groups) == {_STAFF, _OPS}
        assert _ROOT_GROUP not in context.credentials.groups


class TestIdentityManagerOperations:
    """Semantic operations over the state."""

    def test_seed_user_requires_seeded_groups(self):
        manager = _root_manager()
        with pytest.raises(ValueError, match="unknown group"):
            manager.seed_user(
                SNXUser(1002, "bob"),
                groups=[SNXGroup(3001, "research")],
            )

    def test_manager_resolution_delegates_to_state(self):
        manager = _root_manager()
        assert manager.user_by_identifier("root") is _ROOT_USER
        assert manager.user_by_id(0) is _ROOT_USER
        assert manager.group_by_identifier("root") is _ROOT_GROUP
        assert manager.group_by_id(0) is _ROOT_GROUP
        assert manager.users() == (_ROOT_USER,)
        assert manager.groups() == (_ROOT_GROUP,)

    def test_seed_user_without_groups_has_no_membership(self):
        manager = _root_manager()
        manager.seed_user(_ALICE)
        assert manager.membership_view().group_ids_of(_ALICE) == frozenset()
        assert manager.membership_view().primary_group(_ALICE) is None


class TestLoaderSeedsIdentityState:
    """ScenarioLoader seeds the authoritative identity state."""

    @pytest.fixture(autouse=True)
    def _patch_scenarios_dir(self, monkeypatch):
        from pathlib import Path

        import yaml

        from simnux.core.scenarios.loader import ScenarioLoader

        tmp = Path("/tmp/simnux_identity_loader_seed")
        tmp.mkdir(exist_ok=True)
        (tmp / "idtest").mkdir(exist_ok=True)
        (tmp / "idtest" / "scenario.yaml").write_text(
            yaml.safe_dump(
                {
                    "name": "IdentitySeed",
                    "difficulty": "Easy",
                    "users": [
                        {"user_id": 1001, "identifier": "tester"},
                    ],
                    "starting_dir": "/home/tester",
                }
            ),
            encoding="utf-8",
        )
        monkeypatch.setattr(ScenarioLoader, "_get_scenarios_dir", lambda: tmp)

    def test_loader_state_matches_projections(self):
        from simnux.core.scenarios.loader import ScenarioLoader

        scenario = ScenarioLoader.load("idtest")

        assert scenario.users == {"root": _ROOT_USER, "tester": SNXUser(1001, "tester")}
        assert scenario.identity_state.user_by_identifier("tester") == SNXUser(1001, "tester")
        assert scenario.identity_state.user_by_id(0) == _ROOT_USER

    def test_loader_membership_view_matches_convention(self):
        from simnux.core.scenarios.loader import ScenarioLoader

        scenario = ScenarioLoader.load("idtest")
        manager = IdentityManager(scenario.identity_state)
        tester = manager.user_by_identifier("tester")
        membership = manager.membership_view()

        assert tester is not None
        assert membership.is_member(1001, 1001) is True
        assert membership.primary_group(tester) == SNXGroup(1001, "tester")
