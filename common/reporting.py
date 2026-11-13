"""Classify native Allure statuses without counting blocked/N/A/review as passes."""
import json
from collections import Counter, defaultdict
from pathlib import Path


def classify_result(result):
    labels = {item["name"]: item["value"] for item in result.get("labels", [])}
    status, outcome = result.get("status"), labels.get("outcome_type")
    if status == "passed":
        return "passed"
    if outcome == "cleanup_failure":
        return "cleanup_failure"
    if status == "broken":
        return "prerequisite_blocked" if outcome == "prerequisite_blocked" or "PrerequisiteBlocked" in result.get("statusDetails", {}).get("message", "") else "infrastructure_error"
    if status == "skipped":
        return outcome if outcome in {"version_unsupported", "contract_review"} else "not_applicable"
    if status == "failed":
        group = labels.get("test_group")
        return "compatibility_gap" if group == "compatibility" else "backend_defect" if group == "backend_defect" else "assertion_failure"
    return "unknown"


def summarize_results(results):
    counts, issues, cases = Counter(), defaultdict(list), []
    for result in results:
        category = classify_result(result)
        counts[category] += 1
        labels = {item["name"]: item["value"] for item in result.get("labels", [])}
        item = {"name": result.get("name"), "native_status": result.get("status"), "classification": category,
                "issue_id": labels.get("issue_id"), "reason": result.get("statusDetails", {}).get("message")}
        cases.append(item)
        if item["issue_id"] and result.get("status") != "passed":
            issues[item["issue_id"]].append(item["name"])
    return {"counts": dict(counts), "native_counts": dict(Counter(r.get("status") for r in results)),
            "issues": dict(issues), "cases": cases}


def read_results(directory):
    return [json.loads(path.read_text(encoding="utf-8")) for path in Path(directory).glob("*-result.json")]


def write_summary(directory, destination):
    summary = summarize_results(read_results(directory))
    Path(destination).write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    return summary
