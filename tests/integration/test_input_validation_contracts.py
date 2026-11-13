"""Confirmed input contracts, including the retained JSON coercion behavior."""
import uuid
import allure
import pytest
from common.assertions import assert_rules
from common.executor import attach
from common.scenarios import same_rows

pytestmark = pytest.mark.integration
MISSING = object()
SELECTOR_CASES = [
    ("missing", MISSING), ("null", None), ("empty", ""), ("blank", " \t"),
    ("text", "test"), ("other_number", "2"), ("number_zero", 0),
    ("number_one", 1), ("boolean", True), ("array", []), ("object", {})]
SWITCH_INPUT_CASES = [
    ("missing", MISSING), ("null", None), ("empty", ""), ("blank", " \t"),
    ("string_true", "true"), ("string_false", "false"), ("number_zero", 0),
    ("number_one", 1), ("array", []), ("object", {})]


def with_field(base, field, value):
    params = dict(base)
    if value is MISSING:
        params.pop(field, None)
    else:
        params[field] = value
    return params


def check_response(result, expected, before=None, after=None):
    attach("Validation response", result.evidence())
    errors = []
    if result.invoke_code != expected or result.response_code != expected:
        errors.append("Expected both envelope codes %s, got %s/%s" % (expected, result.invoke_code, result.response_code))
    if before is not None:
        attach("Validation state comparison", {"before": before, "after": after})
        if not same_rows(after, before):
            errors.append("Invalid request changed business state")
    assert not errors, "; ".join(errors)


def assert_selected_node(result, expected):
    if expected:
        assert len(expected) == 1, "Selector requires an unambiguous node result"
        assert_rules(result.legacy(), [{"path": "$.nodeId", "op": "eq", "value": expected[0]["NodeID"]}])
    else:
        assert_rules(result.legacy(), [{"path": "$.nodeId", "op": "exists", "value": False}])


@pytest.mark.parametrize("name,value", SELECTOR_CASES, ids=[v[0] for v in SELECTOR_CASES])
def test_node_selector_contract(gateway_runtime, name, value):
    before = gateway_runtime.database.fetch("SELECT NodeID,IsLocal FROM t_nodeinfo")
    params = with_field({}, "isLocal", value)
    result = gateway_runtime.call("device", "getNodeIdByLocal", params)
    after = gateway_runtime.database.fetch("SELECT NodeID,IsLocal FROM t_nodeinfo")
    if name in {"number_zero", "number_one"}:
        allure.dynamic.label("test_group", "behavior_baseline")
        allure.dynamic.title("node_selector_numeric_compat_" + name)
        check_response(result, 0, before, after)
        expected = [row for row in before if int(row["IsLocal"]) == value]
        assert_selected_node(result, expected)
        attach("Developer-confirmed numeric selector", {"input": params, "expected_nodes": expected,
               "scope": "Developer retained numeric 0/1 compatibility; query result and unchanged nodes are verified"})
    else:
        check_response(result, 4108, before, after)


@pytest.mark.parametrize("value", ["0", "1"], ids=["nonlocal", "local"])
def test_node_selector_valid(gateway_runtime, value):
    expected = gateway_runtime.database.fetch("SELECT NodeID FROM t_nodeinfo WHERE IsLocal=%s", [int(value)])
    result = gateway_runtime.call("device", "getNodeIdByLocal", {"isLocal": value})
    check_response(result, 0)
    assert_selected_node(result, expected)


