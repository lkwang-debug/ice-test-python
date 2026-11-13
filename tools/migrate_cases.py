"""Read-only XLSX/PDF audit; emit edits for the Artifact Tool workbook editor."""
import json
import re
import sys
import unicodedata
from collections import defaultdict
from pathlib import Path
from openpyxl import load_workbook
from pypdf import PdfReader

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from common.interface_catalog import RETIRED_METHODS
RETIRED_FACE_METHODS = {"addFaceRollCallUser", "getFaceUserInfo", "insertIntoFaceRollCall",
                        "getFaceInfoList", "getFaceInfoByFaceId", "updateFaceInfoByFaceId"}
RETIREMENT_REASON = "人脸已迁出本数据库网关；旧接口保留历史，不纳入当前回归"
NEW = ["case_id", "topology", "requires", "fixture", "assertions", "verification", "doc_ref", "intentional_invalid", "contract_issue", "expected_outcome", "test_group", "issue_id"]
LIST_APIS = {"checkDevList", "getAppSrvList", "getDevFileList", "getDevInfoByType", "getDevSipPhoneList",
             "getNodeList", "getServiceList", "getSubNodeList", "getRoomUserList", "getRoomDeptList",
             "getRoomFileList", "getRootDirList", "getUselessFile", "getAllPhoneGwInfo", "getFaceInfoList"}
WRITES = {"changeToSlave", "delRoomRouteByTimer", "devRegister", "devUnRegister", "devUpdate", "devUpdate2",
          "frontNodeRegister", "frontNodeUnregister", "frontStart", "serviceUnregister", "registerService",
          "setDocumentConversionSwitch", "setNodeStatus", "stopLocalNode", "startLocalNode", "tryChangeToMaster",
          "updateLicenseInfo", "updateLicenseState", "updateMeetingLogInfo", "updateSystemParam", "updateService",
          "updateDevInfoStatusByDevId", "addFile", "delDir", "delFile", "moveDocFile", "renameFile", "confLog",
          "confRoomStart", "confRoomStop", "confUserLogin2", "deleteRoomRouteInfo", "delRoomRoute", "meetingLog",
          "replaceRoomRoute", "requestChairRight", "updateRoomRoute", "updateRoomRouteTime", "updateRoomUserState",
          "updateRoomInfoByRoomId", "updateUserInfo", "addFaceRollCallUser", "insertIntoFaceRollCall", "updateFaceInfoByFaceId"}
GLOBAL = {"changeToSlave", "delRoomRouteByTimer", "devRegister", "devUnRegister", "devUpdate", "devUpdate2",
          "frontNodeRegister", "frontNodeUnregister", "frontStart", "serviceUnregister", "registerService",
          "setDocumentConversionSwitch", "setNodeStatus", "stopLocalNode", "startLocalNode", "tryChangeToMaster",
          "updateLicenseInfo", "updateLicenseState", "updateMeetingLogInfo"}
TYPE_FIELDS = {"getLastLicenseTime": {"lastUpdateTime": "int"}, "getOnlineDevCount": {"count": "int"},
               "getFrontIp": {"devIp": "string"}, "getFrontAddress": {"nodeManAddress": "string"},
               "meetingLog": {"meetingId": "int"}, "getRoomInfo": {"roomId": "int", "curUserCount": "int", "maxUserCount": "int"},
               "getRoomCompanyId": {"companyId": "int", "businessId": "int", "result": "int"},
               "getCDNInfo": {"result": "int"}, "getRoomH323SettingsInfo": {"callBitrate": "int", "videoMixMode": "int"}}


