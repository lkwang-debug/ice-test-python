"""Single-meeting stateful tests: capture via SELECT, restore through gateway APIs."""
from common.database import db_text

LICENSE_FIELDS = {
    "supDogSerialId": "SupDogSerialID", "accessCount": "AccessCount", "endTime": "LimitedEndTime",
    "startTime": "LimitedStartTime", "phoneCount": "PhoneCallCount", "h323Count": "H323CallCount",
    "supportRecord": "RecordCount", "isShowLimitedTime": "ShowLimitedTime", "maxVideoWidth": "MaxVideoWidth",
    "maxVideoHeight": "MaxVideoHeight", "businessName": "BusinessName", "authSeq": "AuthSequence",
    "fspType": "LicenseType", "liveLicense": "LiveLicense", "liveRoomCount": "LiveRoomCount",
    "liveUserCount": "LiveUserCount", "recordType": "RecordType", "recordPoint": "RecordPoint",
    "devSdk": "DevSdk", "4KCount": "FourKCount", "licenseStatus": "LicenseStatue", "lastUpdateTime": "LastUpdateTime"}


def as_int(v):
    return int(v or 0)


class MutationFixtures:
    def prepare_mutation(self, kind):
        env, fixture = self.context["env"], self.context["fixture"]
        if kind == "service":
            secondary = self.case["topology"] == "dual"
            device = env["secondary" if secondary else "primary"]["device_id"]
            app = env["test_service_app_id"]
            fixture.update(device_id=device, app_id=app, address="TCP:127.0.0.1:54011;", name="autotest_service")
            sql = "SELECT ServiceID,ServiceAppID,ServiceName,ServiceAddrs,ServiceStatus FROM t_serviceinfo WHERE DevID=%s AND ServiceAppID IN (%s,0)"
            original = self.rows(sql, [device, app])
            def restore():
                current = self.rows(sql, [device, app])
                old = {as_int(r["ServiceAppID"]): r for r in original}
                for row in current:
                    previous = old.get(as_int(row["ServiceAppID"]))
                    if previous:
                        self.api("device", "registerService", {"deviceId": device, "srvAppId": as_int(row["ServiceAppID"]),
                                 "srvName": previous["ServiceName"], "srvAddress": previous["ServiceAddrs"],
                                 "state": as_int(previous["ServiceStatus"])}, business=0)
                    else:
                        self.api("device", "serviceUnregister", {"serviceId": as_int(row["ServiceID"])})
            self.add_cleanup("service registry snapshot", restore)
            prepared = self.api("device", "registerService", {"deviceId": device, "srvAppId": app,
                                "srvName": fixture["name"], "state": 1, "srvAddress": fixture["address"]}, business=0)
            fixture["service_id"] = prepared["serviceId"]
            self.before["service"] = self.rows(sql, [device, app])
        elif kind == "route_timer":
            sql = "SELECT RoomID,SvrAppID,SvrNodeID,SvrAddr,SvrAuthCode FROM t_roomroute"
            original = self.rows(sql)
            groups = [(row["RoomID"], row["SvrAppID"]) for row in original]
            if len(groups) != len(set(groups)):
                raise RuntimeError("Route timer fixture cannot restore multiple nodes in one room/app through replaceRoomRoute")
            self.before["route_timer"] = original
            def restore_routes():
                from common.scenarios import same_rows
                for row in original:
                    current = self.rows(sql + " WHERE RoomID=%s AND SvrAppID=%s", [int(row["RoomID"]), int(row["SvrAppID"])])
                    if not same_rows(current, [row]):
                        self.api("room", "replaceRoomRoute", {"roomId": int(row["RoomID"]), "svrAppId": int(row["SvrAppID"]),
                                 "svrNodeId": row["SvrNodeID"], "svrAddress": row["SvrAddr"], "svrAuthCode": row["SvrAuthCode"]})
                assert same_rows(self.rows(sql), original), "Timer cleanup did not restore routing records"
            self.add_cleanup("route timer snapshot (timestamps refreshed through API)", restore_routes)
        elif kind == "node":
            original = self.rows("SELECT NodeID,IsLocal,NodeManAddr,StatusReasons,CheckCode FROM t_nodeinfo")
            self.before["node"] = original
            def restore():
                for row in original:
                    if as_int(row["IsLocal"]):
                        self.api("device", "startLocalNode", {"nodeId": row["NodeID"], "address": row["NodeManAddr"]})
                    else:
                        self.api("device", "frontNodeRegister", {"nodeId": row["NodeID"], "nodeCheckCode": row["CheckCode"],
                                 "subNodeAddress": row["NodeManAddr"]})
                    self.api("device", "setNodeStatus", {"nodeId": row["NodeID"], "status": as_int(row["StatusReasons"])})
                from common.scenarios import same_rows
                assert same_rows(self.rows("SELECT NodeID,IsLocal,NodeManAddr,StatusReasons,CheckCode FROM t_nodeinfo"), original), "Node restore did not match snapshot"
            self.add_cleanup("node address/status snapshot", restore)
        elif kind == "license":
            original = self.rows("SELECT * FROM t_licenseinfo WHERE ID=0")
            if len(original) != 1:
                raise RuntimeError("License row ID=0 is missing")
            row = original[0]
            self.before["license"] = row
            features = self.rows("SELECT code,feature_value,global_switch FROM t_features WHERE code IN ('fsp.login.enable','fsp.ss2.enable','fsp.ss.enable')")
            if self.case["method"] == "updateLicenseInfo" and any(as_int(f["global_switch"]) != 1 or f["feature_value"] != "true" for f in features):
                raise RuntimeError("Target license update changes FSP flags; current API cannot restore disabled flags")
            params = {key: str(row[column] or "") if key in {"supDogSerialId", "businessName", "authSeq"}
                      else bool(as_int(row[column])) if key == "devSdk" else as_int(row[column])
                      for key, column in LICENSE_FIELDS.items()}
            def restore():
                if self.case["method"] == "updateLicenseInfo":
                    self.api("device", "updateLicenseInfo", params)
                self.api("device", "updateLicenseState", {"licenseStatus": as_int(row["LicenseStatue"]),
                         "lastUpdateTime": as_int(row["LastUpdateTime"])})
                restored = self.rows("SELECT * FROM t_licenseinfo WHERE ID=0")[0]
                # The license daemon refreshes LastUpdateTime concurrently.
                differences = {k: {"expected": row[k], "actual": restored[k]} for k in row if k != "LastUpdateTime" and db_text(restored[k]) != db_text(row[k])}
                assert not differences, "License snapshot restoration failed: %r" % differences
            self.add_cleanup("license snapshot", restore)
        elif kind == "feature":
            row = self.rows("SELECT global_switch FROM t_features WHERE code='DocumentConversion'")
            if len(row) != 1:
                raise RuntimeError("DocumentConversion feature is missing")
            self.before["feature"] = row
            def restore():
                self.api("device", "setDocumentConversionSwitch", {"globalSwitch": bool(as_int(row[0]["global_switch"]))})
                assert self.rows("SELECT global_switch FROM t_features WHERE code='DocumentConversion'") == row
            self.add_cleanup("document conversion feature", restore)
        elif kind == "master":
            server_type = self.runtime.profile.get("test_master_server_type", 54013)
            fixture["server_type"] = server_type
            original = self.rows("SELECT devid,address,servertype FROM t_master_slave WHERE servertype IN (%s,0)", [server_type])
            self.before["master"] = original
            def restore():
                for row in self.rows("SELECT devid,servertype FROM t_master_slave WHERE servertype IN (%s,0)", [server_type]):
                    self.api("device", "changeToSlave", {"serverType": as_int(row["servertype"]), "devId": row["devid"]})
                for row in original:
                    self.api("device", "tryChangeToMaster", {"serverType": as_int(row["servertype"]), "devId": row["devid"], "address": row["address"]})
                from common.scenarios import same_rows
                assert same_rows(self.rows("SELECT devid,address,servertype FROM t_master_slave WHERE servertype IN (%s,0)", [server_type]), original), "Master identity snapshot did not restore"
            self.add_cleanup("isolated master role", restore)
        elif kind == "device":
            role = "secondary" if self.case["topology"] == "dual" else "primary"
            device = env[role]["device_id"]
            original = self.rows("SELECT * FROM t_devinfo WHERE DevID=%s", [device])
            if len(original) != 1:
                raise RuntimeError("Device snapshot target not found")
            row = original[0]; self.before["device"] = row
            services = self.rows("SELECT ServiceAppID,ServiceName,ServiceAddrs,ServiceStatus FROM t_serviceinfo WHERE DevID=%s", [device])
            rooms = self.rows("SELECT RoomID,CurUserCount,CurrentServiceID,group_id FROM t_roominfo WHERE CurrentServiceID IN (SELECT ServiceID FROM t_serviceinfo WHERE DevID=%s)", [device])
            users = self.rows("SELECT RoomID,UserID,UserOnline FROM t_roomusers WHERE UserOnline<>0") if self.case["method"] == "devUnRegister" else []
            route_sql = "SELECT RoomID,SvrAppID,SvrNodeID,SvrAddr,SvrAuthCode FROM t_roomroute"
            # Device registration/unregistration may clear routes beyond this device.
            routes = self.rows(route_sql)
            for route in routes:
                group = self.rows(route_sql + " WHERE RoomID=%s AND SvrAppID=%s", [as_int(route["RoomID"]), as_int(route["SvrAppID"])])
                if len(group) != 1:
                    from common.outcomes import blocked
                    blocked("Device cleanup cannot safely restore a multi-node routing group", {"room_id": route["RoomID"], "app_id": route["SvrAppID"]})
            def restore():
                self.api("device", "devRegister", {"deviceId": device, "verifyCode": env[role]["verify_code"],
                         "deviceAddress": row["DevIP"], "deviceType": as_int(row["DevType"]), "online": as_int(row["CurOnline"]),
                         "bandWidth": as_int(row["CurBandwidth"]), "roomCount": as_int(row["CurRoomCount"]), "cpuLoad": as_int(row["CPULoad"])}, business=0)
                self.api("device", "devUpdate2", {"deviceId": device, "verifyCode": env[role]["verify_code"],
                         "deviceAddress": row["DevIP"], "online": as_int(row["CurOnline"]), "bandWidth": as_int(row["CurBandwidth"]),
                         "roomCount": as_int(row["CurRoomCount"]), "cpuLoad": as_int(row["CPULoad"]), "memLoad": as_int(row.get("MemoryLoad"))})
                for srv in services:
                    self.api("device", "registerService", {"deviceId": device, "srvAppId": as_int(srv["ServiceAppID"]),
                             "srvName": srv["ServiceName"], "srvAddress": srv["ServiceAddrs"], "state": as_int(srv["ServiceStatus"])})
                if self.case["method"] == "devUnRegister":
                    for room in rooms:
                        self.api("room", "confRoomStart", {"roomId": as_int(room["RoomID"]), "serviceId": as_int(room["CurrentServiceID"]), "groupId": room["group_id"]})
                        self.api("room", "updateRoomInfoByRoomId", {"roomId": as_int(room["RoomID"]), "curUserCount": as_int(room["CurUserCount"])})
                    for user in users:
                        self.api("room", "updateRoomUserState", {"roomId": as_int(user["RoomID"]), "userId": as_int(user["UserID"]), "online": as_int(user["UserOnline"])})
                self.api("device", "updateDevInfoStatusByDevId", {"devId": device, "verifyCode": env[role]["verify_code"], "devStatus": str(row["DevStatus"])})
                from common.scenarios import same_rows
                for route in routes:
                    key = [as_int(route["RoomID"]), as_int(route["SvrAppID"])]
                    current = self.rows(route_sql + " WHERE RoomID=%s AND SvrAppID=%s", key)
                    if not same_rows(current, [route]):
                        self.api("room", "replaceRoomRoute", {"roomId": key[0], "svrAppId": key[1],
                                 "svrNodeId": route["SvrNodeID"], "svrAddress": route["SvrAddr"], "svrAuthCode": route["SvrAuthCode"]})
                    assert same_rows(self.rows(route_sql + " WHERE RoomID=%s AND SvrAppID=%s", key), [route]), "Device cleanup route did not restore"
            self.add_cleanup("device/services/room snapshot", restore)
        else:
            raise ValueError("Unknown mutation fixture: " + kind)

    def verify_mutation(self, checker, params):
        if checker == "license":
            current = self.rows("SELECT * FROM t_licenseinfo WHERE ID=0")[0]
            for key, column in LICENSE_FIELDS.items():
                if key in params:
                    desired = int(params[key]) if isinstance(params[key], bool) else params[key]
                    assert db_text(current[column]) == db_text(desired), "%s was not persisted" % key
        elif checker == "feature":
            row = self.rows("SELECT global_switch FROM t_features WHERE code='DocumentConversion'")[0]
            assert as_int(row["global_switch"]) == int(bool(params["globalSwitch"]))
        elif checker == "node":
            row = self.rows("SELECT StatusReasons,NodeManAddr FROM t_nodeinfo WHERE NodeID=%s", [params.get("nodeId")])
            if not row:
                return  # Explicit missing-node contract cases are checked by response.
            if self.case["method"] == "setNodeStatus" and params.get("status") is not None:
                assert as_int(row[0]["StatusReasons"]) == params["status"]
            if self.case["method"] == "stopLocalNode":
                assert as_int(row[0]["StatusReasons"]) == 10
            if self.case["method"] == "startLocalNode" and params.get("address") is not None:
                assert row[0]["NodeManAddr"] == params["address"]
        elif checker == "service":
            f = self.context["fixture"]
            rows = self.rows("SELECT ServiceStatus,ServiceAddrs FROM t_serviceinfo WHERE DevID=%s AND ServiceAppID=%s", [f["device_id"], f["app_id"]])
            assert len(rows) == 1
            if self.case["method"] == "serviceUnregister" and params.get("serviceId") == f["service_id"]:
                assert as_int(rows[0]["ServiceStatus"]) == 0
            if self.case["method"] == "registerService" and params.get("deviceId") == f["device_id"] and params.get("srvAppId") == f["app_id"]:
                assert rows[0]["ServiceAddrs"] == params.get("srvAddress")
        elif checker == "device":
            device = self.before["device"]["DevID"]
            row = self.rows("SELECT DevID,DevOnline FROM t_devinfo WHERE DevID=%s", [device])
            assert len(row) == 1 and row[0]["DevID"] == device
        else:
            raise ValueError(checker)
