"""Business confirmation must retain independent state and identity checks."""
import copy

import pytest

from common.scenarios import Scenario


def route_scenario():
    s = Scenario.__new__(Scenario)
    s.context = {"env": {}, "fixture": {"app_id": 12, "room_id": 10}}
    s.case = {"method": "updateRoomRoute"}
    original = {"RoomID": "10", "SvrAppID": "12", "SvrNodeID": "node",
                "SvrAddr": "original", "SvrAuthCode": "original-code"}
    inserted = dict(original, RoomID="99", SvrAddr="new", SvrAuthCode="new-code")
    s.before = {"route": [original]}
    params = {"roomId": 99, "svrAppId": 12, "svrNodeId": "node", "svrAddress": "new", "svrAuthCode": "new-code"}
    return s, params, original, inserted


@pytest.mark.parametrize("damage", [None, "delete_original", "change_original", "extra_insert"])
def test_precreation_checks_exact_addition_and_original_route_preservation(damage):
    s, params, original, inserted = route_scenario()
    scope = [copy.deepcopy(original), inserted]
    if damage == "delete_original":
        scope.pop(0)
    elif damage == "change_original":
        scope[0]["SvrAddr"] = "corrupted"
    elif damage == "extra_insert":
        scope.append(dict(inserted, RoomID="98"))
    s.rows = lambda sql, args=(): [inserted] if "UpdateTime FROM" in sql else scope
    if damage:
        with pytest.raises(AssertionError, match="preserve existing routes"):
            s.verify_state("route_precreate", params, None)
    else:
        s.verify_state("route_precreate", params, None)


def test_parent_assignment_cannot_clear_an_unrelated_file_name():
    s = Scenario.__new__(Scenario)
    s.context = {"env": {}, "fixture": {}}
    s.case = {"method": "moveDocFile", "verification": {"preserve_other_fields": True}}
    s.before = {"file": [{"DocID": "doc", "DocName": "original", "ParentID": ""}]}
    after = {"DocID": "doc", "DocName": "original", "ParentID": "external-parent"}
    s.rows = lambda *args: [copy.deepcopy(after)]
    s.verify_state("file", {"roomId": 10, "docId": "doc", "parentId": "external-parent"}, None)
    after["DocName"] = None
    with pytest.raises(AssertionError, match="unrelated field"):
        s.verify_state("file", {"roomId": 10, "docId": "doc", "parentId": "external-parent"}, None)


def test_identity_fixture_reads_expected_nickname_without_registering_writes():
    class Database:
        def fetch(self, *args):
            return [{"UserID": "11", "UserName": "test", "DisplayName": "actual nickname"}]
    class Runtime:
        env = {"user_id": 11, "username": "test"}
        database = Database()
    s = Scenario(Runtime(), {"case_id": "user-020", "fixture": "user_identity", "requires": []})
    s.prepare()
    assert s.context["fixture"]["nickname"] == "actual nickname"
    assert not s.cleanups
