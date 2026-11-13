import pytest
from common.reporting import classify_result, summarize_results
from common.runtime import GatewayRuntime
from common.outcomes import PrerequisiteBlocked
from common.gateway_response import GatewayResult
from common.executor import execute_case


def result(status, **labels):
    return {"status": status, "name": "case", "labels": [{"name": k, "value": v} for k, v in labels.items()]}


@pytest.mark.parametrize("status,labels,category", [
    ("broken", {"outcome_type": "prerequisite_blocked"}, "prerequisite_blocked"),
    ("skipped", {"outcome_type": "version_unsupported"}, "version_unsupported"),
    ("skipped", {"outcome_type": "contract_review"}, "contract_review"),
    ("skipped", {}, "not_applicable"),
    ("failed", {"test_group": "backend_defect"}, "backend_defect"),
    ("failed", {"test_group": "compatibility"}, "compatibility_gap"),
])
def test_distinct_nonpass_categories(status, labels, category):
    assert classify_result(result(status, **labels)) == category


def test_blocked_unsupported_and_review_never_inflate_pass_count():
    summary = summarize_results([result("passed"), result("skipped", outcome_type="contract_review"),
                                 result("broken", outcome_type="prerequisite_blocked"),
                                 result("skipped", outcome_type="version_unsupported")])
    assert summary["counts"]["passed"] == 1 and sum(summary["counts"].values()) == 4


def test_modern_face_id_is_never_used_as_legacy_id():
    runtime = GatewayRuntime({"topology": "single", "primary_device_id": "MainDev", "capabilities": ["face"]})
    def query(cls, method, params):
        if method == "checkDevList":
            return {"data": [{"devId": "MainDev", "devNodeId": "n", "devIp": "a"}]}
        return {"data": []}
    runtime.query = query
    class DB:
        def fetch(self, sql, params=()):
            if "COUNT" in sql: return [{"total": 0}]
            if "t_face_library" in sql: return [{"id": 5, "source_id": 99, "source_type": 1}]
            return []
    runtime.database = DB()
    assert runtime.env["face_id"] is None
    assert runtime.env["modern_face_present"] is True
    with pytest.raises(PrerequisiteBlocked): runtime.require_legacy_face()


def test_version_probe_is_cached_in_one_run():
    runtime = GatewayRuntime({})
    calls = []
    runtime.call = lambda *args: calls.append(args) or GatewayResult(4108, 4108, None, b"", "probe", 0)
    assert runtime.probe_method("device.exampleMethod", {}).invoke_code == 4108
    assert runtime.probe_method("device.exampleMethod", {}).invoke_code == 4108
    assert len(calls) == 1


def prepared_case(group="regression"):
    class Runtime:
        topology = "single"
        def call(self, *args): return GatewayResult(4107, 4107, None, b"", "case", 0)
    class Prepared:
        case = {"case_id": "baseline", "case_name": "baseline", "class_name": "user", "method": "updateUserInfo",
                "params": {}, "expected": {"resultCode": 4107}, "assertions": [],
                "verification": {"kind": "state", "checker": "no_change", "target": "user"},
                "test_group": group, "doc_ref": "PDF p77", "contract_issue": "Unspecified rule"}
        context = {"env": {}, "fixture": {}, "case": {}}
        runtime = Runtime()
        checked = False
        def verify_state(self, *args): self.checked = True
    return Prepared()


def test_explicit_4107_baseline_still_requires_unchanged_state():
    scenario = prepared_case()
    execute_case(scenario)
    assert scenario.checked
    def bad_state(*args): raise AssertionError("state changed")
    scenario.verify_state = bad_state
    with pytest.raises(AssertionError, match="state changed"): execute_case(scenario)


def test_contract_review_executes_call_and_state_check_before_xfail():
    scenario = prepared_case("contract_review")
    with pytest.raises(pytest.xfail.Exception): execute_case(scenario)
    assert scenario.checked


@pytest.mark.parametrize("old_outcome", ["contract_review", "version_unsupported"])
def test_runtime_error_cannot_be_hidden_by_review_or_unsupported_label(old_outcome):
    assert classify_result(result("broken", outcome_type=old_outcome)) == "infrastructure_error"


def test_cleanup_failure_takes_priority_over_contract_status():
    assert classify_result(result("broken", outcome_type="cleanup_failure", test_group="contract_review")) == "cleanup_failure"
