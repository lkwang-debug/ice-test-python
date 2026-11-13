"""A run-scoped gateway connection and explicit environment resource identities."""
import copy
import json
import os
import time
import uuid
from pathlib import Path
from common.assertions import assert_rules
from common.database import ReadonlyDatabase, db_text

APP_IDS = {"FMFileSrv": 3, "FMFileMgrSrv": 10, "FMConfSrv": 11, "FMFrontSrv": 20, "FMWebProxy": 65528}


class GatewayRuntime:
    def __init__(self, profile, client_factory=None):
        self.profile = profile
        self.topology = profile.get("topology", "single")
        if self.topology not in ("single", "dual"):
            raise ValueError("Invalid environment topology")
        self.client_factory = client_factory
        self.client = None
        self._env = None
        self.database = ReadonlyDatabase(profile.get("database"))
        self.run_id = uuid.uuid4().hex
        self.method_support = {}
        self._resources_validated = False

    def close(self):
        if self.client:
            self.client.disconnect()
        self.database.close()

    def call(self, cls, method, params, success=False):
        if self.client is None:
            if self.client_factory:
                self.client = self.client_factory()
            else:
                from common.ice_client import IceClient
                self.client = IceClient()
                if self.profile.get("host"):
                    from common.config import build_ice_locator
                    self.client.locator = build_ice_locator(self.profile["host"], self.profile.get("locator_port", 22000),
                                                            self.profile.get("protocol", "tcp"))
                self.client.service = self.profile.get("service", self.client.service)
                self.client.adapter = self.profile.get("adapter", self.client.adapter)
            if not self.client.connect():
                raise RuntimeError("Environment blocked: cannot connect to configured gateway")
        wire_method = self.profile.get("method_aliases", {}).get(cls + "." + method, method)
        result = self.client.invoke_result(cls, wire_method, params, self.profile.get("version", "1.0"))
        if result.error:
            raise RuntimeError(result.error)
        if success:
            assert result.invoke_code == 0 and result.response_code == 0, result.evidence()
        return result

    def query(self, cls, method, params):
        return self.call(cls, method, params, success=True).legacy()

    @property
    def env(self):
        if self._env is None:
            devices = self.query("device", "checkDevList", {}).get("data", [])
            env = {"topology": self.topology, "room_id": self.profile.get("room_id"),
                   "user_id": self.profile.get("user_id"), "username": self.profile.get("username"),
                   "password": os.environ.get(self.profile.get("user_password_env", "ICE_TEST_USER_PASSWORD"), self.profile.get("user_password", "")),
                   "absent_device_id": "missing_" + self.run_id[:12],
                   "absent_room_id": self.profile.get("absent_room_id", 2147483000),
                   "test_service_app_id": self.profile.get("test_service_app_id", 54011),
                   "test_route_app_id": self.profile.get("test_route_app_id", 54012),
                   "file_parent_id": self.profile.get("file_parent_id", "")}
            if "record_global_switch" in self.profile:
                configured = self.profile["record_global_switch"]
                env["record_global_switch"] = self.record_switch(env["room_id"]) if configured is None else configured
            if "record_config" in self.profile.get("capabilities", []):
                env["record_enable_ext_full_record"] = self.record_extra_switch(env["room_id"])
            for role in (["primary", "secondary"] if self.topology == "dual" else ["primary"]):
                device_id = self.profile.get(role + "_device_id")
                matches = [d for d in devices if d.get("devId") == device_id]
                if len(matches) != 1:
                    raise RuntimeError("Environment blocked: expected exactly one %s device %r" % (role, device_id))
                item = matches[0]
                services = self.query("device", "getServiceList", {"devId": device_id}).get("data", [])
                mapping = {}
                for name, app in APP_IDS.items():
                    found = [s for s in services if s.get("serviceAppId") == app]
                    if len(found) > 1:
                        raise RuntimeError("Duplicate service identity: %s/%s" % (device_id, app))
                    if found:
                        mapping[name] = {"id": found[0]["serviceId"], "address": found[0].get("serviceAddress", ""),
                                         "app_id": app}
                env[role] = {"device_id": device_id, "node_id": item["devNodeId"],
                             "address": item.get("devIp", ""), "services": mapping,
                             "route_node": "NID:%s$DID:%s" % (item["devNodeId"], device_id),
                             "verify_code": os.environ.get(self.profile.get(role + "_verify_code_env", "ICE_DEVICE_VERIFY_CODE"), self.profile.get("device_verify_code", "1111"))}
            if self.topology == "dual":
                if env["primary"]["device_id"] == env["secondary"]["device_id"]:
                    raise RuntimeError("Dual topology requires two distinct devices")
                if env["primary"]["node_id"] != env["secondary"]["node_id"]:
                    raise RuntimeError("This dual profile requires two devices on the same node")
            env["node_id"] = env["primary"]["node_id"]
            if "face" in self.profile.get("capabilities", []):
                configured = self.profile.get("face_id")
                legacy = self.database.fetch("SELECT face_id,user_name FROM t_faceinfo WHERE face_id=%s", [configured]) if configured is not None else self.database.fetch("SELECT face_id,user_name FROM t_faceinfo ORDER BY face_id LIMIT 1")
                modern = self.database.fetch("SELECT id,source_id,source_type FROM t_face_library ORDER BY id DESC LIMIT 1")
                legacy_total = int(self.database.fetch("SELECT COUNT(*) AS total FROM t_faceinfo")[0]["total"])
                # IDs from these tables are different identities; never fall back.
                env["face_id"] = int(legacy[0]["face_id"]) if legacy else None
                env["face_data_source"] = "legacy" if legacy else "modern_only" if modern else "empty"
                env["modern_face_present"] = bool(modern)
                env["legacy_face_total"] = legacy_total
                env["configured_face_id"] = configured
            self._env = env
        return copy.deepcopy(self._env)

    def record_switch(self, room_id):
        from common.outcomes import blocked
        if room_id is None or not self.database.fetch("SELECT RoomID FROM t_roominfo WHERE RoomID=%s", [room_id]):
            blocked("Recording expectation requires an existing configured room", {"room_id": room_id})
        for candidate in dict.fromkeys([room_id, 0]):
            rows = self.database.fetch("SELECT global_switch FROM t_record_settings WHERE roomid=%s", [candidate])
            if len(rows) > 1:
                blocked("Ambiguous recording settings", {"room_id": candidate})
            if rows and rows[0]["global_switch"] is not None:
                return int(rows[0]["global_switch"])
        blocked("Room and global recording settings are both missing", {"room_id": room_id})

    def record_extra_switch(self, room_id):
        from common.outcomes import blocked
        # Older schemas omit this column and the response DTO defaults to false.
        if "enable_ext_full_record" not in self.database.table_columns("t_record_settings"):
            return False
        for candidate in dict.fromkeys([room_id, 0]):
            rows = self.database.fetch("SELECT enable_ext_full_record FROM t_record_settings WHERE roomid=%s", [candidate])
            if len(rows) > 1:
                blocked("Ambiguous extended recording settings", {"room_id": candidate})
            if rows:
                value = rows[0]["enable_ext_full_record"]
                if value is None or str(value).lower() in {"0", "false", "f"}:
                    return False
                if str(value).lower() in {"1", "true", "t"}:
                    return True
                blocked("Invalid extended recording flag", {"room_id": candidate})
        blocked("Room and global extended recording settings are both missing", {"room_id": room_id})

    def validate_test_resources(self):
        if self._resources_validated:
            return
        env = self.env
        service_app = env["test_service_app_id"]
        route_app = env["test_route_app_id"]
        master_type = self.profile.get("test_master_server_type", 54013)
        for name, value in [("test_service_app_id", service_app), ("test_route_app_id", route_app),
                            ("test_master_server_type", master_type)]:
            if type(value) is not int or value <= 0:
                raise RuntimeError("Invalid test-only configuration: " + name)
        for role in (["primary", "secondary"] if self.topology == "dual" else ["primary"]):
            rows = self.database.fetch("SELECT ServiceName FROM t_serviceinfo WHERE DevID=%s AND ServiceAppID=%s",
                                       [env[role]["device_id"], service_app])
            if service_app in APP_IDS.values() or any(not str(r["ServiceName"] or "").startswith("autotest_") for r in rows):
                raise RuntimeError("Business service conflict: configure an unused test_service_app_id")
        if self.database.fetch("SELECT RoomID FROM t_roomroute WHERE SvrAppID=%s", [route_app]):
            raise RuntimeError("Existing routing records: configure an unused test_route_app_id; do not overwrite business/unknown routes")
        rows = self.database.fetch("SELECT devid FROM t_master_slave WHERE servertype=%s", [master_type])
        if any(r["devid"] != "autotest_role" for r in rows):
            raise RuntimeError("Business master identity conflict: configure an unused test_master_server_type")
        self._resources_validated = True

    def preflight(self, scope="global"):
        self.database.fetch("SELECT 1 AS oracle_available")
        self.env
        if scope != "read":
            self.validate_test_resources()
        return self.database.description()

    def check_case_applicability(self, case, scope):
        import pytest
        if case["topology"] != "any" and case["topology"] != self.topology:
            pytest.skip("Topology not applicable: requires " + case["topology"])
        requirements = set(case.get("requires", []))
        if "write" in requirements and scope == "read":
            pytest.skip("Read-only run: write scenario not selected")
        if "global" in requirements and scope != "global":
            pytest.skip("Global mutation suite not selected")
        features = set(self.profile.get("capabilities", []))
        for cap in requirements - {"write", "global", "exclusive", "database", "contract_pending", "legacy_face"}:
            if cap not in features:
                if cap == "face":
                    pytest.skip("Retired gateway face APIs: face functionality migrated; face_enabled=False")
                pytest.skip("Capability not applicable: " + cap)
        if "user_auth" in features and not self.env["password"]:
            raise RuntimeError("Environment blocked: user_auth declared without the password environment variable")
        if "legacy_face" in requirements:
            self.require_legacy_face()
        # A user selecting a broader suite must not accidentally bypass restoration.
        # Python lifecycle workflows register their own cleanups and use class_name=workflow.
        if "database" in requirements:
            self.database.fetch("SELECT 1 AS oracle_available")
        for cap, fields in {"room": ["room_id"], "user": ["user_id"], "file": ["room_id", "user_id"],
                            "user_auth": ["user_id", "username"]}.items():
            if cap in requirements and any(self.env.get(key) is None for key in fields):
                raise RuntimeError("Environment blocked: %s requires %s" % (cap, fields))
        if "${env.absent_room_id}" in json.dumps(case.get("params", {})):
            absent = self.query("room", "getRoomInfo", {"roomId": self.env["absent_room_id"]})
            if "roomId" in absent:
                raise RuntimeError("Negative-test room ID unexpectedly exists")

    def require_legacy_face(self):
        from common.outcomes import blocked
        env = self.env
        if env.get("face_id") is None:
            blocked("Applicable legacy face scenario has no valid t_faceinfo data; modern library IDs cannot be substituted",
                    {"legacy_face_id": None, "modern_face_present": env.get("modern_face_present"),
                     "configured_face_id": env.get("configured_face_id"), "source": env.get("face_data_source")})
        return env["face_id"]

    def probe_method(self, api, params):
        if api not in self.method_support:
            cls, method = api.split(".", 1)
            result = self.call(cls, method, params)
            self.method_support[api] = result
        return self.method_support[api]