def j(value):
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def migrate(case, sheet, row, pages):
    c = dict(case)
    method = str(c.get("method") or "").strip()
    enabled = str(c.get("auto", True)).lower() != "false"
    c.update(case_id="%s-%03d" % (sheet, row), topology="any", requires=[], fixture="none",
             assertions=[], verification={"kind": "contract", "reason": "Invocation contract only; business effect is not claimed"},
             doc_ref="PDF p." + ",".join(map(str, pages.get((sheet, method), []))), intentional_invalid=[], contract_issue="")
    if not enabled:
        c["requires"] = ["contract_pending"]
        c["contract_issue"] = "Previously disabled; pending contract/resource review"
        return c, {"case_id": c["case_id"], "enabled": False, "scope": "disabled"}
    c["method"] = method
    params = json.loads(c["params"]) if c.get("params") else {}
    expected = json.loads(c["expected"])
    code_only = set(expected) == {"resultCode"}
    raw = j(params)
    dual = "meeting2" in raw or ("meeting2" in str(c.get("case_name")) and method not in {"serviceUnregister"})
    # Room routing does not intrinsically need a second device.
    if sheet == "room":
        dual = False
    role = "secondary" if dual else "primary"
    if dual:
        c["topology"] = "dual"
    if method in WRITES:
        c["requires"].append("write")
    if method in GLOBAL:
        c["requires"] += ["global", "exclusive"]
    if "不传" in str(c["case_name"]) or "为空" in str(c["case_name"]) or "传空" in str(c["case_name"]) or "异常" in str(c["case_name"]):
        c["intentional_invalid"] = [k for k, v in (params or {}).items() if v is None]
        if not c["intentional_invalid"]:
            c["intentional_invalid"] = ["scenario_target"]
    # Resolve identity from environment, not the ordering of an earlier response.
    replacements = {
        "${device_checkDevList.response.data.0.devIp}": "${env." + role + ".address}",
        "${device_checkDevList.response.data.1.devIp}": "${env." + role + ".address}",
        "${device_devRegister.response.devNodeId}": "${env.node_id}",
        "${device_getNodeList.response.data.0.nodeId}": "${env.node_id}",
        "${device_getServiceList.response.data.0.serviceAddress}": "${env." + role + ".services.FMConfSrv.address}",
        "${device_getServiceList.response.data.1.serviceAddress}": "${env." + role + ".services.FMConfSrv.address}",
        "${origWmcaAddr.response.paramValue}": "${fixture.original_value}",
        "${origLogLevel.response.paramValue}": "${fixture.original_value}"}
    raw = raw.replace('"${device_devRegister.response.devNodeId"', '"${env.node_id}"')
    for old, new in replacements.items():
        raw = raw.replace(old, new)
    raw = re.sub(r"\$\{RANDOM_STR(?:\[\d+\])?\}", "${case.random}", raw)
    params = json.loads(raw)
    if isinstance(params, dict):
        if "roomid" in params:
            params["roomId"] = params.pop("roomid")
        for key in ("deviceId", "devId"):
            if params.get(key) == "MainDev": params[key] = "${env.primary.device_id}"
            elif params.get(key) == "meeting2": params[key] = "${env.secondary.device_id}"
            elif params.get(key) == "meeting3": params[key] = "${env.absent_device_id}"
        if params.get("roomId") == 10000: params["roomId"] = "${env.room_id}"
        if params.get("roomId") == 12345: params["roomId"] = "${env.absent_room_id}"
        if params.get("userId") == 1000000001: params["userId"] = "${env.user_id}"
        if method in {"registerService", "getServiceList"}:
            service = {3: "FMFileSrv", 10: "FMFileMgrSrv", 11: "FMConfSrv", 20: "FMFrontSrv"}.get(params.get("srvAppId"))
            if service and params.get("srvAddress") is not None:
                params["srvAddress"] = "${env." + role + ".services." + service + ".address}"
        if method == "verifyUser":
            if "name" in params: params["name"] = "${env.username}"
            if "password" in params: params["password"] = "${env.password}"
            c["requires"].append("user_auth")
        if method == "serviceUnregister" and type(params.get("serviceId")) is int:
            # Service IDs are installation-specific; identify by case's application name.
            service = next((n for n in ["FMFileMgrSrv", "FMFrontSrv", "FMConfSrv", "FMFileSrv", "FMWebProxy"] if n in c["case_name"]), "FMConfSrv")
            service_role = "secondary" if "meeting2" in c["case_name"] else "primary"
            if service_role == "secondary": c["topology"] = "dual"
            params["serviceId"] = "${env." + service_role + ".services." + service + ".id}"
        if method in {"confRoomStart", "confRoomStop"}:
            c["fixture"] = "meeting"
            c["requires"] += ["room", "database"]
            if params.get("serviceId") is not None:
                params["serviceId"] = "${env.primary.services.FMFileSrv.id}" if "不一致" in c["case_name"] else "${fixture.service_id}"
            if "meetingId" in params: params["meetingId"] = "${fixture.meeting_id}"
            if "groupId" in params: params["groupId"] = "${fixture.group_id}"
            if method == "confRoomStart" and "不传serviceid" in c["case_name"]:
                # Old row accidentally tested a missing room, not a missing service.
                params["serviceId"], params["roomId"] = None, "${env.room_id}"
                c["intentional_invalid"] = ["serviceId"]
                c["requires"].append("contract_pending")
                c["contract_issue"] = "Missing-service business return is not specified in the PDF"
        if sheet == "room" and method in {"updateRoomRoute", "replaceRoomRoute", "delRoomRoute", "updateRoomRouteTime"}:
            c["fixture"] = "route"
            c["requires"] += ["room", "database"]
            for key, ref in {"roomId": "${fixture.room_id}", "svrAppId": "${fixture.app_id}", "svrNodeId": "${fixture.node_id}"}.items():
                if key in params and params[key] is not None and (key != "roomId" or params[key] != "${env.absent_room_id}"):
                    params[key] = ref
            if params.get("svrAddress") is not None: params["svrAddress"] = "${fixture.address}"
            if params.get("svrAuthCode") is not None: params["svrAuthCode"] = "${fixture.auth_code}"
            negative = any(v is None for v in params.values()) or params.get("roomId") == "${env.absent_room_id}"
            c["verification"] = {"kind": "state", "checker": "no_change", "target": "route"} if negative else {"kind": "state", "checker": "route_time" if method == "updateRoomRouteTime" else "route"}
            if "data" in expected:
                c["requires"].append("contract_pending")
                c["contract_issue"] = "Legacy route expectation conflicts with the documented empty response"
        if sheet == "file" and method in {"addFile", "delFile", "delDir", "renameFile", "moveDocFile", "getRoomFileList"}:
            c["fixture"] = "file"
            c["requires"] += ["file", "room", "database"]
            if params.get("docId") and params["docId"] not in {"{8de2008b}"}: params["docId"] = "${fixture.doc_id}"
            if params.get("parentId") == "{687739bf-3dd5-d3da-0100-000000000000}": params["parentId"] = "${fixture.parent_id}"
            if params.get("docName"): params["docName"] = "${fixture.name}_changed"
            if params.get("creatorId"): params["creatorId"] = "${env.user_id}"
            if method == "addFile": params["fileServiceId"] = "${env.primary.services.FMFileSrv.id}"
            negative = "不传" in c["case_name"] or "错误" in c["case_name"] or "不存在" in c["case_name"]
            if method == "moveDocFile" and "不存在的roomid" in c["case_name"]: params["roomId"] = "${env.absent_room_id}"
            c["verification"] = {"kind": "state", "checker": "no_change", "target": "file"} if negative else {"kind": "state", "checker": "file"}
            if method == "getRoomFileList":
                c["assertions"].append({"path": "$.data", "op": "contains_record", "value": {"docId": "${fixture.doc_id}"}, "count": 1})
                c["verification"] = {"kind": "response", "reason": "Prepared file must appear in this room's result"}
        if method == "updateUserInfo":
            c["fixture"] = "user"
            c["requires"] += ["user", "database"]
            negative = "不传" in c["case_name"] or "异常" in c["case_name"]
            c["verification"] = {"kind": "state", "checker": "no_change", "target": "user"} if negative else {"kind": "state", "checker": "user"}
        if method == "updateSystemParam":
            c["fixture"] = "system_param"
            c["requires"] += ["global", "exclusive"]
            c["verification"] = {"kind": "state", "checker": "system_param"}
        if method == "getRecordRoomCfg" and "globalSwitch" in expected:
            expected["globalSwitch"] = "${env.record_global_switch}"
            c["requires"].append("record_config")
        if method == "getRoomSettings":
            c["requires"].append("contract_pending")
            c["contract_issue"] = "Legacy settings fields are outside this PDF version"
        if method == "getServiceList":
            expected = {"resultCode": expected.get("resultCode", 0)}
            c["requires"].append("database")
            c["verification"] = {"kind": "state", "checker": "service_list"}
        if method == "getRoomRouteInfo" and "成功" in c["case_name"]:
            c["fixture"] = "route"
            c["requires"] += ["room", "database"]
            params = {"roomId": "${fixture.room_id}", "svrAppId": "${fixture.app_id}", "svrNodeId": "${fixture.node_id}"}
            expected.update(svrAddress="${fixture.address}", svrAuthCode="${fixture.auth_code}")
            c["verification"] = {"kind": "response", "reason": "Read the independently prepared route by its complete identity"}
        if method == "getCDNInfo":
            c["requires"].append("cdn")
        if method == "getNodeIdByLocal" and params.get("isLocal") == "test":
            c["requires"].append("contract_pending")
            c["contract_issue"] = "PDF declares isLocal String; non-int error expectation is unconfirmed"
        if method in {"meetingLog", "confUserLogin2", "updateRoomUserState", "updateRoomInfoByRoomId", "requestChairRight"}:
            c["requires"] += ["room", "exclusive"]
        if sheet == "user" and method in {"addFaceRollCallUser", "getFaceUserInfo"}: c["requires"].append("face")
    # Convert flat legacy list assertions to a predicate on ONE record.
    fields = {k: v for k, v in expected.items() if k not in {"resultCode", "data"}}
    for k, v in list(fields.items()):
        if v == "MainDev": fields[k] = "${env.primary.device_id}"
        elif v == "meeting2": fields[k] = "${env.secondary.device_id}"; c["topology"] = "dual"
        elif k == "roomId" and v == 10000: fields[k] = "${env.room_id}"
    if method in LIST_APIS and fields:
        c["assertions"].append({"path": "$.data", "op": "contains_record", "value": fields, "count": 1})
        expected = {k: v for k, v in expected.items() if k in {"resultCode", "data"}}
    else:
        expected.update(fields)
    if method == "getRecordUserName" and isinstance(params, dict) and params.get("userId") == "${env.user_id}" and "userName" in expected:
        expected["userName"] = "${env.username}"
    for k, v in list(expected.items()):
        if v == "!null":
            numeric = k in {"callBitrate", "videoMixMode", "meetingId", "count", "userId", "roomId", "maxUserCount", "videoNum"}
            c["assertions"].append({"path": "$." + k, "op": "not_null" if numeric else "not_empty"})
            if numeric: c["assertions"].append({"path": "$." + k, "op": "type", "value": "int"})
            expected.pop(k)
    if method in LIST_APIS:
        if expected.get("resultCode", 0) == 0:
            c["assertions"].append({"path": "$.data", "op": "type", "value": "array"})
    positive = isinstance(params, dict) and not any(v is None for v in params.values()) and "不存在" not in c["case_name"] and "不传" not in c["case_name"]
    if method == "getRoomInfo" and isinstance(params, dict) and params.get("roomId") == "10000":
        params["roomId"] = "${env.room_id}"
    if method == "getRoomInfo" and positive:
        expected["roomId"] = "${env.room_id}"
    if method == "getOnlineDevCount":
        c["assertions"].append({"path": "$.count", "op": "range", "value": [1, 2147483647]})
    if method == "getNodeList":
        c["assertions"].append({"path": "$.data", "op": "contains_record", "value": {"nodeId": "${env.node_id}"}, "count": 1})
    if "${env.room_id}" in j(params) and "room" not in c["requires"]:
        c["requires"].append("room")
    if "${env.user_id}" in j(params) and "user" not in c["requires"]:
        c["requires"].append("user")
    if method == "getAppSrvList" and "子节点" in c["case_name"]:
        c["topology"] = "dual"
    if method == "getNodeIdByLocal" and positive and params.get("isLocal") in (1, "1"):
        expected["nodeId"] = "${env.node_id}"
    if positive:
        for key, typ in TYPE_FIELDS.get(method, {}).items():
            c["assertions"].append({"path": "$." + key, "op": "type", "value": typ})
    if c["verification"]["kind"] == "contract" and (c["assertions"] or fields):
        c["verification"] = {"kind": "response", "reason": "Exact response contract; persistence is not claimed"}
    if method in GLOBAL and c["verification"]["kind"] == "contract":
        c["verification"]["reason"] = "Empty response contract; lifecycle effects are verified in separate workflows or remain a declared gap"
    if expected.get("resultCode", 0) == 0 and method in {"getRoomDefDevId", "getVgwAddr", "confRoomStart", "confRoomStop", "getRoomCompanyId", "getRoomCurDevId", "moveDocFile"}:
        c["assertions"].append({"path": "$.result", "op": "type", "value": "int"})
        if c["verification"]["kind"] == "contract":
            c["verification"] = {"kind": "response", "reason": "Business-code structure checked; undefined branch semantics remain unclaimed"}
    if method == "moveDocFile" and "成功" in c["case_name"] and "不传" not in c["case_name"]:
        expected["result"] = 0
        c["expected"] = j(expected)
    if c["fixture"] != "none":
        c["requires"].append("write")
    if c["intentional_invalid"] == ["scenario_target"]:
        target_map = {"userid": "userId", "roomid": "roomId", "docid": "docId", "parentid": "parentId",
                      "docname": "docName", "serviceid": "serviceId", "nodeid": "nodeId", "logintype": "loginType",
                      "password": "password", "name": "name", "昵称": "nickName", "online": "online"}
        lowered = str(c["case_name"]).lower()
        targets = [field for text, field in target_map.items() if text in lowered]
        c["intentional_invalid"] = targets or ["request"]
    c["requires"] = sorted(set(c["requires"]))
    c.update(params=j(params), expected=j(expected), partial_validation=False, save_response=None)
    for key in ["requires", "assertions", "verification", "intentional_invalid"]: c[key] = j(c[key])
    return c, {"case_id": c["case_id"], "enabled": True, "api": sheet + "." + method,
               "previous_code_only": code_only, "scope": json.loads(c["verification"]),
               "topology": c["topology"], "contract_issue": c["contract_issue"], "source_row": row,
               "scenario": c["case_name"], "intentional_invalid": json.loads(c["intentional_invalid"]), "expected": json.loads(c["expected"])}


