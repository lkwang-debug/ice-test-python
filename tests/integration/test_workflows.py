"""Independent core lifecycles. DB is only an oracle, never a data writer."""
import uuid
import pytest
import allure
from common.assertions import assert_rules
from common.scenarios import same_rows
from common.executor import attach

pytestmark = [pytest.mark.integration, pytest.mark.workflow]


def test_primary_device_update_current_version(workflow):
    """The supported heartbeat is also covered when there is only one meeting."""
    from common.mutation_fixtures import as_int
    from common.database import db_text
    with workflow("primary_device_update_current_version", fixture="device", method="devUpdate2",
                  requires=["write", "database"]) as s:
        original = s.before["device"]
        env = s.context["env"]
        mapping = {"online": "CurOnline", "bandWidth": "CurBandwidth", "roomCount": "CurRoomCount",
                   "cpuLoad": "CPULoad", "memLoad": "MemoryLoad"}
        params = {key: as_int(original[column]) for key, column in mapping.items()}
        params.update(deviceId=env["primary"]["device_id"], verifyCode=env["primary"]["verify_code"],
                      deviceAddress=original["DevIP"])
        result = s.api("device", "devUpdate2", params)
        assert_rules(result, [{"path": "$." + key, "op": "type", "value": "int"}
                             for key in ["maxOnline", "maxBandwidth", "roomMaxUserCount"]])
        assert_rules(result, [{"path": "$.devName", "op": "eq", "value": original["DevName"]}])
        rows = s.rows("SELECT DevID,DevIP,CurOnline,CurBandwidth,CurRoomCount,CPULoad,MemoryLoad FROM t_devinfo WHERE DevID=%s",
                      [params["deviceId"]])
        assert len(rows) == 1 and rows[0]["DevID"] == params["deviceId"]
        for key, column in mapping.items():
            assert db_text(rows[0][column]) == db_text(params[key]), (key, rows[0])
        assert rows[0]["DevIP"] == params["deviceAddress"]


@pytest.mark.parametrize("role", ["primary", "secondary"])
def test_service_lifecycle(workflow, role):
    with workflow("service_lifecycle_" + role, topology="dual" if role == "secondary" else "any",
                  requires=["write", "database"]) as s:
        env = s.context["env"]; device = env[role]["device_id"]; app = env["test_service_app_id"]
        sql = "SELECT ServiceID,ServiceName,ServiceAddrs,ServiceStatus FROM t_serviceinfo WHERE DevID=%s AND ServiceAppID=%s"
        original = s.rows(sql, [device, app]); assert len(original) <= 1
        params = {"deviceId": device, "srvAppId": app, "srvName": "autotest_service", "state": 1,
                  "srvAddress": "TCP:127.0.0.1:54011;"}
        def cleanup():
            current = s.rows(sql, [device, app])
            if original:
                p = dict(params, srvName=original[0]["ServiceName"], srvAddress=original[0]["ServiceAddrs"],
                         state=int(original[0]["ServiceStatus"]))
                s.api("device", "registerService", p, business=0)
                assert same_rows(s.rows(sql, [device, app]), original)
            elif current:
                s.api("device", "serviceUnregister", {"serviceId": int(current[0]["ServiceID"])})
                assert int(s.rows(sql, [device, app])[0]["ServiceStatus"]) == 0
                attach("Retained test registry record", {"device_id": device, "app_id": app,
                       "reason": "Gateway has unregister but no delete-service API; record retained disabled"})
        s.add_cleanup("test service registration", cleanup)
        created = s.api("device", "registerService", params, business=0)
        assert type(created["serviceId"]) is int and created["serviceId"] > 0
        repeated = s.api("device", "registerService", params, business=0)
        assert repeated["serviceId"] == created["serviceId"]
        assert len(s.rows(sql, [device, app])) == 1
        listed = s.api("device", "getServiceList", {"devId": device})
        assert_rules(listed, [{"path": "$.data", "op": "contains_record", "count": 1,
                              "value": {"serviceId": created["serviceId"], "serviceAppId": app, "serviceName": params["srvName"]}}])
        updated = dict(params, srvName="autotest_updated", srvAddress="TCP:127.0.0.1:54013;")
        s.api("device", "registerService", updated, business=0)
        row = s.rows(sql, [device, app])[0]
        assert row["ServiceName"] == updated["srvName"] and row["ServiceAddrs"] == updated["srvAddress"]
        s.api("device", "serviceUnregister", {"serviceId": created["serviceId"]})
        assert int(s.rows(sql, [device, app])[0]["ServiceStatus"]) == 0
        # An allowed repeated no-op is checked by final state, not affected row count.
        s.api("device", "serviceUnregister", {"serviceId": created["serviceId"]})
        assert int(s.rows(sql, [device, app])[0]["ServiceStatus"]) == 0