def load_profile(path=None, topology=None, host=None):
    from common.config import TEST_CONFIG
    profile = copy.deepcopy(TEST_CONFIG)
    default_host = profile["host"]
    default_database_host = profile.get("database", {}).get("host")
    overrides = {}
    profile.setdefault("method_aliases", {"device.getRoomDefDevId": "getRoomDefDevID",
                                         "user.getFaceInfoByFaceId": "getFaceInfo"})
    profile["capabilities"] = ["room", "file", "user", "record_config", "user_auth"]
    for flag, capability in [("face_enabled", "face"), ("cdn_enabled", "cdn"), ("phone_gateway_enabled", "phone_gateway")]:
        if profile.get(flag):
            profile["capabilities"].append(capability)
    if path:
        overrides = json.loads(Path(path).read_text(encoding="utf-8"))
        profile.update(overrides)
    if topology:
        profile["topology"] = topology
    if host:
        profile["host"] = host
    # The normal same-server SSH oracle follows a host override too. Explicit
    # database hosts in legacy profiles remain separate when intentionally set.
    database = profile.get("database", {})
    if (database.get("backend") in {"auto", "ssh_mysql", "ssh_kingbase"} and default_database_host == default_host
            and "host" not in overrides.get("database", {})):
        database["host"] = profile["host"]
    if profile["topology"] == "dual" and not profile.get("secondary_device_id"):
        raise ValueError("Dual topology requires secondary_device_id")
    return profile
