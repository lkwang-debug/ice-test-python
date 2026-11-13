"""Join documented-interface inventory with real Allure results; never equate touch with coverage."""
import argparse
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from common.reporting import summarize_results


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--results", type=Path)
    parser.add_argument("--output", type=Path, default=ROOT / "docs/coverage-status.json")
    args = parser.parse_args()
    matrix = json.loads((ROOT / "docs/interface-coverage.json").read_text(encoding="utf-8"))
    definitions = json.loads((ROOT / "docs/case-migration.json").read_text(encoding="utf-8"))
    statuses, all_results = {}, []
    if args.results:
        for f in args.results.glob("*-result.json"):
            r = json.loads(f.read_text(encoding="utf-8")); all_results.append(r)
            for c in definitions:
                if c["case_id"] in r.get("name", ""):
                    statuses[c["case_id"]] = r["status"]
    for item in matrix:
        item["execution_status"] = dict(Counter(statuses[c] for c in item["case_ids"] if c in statuses))
        item["last_validation"] = "executed" if any(s != "skipped" for s in item["execution_status"]) else "not_run"
        if item.get("workflow"):
            item["workflow_execution_status"] = dict(Counter(
                r["status"] for r in all_results if item["workflow"] in r.get("name", "")))
        item["uncovered"] = {
            "business_branches": "No completeness claim; documented business branches require their own scenario mapping",
            "state_effect": not item["state_verification_configured"]}
        if item["execution_status"].get("passed"):
            item["version_support"] = "At least one Excel scenario executed successfully against the selected target"
    report = {"documented_interfaces": len(matrix),
              "active_interfaces": sum(i.get("scope_status") != "retired" for i in matrix),
              "retired_interfaces": sum(i.get("scope_status") == "retired" for i in matrix),
              "enabled_excel_cases": sum(c["enabled"] for c in definitions),
              "previous_code_only_cases": sum(c.get("previous_code_only", False) for c in definitions),
              "verification_scopes": dict(Counter(c["scope"]["kind"] for c in definitions if c.get("previous_code_only"))),
              "run_statistics": dict(Counter(r["status"] for r in all_results)),
              "result_directory": str(args.results.resolve()) if args.results else None,
              "result_time_range": {"start_epoch_ms": min(r.get("start", 0) for r in all_results),
                                    "stop_epoch_ms": max(r.get("stop", 0) for r in all_results)} if all_results else None,
              "outcome_classifications": summarize_results(all_results)["counts"],
              "issue_groups": summarize_results(all_results)["issues"],
              "note": "Configured, executed, passed and business-effect coverage are distinct; skips do not count as execution. Selected result files may predate current definitions; historical counts are not a new run.",
              "interfaces": matrix}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({k: v for k, v in report.items() if k != "interfaces"}, ensure_ascii=True, indent=2))


if __name__ == "__main__": main()