def test_meeting_lifecycle(workflow):
    with workflow("meeting_lifecycle") as s:
        env = s.context["env"]; room = env["room_id"]
        baseline = s.rows("SELECT RoomID,CurUserCount,CurrentServiceID FROM t_roominfo WHERE RoomID=%s", [room])
        if len(baseline) != 1 or int(baseline[0]["CurUserCount"] or 0) or int(baseline[0]["CurrentServiceID"] or 0):
            from common.outcomes import blocked
            blocked("Meeting lifecycle requires an idle dedicated room", {"room_id": room, "state": baseline})
        user_state = s.require_room_membership()
        service = env["primary"]["services"]["FMConfSrv"]["id"]
        group = s.context["case"]["group_id"]; meeting = {"id": None, "started": False}
        def cleanup():
            if meeting["started"]:
                if meeting["id"] is None:
                    meeting["id"] = s.api("room", "meetingLog", {"roomId": room, "groupId": group})["meetingId"]
                s.api("room", "confRoomStop", {"serviceId": service, "roomId": room,
                        "meetingId": meeting["id"], "peakUserCount": 1})
            s.api("room", "updateRoomUserState", {"roomId": room, "userId": env["user_id"], "online": int(user_state[0]["UserOnline"])})
            s.api("room", "updateRoomInfoByRoomId", {"roomId": room, "curUserCount": int(baseline[0]["CurUserCount"])})
            assert same_rows(s.rows("SELECT RoomID,CurUserCount,CurrentServiceID FROM t_roominfo WHERE RoomID=%s", [room]), baseline)
        s.add_cleanup("meeting and membership state", cleanup)
        started = s.api("room", "confRoomStart", {"serviceId": service, "roomId": room, "groupId": group}, business=0)
        meeting["started"] = True
        assert isinstance(started["roomInfo"], dict) and started["roomInfo"]["maxUserCount"] > 0
        meeting["id"] = s.api("room", "meetingLog", {"roomId": room, "groupId": group})["meetingId"]
        logs = s.rows("SELECT MeetingID,RoomID,MeetingStartTime FROM t_meetinglog WHERE MeetingID=%s", [meeting["id"]])
        assert len(logs) == 1 and int(logs[0]["RoomID"]) == room and logs[0]["MeetingStartTime"] is not None
        s.api("room", "confUserLogin2", {"serviceId": service, "roomId": room, "userId": env["user_id"],
                "userName": env["username"], "userType": 1, "terminalType": 21, "roomPassword": ""}, business=0)
        s.api("room", "updateRoomUserState", {"roomId": room, "userId": env["user_id"], "online": 1})
        online = s.rows("SELECT UserOnline FROM t_roomusers WHERE RoomID=%s AND UserID=%s", [room, env["user_id"]])
        assert int(online[0]["UserOnline"]) == 1
        s.api("room", "updateRoomInfoByRoomId", {"roomId": room, "curUserCount": 1})
        assert s.api("room", "getRoomInfo", {"roomId": room})["curUserCount"] == 1
        s.api("room", "confRoomStop", {"serviceId": service, "roomId": room, "meetingId": meeting["id"], "peakUserCount": 1}, business=0)
        attach("Meeting ID ownership verified", {"meeting_id": meeting["id"], "room_id": room})


