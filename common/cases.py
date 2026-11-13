"""Validate test definitions before any remote business request is sent."""
import json
import re
from pathlib import Path
from common.assertions import validate_assertions

ROOT = Path(__file__).resolve().parent.parent
FIXTURES = {"none", "meeting", "route", "route_timer", "file", "user", "user_identity", "system_param", "service", "node", "license", "feature", "master", "device", "face_rollcall"}
VERIFICATIONS = {"contract", "response", "query", "db", "state"}


def walk_strings(value):
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for item in value.values():
            yield from walk_strings(item)
    elif isinstance(value, list):
        for item in value:
            yield from walk_strings(item)


def validate_references(value):
    for text in walk_strings(value):
        rest = re.sub(r"\$\{(?:env|fixture|case)\.[A-Za-z_0-9.]+\}", "", text)
        if "${" in rest:
            raise ValueError("Unresolved/legacy/malformed reference: %s" % text)


def validate_case(case):
    for field in ("class_name", "method", "case_name", "case_id"):
        if not isinstance(case.get(field), str) or not case[field].strip():
            raise ValueError("Missing %s" % field)
    if case.get("topology") not in ("any", "single", "dual"):
        raise ValueError("topology must be any, single or dual")
    if case.get("fixture") not in FIXTURES:
        raise ValueError("Unknown fixture")
    if not isinstance(case.get("requires"), list) or any(not isinstance(v, str) for v in case["requires"]):
        raise ValueError("requires must be an array of capability names")
    if not isinstance(case.get("expected"), dict):
        raise ValueError("expected must be an object")
    if case.get("expected_outcome", "exact") not in {"exact", "rejected"}:
        raise ValueError("expected_outcome must be exact or rejected")
    if case.get("test_group", "regression") not in {"regression", "behavior_baseline", "backend_defect", "contract_review"}:
        raise ValueError("Unknown test_group")
    validate_assertions(case.get("assertions"))
    verification = case.get("verification")
    if not isinstance(verification, dict) or verification.get("kind") not in VERIFICATIONS:
        raise ValueError("verification.kind must describe the validation scope")
    if verification["kind"] in {"contract", "response"} and not verification.get("reason"):
        raise ValueError("Contract/response-only cases require a verification reason")
    if verification["kind"] == "query":
        if not isinstance(verification.get("query"), dict):
            raise ValueError("query verification requires query")
        validate_assertions(verification.get("assertions"))
    if verification["kind"] == "db":
        from common.database import validate_select
        validate_select(verification.get("sql", ""))
        validate_assertions(verification.get("assertions"))
    if verification["kind"] == "state" and verification.get("checker") not in {
            "system_param", "user", "room_count", "room_user", "route", "route_time", "route_precreate",
            "file", "service_list", "device_list", "license_time", "no_change", "license", "feature", "node", "service", "device"}:
        raise ValueError("Unknown state checker")
    if verification["kind"] == "state" and verification.get("checker") == "no_change":
        if verification.get("target") not in {"user", "route", "file", "room", "feature", "master", "face_members"}:
            raise ValueError("no_change requires a declared snapshot target")
    intentional = case.get("intentional_invalid", [])
    if not isinstance(intentional, list) or any(not isinstance(v, str) for v in intentional):
        raise ValueError("intentional_invalid must list deliberately invalid request fields")
    validate_references([case.get("params"), case["expected"], case["assertions"], verification])
    if not isinstance(case.get("doc_ref"), str) or not case["doc_ref"]:
        raise ValueError("doc_ref is required")


def parse_auto(value):
    """Excel execution switch; preserve the legacy enabled default for blank cells."""
    if value is None or value == "":
        return True
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)) and value in (0, 1):
        return bool(value)
    if isinstance(value, str) and value.strip().lower() in {"true", "false"}:
        return value.strip().lower() == "true"
    raise ValueError("auto must be True/False (or 1/0); blank defaults to True")


def load_workbook_cases(path):
    from openpyxl import load_workbook
    cases, errors, ids = [], [], set()
    with_workbook = load_workbook(path, read_only=True, data_only=True)
    try:
        for sheet in with_workbook:
            if sheet.title.lower() in {"summary", "config", "说明", "coverage", "migration"}:
                continue
            rows = sheet.iter_rows(values_only=True)
            headers = [str(v).strip() if v is not None else "" for v in next(rows)]
            if len([v for v in headers if v]) != len(set(v for v in headers if v)):
                errors.append("%s: duplicate column headers" % sheet.title)
            for row_num, values in enumerate(rows, 2):
                if not any(v is not None for v in values):
                    continue
                case = {k: v for k, v in zip(headers, values) if k}
                try:
                    if not parse_auto(case.get("auto", True)):
                        continue
                    case["class_name"] = sheet.title
                    for field, default in (("params", {}), ("expected", {}), ("requires", []),
                                           ("assertions", []), ("verification", {}), ("intentional_invalid", [])):
                        val = case.get(field)
                        case[field] = default if val in (None, "") else json.loads(val) if isinstance(val, str) else val
                    case["method"] = str(case.get("method", "")).strip()
                    case["source"] = "%s!row=%s" % (sheet.title, row_num)
                    validate_case(case)
                    if case["case_id"] in ids:
                        raise ValueError("Duplicate case_id: " + case["case_id"])
                    ids.add(case["case_id"])
                    cases.append(case)
                except (ValueError, TypeError) as exc:
                    errors.append("%s!%s: %s" % (sheet.title, row_num, exc))
    finally:
        with_workbook.close()
    if errors:
        raise ValueError("Case prevalidation failed before execution:\n" + "\n".join(errors))
    return cases
