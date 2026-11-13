import copy
import pytest
from common.gateway_response import GatewayResult
from common.scenarios import Scenario, same_rows


def make_timer(rows):
    class Database:
        def __init__(self): self.rows = copy.deepcopy(rows)
        def fetch(self, sql, params=()):
            if "oracle_available" in sql: return []
            found = self.rows
            if params:
                found = [r for r in found if int(r["RoomID"]) == params[0] and int(r["SvrAppID"]) == params[1]]
            return copy.deepcopy(found)
    class Runtime:
        env = {}
        database = Database()
        calls = []
        def call(self, cls, method, params, success=False):
            assert (cls, method) == ("room", "replaceRoomRoute")
            self.calls.append(params)
            self.database.rows = [r for r in self.database.rows
                                  if (int(r["RoomID"]), int(r["SvrAppID"])) != (params["roomId"], params["svrAppId"])]
            self.database.rows.append({"RoomID": params["roomId"], "SvrAppID": params["svrAppId"],
                                       "SvrNodeID": params["svrNodeId"], "SvrAddr": params["svrAddress"],
                                       "SvrAuthCode": params["svrAuthCode"]})
            return GatewayResult(0, 0, None, b"", "restore", 0)
    return Scenario(Runtime(), {"case_id": "timer", "fixture": "route_timer", "requires": ["database"]})


def test_expired_routes_are_restored_through_api():
    original = [{"RoomID": "10000", "SvrAppID": "0", "SvrNodeID": "other_node", "SvrAddr": "address", "SvrAuthCode": "auth"},
                {"RoomID": "20000", "SvrAppID": "3", "SvrNodeID": "primary_node", "SvrAddr": "other", "SvrAuthCode": "other_auth"}]
    scenario = make_timer(original)
    scenario.prepare()
    scenario.runtime.database.rows = []  # Emulate timer deleting the expired records.
    scenario.close()
    assert same_rows(scenario.runtime.database.rows, original)
    assert len(scenario.runtime.calls) == 2


def test_unrestorable_multi_node_group_stops_before_timer_can_be_sent():
    first = {"RoomID": "10000", "SvrAppID": "3", "SvrNodeID": "one", "SvrAddr": "address", "SvrAuthCode": "auth"}
    scenario = make_timer([first, dict(first, SvrNodeID="two")])
    with pytest.raises(RuntimeError, match="cannot restore multiple"):
        scenario.prepare()
    assert not scenario.runtime.calls