@pytest.mark.parametrize("initial", [False, True], ids=["off", "on"])
@pytest.mark.parametrize("name,value", SWITCH_INPUT_CASES, ids=[v[0] for v in SWITCH_INPUT_CASES])
def test_conversion_switch_contract(workflow, initial, name, value):
    coercions = {"empty": False, "blank": False, "string_true": True, "string_false": False}
    retained = name in coercions
    title = ("switch_string_compat_" if retained else "switch_invalid_") + "%s_%s" % (name, int(initial))
    if retained:
        allure.dynamic.label("test_group", "behavior_baseline")
    with workflow(title, fixture="feature",
                  method="setDocumentConversionSwitch", requires=["write", "database"]) as s:
        s.api("device", "setDocumentConversionSwitch", {"globalSwitch": initial})
        sql = "SELECT global_switch FROM t_features WHERE code='DocumentConversion'"
        before = s.rows(sql)
        assert before == [{"global_switch": str(int(initial))}]
        result = s.runtime.call("device", "setDocumentConversionSwitch", with_field({}, "globalSwitch", value))
        after = s.rows(sql)
        if retained:
            check_response(result, 0)
            expected = [{"global_switch": str(int(coercions[name]))}]
            attach("Developer-confirmed string switch conversion", {"input": value, "before": before,
                   "after": after, "expected": expected, "scope": "Existing string conversion retained by developer decision"})
            assert same_rows(after, expected), "String switch conversion did not produce the confirmed stored value"
        else:
            check_response(result, 4108, before, after)


@pytest.mark.parametrize("value", [False, True], ids=["off", "on"])
def test_conversion_switch_valid(workflow, value):
    with workflow("switch_valid_%s" % int(value), fixture="feature", method="setDocumentConversionSwitch",
                  requires=["write", "database"]) as s:
        result = s.runtime.call("device", "setDocumentConversionSwitch", {"globalSwitch": value})
        check_response(result, 0)
        assert s.rows("SELECT global_switch FROM t_features WHERE code='DocumentConversion'") == [{"global_switch": str(int(value))}]


MASTER_INVALID = [(field, name, value) for field in ["devId"]
                  for name, value in [("missing", MISSING), ("null", None), ("empty", ""), ("blank", " \t")]]


@pytest.mark.parametrize("field,name,value", MASTER_INVALID, ids=[f + "_" + n for f, n, _ in MASTER_INVALID])
def test_master_identity_invalid(workflow, field, name, value):
    with workflow("master_invalid_%s_%s" % (field, name), fixture="master", method="tryChangeToMaster",
                  requires=["write", "database"]) as s:
        env, f = s.context["env"], s.context["fixture"]
        params = {"devId": env["primary"]["device_id"], "serverType": f["server_type"],
                  "address": env["primary"]["services"]["FMConfSrv"]["address"]}
        # A valid request using the same isolated type proves the rejection is
        # testing the bad field rather than an unsupported serverType.
        s.api("device", "tryChangeToMaster", params)
        sql = "SELECT devid,address,servertype,flushtime FROM t_master_slave WHERE servertype=%s"
        before = s.rows(sql, [f["server_type"]])
        assert len(before) == 1 and before[0]["devid"] == params["devId"]
        result = s.runtime.call("device", "tryChangeToMaster", with_field(params, field, value))
        check_response(result, 4108, before, s.rows(sql, [f["server_type"]]))


@pytest.mark.parametrize("name,value", [("missing", MISSING), ("null", None), ("empty", ""), ("blank", " \t")],
                         ids=["missing", "null", "empty", "blank"])
def test_master_optional_address(workflow, name, value):
    allure.dynamic.label("test_group", "behavior_baseline")
    with workflow("master_optional_address_" + name, fixture="master", method="tryChangeToMaster",
                  requires=["write", "database"]) as s:
        env, f = s.context["env"], s.context["fixture"]
        params = {"devId": env["primary"]["device_id"], "serverType": f["server_type"],
                  "address": env["primary"]["services"]["FMConfSrv"]["address"]}
        s.api("device", "tryChangeToMaster", params)
        sql = "SELECT devid,address,servertype FROM t_master_slave WHERE servertype=%s"
        before = s.rows(sql, [f["server_type"]])
        assert len(before) == 1 and before[0]["devid"] == params["devId"]
        result = s.runtime.call("device", "tryChangeToMaster", with_field(params, "address", value))
        check_response(result, 0, before, s.rows(sql, [f["server_type"]]))
        assert_rules(result.legacy(), [{"path": "$.devId", "op": "eq", "value": params["devId"]}])