def test_route_lifecycle(workflow):
    with workflow("route_lifecycle", fixture="route") as s:
        f = s.context["fixture"]
        key = {"roomId": f["room_id"], "svrAppId": f["app_id"], "svrNodeId": f["node_id"]}
        query = s.api("room", "getRoomRouteInfo", key)
        assert query["svrAddress"] == f["address"] and query["svrAuthCode"] == f["auth_code"]
        update = dict(key, svrAddress=f["address"], svrAuthCode=f["auth_code"])
        returned = s.api("room", "updateRoomRoute", update)
        s.verify_state("route", update, returned)
        s.wait_for_route_clock_tick()
        s.api("room", "updateRoomRouteTime", key)
        s.verify_state("route_time", key, None)
        replaced = dict(key, svrAddress="TCP:127.0.0.1:54014;", svrAuthCode="new_" + f["auth_code"])
        s.api("room", "replaceRoomRoute", replaced)
        s.verify_state("route", replaced, None)
        s.api("room", "delRoomRoute", key)
        s.case["method"] = "delRoomRoute"; s.verify_state("route", key, None)
        s.api("room", "delRoomRoute", key); s.verify_state("route", key, None)


def test_file_lifecycle(workflow):
    with workflow("file_lifecycle", fixture="file", requires=["write", "database", "room", "file"], method="moveDocFile") as s:
        env, f = s.context["env"], s.context["fixture"]
        files = s.api("file", "getRoomFileList", {"roomId": env["room_id"]})
        assert_rules(files, [{"path": "$.data", "op": "contains_record", "value": {"docId": f["doc_id"]}, "count": 1}])
        rename = {"roomId": env["room_id"], "docId": f["doc_id"], "docName": f["name"] + "_renamed"}
        s.api("file", "renameFile", rename); s.verify_state("file", rename, None)
        parent = "autotest_dir_" + uuid.uuid4().hex
        folder = {"roomId": env["room_id"], "docId": parent, "parentId": env["file_parent_id"], "docName": "autotest_folder",
                  "docType": 0, "fileName": "", "fileExt": "", "fileSize": 0, "checkCode": 0, "creatorId": env["user_id"],
                  "fileWidth": 0, "fileHeight": 0, "subFileCount": 0, "fileUrl": "",
                  "fileServiceId": env["primary"]["services"]["FMFileSrv"]["id"]}
        def cleanup_folder():
            s.api("file", "delFile", {"roomId": env["room_id"], "docId": parent})
            assert not s.rows("SELECT DocID FROM t_roomdocslist WHERE RoomID=%s AND DocID=%s", [env["room_id"], parent])
        s.cleanups.insert(0, ("test parent directory", cleanup_folder))
        s.api("file", "addFile", folder)
        move = {"roomId": env["room_id"], "docId": f["doc_id"], "parentId": parent}
        s.api("file", "moveDocFile", move, business=0); s.verify_state("file", move, None)
        s.api("file", "delFile", {"roomId": env["room_id"], "docId": f["doc_id"]})
        s.case["method"] = "delFile"; s.verify_state("file", move, None)
        assert not s.rows("SELECT DocID FROM t_roomdocslist WHERE RoomID=%s AND DocID=%s", [env["absent_room_id"], f["doc_id"]])


def test_user_update_roundtrip(workflow):
    with workflow("user_update", fixture="user", requires=["write", "database", "user"]) as s:
        old = s.before["user"][0]
        params = {"userId": s.context["env"]["user_id"], "nickName": "autotest_" + s.context["case"]["random"],
                  "sex": old["Sex"], "tel": old["TelePhone"], "mobile": old["Mobile"], "mail": old["EMail"]}
        s.api("user", "updateUserInfo", params); s.verify_state("user", params, None)
        # Same-value update is valid: final state is checked, not row-count delta.
        s.api("user", "updateUserInfo", params); s.verify_state("user", params, None)


