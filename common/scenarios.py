"""API-owned preparation and reverse-order cleanup, with read-only DB oracles."""
import uuid
import time
from common.database import db_text
from common.mutation_fixtures import MutationFixtures


def same_rows(actual, expected):
    def canonical(rows):
        return sorted(tuple(sorted((k, db_text(v)) for k, v in row.items())) for row in rows)
    return canonical(actual) == canonical(expected)


class Scenario(MutationFixtures):
    def __init__(self, runtime, case):
        self.runtime, self.case = runtime, case
        self.context = {"env": runtime.env, "fixture": {},
                        "case": {"id": case["case_id"], "random": uuid.uuid4().hex[:12],
                                 "group_id": "{" + str(uuid.uuid4()) + "}"}}
        self.cleanups = []
        self.before = {}

    def api(self, cls, method, params, business=None):
        result = self.runtime.call(cls, method, params, success=True).legacy()
        if business is not None:
            assert result.get("result") == business, result
        return result

    def rows(self, sql, params=()):
        return self.runtime.database.fetch(sql, params)

    def add_cleanup(self, name, callback):
        self.cleanups.append((name, callback))

    def require_room_membership(self):
        from common.outcomes import blocked
        env = self.context["env"]
        rows = self.rows("SELECT UserID,UserOnline FROM t_roomusers WHERE RoomID=%s AND UserID=%s",
                         [env["room_id"], env["user_id"]])
        if len(rows) != 1:
            blocked("Configured user must be a member of the dedicated room",
                    {"room_id": env["room_id"], "user_id": env["user_id"], "matching_rows": len(rows)})
        return rows

    def close(self):
        errors = []
        for name, callback in reversed(self.cleanups):
            try:
                callback()
            except Exception as exc:
                errors.append("%s: %s" % (name, exc))
        if errors:
            raise RuntimeError("Cleanup failed (all remaining actions attempted):\n" + "\n".join(errors))

    def prepare(self):
        env, fixture = self.context["env"], self.context["fixture"]
        kind = self.case["fixture"]
        if kind == "none":
            return
        self.runtime.database.fetch("SELECT 1 AS oracle_available") if "database" in self.case.get("requires", []) else None
        if kind in {"meeting", "route", "file"} and env["room_id"] is None:
            raise RuntimeError("Environment blocked: configure a dedicated room_id")
        if kind in {"service", "node", "license", "feature", "master", "device", "route_timer"}:
            return self.prepare_mutation(kind)
        if kind == "meeting":
            room = env["room_id"]
            original = self.rows("SELECT RoomID,CurUserCount,CurrentServiceID FROM t_roominfo WHERE RoomID=%s", [room])
            if len(original) != 1 or int(original[0]["CurUserCount"] or 0) != 0 or int(original[0]["CurrentServiceID"] or 0) != 0:
                from common.outcomes import blocked
                blocked("Meeting fixture requires an existing idle dedicated room", {"room_id": room, "state": original})
            user_original = self.require_room_membership()
            service = env["primary"]["services"]["FMConfSrv"]["id"]
            fixture.update(service_id=service, group_id=self.context["case"]["group_id"])
            # For legacy parameter cases create a valid log before any stop request.
            log = self.api("room", "meetingLog", {"roomId": room, "groupId": fixture["group_id"]})
            fixture["meeting_id"] = log["meetingId"]
            def cleanup():
                self.api("room", "confRoomStop", {"roomId": room, "serviceId": service,
                         "meetingId": fixture["meeting_id"], "peakUserCount": 0})
                self.api("room", "updateRoomInfoByRoomId", {"roomId": room, "curUserCount": int(original[0]["CurUserCount"])})
                for user in user_original:
                    self.api("room", "updateRoomUserState", {"roomId": room, "userId": int(user["UserID"]), "online": int(user["UserOnline"])})
                restored = self.rows("SELECT RoomID,CurUserCount,CurrentServiceID FROM t_roominfo WHERE RoomID=%s", [room])
                assert same_rows(restored, original), "Room state did not restore"
            self.add_cleanup("meeting/room state", cleanup)
            if self.case["method"] != "confRoomStart":
                self.api("room", "confRoomStart", {"roomId": room, "serviceId": service,
                         "groupId": fixture["group_id"]}, business=0)
            self.before["room"] = self.rows("SELECT RoomID,CurUserCount,CurrentServiceID FROM t_roominfo WHERE RoomID=%s", [room])
        elif kind == "route":
            fixture.update(room_id=env["room_id"], app_id=env["test_route_app_id"],
                           node_id=env["primary"]["route_node"], address="TCP:127.0.0.1:54012;", auth_code=self.context["case"]["random"])
            key = [fixture["room_id"], fixture["app_id"], fixture["node_id"]]
            sql = "SELECT RoomID,SvrAppID,SvrNodeID,SvrAddr,SvrAuthCode FROM t_roomroute WHERE RoomID=%s AND SvrAppID=%s AND SvrNodeID=%s"
            original = self.rows(sql, key)
            scope_sql = "SELECT RoomID,SvrAppID,SvrNodeID,SvrAddr,SvrAuthCode FROM t_roomroute WHERE SvrAppID=%s OR (RoomID=%s AND SvrAppID=0)"
            original_scope = self.rows(scope_sql, [fixture["app_id"], fixture["room_id"]])
            def cleanup():
                for row in self.rows(scope_sql, [fixture["app_id"], fixture["room_id"]]):
                    self.api("room", "delRoomRoute", {"roomId": int(row["RoomID"]), "svrAppId": int(row["SvrAppID"]), "svrNodeId": row["SvrNodeID"]})
                for row in original_scope:
                    self.api("room", "replaceRoomRoute", {"roomId": int(row["RoomID"]), "svrAppId": int(row["SvrAppID"]), "svrNodeId": row["SvrNodeID"],
                             "svrAddress": row["SvrAddr"], "svrAuthCode": row["SvrAuthCode"]})
                assert same_rows(self.rows(scope_sql, [fixture["app_id"], fixture["room_id"]]), original_scope), "Route scope did not restore"
            self.add_cleanup("route", cleanup)
            self.api("room", "replaceRoomRoute", {"roomId": key[0], "svrAppId": key[1], "svrNodeId": key[2],
                     "svrAddress": fixture["address"], "svrAuthCode": fixture["auth_code"]})
            self.before["route"] = self.rows(scope_sql, [fixture["app_id"], fixture["room_id"]])
            ticks = self.rows("SELECT " + self.runtime.database.epoch_expression("UpdateTime") + " AS tick FROM t_roomroute WHERE RoomID=%s AND SvrAppID=%s AND SvrNodeID=%s", key)
            self.before["route_tick"] = int(ticks[0]["tick"] or 0)
        elif kind == "file":
            fixture.update(doc_id="autotest_" + uuid.uuid4().hex, parent_id=env["file_parent_id"], name="autotest_" + self.context["case"]["random"])
            params = {"roomId": env["room_id"], "docId": fixture["doc_id"], "parentId": fixture["parent_id"],
                      "docName": fixture["name"], "docType": 0 if self.case["method"] in {"moveDocFile", "delDir"} else 2, "fileName": fixture["name"], "fileExt": "txt",
                      "fileSize": 1, "checkCode": 1, "creatorId": env["user_id"], "fileWidth": 0,
                      "fileHeight": 0, "subFileCount": 0, "fileUrl": "autotest.txt",
                      "fileServiceId": env["primary"]["services"]["FMFileSrv"]["id"]}
            def cleanup():
                self.api("file", "delFile", {"roomId": env["room_id"], "docId": fixture["doc_id"]})
                assert not self.rows("SELECT DocID FROM t_roomdocslist WHERE RoomID=%s AND DocID=%s", [env["room_id"], fixture["doc_id"]]), "File cleanup did not delete the record"
            self.add_cleanup("file", cleanup)
            if self.case["method"] != "addFile":
                self.api("file", "addFile", params)
                self.before["file"] = self.rows("SELECT DocID,DocName,ParentID FROM t_roomdocslist WHERE RoomID=%s AND DocID=%s", [env["room_id"], fixture["doc_id"]])
                assert len(self.before["file"]) == 1, "File preparation did not create a record"
        elif kind == "user_identity":
            rows = self.rows("SELECT UserID,UserName,DisplayName FROM t_userinfo WHERE UserID=%s", [env["user_id"]])
            if len(rows) != 1 or rows[0]["UserName"] != env["username"]:
                from common.outcomes import blocked
                blocked("Identity fixture needs matching configured user_id and username")
            fixture["nickname"] = rows[0]["DisplayName"]
        elif kind == "user":
            if self.runtime.profile.get("user_fixture_mode", "configured_user") == "temporary_api":
                from common.user_fixtures import prepare_temporary_user
                prepare_temporary_user(self)
                env = self.context["env"]
            rows = self.rows("SELECT UserID,DisplayName,Sex,TelePhone,Mobile,EMail FROM t_userinfo WHERE UserID=%s", [env["user_id"]])
            if len(rows) != 1:
                raise RuntimeError("Environment blocked: configured user_id does not exist")
            self.before["user"] = rows
            if self.case["case_id"] == "user-014":
                limits = self.runtime.database.text_column_length("t_userinfo", "Sex")
                if len(limits) != 1 or not 0 < int(limits[0]["max_length"] or 0) < 4096:
                    raise RuntimeError("Cannot derive a bounded Sex length boundary from the target schema")
                fixture["sex_over_limit"] = "X" * (int(limits[0]["max_length"]) + 1)
            row = rows[0]
            fixture.update(original_nickname=row["DisplayName"], original_tel=row["TelePhone"],
                           original_mobile=row["Mobile"], original_mail=row["EMail"])
            # Current deployed UserSex uses string codes 0/1; unrelated phone
            # and email cases must not accidentally exercise invalid sex text.
            fixture["sex_valid"] = row["Sex"] if row["Sex"] in {"0", "1"} else "0"
            if self.runtime.profile.get("user_update_mode") == "nonempty_fields":
                from common.references import resolve
                from common.outcomes import blocked
                proposed = resolve(self.case.get("params", {}), self.context)
                unsafe = [field for field, column in {"nickName": "DisplayName", "sex": "Sex", "tel": "TelePhone",
                          "mobile": "Mobile", "mail": "EMail"}.items()
                          if row[column] in (None, "") and isinstance(proposed.get(field), str) and proposed[field].strip()]
                if unsafe:
                    blocked("User fixture cannot restore empty original fields through the current nonempty-only API: " + ", ".join(unsafe),
                            {"user_id": env["user_id"], "fields": unsafe})
            params = {"userId": env["user_id"], "nickName": row["DisplayName"], "sex": row["Sex"],
                      "tel": row["TelePhone"], "mobile": row["Mobile"], "mail": row["EMail"]}
            self.add_cleanup("user", lambda: self._restore_user(params, rows))
        elif kind == "system_param":
            name = self.case["params"]["paramName"]
            original = self.rows("SELECT ParamName,ParamValue FROM t_systemparam WHERE ParamName=%s", [name])
            if len(original) != 1:
                from common.outcomes import blocked
                blocked("System parameter must have exactly one restorable row", {"param_name": name, "matching_rows": len(original)})
            self.before["system_param"] = original
            fixture["original_value"] = original[0]["ParamValue"]
            self.add_cleanup("system parameter", lambda: self._restore_param(name, original))
        elif kind == "face_rollcall":
            log = self.api("room", "meetingLog", {"roomId": env["room_id"], "groupId": self.context["case"]["group_id"]})
            roll = self.api("user", "insertIntoFaceRollCall", {"rollCallTitle": "autotest_" + self.context["case"]["random"],
                            "countdownTime": 1, "userId": env["user_id"], "userName": env["username"], "meetingId": log["meetingId"]})
            fixture["rollcall_id"] = roll["rollCallId"]
            self.before["face_members"] = self.rows("SELECT COUNT(*) AS member_count FROM t_face_rollcall_users WHERE rollcall_id=%s", [fixture["rollcall_id"]])
            from common.executor import attach
            attach("Retained point-in-time test log", {"meeting_id": log["meetingId"], "rollcall_id": fixture["rollcall_id"],
                   "reason": "Gateway exposes insert but no deletion API for meeting/rollcall logs"})
        else:
            raise RuntimeError("Fixture %s is restricted to its Python lifecycle workflow" % kind)

    def _restore_user(self, params, original):
        self.api("user", "updateUserInfo", params)
        rows = self.rows("SELECT UserID,DisplayName,Sex,TelePhone,Mobile,EMail FROM t_userinfo WHERE UserID=%s", [params["userId"]])
        assert same_rows(rows, original), "User state did not restore"

    def wait_for_route_clock_tick(self):
        # MySQL NOW() uses second precision. Poll the server clock, never retry a write.
        deadline = time.monotonic() + 10
        while int(self.rows("SELECT " + self.runtime.database.epoch_expression("CURRENT_TIMESTAMP") + " AS tick")[0]["tick"]) <= self.before["route_tick"]:
            if time.monotonic() >= deadline:
                raise RuntimeError("Server clock did not advance for route timestamp verification")
            time.sleep(0.2)

    def _restore_param(self, name, original):
        value = original[0]["ParamValue"]
        self.api("device", "updateSystemParam", {"paramName": name, "paramValue": value})
        assert self.api("device", "getSystemParam", {"paramName": name}).get("paramValue") == value
        assert same_rows(self.rows("SELECT ParamName,ParamValue FROM t_systemparam WHERE ParamName=%s", [name]), original), "System parameter snapshot did not restore"

    def verify_state(self, checker, params, result):
        env, fixture = self.context["env"], self.context["fixture"]
        if checker in {"license", "feature", "node", "service", "device"}:
            return self.verify_mutation(checker, params)
        if checker == "service_list":
            rows = self.rows("SELECT ServiceID,ServiceAppID,ServiceName,ServiceAddrs,ServiceStatus FROM t_serviceinfo WHERE DevID=%s", [params["devId"]])
            actual = result.legacy().get("data", [])
            expected = [{"serviceId": int(r["ServiceID"]), "serviceAppId": int(r["ServiceAppID"]),
                         "serviceName": r["ServiceName"], "serviceAddress": r["ServiceAddrs"],
                         "serviceStatus": str(r["ServiceStatus"])} for r in rows]
            assert same_rows(actual, expected), "Service query differs from the configured device's database records"
        elif checker == "system_param":
            actual = self.api("device", "getSystemParam", {"paramName": params["paramName"]})
            assert actual.get("paramValue") == params.get("paramValue"), actual
            rows = self.rows("SELECT ParamName,ParamValue FROM t_systemparam WHERE ParamName=%s", [params["paramName"]])
            assert len(rows) == 1 and db_text(rows[0]["ParamValue"]) == db_text(params.get("paramValue")), "System parameter row/value differs from request"
        elif checker == "device_list":
            selected = [env[role]["device_id"] for role in (["primary", "secondary"] if env["topology"] == "dual" else ["primary"])]
            placeholders = ",".join(["%s"] * len(selected))
            expected = self.rows("SELECT DevID,DevName,DevType,DevIP FROM t_devinfo WHERE DevID IN (" + placeholders + ")", selected)
            actual = result.legacy().get("data")
            assert isinstance(actual, list) and all(isinstance(item, dict) for item in actual), "Device list must contain records"
            matching = [item for item in actual if item.get("devId") in selected]
            assert len(expected) == len(selected) == len(matching), "Configured devices must occur exactly once"
            fields = {"DevID": "devId", "DevName": "devName", "DevType": "devType", "DevIP": "devIp"}
            observed = [{column: item.get(field) for column, field in fields.items()} for item in matching]
            assert same_rows(observed, expected), "Device identities differ from read-only database records"
            for item in matching:
                cpu = item.get("cpuLoad")
                assert type(cpu) is int and 0 <= cpu <= 100, "Invalid CPU percentage for %s: %r" % (item["devId"], cpu)
        elif checker == "user":
            rows = self.rows("SELECT DisplayName,Sex,TelePhone,Mobile,EMail FROM t_userinfo WHERE UserID=%s", [params.get("userId")])
            assert len(rows) == 1, "Updated user must exist"
            for key, column in {"nickName": "DisplayName", "sex": "Sex", "tel": "TelePhone", "mobile": "Mobile", "mail": "EMail"}.items():
                wanted = self.before["user"][0][column]
                if key in params and (self.runtime.profile.get("user_update_mode") != "nonempty_fields"
                                      or params[key] not in (None, "")):
                    wanted = params[key]
                assert db_text(rows[0][column]) == db_text(wanted), (key, rows[0])
        elif checker in {"route", "route_time", "route_precreate"}:
            key = [params.get("roomId"), params.get("svrAppId"), params.get("svrNodeId")]
            rows = self.rows("SELECT RoomID,SvrAppID,SvrNodeID,SvrAddr,SvrAuthCode,UpdateTime FROM t_roomroute WHERE RoomID=%s AND SvrAppID=%s AND SvrNodeID=%s", key)
            if self.case["method"] == "delRoomRoute":
                assert not rows, "Deleted route still exists"
            else:
                assert len(rows) == 1, "Expected one route"
                if checker in {"route", "route_precreate"}:
                    for key, column in {"svrAddress": "SvrAddr", "svrAuthCode": "SvrAuthCode"}.items():
                        assert db_text(rows[0][column]) == db_text(params[key]), rows
                    if checker == "route_precreate":
                        columns = {"roomId": "RoomID", "svrAppId": "SvrAppID", "svrNodeId": "SvrNodeID",
                                   "svrAddress": "SvrAddr", "svrAuthCode": "SvrAuthCode"}
                        inserted = {column: params[field] for field, column in columns.items()}
                        current = self.rows("SELECT RoomID,SvrAppID,SvrNodeID,SvrAddr,SvrAuthCode FROM t_roomroute WHERE SvrAppID=%s OR (RoomID=%s AND SvrAppID=0)",
                                            [fixture["app_id"], fixture["room_id"]])
                        expected = self.before["route"] + [inserted]
                        from common.executor import attach
                        attach("Precreated route scope verification", {"before": self.before["route"], "inserted": inserted, "after": current})
                        assert same_rows(current, expected), "Precreation must add exactly the requested route and preserve existing routes"
                else:
                    ticks = self.rows("SELECT " + self.runtime.database.epoch_expression("UpdateTime") + " AS tick FROM t_roomroute WHERE RoomID=%s AND SvrAppID=%s AND SvrNodeID=%s", key)
                    assert int(ticks[0]["tick"] or 0) > self.before["route_tick"], "Route timestamp did not advance"
        elif checker == "file":
            rows = self.rows("SELECT DocID,DocName,ParentID FROM t_roomdocslist WHERE RoomID=%s AND DocID=%s", [params.get("roomId"), params.get("docId")])
            if self.case["method"] == "delFile":
                assert not rows, "Deleted file still exists"
            else:
                assert len(rows) == 1, "Expected one file"
                for key, column in {"docName": "DocName", "parentId": "ParentID"}.items():
                    if key in params:
                        assert db_text(rows[0][column]) == db_text(params[key]), rows
                if self.case.get("verification", {}).get("preserve_other_fields"):
                    expected = dict(self.before["file"][0])
                    for field, column in {"docName": "DocName", "parentId": "ParentID"}.items():
                        if field in params:
                            expected[column] = params[field]
                    from common.executor import attach
                    attach("File relation assignment verification", {"before": self.before["file"], "expected": expected, "after": rows})
                    assert same_rows(rows, [expected]), "File relation update changed an unrelated field"
        elif checker == "room_count":
            rows = self.rows("SELECT CurUserCount FROM t_roominfo WHERE RoomID=%s", [params.get("roomId")])
            assert len(rows) == 1 and int(rows[0]["CurUserCount"]) == params["curUserCount"], rows
        elif checker == "room_user":
            rows = self.rows("SELECT UserOnline FROM t_roomusers WHERE RoomID=%s AND UserID=%s", [params.get("roomId"), params.get("userId")])
            assert len(rows) == 1 and int(rows[0]["UserOnline"]) == params["online"], rows
        elif checker == "license_time":
            assert self.api("device", "getLastLicenseTime", {}).get("lastUpdateTime") == params["lastUpdateTime"]
        elif checker == "no_change":
            target = self.case["verification"]["target"]
            if target == "user":
                current = self.rows("SELECT UserID,DisplayName,Sex,TelePhone,Mobile,EMail FROM t_userinfo WHERE UserID=%s", [env["user_id"]])
            elif target == "route":
                current = self.rows("SELECT RoomID,SvrAppID,SvrNodeID,SvrAddr,SvrAuthCode FROM t_roomroute WHERE SvrAppID=%s OR (RoomID=%s AND SvrAppID=0)", [fixture["app_id"], fixture["room_id"]])
            elif target == "file":
                current = self.rows("SELECT DocID,DocName,ParentID FROM t_roomdocslist WHERE RoomID=%s AND DocID=%s", [env["room_id"], fixture["doc_id"]])
            elif target == "room":
                current = self.rows("SELECT RoomID,CurUserCount,CurrentServiceID FROM t_roominfo WHERE RoomID=%s", [env["room_id"]])
            elif target == "feature":
                current = self.rows("SELECT global_switch FROM t_features WHERE code='DocumentConversion'")
            elif target == "master":
                current = self.rows("SELECT devid,address,servertype FROM t_master_slave WHERE servertype IN (%s,0)", [fixture["server_type"]])
            elif target == "face_members":
                current = self.rows("SELECT COUNT(*) AS member_count FROM t_face_rollcall_users WHERE rollcall_id=%s", [fixture["rollcall_id"]])
            else:
                raise ValueError("Unknown no_change target")
            from common.executor import attach
            attach("Negative request state comparison", {"target": target, "before": self.before[target], "after": current})
            assert same_rows(current, self.before[target]), "Negative request changed the prepared resource"
        else:
            raise ValueError("State checker is not implemented: " + checker)
