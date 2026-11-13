"""Execute one prevalidated case and its explicitly declared verification."""
import json
import allure
from common.assertions import assert_expected, assert_rules
from common.references import resolve
from common.evidence import redact
from common.outcomes import contract_review


def attach(name, value):
    allure.attach(json.dumps(redact(value), ensure_ascii=False, indent=2, default=str),
                  name=name, attachment_type=allure.attachment_type.JSON)


def execute_case(scenario):
    case, runtime = scenario.case, scenario.runtime
    context = scenario.context
    allure.dynamic.title(case["case_id"] + " - " + case["case_name"])
    allure.dynamic.label("topology", runtime.topology)
    allure.dynamic.label("verification", case["verification"]["kind"])
    allure.dynamic.label("doc_ref", case["doc_ref"])
    group = case.get("test_group", "regression")
    allure.dynamic.label("test_group", group)
    if case.get("issue_id"):
        allure.dynamic.label("issue_id", case["issue_id"])
    params = resolve(case.get("params") or {}, context)
    expected = resolve(case["expected"], context)
    assertions = resolve(case["assertions"], context)
    verification = resolve(case["verification"], context)
    attach("Case definition and verification scope", {"case_id": case["case_id"], "source": case.get("source"),
           "topology": runtime.topology, "params": params, "expected": expected,
           "assertions": assertions, "verification": verification, "intentional_invalid": case.get("intentional_invalid", [])})
    if verification.get("checker") == "route_time":
        scenario.wait_for_route_clock_tick()
    with allure.step("ICE call (no automatic write retries)"):
        result = runtime.call(case["class_name"], case["method"], params)
    attach("Actual result", result.evidence())
    failures = []
    with allure.step("Envelope and exact-path assertions"):
        try:
            wanted = expected.get("resultCode", 0)
            if case.get("expected_outcome") == "rejected":
                # Error semantics are per-case. A code alone does not prove an
                # implementation bug; known SQL defects have explicit assertions.
                business = result.payload.get("result") if isinstance(result.payload, dict) else None
                rejected = result.invoke_code != 0 or result.response_code != 0 or type(business) is int and business < 0
                assert rejected, "Invalid request was not rejected"
            else:
                assert type(wanted) is int and result.invoke_code == wanted, "invoke_code expected=%r actual=%r" % (wanted, result.invoke_code)
            if case.get("expected_outcome") != "rejected" and (result.invoke_code == 0 or "response_code" in case):
                response_wanted = case.get("response_code", wanted)
                assert result.response_code == response_wanted, "response_code expected=%r actual=%r" % (response_wanted, result.response_code)
            assert_expected({k: v for k, v in expected.items() if k != "resultCode"}, result.legacy())
            assert_rules(result.legacy(), assertions)
        except AssertionError as exc:
            failures.append("Response: " + str(exc))
    with allure.step("Declared business verification: " + verification["kind"]):
        try:
            kind = verification["kind"]
            if kind == "query":
                query = verification["query"]
                actual = runtime.query(query["class_name"], query["method"], query.get("params", {}))
                attach("Read-back result", actual)
                assert_rules(actual, verification["assertions"])
            elif kind == "db":
                actual = runtime.database.fetch(verification["sql"], verification.get("params", []))
                attach("Read-only database result", actual)
                assert_rules(actual, verification["assertions"])
            elif kind == "state":
                scenario.verify_state(verification["checker"], params, result)
            else:
                attach("Verification scope", verification)
        except AssertionError as exc:
            failures.append("State: " + str(exc))
        except Exception:
            attach("Response assertion failures before blocked verification", failures)
            raise
    if group == "contract_review":
        contract_review(case.get("contract_issue") or case["case_name"],
                        {"result": result.evidence(), "rule_differences": failures,
                         "verification": verification, "case_id": case["case_id"]})
    if failures:
        attach("Assertion differences", failures)
        allure.dynamic.label("outcome_type", "backend_defect" if group == "backend_defect" else "assertion_failure")
        raise AssertionError("\n".join(failures))
    return result