def test_user_permissions(workflow):
    with workflow("user_permissions", requires=["user_auth", "database", "user"]) as s:
        env = s.context["env"]
        params = {"nodeId": env["node_id"], "loginType": 1, "name": env["username"], "password": env["password"]}
        good = s.api("user", "verifyUser", params, business=0)
        original = s.rows("SELECT UserID,DisplayName FROM t_userinfo WHERE UserID=%s", [env["user_id"]])
        assert len(original) == 1
        bad = s.api("user", "verifyUser", dict(params, password="wrong_" + uuid.uuid4().hex), business=0)
        for observed in [good, bad]:
            assert_rules(observed, [{"path": "$.localUserId", "op": "eq", "value": int(original[0]["UserID"])},
                                    {"path": "$.nickname", "op": "eq", "value": original[0]["DisplayName"]},
                                    {"path": "$.role", "op": "type", "value": "string"},
                                    {"path": "$.result", "op": "type", "value": "int"}])
        assert {k: good[k] for k in ["localUserId", "nickname", "role", "result"]} == {
            k: bad[k] for k in ["localUserId", "nickname", "role", "result"]}, "Password variation changed identity lookup results"
        members = s.api("room", "verifyRoomUser", {"roomId": env["room_id"], "userType": 1,
                        "userId": env["user_id"], "checkType": 0, "password": ""}, business=0)
        assert members["roomId"] == env["room_id"] and type(members["right"]) is int
        allure.dynamic.label("test_group", "regression")
        allure.dynamic.label("issue_id", "CONTRACT-AUTH-RESPONSIBILITY")
        attach("Developer-confirmed identity lookup scope", {"login_type": 1, "correct_password_result": good,
               "wrong_password_result": bad, "scope": "Developer confirmed existing lookup behavior; upstream authentication is outside this test"})


def test_move_directory_to_root(workflow):
    with workflow("move_directory_to_root", fixture="file", method="moveDocFile", requires=["write", "database", "room", "file"]) as s:
        env = s.context["env"]
        parent = "autotest_dir_" + uuid.uuid4().hex
        def cleanup_parent():
            s.api("file", "delFile", {"roomId": env["room_id"], "docId": parent})
            assert not s.rows("SELECT DocID FROM t_roomdocslist WHERE RoomID=%s AND DocID=%s", [env["room_id"], parent])
        s.cleanups.insert(0, ("root-move parent", cleanup_parent))
        s.api("file", "addFile", {"roomId": env["room_id"], "docId": parent, "parentId": "", "docName": "autotest_parent",
              "docType": 0, "fileName": "", "fileExt": "", "fileSize": 0, "checkCode": 0, "creatorId": env["user_id"],
              "fileWidth": 0, "fileHeight": 0, "subFileCount": 0, "fileUrl": "",
              "fileServiceId": env["primary"]["services"]["FMFileSrv"]["id"]})
        params = {"roomId": env["room_id"], "docId": s.context["fixture"]["doc_id"], "parentId": parent}
        s.api("file", "moveDocFile", params, business=0)
        s.verify_state("file", params, None)
        params["parentId"] = ""
        s.api("file", "moveDocFile", params, business=0)
        s.verify_state("file", params, None)


def test_delete_empty_directory_positive(workflow):
    allure.dynamic.label("test_group", "backend_defect")
    allure.dynamic.label("issue_id", "BUG-DEL-DIR-SQL")
    with workflow("delete_empty_directory_positive", fixture="file", method="delDir", requires=["write", "database", "room", "file"]) as s:
        params = {"roomId": s.context["env"]["room_id"], "docId": s.context["fixture"]["doc_id"]}
        s.api("file", "delDir", params)
        assert not s.rows("SELECT DocID FROM t_roomdocslist WHERE RoomID=%s AND DocID=%s", [params["roomId"], params["docId"]]), "Valid directory delete was acknowledged but the record remains"
