"""Visible coverage for previously missing interfaces; uncertain contracts stay explicit."""
import pytest
import re
import time
import allure
from common.assertions import assert_rules
DOCUMENTED_METHODS = ["user.insertIntoFaceRollCall", "user.updateFaceInfoByFaceId"]


@pytest.mark.integration
@pytest.mark.parametrize("api", DOCUMENTED_METHODS)
def test_documented_method_support(api, gateway_runtime, workflow):
    # Historical face tests remain opt-in; confirmed removed methods are not probed.
    cls, method = api.split(".")
    if cls == "user" and "Face" in method:
        gateway_runtime.check_case_applicability({"topology": "any", "requires": ["face"]}, "read")
    env = gateway_runtime.env
    if api == "user.insertIntoFaceRollCall":
        with workflow("documented_face_rollcall", fixture="face_rollcall", requires=["write", "database", "face"]) as s:
            assert type(s.context["fixture"]["rollcall_id"]) is int
        return
    if api == "user.updateFaceInfoByFaceId":
        gateway_runtime.check_case_applicability({"topology": "any", "requires": ["face"]}, "read")
        face_id = gateway_runtime.require_legacy_face()
        rows = gateway_runtime.database.fetch("SELECT face_feature FROM t_faceinfo WHERE face_id=%s", [face_id])
        params = {"faceId": env["face_id"], "faceFeature": rows[0]["face_feature"]}
    else:
        raise ValueError("No explicit request fixture for " + api)
    result = gateway_runtime.call(cls, method, params)
    assert result.invoke_code == 0 and result.response_code == 0, result.evidence()


@pytest.mark.integration
def test_get_user_room_list(gateway_runtime):
    allure.dynamic.label("test_group", "backend_defect")
    allure.dynamic.label("issue_id", "BUG-USER-ROOM-SQL")
    gateway_runtime.check_case_applicability({"topology": "any", "requires": ["room", "user"]}, "read")
    env = gateway_runtime.env
    result = gateway_runtime.query("room", "getUserRoomList", {"userType": 1, "localUserId": env["user_id"],
                                  "roomAppType": 0, "nodeId": env["node_id"]})
    assert_rules(result, [{"path": "$.getUserRoomList", "op": "type", "value": "array"},
                          {"path": "$.result", "op": "type", "value": "int"}])


@pytest.mark.integration
@pytest.mark.parametrize("method", ["getFaceInfoByFaceId", "getFaceInfoList"])
def test_face_queries(gateway_runtime, method):
    gateway_runtime.check_case_applicability({"topology": "any", "requires": ["face"]}, "read")
    face_id = gateway_runtime.require_legacy_face()
    result = gateway_runtime.query("user", method, {"faceId": face_id})
    rules = [{"path": "$.data", "op": "contains_record", "value": {"faceId": face_id}, "count": 1}] if method == "getFaceInfoList" else [{"path": "$.faceId", "op": "eq", "value": face_id}]
    assert_rules(result, rules)


@pytest.mark.integration
def test_room_department_list_current_version(gateway_runtime):
    """Validate the supported response against independently read department data."""
    from common.scenarios import same_rows
    gateway_runtime.check_case_applicability({"topology": "any", "requires": ["room", "database"]}, "read")
    room_id = gateway_runtime.env["room_id"]
    db = gateway_runtime.database
    rooms = db.fetch("SELECT DepartID FROM t_roominfo WHERE RoomID=%s", [room_id])
    if not rooms:
        rooms = db.fetch("SELECT DepartID FROM t_roomruninfo WHERE RoomID=%s", [room_id])
    assert len(rooms) == 1, "Configured room must have one independently observable department"
    departments = db.fetch("SELECT DepartID,DepartName,DepartType,ParentDepartID,NodeID FROM t_departinfo")
    result = gateway_runtime.query("room", "getRoomDeptList2", {"roomId": room_id})
    assert_rules(result, [{"path": "$.departId", "op": "eq", "value": int(rooms[0]["DepartID"])},
                          {"path": "$.getRoomDeptList2", "op": "type", "value": "array"}])
    mapping = {"DepartID": "departId", "DepartName": "departName", "DepartType": "departType",
               "ParentDepartID": "parentDepartId", "NodeID": "nodeId"}
    actual = result["getRoomDeptList2"]
    for index, row in enumerate(actual):
        assert_rules(result, [{"path": "$.getRoomDeptList2[%d].%s" % (index, key), "op": "type", "value": typ}
                             for key, typ in [("departId", "int"), ("departName", "string"),
                                              ("departType", "int"), ("parentDepartId", "int"), ("nodeId", "string")]])
        assert set(mapping.values()) <= row.keys()
    expected = [{field: row[column] for column, field in mapping.items()} for row in departments]
    assert same_rows([{field: row[field] for field in mapping.values()} for row in actual], expected), "Department records differ from read-only DB oracle"


