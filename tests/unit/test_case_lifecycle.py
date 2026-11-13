import copy
import json
from pathlib import Path
import pytest
from common.cases import validate_case, load_workbook_cases
from common.references import resolve
from common.database import validate_select, bind_select
from common.scenarios import Scenario
from common.runtime import GatewayRuntime, load_profile
from common.gateway_response import GatewayResult


def valid_case():
    return {"class_name": "room", "method": "getRoomInfo", "case_name": "negative",
            "case_id": "case-1", "topology": "any", "requires": [], "fixture": "none",
            "expected": {"resultCode": 0}, "params": {"roomId": None}, "assertions": [],
            "verification": {"kind": "contract", "reason": "Call contract only"},
            "doc_ref": "PDF p.62", "intentional_invalid": ["roomId"]}


def test_intentionally_invalid_request_reaches_execution_definition():
    case = valid_case(); case["params"]["roomId"] = "deliberately_wrong_type"
    validate_case(case)


@pytest.mark.parametrize("ref", ["${env.node_id", "${device_devRegister.response.id}", "${env.data.0.id}"])
def test_invalid_and_legacy_references_are_rejected(ref):
    c = valid_case(); c["params"] = {"node": ref}
    # Numeric positional environment paths are rejected separately by resource schema.
    if ref == "${env.data.0.id}":
        with pytest.raises(ValueError): resolve(ref, {"env": {"data": []}})
    else:
        with pytest.raises(ValueError): validate_case(c)


def test_references_preserve_types_and_are_scenario_local():
    assert resolve("${env.id}", {"env": {"id": 5}}) == 5
    assert resolve("prefix_${env.id}", {"env": {"id": 5}}) == "prefix_5"
    with pytest.raises(ValueError): resolve("${fixture.id}", {"fixture": {}})


@pytest.mark.parametrize("sql", ["DELETE FROM t_roominfo", "SELECT 1; DELETE FROM t_roominfo",
                                  "SELECT 1 INTO OUTFILE 'file'", "SELECT SLEEP(1)", "SELECT 1 /* comment */"])
def test_database_oracles_cannot_write_or_run_multiple_statements(sql):
    with pytest.raises(ValueError): validate_select(sql)


def test_sql_parameters_cannot_become_sql():
    sql = bind_select("SELECT DocID FROM t_roomdocslist WHERE DocID=%s", ["x';DELETE FROM t_roominfo;"])
    assert "DELETE" not in sql and "CONVERT(0x" in sql


def test_cleanup_continues_after_failure():
    s = Scenario.__new__(Scenario); s.cleanups = []
    events = []
    s.add_cleanup("first", lambda: events.append("first"))
    def failure():
        events.append("last"); raise RuntimeError("failure")
    s.add_cleanup("last", failure)
    with pytest.raises(RuntimeError, match="Cleanup failed"): s.close()
    assert events == ["last", "first"]


def test_single_skips_dual_cases_before_connecting():
    r = GatewayRuntime({"topology": "single"})
    with pytest.raises(pytest.skip.Exception):
        r.check_case_applicability({"topology": "dual", "requires": []}, "resource")
    assert r.client is None


def test_declared_database_oracle_cannot_silently_degrade():
    r = GatewayRuntime({"topology": "single"})
    with pytest.raises(RuntimeError, match="not configured"):
        r.check_case_applicability({"topology": "any", "requires": ["database"]}, "resource")


def test_migrated_workbook_has_independent_valid_cases():
    cases = load_workbook_cases(Path(__file__).resolve().parents[2] / "data/test_cases.xlsx")
    assert len(cases) == 270
    assert all("face" not in c["method"].lower() for c in cases)
    assert len({c["case_id"] for c in cases}) == len(cases)
    assert all(not c.get("save_response") for c in cases)
    assert all(".response." not in json.dumps(c["params"]) for c in cases)


def test_dual_profile_requires_second_identity(tmp_path):
    p = tmp_path / "profile.json"; p.write_text('{"topology":"dual","secondary_device_id":null}', encoding="utf-8")
    with pytest.raises(ValueError, match="secondary_device_id"): load_profile(p)


class FakeClient:
    adapter = "adapter"
    def connect(self): return True
    def disconnect(self): pass
    def invoke_result(self, cls, method, params, version):
        if method == "checkDevList":
            payload = [{"devId": "second", "devNodeId": "n", "devIp": "b"},
                       {"devId": "first", "devNodeId": "n", "devIp": "a"}]
        else:
            payload = [{"serviceId": 9, "serviceAppId": 11, "serviceAddress": "TCP:a:1;"}]
        return GatewayResult(0, 0, payload, b"[]", "fake", 0)