def main():
    from common.cases import parse_auto
    current_autos = {}
    current_path = ROOT / "data/test_cases.xlsx"
    if current_path.exists():
        current = load_workbook(current_path, read_only=True, data_only=True)
        for sheet in current:
            rows = sheet.values
            headers = list(next(rows))
            for row in rows:
                case = dict(zip(headers, row))
                if case.get("case_id"):
                    current_autos[case["case_id"]] = parse_auto(case.get("auto"))
        current.close()
    pages = defaultdict(list)
    texts = []
    pdf = PdfReader(ROOT / "数据库网关接口文档.pdf")
    for i, page in enumerate(pdf.pages, 1):
        text = unicodedata.normalize("NFKC", page.extract_text() or "").replace("\x01", " ")
        texts.append(text)
        for m in re.finditer(r"className\s+(company|device|file|room|user)\s+method\s+(\w+)", text): pages[(m[1], m[2])].append(i)
    for m in re.finditer(r"className\s+(company|device|file|room|user)\s+method\s+(\w+)", "\n".join(texts)): pages.setdefault((m[1], m[2]), [])
    wb = load_workbook(ROOT / ".codex-temp/artifacts/test_cases.before.xlsx", read_only=True, data_only=True)
    edits, audit = [], []
    for sheet in wb:
        rows = list(sheet.values); headers = list(rows[0])
        new_headers = ["auto"] + [h for h in headers + NEW if h != "auto"]
        values = [new_headers]
        for n, row in enumerate(rows[1:], 2):
            if not any(v is not None for v in row): values.append([None]*len(new_headers)); continue
            c, record = migrate(dict(zip(headers, row)), sheet.title, n, pages)
            if record["enabled"]:
                from revise_cases import revise_case
                c = revise_case(c)
                record.update(scope=json.loads(c["verification"]), topology=c["topology"],
                              scenario=c["case_name"], contract_issue=c["contract_issue"],
                              expected=json.loads(c["expected"]), expected_outcome=c.get("expected_outcome", "exact"),
                              test_group=c.get("test_group", "regression"), issue_id=c.get("issue_id", ""))
            record["original_enabled"] = record["enabled"]
            c["auto"] = current_autos.get(c["case_id"], record["enabled"])
            record["enabled"] = c["auto"]
            method = str(c.get("method") or "").strip()
            if sheet.title == "user" and method in RETIRED_FACE_METHODS:
                c.update(auto=False, contract_issue=RETIREMENT_REASON)
                c["requires"] = j(sorted(set(json.loads(c["requires"]) if isinstance(c["requires"], str) else c["requires"]) | {"face"}))
                record.update(enabled=False, scope_status="retired", retirement_reason=RETIREMENT_REASON,
                              api="user." + method, contract_issue=RETIREMENT_REASON)
            values.append([c.get(h) if not isinstance(c.get(h), (dict, list)) else j(c[h]) for h in new_headers]); audit.append(record)
        edits.append({"sheet": sheet.title, "values": values})
    wb.close()
    out = ROOT / "docs"; out.mkdir(exist_ok=True)
    (ROOT / ".codex-temp/artifacts/workbook-updates.json").write_text(j(edits), encoding="utf-8")
    (out / "case-migration.json").write_text(json.dumps(audit, ensure_ascii=False, indent=2), encoding="utf-8")
    matrix = []
    workflows = {"device.devUpdate2": "primary_device_update_current_version", "room.getRoomDeptList2": "test_room_department_list_current_version", "device.registerService": "service_lifecycle", "device.serviceUnregister": "service_lifecycle", "room.confRoomStart": "meeting_lifecycle", "room.confRoomStop": "meeting_lifecycle", "room.meetingLog": "meeting_lifecycle", "room.updateRoomRoute": "route_lifecycle", "room.replaceRoomRoute": "route_lifecycle", "room.delRoomRoute": "route_lifecycle", "file.addFile": "file_lifecycle", "file.renameFile": "file_lifecycle", "file.moveDocFile": "file_lifecycle", "file.delFile": "file_lifecycle", "user.verifyUser": "user_permissions", "user.updateUserInfo": "user_update"}
    workflows.update({"device.getNodeIdByLocal": "test_node_selector_contract/test_node_selector_valid",
                      "device.setDocumentConversionSwitch": "test_conversion_switch_contract/test_conversion_switch_valid",
                      "file.delDir": "test_delete_directory_entries_preserves_file_records"})
    confirmed_design = {
        "device.getNodeIdByLocal": "Developer retained numeric 0/1 coercion; verify selected node against read-only data and preserve node state.",
        "device.setDocumentConversionSwitch": "Developer retained string conversion: empty/blank/false -> false, true -> true; verify stored switch and fixture restoration.",
        "file.delDir": "Developer retained directory-entry deletion only; descendant DocType 1/2/3 file records remain unchanged. Complete file-tree cleanup is outside this API regression."}
    for (cls, method), pp in sorted(pages.items()):
        api = cls + "." + method; cases = [r for r in audit if r.get("api") == api and r["enabled"]]
        retired = RETIRED_METHODS.get(api)
        face_retired = cls == "user" and method in RETIRED_FACE_METHODS
        matrix.append({"api": api, "pdf_pages": pp, "case_ids": [r["case_id"] for r in cases],
                       "scope_status": "retired" if face_retired or retired else "active",
                       "retirement_reason": retired["reason"] if retired else RETIREMENT_REASON if face_retired else None,
                       "replacement": retired["replacement"] if retired else None,
                       "lifecycle_change": retired["change"] if retired else None,
                       "removal_commit": retired["commit"] if retired else None,
                       "invocation_configured": bool(cases), "response_assertions_configured": any(r["scope"]["kind"] == "response" for r in cases),
                       "state_verification_configured": any(r["scope"]["kind"] in {"state", "query", "db"} for r in cases) or api in workflows,
                       "workflow": workflows.get(api), "version_support": "Removed from current 4.39.7 code line; developer confirmed 2026-10-15" if retired else "requires target-version confirmation",
                       "contract_pending": [r["contract_issue"] for r in cases if r.get("test_group") == "contract_review" and r["contract_issue"]],
                       "developer_confirmed_behavior": confirmed_design.get(api),
                       "configured_business_scenarios": [{"case_id": r["case_id"], "scenario": r["scenario"], "expected": r["expected"], "intentional_invalid": r["intentional_invalid"]} for r in cases],
                       "last_validation": "not_run", "gap": None if cases or face_retired or retired else "No enabled Excel case; wrapper/feature/contract verification required"})
    (out / "interface-coverage.json").write_text(json.dumps(matrix, ensure_ascii=False, indent=2), encoding="utf-8")
    print("Migrated",sum(r['enabled'] for r in audit),"enabled cases;",sum(r.get('previous_code_only',False) for r in audit),"code-only cases reviewed;",len(matrix),"interfaces mapped")


if __name__ == "__main__": main()
