"""Document-driven corrections; no blanket pending/exclusive skip policy."""
import json


def revise_case(c):
    method, cid = c["method"], c["case_id"]
    params, expected = json.loads(c["params"]), json.loads(c["expected"])
    # Transport diagnostics are evidence, not business fields in an empty payload.
    expected.pop("message", None)
    assertions = json.loads(c["assertions"])
    requires = set(json.loads(c["requires"])) - {"exclusive", "global", "contract_pending"}
    verification = json.loads(c["verification"])
    c["contract_issue"] = ""
    c["expected_outcome"] = "exact"
    c["test_group"], c["issue_id"] = "regression", ""
    if method == "delRoomRouteByTimer":
        c["fixture"] = "route_timer"
        requires |= {"database", "global", "write"}
        verification = {"kind": "contract", "reason": "Timer invocation; fixture restores pre-existing routing records through API. Expiration branches need dedicated timed data; restored timestamps are refreshed."}
    if method in {"serviceUnregister", "registerService"}:
        c["fixture"] = "service"; requires.add("database")
        if method == "serviceUnregister" and type(params.get("serviceId")) is not str:
            if params.get("serviceId") is not None: params["serviceId"] = "${fixture.service_id}"
        elif method == "serviceUnregister" and str(params.get("serviceId", "")).startswith("${"):
            params["serviceId"] = "${fixture.service_id}"
        if method == "registerService":
            if params.get("srvAppId") is not None: params["srvAppId"] = "${fixture.app_id}"
            if params.get("srvAddress") is not None: params["srvAddress"] = "${fixture.address}"
        verification = {"kind": "state", "checker": "service"}
    if method in {"devRegister", "devUnRegister", "devUpdate", "devUpdate2"}:
        c["fixture"] = "device"; requires.add("database")
        if isinstance(params, dict) and "deviceId" in params and str(params.get("deviceId", "")).startswith("${env.") and "absent" not in params["deviceId"]:
            params["verifyCode"] = "${env." + ("secondary" if c["topology"] == "dual" else "primary") + ".verify_code}" if params.get("verifyCode") == "1111" else params.get("verifyCode")
        verification = {"kind": "state", "checker": "device"}
    if method in {"setNodeStatus", "startLocalNode", "stopLocalNode", "frontNodeRegister", "frontNodeUnregister", "frontStart"}:
        c["fixture"] = "node"; requires.add("database")
        verification = {"kind": "state", "checker": "node"}
    if method in {"updateLicenseInfo", "updateLicenseState"}:
        c["fixture"] = "license"; requires.add("database")
        # Gson @SerializedName("4KCount") overrides the Java field fourKCount.
        if "supDogSerialId" in params: params["supDogSerialId"] = str(params["supDogSerialId"])
        verification = {"kind": "state", "checker": "license"}
        if any(value is None for value in params.values()):
            verification = {"kind": "contract", "reason": "PDF p35 does not specify defaults for omitted optional license fields; fixture still restores the snapshot"}
    if method == "setDocumentConversionSwitch":
        c["fixture"] = "feature"; requires.add("database")
        if type(params.get("globalSwitch")) is int: params["globalSwitch"] = bool(params["globalSwitch"])
        verification = {"kind": "state", "checker": "feature"} if params.get("globalSwitch") is not None else {"kind": "contract", "reason": "PDF p31 does not define null default; response contract is checked"}
    if method in {"changeToSlave", "tryChangeToMaster"}:
        c["fixture"] = "master"; requires.add("database")
        if params.get("serverType") is not None: params["serverType"] = "${fixture.server_type}"
        params["devId"] = "autotest_role" if params.get("devId") is not None else None
        expected.pop("devId", None)
    if method in {"confUserLogin2", "updateRoomUserState", "updateRoomInfoByRoomId", "updateMeetingLogInfo", "requestChairRight"}:
        c["fixture"] = "meeting"; requires |= {"database", "room", "write"}
        if "meetingId" in params and params["meetingId"] is not None: params["meetingId"] = "${fixture.meeting_id}"
        if "serviceId" in params and params["serviceId"] is not None: params["serviceId"] = "${fixture.service_id}"
        if method == "updateRoomInfoByRoomId" and params.get("roomId") == "${env.room_id}" and type(params.get("curUserCount")) is int:
            verification = {"kind": "state", "checker": "room_count"}
        elif method == "updateRoomInfoByRoomId" and expected.get("resultCode", 0) != 0:
            verification = {"kind": "state", "checker": "no_change", "target": "room"}
        if method == "updateRoomUserState" and params.get("roomId") == "${env.room_id}" and params.get("userId") == "${env.user_id}" and params.get("online") in (0,1):
            verification = {"kind": "state", "checker": "room_user"}
    if method == "getRoomSettings":
        expected = {"resultCode": 0}
        if params.get("roomId") == "${env.room_id}":
            expected["roomId"] = "${env.room_id}"
            assertions = [{"path": "$." + key, "op": "type", "value": typ} for key, typ in
                          [("roomId", "int"), ("enableRecord", "int"), ("enableFile", "int"), ("roomContext", "string"), ("layoutData", "string")]]
        else:
            assertions = [{"path": "$.roomId", "op": "eq", "value": 0}]
            if params.get("roomId") is None:
                expected = {}; assertions = []; c["expected_outcome"] = "rejected"
        verification = {"kind": "response", "reason": "PDF p65-66 exact documented fields; old waiting-room defaults are environment-specific"}
    if cid == "device-047":
        c["case_name"] = "节点查询-isLocal为不匹配字符串时返回空结果（文档类型String）"
        expected = {"resultCode": 0}; assertions = [{"path": "$.nodeId", "op": "exists", "value": False}]
        verification = {"kind": "response", "reason": "PDF p22: String filter, not an integer parsing test"}
    if cid == "room-011":
        c["case_name"] = "开启会议室-缺少文档必填serviceId应拒绝"
        expected = {}; assertions = []; c["expected_outcome"] = "rejected"
    if method == "replaceRoomRoute":
        if "data" in expected:
            expected = {"resultCode": 0}; assertions = []
            verification = {"kind": "state", "checker": "route"}
            if params.get("roomId") in (None, "${env.absent_room_id}"):
                # Missing roomId must not masquerade as a positive insert.
                verification = {"kind": "state", "checker": "no_change", "target": "route"}
        if cid in {"room-069", "room-070", "room-071", "room-072"}:
            expected = {}; assertions = []; c["expected_outcome"] = "rejected"
            verification = {"kind": "state", "checker": "no_change", "target": "route"}
            c["contract_issue"] = "PDF p48 required field: reject before modifying the prepared route"
    if cid in {"user-014", "user-015", "file-004", "file-005", "file-006", "file-007", "file-020", "file-027"}:
        expected = {}; assertions = []; c["expected_outcome"] = "rejected"
        c["contract_issue"] = "Invalid target field must be rejected without an uncaught SQL exception or data modification"
    if cid == "file-023":
        c["case_name"] = "移动目录-不存在父目录的数据完整性回归（文档未定义具体错误码）"
        expected = {}; assertions = []; c["expected_outcome"] = "rejected"
        c["contract_issue"] = "Data integrity regression, not a claim that PDF specifies business code -9"
    if method == "getFaceUserInfo" and params.get("faceId") == 1:
        params["faceId"] = "${env.face_id}"
        assertions += [{"path": "$.userName", "op": "type", "value": "string"}, {"path": "$.faceFeature", "op": "not_null"}]
    if method == "addFaceRollCallUser":
        c["fixture"] = "face_rollcall"; requires |= {"face", "database"}
        if params.get("rollCallId") is not None: params["rollCallId"] = "${fixture.rollcall_id}"
        if params.get("faceId") == 1: params["faceId"] = "${env.face_id}"
        if "faceId" in params:
            requires.add("legacy_face")
    if cid == "user-024":
        requires.add("legacy_face")

    # These are explicitly observed behavior baselines, not assertions that an
    # uncaught SQL exception is the desired product design.
    if cid in {"device-088", "user-014", "file-020", "file-027"}:
        expected, assertions = {"resultCode": 4107}, []
        c["expected_outcome"] = "exact"
        c["test_group"] = "behavior_baseline"
        c["contract_issue"] = "Observed current-build error code plus unchanged business state; SQL robustness remains tracked separately"
        if cid == "device-088":
            verification = {"kind": "state", "checker": "no_change", "target": "feature"}
        if cid == "user-014":
            c["case_name"] = "更新用户信息-sex超出目标字段长度，拒绝且资料不变"
            params["sex"] = "${fixture.sex_over_limit}"
        if cid == "file-027":
            c["case_name"] = "重命名缺少docName，拒绝且原文件名不变"

    issues = {
        "file-004": "BUG-DEL-DIR-SQL", "file-005": "BUG-DEL-DIR-SQL",
        "file-006": "BUG-DEL-DIR-SQL", "file-007": "BUG-DEL-DIR-SQL",
        "room-070": "BUG-ROUTE-ATOMICITY", "room-071": "BUG-ROUTE-ATOMICITY", "room-072": "BUG-ROUTE-ATOMICITY",
        "room-040": "BUG-REQUIRED-ROOM", "room-064": "BUG-REQUIRED-ROOM", "room-067": "BUG-REQUIRED-ROOM",
        "user-015": "BUG-REQUIRED-NICKNAME", "user-023": "BUG-REQUIRED-FACE"}
    if cid in issues:
        c["test_group"], c["issue_id"] = "backend_defect", issues[cid]
        if cid in {"room-064", "room-067"}:
            expected, assertions = {}, []
            c["expected_outcome"] = "rejected"
        if cid == "user-023":
            expected, assertions = {}, []
            c["expected_outcome"] = "rejected"
            verification = {"kind": "state", "checker": "no_change", "target": "face_members"}
            c["contract_issue"] = "PDF p79 faceId is required; a test deliberately omitting it does not require a valid face fixture"
        if cid.startswith("file-"):
            assertions = [{"path": "$.resultCode", "op": "not_in", "value": [4107]}]
            c["contract_issue"] = "开发2026-10-15确认SQL绑定缺陷；缺参应拒绝且状态不变，建议的4108尚未定为正式错误码，不将其排除"
            if cid in {"file-006", "file-007"}:
                expected, assertions = {"resultCode": 0}, []
                c["expected_outcome"] = "exact"
                c["case_name"] = "删除目录-" + ("目标docId不存在" if cid == "file-006" else "目标roomId不存在") + "，幂等成功且原目录不变"
                c["contract_issue"] = "开发2026-10-15确认现有实现忽略DELETE影响行数，目标不存在按幂等0基线验证；产品如修订契约再调整；不得误删其他目标"

    questions = {
        "room-062": "CONTRACT-APP-DEFAULT", "room-069": "CONTRACT-APP-DEFAULT",
        "room-065": "CONTRACT-ROOM-EXISTENCE", "room-068": "CONTRACT-ROOM-EXISTENCE",
        "file-023": "CONTRACT-PARENT-EXISTENCE", "user-020": "CONTRACT-AUTH-RESPONSIBILITY"}
    if cid in questions:
        c["test_group"], c["issue_id"] = "contract_review", questions[cid]
        c["contract_issue"] = questions[cid] + ": record current behavior and evaluate the proposed rule separately; not a confirmed backend defect"
    if cid in {"user-008", "user-009", "user-010", "user-011", "user-012", "user-013"}:
        params["sex"] = "${fixture.sex_valid}"
    if cid == "user-014":
        expected = {"resultCode": 4108}
        assertions = []
        c["expected_outcome"] = "exact"
        c["test_group"] = "regression"
        c["contract_issue"] = "Deployed 2026-10-16 UserSex accepts only 0/1; invalid sex is rejected with 4108 before SQL. Keep independent unchanged-state verification."
    # Developer-confirmed 2026-10-19 request-validation contract (screenshot).
    if cid in {"device-047", "device-088", "device-101", "file-027"}:
        expected, assertions = {"resultCode": 4108}, []
        c["expected_outcome"] = "exact"
        c["test_group"] = "regression"
        c["contract_issue"] = "Developer confirmed 2026-10-19: invalid input returns 4108; 4107 is reserved for unexpected system/database failures."
        if cid == "device-047":
            c["case_name"] = "节点查询-isLocal非法字符串应返回4108"
        if cid == "device-101":
            verification = {"kind": "state", "checker": "no_change", "target": "master"}
    if cid == "file-020":
        expected, assertions = {"resultCode": 0, "result": 0}, []
        c["expected_outcome"] = "exact"
        c["test_group"] = "behavior_baseline"
        c["case_name"] = "移动文档-省略parentId按当前版本默认根目录处理"
        verification = {"kind": "db", "sql": "SELECT ParentID FROM t_roomdocslist WHERE RoomID=%s AND DocID=%s",
                        "params": ["${env.room_id}", "${fixture.doc_id}"],
                        "assertions": [{"path": "$", "op": "length", "value": 1},
                                       {"path": "$[0].ParentID", "op": "eq", "value": ""}]}
        c["contract_issue"] = "Current-version baseline: omitted parentId moves to root; independently confirmed from a non-root fixture on 2026-10-16. Not one of the four 4108 contracts in the developer screenshot."
    if cid in {"device-048", "device-102", "device-103", "file-025", "file-026"}:
        expected, assertions = {"resultCode": 4108}, []
        c["expected_outcome"], c["test_group"] = "exact", "regression"
        c["contract_issue"] = "2026-10-19 validation contract: reject missing/null required input with 4108; retain independent state checks. serverType enumeration remains separate from null validation."
        names = {"device-048": "节点查询-isLocal为null应返回4108",
                 "device-102": "尝试切换主设备-serverType为null应拒绝且状态不变",
                 "device-103": "尝试切换主设备-address为null应拒绝且状态不变",
                 "file-025": "重命名缺少docId，拒绝且原文件不变",
                 "file-026": "重命名缺少roomId，拒绝且原文件不变"}
        c["case_name"] = names[cid]
        if cid == "device-048":
            c["intentional_invalid"] = json.dumps(["isLocal"])
        if cid in {"device-102", "device-103"}:
            params["devId"] = "${env.primary.device_id}"
            verification = {"kind": "state", "checker": "no_change", "target": "master"}
    if cid in {"user-008", "user-009", "user-010", "user-011", "user-012", "user-013", "user-014", "user-015"}:
        c["description"] = "API创建独立临时用户并准备完整非空基线；逐项回查所有资料字段，API恢复后删除临时账号；不修改配置用户资料。"
        # Each format variation changes one target field. Other fields preserve
        # their fixture values; missing nickname is legitimate partial update.
        if cid != "user-008":
            params.update(nickName="${fixture.original_nickname}", tel="${fixture.original_tel}",
                          sex="${fixture.sex_valid}", mobile="${fixture.original_mobile}", mail="${fixture.original_mail}")
        variations = {"user-009": ("mobile", "12345678901", "mobile非标准号段按字符串保存并回查"),
                      "user-010": ("mobile", "1234567890", "mobile为10位字符串保存并回查"),
                      "user-011": ("mail", "yy163", "mail无分隔符字符串保存并回查"),
                      "user-012": ("tel", "12345", "tel为5位字符串保存并回查"),
                      "user-013": ("tel", "123451234512345123451234512345123", "tel为33位字符串保存并回查")}
        if cid in variations:
            field, value, title = variations[cid]
            params[field] = value
            c["case_name"] = "更新用户信息-" + title
            c["test_group"] = "behavior_baseline"
            c["contract_issue"] = "PDF p77 does not define phone/email format validation. Verify string persistence and unrelated-field preservation; do not claim these strings satisfy a business format policy."
        if cid == "user-014":
            params["sex"] = "${fixture.sex_over_limit}"
            c["intentional_invalid"] = json.dumps(["sex"])
        if cid == "user-015":
            params.pop("nickName", None)
            params["tel"] = "01088888888"
            expected, assertions = {"resultCode": 0}, []
            c["expected_outcome"], c["test_group"] = "exact", "regression"
            c["case_name"] = "局部更新省略nickName，保留原昵称且指定电话更新成功"
            c["intentional_invalid"] = json.dumps([])
            c["contract_issue"] = "Configured nonempty_fields update mode: deployed Processor validates nonempty sex, DAO ignores missing nickname. Preserve original nickname and verify the requested telephone change; invalid sex must not masquerade as missing-nickname validation."
            verification = {"kind": "state", "checker": "user"}
    # User clarified that the seven scenarios follow the confirmed deployed
    # design. Both route methods reject nonexistent rooms with 4108.
    if cid in {"room-062", "room-069", "room-065", "room-068", "file-023", "user-020"}:
        c["test_group"], c["expected_outcome"] = "regression", "exact"
        c["contract_issue"] = "User clarified developer-confirmed design on 2026-10-19: use current deployed behavior for these seven scenarios; both route methods reject nonexistent rooms with 4108. Retain independent business-state/identity verification."
        if cid in {"room-062", "room-069", "room-065", "room-068"}:
            expected, assertions = {"resultCode": 4108}, []
            verification = {"kind": "state", "checker": "no_change", "target": "route"}
            c["case_name"] = {"room-062": "更新路由-svrAppId为null拒绝且原路由不变",
                              "room-069": "替换路由-svrAppId为null拒绝且原路由不变",
                              "room-065": "更新路由-不存在房间返回4108且原路由不变",
                              "room-068": "替换路由-不存在房间拒绝且原路由不变"}[cid]
            c["intentional_invalid"] = json.dumps(["roomId" if cid in {"room-065", "room-068"} else "svrAppId"])
        elif cid == "file-023":
            expected, assertions = {"resultCode": 0, "result": 0}, []
            verification = {"kind": "state", "checker": "file", "preserve_other_fields": True}
            c["case_name"] = "移动目录-按设计写入指定parentId并保留其他文件字段"
            c["intentional_invalid"] = json.dumps([])
        else:
            c["fixture"] = "user_identity"
            requires |= {"database", "user"}
            expected = {"resultCode": 0, "result": 0, "localUserId": "${env.user_id}", "nickname": "${fixture.nickname}"}
            assertions = [{"path": "$.localUserId", "op": "type", "value": "int"},
                          {"path": "$.result", "op": "type", "value": "int"},
                          {"path": "$.role", "op": "type", "value": "string"}]
            verification = {"kind": "response", "reason": "Developer confirmed loginType=1 identity lookup without password validation; expected ID/nickname come from a read-only DB fixture. Upstream authentication is not claimed."}
            c["case_name"] = "用户身份查询-按设计省略password仍返回匹配用户"
            c["intentional_invalid"] = json.dumps([])
    c["requires"] = json.dumps(sorted(requires), ensure_ascii=False)
    c["params"], c["expected"] = json.dumps(params, ensure_ascii=False), json.dumps(expected, ensure_ascii=False)
    c["assertions"], c["verification"] = json.dumps(assertions, ensure_ascii=False), json.dumps(verification, ensure_ascii=False)
    return c