def test_device_and_service_identity_is_independent_of_order():
    r = GatewayRuntime({"topology": "dual", "primary_device_id": "first", "secondary_device_id": "second"}, FakeClient)
    assert r.env["primary"]["address"] == "a"
    assert r.env["secondary"]["address"] == "b"
    assert r.env["primary"]["services"]["FMConfSrv"]["id"] == 9


def test_duplicate_device_identity_blocks_instead_of_using_first_record():
    class Duplicates(FakeClient):
        def invoke_result(self, cls, method, params, version):
            return GatewayResult(0, 0, [{"devId": "first"}, {"devId": "first"}], b"[]", "fake", 0)
    with pytest.raises(RuntimeError, match="exactly one"):
        GatewayRuntime({"topology": "single", "primary_device_id": "first"}, Duplicates).env


def test_two_devices_on_different_nodes_do_not_satisfy_same_node_dual_profile():
    class DifferentNodes(FakeClient):
        def invoke_result(self, cls, method, params, version):
            result = super().invoke_result(cls, method, params, version)
            if method == "checkDevList": result.payload[0]["devNodeId"] = "other"
            return result
    with pytest.raises(RuntimeError, match="same node"):
        GatewayRuntime({"topology": "dual", "primary_device_id": "first", "secondary_device_id": "second"}, DifferentNodes).env


def test_negative_request_is_actually_sent_and_declared_oracle_runs_after_assertion_failure():
    from common.executor import execute_case
    class Runtime:
        topology = "single"
        sent = []
        def call(self, cls, method, params):
            self.sent.append(params)
            return GatewayResult(0, 0, {"result": -1}, b'{}', "fake", 0)
    class Prepared:
        case = valid_case()
        context = {"env": {}, "fixture": {}, "case": {}}
        runtime = Runtime()
        verified = False
        def verify_state(self, *args): self.verified = True
    s = Prepared()
    s.case["params"] = {"roomId": "wrong_type"}
    s.case["expected"] = {"resultCode": 0, "result": 0}
    s.case["verification"] = {"kind": "state", "checker": "no_change", "target": "route"}
    with pytest.raises(AssertionError): execute_case(s)
    assert s.runtime.sent == [{"roomId": "wrong_type"}] and s.verified


def test_loader_reports_all_bad_rows_and_duplicate_ids_before_any_call(monkeypatch):
    import openpyxl
    class Sheet:
        title = "room"
        def iter_rows(self, **kwargs):
            headers = list(valid_case()) + ["auto"]
            c = valid_case()
            row = [json.dumps(c[k]) if isinstance(c[k], (dict, list)) else c[k] for k in c] + [True]
            invalid = dict(c, case_id="")
            return iter([headers, row, row,
                         [json.dumps(invalid[k]) if isinstance(invalid[k], (dict, list)) else invalid[k] for k in invalid] + [True]])
    class Workbook:
        def __iter__(self): return iter([Sheet()])
        def close(self): pass
    monkeypatch.setattr(openpyxl, "load_workbook", lambda *a, **k: Workbook())
    with pytest.raises(ValueError) as error:
        load_workbook_cases("fake.xlsx")
    assert "Duplicate case_id" in str(error.value) and "Missing case_id" in str(error.value)


def test_evidence_redacts_nested_password_without_changing_request():
    from common.evidence import redact
    value = {"params": {"password": "secret", "verifyCode": "123", "roomId": 1}}
    result = redact(value)
    assert result["params"]["password"] == "<redacted>" and result["params"]["roomId"] == 1
    assert value["params"]["password"] == "secret"


def test_single_meeting_does_not_require_an_exclusive_flag():
    r = GatewayRuntime({"topology": "single", "exclusive": True})
    case = {"class_name": "device", "method": "updateLicenseInfo", "fixture": "none",
            "topology": "any", "requires": ["write", "global", "exclusive"]}
    r.check_case_applicability(case, "global")
    assert r.client is None


def test_default_configuration_does_not_require_json_or_ini():
    from common.config import TEST_CONFIG, ICE_CONFIG
    profile = load_profile()
    assert profile["host"] == TEST_CONFIG["host"]
    assert profile["topology"] == TEST_CONFIG["topology"]
    assert TEST_CONFIG["face_enabled"] is False
    assert "face" not in profile["capabilities"]
    assert "cdn" not in profile["capabilities"] and "phone_gateway" not in profile["capabilities"]
    assert TEST_CONFIG["host"] in ICE_CONFIG["locator"]