@pytest.mark.integration
def test_face_source_compatibility(gateway_runtime):
    gateway_runtime.check_case_applicability({"topology": "any", "requires": ["face"]}, "read")
    allure.dynamic.label("test_group", "compatibility")
    allure.dynamic.label("outcome_type", "compatibility_gap")
    allure.dynamic.label("issue_id", "COMPAT-FACE-SOURCES")
    env = gateway_runtime.env
    from common.executor import attach
    attach("Face identity domains", {"legacy_face_id": env.get("face_id"), "modern_face_present": env.get("modern_face_present"), "source": env.get("face_data_source")})
    assert not (env.get("modern_face_present") and env.get("legacy_face_total") == 0), "New backend face library contains data; legacy gateway t_faceinfo has no valid fixture. A supported sync/API adapter is required; IDs are not interchangeable."


@pytest.mark.integration
def test_phone_gateway_query(gateway_runtime):
    gateway_runtime.check_case_applicability({"topology": "any", "requires": ["phone_gateway"]}, "read")
    profile = gateway_runtime.profile
    if "phone_gateway_app_id" not in profile:
        raise RuntimeError("phone_gateway capability requires phone_gateway_app_id")
    result = gateway_runtime.query("device", "getAllPhoneGwInfo", {"callerUserId": gateway_runtime.env["user_id"],
                                  "phoneGwAppId": profile["phone_gateway_app_id"]})
    assert_rules(result, [{"path": "$.data", "op": "type", "value": "array"}])


@pytest.mark.integration
def test_conf_log_persistence(workflow):
    with workflow("confLog_persistence", fixture="meeting", requires=["write", "database", "room", "exclusive"], method="confLog") as s:
        env, f = s.context["env"], s.context["fixture"]
        # Table selection varies with room partitioning; do not guess an oracle table.
        verification = s.runtime.profile.get("conf_log_verification_sql")
        if not verification:
            partitions = s.runtime.database.room_log_tables()
            names = [row["table_name"] for row in partitions if re.fullmatch(r"t_roomlog(?:\d{4})?", row["table_name"])]
            if not names:
                raise RuntimeError("No room-log table/annual partition found")
            verification = " UNION ALL ".join("SELECT MeetingID,EventDesc FROM " + name + " WHERE MeetingID=%s AND EventDesc=%s" for name in names)
            verification_params = [v for _ in names for v in [f["meeting_id"], s.context["case"]["random"]]]
        else:
            verification_params = [f["meeting_id"], s.context["case"]["random"]]
        s.api("room", "confLog", {"serviceId": f["service_id"], "roomId": env["room_id"],
                                  "meetingId": f["meeting_id"], "userName": env["username"], "userIp": "127.0.0.1",
                                  "isLogin": 1, "eventCode": 0, "eventDesc": s.context["case"]["random"]})
        deadline = time.monotonic() + 10
        rows = s.rows(verification, verification_params)
        while not rows and time.monotonic() < deadline:
            time.sleep(0.2)
            rows = s.rows(verification, verification_params)
        assert len(rows) == 1, "confLog was acknowledged but its event did not persist"