def test_master_identity_valid(workflow):
    with workflow("master_valid_identity", fixture="master", method="tryChangeToMaster",
                  requires=["write", "database"]) as s:
        env, f = s.context["env"], s.context["fixture"]
        params = {"devId": env["primary"]["device_id"], "serverType": f["server_type"],
                  "address": env["primary"]["services"]["FMConfSrv"]["address"]}
        result = s.runtime.call("device", "tryChangeToMaster", params)
        check_response(result, 0)
        row = s.rows("SELECT devid,address FROM t_master_slave WHERE servertype=%s", [f["server_type"]])
        assert row == [{"devid": params["devId"], "address": params["address"]}]


RENAME_INVALID = [(field, name, value) for field in ["docId", "docName"]
                  for name, value in [("missing", MISSING), ("null", None), ("empty", ""), ("blank", " \t")]]
RENAME_INVALID += [("roomId", name, value) for name, value in
                   [("missing", MISSING), ("null", None), ("zero", 0), ("negative", -1)]]


@pytest.mark.parametrize("field,name,value", RENAME_INVALID, ids=[f + "_" + n for f, n, _ in RENAME_INVALID])
def test_rename_invalid_preserves_name(workflow, field, name, value):
    with workflow("rename_invalid_%s_%s" % (field, name), fixture="file", method="renameFile") as s:
        env, f = s.context["env"], s.context["fixture"]
        params = {"roomId": env["room_id"], "docId": f["doc_id"], "docName": f["name"] + "_new"}
        sql = "SELECT DocID,DocName,ParentID FROM t_roomdocslist WHERE RoomID=%s AND DocID=%s"
        before = s.rows(sql, [env["room_id"], f["doc_id"]])
        assert len(before) == 1
        result = s.runtime.call("file", "renameFile", with_field(params, field, value))
        check_response(result, 4108, before, s.rows(sql, [env["room_id"], f["doc_id"]]))


def test_rename_valid(workflow):
    with workflow("rename_valid_name", fixture="file", method="renameFile") as s:
        env, f = s.context["env"], s.context["fixture"]
        params = {"roomId": env["room_id"], "docId": f["doc_id"], "docName": f["name"] + "_new"}
        result = s.runtime.call("file", "renameFile", params)
        check_response(result, 0)
        assert s.rows("SELECT DocName FROM t_roomdocslist WHERE RoomID=%s AND DocID=%s", [env["room_id"], f["doc_id"]]) == [{"DocName": params["docName"]}]


def test_move_missing_parent_from_nonroot(workflow):
    with workflow("move_missing_parent_from_nonroot", fixture="file", method="moveDocFile") as s:
        env, f = s.context["env"], s.context["fixture"]
        parent = "autotest_dir_" + uuid.uuid4().hex
        def cleanup_parent():
            s.api("file", "delFile", {"roomId": env["room_id"], "docId": parent})
            assert not s.rows("SELECT DocID FROM t_roomdocslist WHERE RoomID=%s AND DocID=%s", [env["room_id"], parent])
        s.cleanups.insert(0, ("nonroot parent directory", cleanup_parent))
        s.api("file", "addFile", {"roomId": env["room_id"], "docId": parent, "parentId": "", "docName": "autotest_parent",
              "docType": 0, "fileName": "", "fileExt": "", "fileSize": 0, "checkCode": 0, "creatorId": env["user_id"],
              "fileWidth": 0, "fileHeight": 0, "subFileCount": 0, "fileUrl": "",
              "fileServiceId": env["primary"]["services"]["FMFileSrv"]["id"]})
        s.api("file", "moveDocFile", {"roomId": env["room_id"], "docId": f["doc_id"], "parentId": parent}, business=0)
        sql = "SELECT ParentID FROM t_roomdocslist WHERE RoomID=%s AND DocID=%s"
        before = s.rows(sql, [env["room_id"], f["doc_id"]])
        assert before == [{"ParentID": parent}]
        result = s.runtime.call("file", "moveDocFile", {"roomId": env["room_id"], "docId": f["doc_id"]})
        after = s.rows(sql, [env["room_id"], f["doc_id"]])
        check_response(result, 4107, before, after)
        attach("File location after omitted parentId", s.rows("SELECT RoomID,DocID,DocName,ParentID FROM t_roomdocslist WHERE DocID=%s", [f["doc_id"]]))