def test_license_restore_uses_gson_wire_alias():
    from common.mutation_fixtures import LICENSE_FIELDS
    assert LICENSE_FIELDS["4KCount"] == "FourKCount"
    assert "fourKCount" not in LICENSE_FIELDS


def test_known_sql_defect_has_explicit_per_case_policy():
    from common.executor import execute_case
    class Runtime:
        topology = "single"
        def call(self, *args): return GatewayResult(4107, 4107, None, b"", "fake", 0)
    class Prepared:
        case = dict(valid_case(), expected={}, expected_outcome="rejected",
                    assertions=[{"path": "$.resultCode", "op": "not_in", "value": [4107]}])
        context = {"env": {}, "fixture": {}, "case": {}}
        runtime = Runtime()
    with pytest.raises(AssertionError, match="not_in"):
        execute_case(Prepared())


def test_known_wire_names_are_preserved_without_a_profile():
    profile = load_profile()
    assert profile["method_aliases"]["device.getRoomDefDevId"] == "getRoomDefDevID"
    assert profile["method_aliases"]["user.getFaceInfoByFaceId"] == "getFaceInfo"


@pytest.mark.parametrize("switch", [False, "False", " false ", 0])
def test_disabled_rows_are_not_loaded_or_prevalidated(monkeypatch, switch):
    import openpyxl
    class Sheet:
        title = "room"
        def iter_rows(self, **kwargs):
            # auto is deliberately first, as in the user-facing workbook.
            c = valid_case()
            headers = ["auto"] + list(c)
            enabled = [True] + [json.dumps(v) if isinstance(v, (dict, list)) else v for v in c.values()]
            # Retired historical rows may contain obsolete or malformed requests.
            disabled = [switch] + ["invalid historical data"] * len(c)
            return iter([headers, disabled, enabled])
    class Workbook:
        def __iter__(self): return iter([Sheet()])
        def close(self): pass
    monkeypatch.setattr(openpyxl, "load_workbook", lambda *a, **k: Workbook())
    assert [c["case_id"] for c in load_workbook_cases("fake.xlsx")] == ["case-1"]


def test_unknown_execution_switch_is_rejected():
    from common.cases import parse_auto
    with pytest.raises(ValueError, match="auto must"):
        parse_auto("flase")


def test_retired_face_supplementary_checks_stop_before_connecting():
    r = GatewayRuntime(load_profile())
    with pytest.raises(pytest.skip.Exception):
        r.check_case_applicability({"topology": "any", "requires": ["face"]}, "global")
    assert r.client is None


@pytest.mark.parametrize("case_id,code,should_pass", [
    ("file-004", 4108, True), ("file-005", 4108, True),
    ("file-004", 4107, False), ("file-005", 0, False),
    ("file-006", 0, True), ("file-007", 0, True),
    ("file-006", 4107, False), ("file-007", 4108, False),
])
def test_confirmed_del_dir_contract_and_state_oracle(case_id, code, should_pass):
    from common.executor import execute_case
    case = next(c for c in load_workbook_cases(Path(__file__).resolve().parents[2] / "data/test_cases.xlsx")
                if c["case_id"] == case_id)
    assert case["verification"] == {"kind": "state", "checker": "no_change", "target": "file"}
    class Runtime:
        topology = "single"
        def call(self, *args): return GatewayResult(code, code, None, b"", "fake", 0)
    class Prepared:
        runtime = Runtime()
        context = {"env": {"room_id": 10000, "absent_room_id": 2147483000},
                   "fixture": {"doc_id": "prepared_directory"}, "case": {}}
        verified = False
        def verify_state(self, *args): self.verified = True
    s = Prepared(); s.case = case
    if should_pass:
        execute_case(s)
    else:
        with pytest.raises(AssertionError): execute_case(s)
    assert s.verified  # State must be checked even when the response is wrong.


def test_del_dir_idempotent_success_cannot_hide_accidental_deletion():
    from common.executor import execute_case
    case = next(c for c in load_workbook_cases(Path(__file__).resolve().parents[2] / "data/test_cases.xlsx")
                if c["case_id"] == "file-006")
    class Runtime:
        topology = "single"
        def call(self, *args): return GatewayResult(0, 0, None, b"", "fake", 0)
    class Prepared:
        runtime = Runtime()
        context = {"env": {"room_id": 10000}, "fixture": {}, "case": {}}
        def verify_state(self, *args): raise AssertionError("Negative request changed the prepared resource")
    s = Prepared(); s.case = case
    with pytest.raises(AssertionError, match="changed the prepared resource"):
        execute_case(s)
