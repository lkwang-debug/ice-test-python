"""Create disposable users through the preparation API; SQL remains read-only."""
import base64
import hashlib
import json
import time
import urllib.error
import urllib.request
import uuid

from common.executor import attach
from common.outcomes import blocked


class UserPreparationApi:
    def __init__(self, runtime):
        self.runtime = runtime
        profile = runtime.profile
        account = profile.get("user_fixture_api_account")
        sql = "SELECT account,secret FROM t_api_power WHERE is_active=1"
        if account:
            sql += " AND account=%s"
        elif "is_show" in runtime.database.table_columns("t_api_power"):
            sql += " AND is_show=0"
        rows = runtime.database.fetch(sql, [account] if account else [])
        if len(rows) != 1 or not rows[0].get("account") or not rows[0].get("secret"):
            blocked("Temporary user fixture needs exactly one active preparation-API credential")
        self.account, self.secret = rows[0]["account"], rows[0]["secret"]
        scheme = profile.get("user_fixture_api_scheme", "http")
        port = profile.get("user_fixture_api_port", 28080)
        self.base_url = "%s://%s:%d" % (scheme, profile["host"], port)

    def call(self, path, params, allowed_codes=("0",)):
        header = base64.b64encode(b'{"alg": "SHA256"}').decode("ascii")
        payload = base64.b64encode(json.dumps({"key": self.account,
                                             "timestamp": round(time.time() * 1000)}).encode()).decode("ascii")
        signature = hashlib.sha256((header + payload + self.secret).encode()).hexdigest()
        request = urllib.request.Request(self.base_url + path, method="POST",
                                         data=json.dumps(params).encode("utf-8"),
                                         headers={"Content-Type": "application/json", "Authorization":
                                                  header + "." + payload + "." + signature})
        # Never persist the Authorization header or the credential query result.
        try:
            with urllib.request.urlopen(request, timeout=15) as response:
                body = json.loads(response.read().decode("utf-8"))
        except (OSError, ValueError, urllib.error.URLError) as exc:
            raise RuntimeError("Preparation API %s unavailable: %s" % (path, type(exc).__name__)) from exc
        attach("Temporary user preparation API", {"path": path, "params": params, "response": body})
        if not isinstance(body, dict) or str(body.get("code")) not in allowed_codes:
            raise RuntimeError("Preparation API %s failed: code=%r" % (path, body.get("code") if isinstance(body, dict) else None))
        return body


def prepare_temporary_user(scenario):
    runtime = scenario.runtime
    try:
        api = UserPreparationApi(runtime)
        # Prove authentication/availability before attempting a mutation.
        api.call("/api/v1/user/list", {"pageNumber": 1, "pageSize": 1,
                                       "userName": "ice_autotest_not_present_" + uuid.uuid4().hex[:8]})
    except RuntimeError as exc:
        blocked(str(exc))
    name = "ice_autotest_" + uuid.uuid4().hex[:12]
    if scenario.rows("SELECT UserID FROM t_userinfo WHERE UserName=%s", [name]):
        blocked("Temporary user name collision; refusing to reuse an existing account")

    def cleanup():
        # The exact UUID name was absent before this fixture. Never delete by
        # a loose prefix, or by the ID supplied in the gateway request under test.
        api.call("/api/v1/user/del", {"userName": name}, allowed_codes=("0", "1012"))
        assert not scenario.rows("SELECT UserID FROM t_userinfo WHERE UserName=%s", [name]), "Temporary user was not deleted"

    # Register before creation: an ambiguous network response must still clean up.
    scenario.add_cleanup("temporary user " + name, cleanup)
    try:
        api.call("/api/v1/user/add", {"userName": name, "password": "IceTest9_" + uuid.uuid4().hex[:12],
                                     "passwordType": 0, "adminRole": 2, "departId": 0})
    except RuntimeError as exc:
        blocked("Temporary user provisioning failed: " + str(exc))
    rows = scenario.rows("SELECT UserID,UserName FROM t_userinfo WHERE UserName=%s", [name])
    if len(rows) != 1 or int(rows[0]["UserID"]) in {1000000001, runtime.env["user_id"]}:
        raise RuntimeError("Preparation API did not create a unique isolated user")
    user_id = int(rows[0]["UserID"])
    scenario.context["env"] = dict(scenario.context["env"], user_id=user_id, username=name)
    # Nonempty, deterministic baseline makes every field restorable through the
    # deployed partial-update API. The whole account is deleted after the test.
    baseline = {"userId": user_id, "nickName": name, "sex": "0", "tel": "01000000000",
                "mobile": "13800000000", "mail": "ice_autotest@example.invalid"}
    scenario.api("user", "updateUserInfo", baseline)
    saved = scenario.rows("SELECT DisplayName,Sex,TelePhone,Mobile,EMail FROM t_userinfo WHERE UserID=%s", [user_id])
    mapping = {"nickName": "DisplayName", "sex": "Sex", "tel": "TelePhone", "mobile": "Mobile", "mail": "EMail"}
    assert len(saved) == 1 and all(saved[0][col] == baseline[field] for field, col in mapping.items()), "Temporary user baseline did not persist"
    attach("Temporary user ownership", {"user_id": user_id, "username": name,
                                        "configured_user_unchanged": runtime.env["user_id"],
                                        "cleanup": "Delete exact fixture-owned username through API"})
