import copy
import pytest
from common.scenarios import Scenario
from common.outcomes import PrerequisiteBlocked


def user_scenario(original_tel, proposed_tel):
    row = {"UserID": "11", "DisplayName": "test", "Sex": "0", "TelePhone": original_tel,
           "Mobile": "13800000000", "EMail": "old@example.com"}
    class Database:
        def fetch(self, *args): return [copy.deepcopy(row)]
    class Runtime:
        env = {"user_id": 11}
        profile = {"user_update_mode": "nonempty_fields"}
        database = Database()
    return Scenario(Runtime(), {"case_id": "user-008", "fixture": "user", "requires": [],
                                "params": {"userId": 11, "tel": proposed_tel}})


@pytest.mark.parametrize("original", [None, ""])
def test_nonempty_only_api_cannot_write_over_an_unrestorable_empty_baseline(original):
    scenario = user_scenario(original, "123456")
    with pytest.raises(PrerequisiteBlocked, match="cannot restore empty original fields"):
        scenario.prepare()
    assert not scenario.cleanups  # No mutation was performed before blocking.


def test_nonempty_baseline_registers_normal_api_restore():
    scenario = user_scenario("old_phone", "new_phone")
    scenario.prepare()
    assert len(scenario.cleanups) == 1


def test_partial_update_cannot_clear_an_omitted_nickname():
    scenario = user_scenario("old_phone", "new_phone")
    scenario.prepare()
    after = dict(scenario.before["user"][0], TelePhone="new_phone")
    scenario.rows = lambda *args: [copy.deepcopy(after)]
    scenario.verify_state("user", {"userId": 11, "tel": "new_phone"}, None)
    after["DisplayName"] = None
    with pytest.raises(AssertionError):
        scenario.verify_state("user", {"userId": 11, "tel": "new_phone"}, None)


def test_temporary_user_is_scenario_local_and_cleanup_owns_the_exact_name(monkeypatch):
    from common import user_fixtures
    scenario = user_scenario("old_phone", "new_phone")
    stored, deleted, writes = {}, [], []

    class Api:
        def __init__(self, runtime): pass
        def call(self, path, params, **kwargs):
            if path.endswith("/add"):
                stored[params["userName"]] = {"UserID": "77", "UserName": params["userName"]}
            elif path.endswith("/del"):
                deleted.append(params["userName"])
                stored.pop(params["userName"], None)
            return {"code": "0"}

    def rows(sql, params=()):
        if "WHERE UserName=" in sql:
            return [copy.deepcopy(stored[params[0]])] if params[0] in stored else []
        return [copy.deepcopy(next(iter(stored.values())))]

    def api(cls, method, params):
        assert params["userId"] == 77
        writes.append(params["userId"])
        next(iter(stored.values())).update(DisplayName=params["nickName"], Sex=params["sex"],
                                          TelePhone=params["tel"], Mobile=params["mobile"], EMail=params["mail"])

    monkeypatch.setattr(user_fixtures, "UserPreparationApi", Api)
    scenario.rows, scenario.api = rows, api
    user_fixtures.prepare_temporary_user(scenario)
    name = next(iter(stored))
    assert scenario.context["env"]["user_id"] == 77
    assert scenario.runtime.env["user_id"] == 11  # Other tests retain their configured identity.
    scenario.close()
    assert deleted == [name] and not stored and writes == [77]


def test_temporary_user_cleanup_survives_ambiguous_creation_response(monkeypatch):
    from common import user_fixtures
    scenario = user_scenario("old_phone", "new_phone")
    stored = set()

    class Api:
        def __init__(self, runtime): pass
        def call(self, path, params, **kwargs):
            if path.endswith("/add"):
                stored.add(params["userName"])
                raise RuntimeError("response lost after server-side creation")
            if path.endswith("/del"):
                stored.remove(params["userName"])
            return {"code": "0"}

    monkeypatch.setattr(user_fixtures, "UserPreparationApi", Api)
    scenario.rows = lambda *args: []
    with pytest.raises(RuntimeError, match="response lost"):
        user_fixtures.prepare_temporary_user(scenario)
    assert len(stored) == 1
    scenario.close()
    assert not stored
