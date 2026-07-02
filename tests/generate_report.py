"""
generate_report.py — Runs the unit + integration test suite and produces a
presentation-ready report: pass/fail summary and coverage, both for the
whole app and scoped to only the modules that actually have tests
(so untested modules like planning/AI-services/notifications don't drag
down the headline coverage number).

Usage
-----
  docker exec FitMind_APIs python tests/generate_report.py
"""
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from xml.etree import ElementTree as ET

RESULTS_DIR = Path(__file__).parent / "results"
RESULTS_DIR.mkdir(parents=True, exist_ok=True)

JUNIT_XML = RESULTS_DIR / "junit.xml"
COVERAGE_JSON = RESULTS_DIR / "coverage.json"
REPORT_JSON = RESULTS_DIR / "test_report.json"

# Modules that actually have unit/integration tests targeting them — used to
# compute a coverage score that isn't diluted by untested modules
# (planning_module, ai_services, notification_module, recommendation scoring, etc.)
TESTED_MODULE_PREFIXES = [
    "app/auth_module/",
    "app/profile_module/",
    "app/tracking_module/",
    "app/core/",
    "app/recommendation_system/routes/coaching.py",
    "app/recommendation_system/schemas/coaching.py",
]


def _run_pytest() -> int:
    cmd = [
        sys.executable, "-m", "pytest",
        "tests/unit", "tests/integration",
        f"--junitxml={JUNIT_XML}",
        "--cov=app",
        f"--cov-report=json:{COVERAGE_JSON}",
    ]
    result = subprocess.run(cmd)
    return result.returncode


def _parse_junit() -> dict:
    root = ET.parse(JUNIT_XML).getroot()
    suites = root.findall("testsuite") if root.tag == "testsuites" else [root]

    by_file: dict[str, dict[str, int]] = {}
    total = failures = errors = skipped = 0
    duration = 0.0

    for suite in suites:
        total += int(suite.attrib.get("tests", 0))
        failures += int(suite.attrib.get("failures", 0))
        errors += int(suite.attrib.get("errors", 0))
        skipped += int(suite.attrib.get("skipped", 0))
        duration += float(suite.attrib.get("time", 0))

        for case in suite.findall("testcase"):
            file_key = case.attrib.get("classname", "unknown").split(".")[0]
            entry = by_file.setdefault(
                file_key, {"passed": 0, "failed": 0, "error": 0, "skipped": 0}
            )
            if case.find("failure") is not None:
                entry["failed"] += 1
            elif case.find("error") is not None:
                entry["error"] += 1
            elif case.find("skipped") is not None:
                entry["skipped"] += 1
            else:
                entry["passed"] += 1

    return {
        "total": total,
        "passed": total - failures - errors - skipped,
        "failed": failures,
        "errors": errors,
        "skipped": skipped,
        "duration_sec": round(duration, 2),
        "by_file": by_file,
    }


def _coverage_summary(files: dict, file_filter) -> dict:
    stmts = miss = 0
    matched = {}
    for path, info in files.items():
        norm = path.replace("\\", "/")
        if file_filter(norm):
            s = info["summary"]["num_statements"]
            m = info["summary"]["missing_lines"]
            stmts += s
            miss += m
            matched[norm] = {
                "statements": s,
                "missing": m,
                "percent_covered": round(info["summary"]["percent_covered"], 1),
            }
    pct = round(100 * (stmts - miss) / stmts, 1) if stmts else 0.0
    return {"statements": stmts, "missing": miss, "percent_covered": pct, "files": matched}


def _parse_coverage() -> dict:
    data = json.loads(COVERAGE_JSON.read_text())
    files = data.get("files", {})
    overall = _coverage_summary(files, lambda p: p.startswith("app/"))
    scoped = _coverage_summary(
        files, lambda p: any(p.startswith(prefix) for prefix in TESTED_MODULE_PREFIXES)
    )
    return {"overall": overall, "scoped_to_tested_modules": scoped}


def main() -> dict:
    print("=" * 65)
    print("  FITMIND TEST REPORT")
    print(f"  Run at: {datetime.now(timezone.utc).isoformat()}")
    print("=" * 65)

    exit_code = _run_pytest()
    tests = _parse_junit()
    coverage = _parse_coverage()

    report = {
        "run_at": datetime.now(timezone.utc).isoformat(),
        "pytest_exit_code": exit_code,
        "tests": tests,
        "coverage": coverage,
    }
    REPORT_JSON.write_text(json.dumps(report, indent=2))

    overall_cov = coverage["overall"]
    scoped_cov = coverage["scoped_to_tested_modules"]

    print("\n" + "=" * 65)
    print("  SUMMARY")
    print("=" * 65)
    print(
        f"  Tests    : {tests['passed']}/{tests['total']} passed "
        f"({tests['failed']} failed, {tests['errors']} errors, {tests['skipped']} skipped)"
    )
    print(f"  Duration : {tests['duration_sec']}s")
    print(
        f"  Coverage (whole app)      : {overall_cov['percent_covered']}%  "
        f"({overall_cov['statements'] - overall_cov['missing']}/{overall_cov['statements']} stmts)"
    )
    print(
        f"  Coverage (tested modules) : {scoped_cov['percent_covered']}%  "
        f"({scoped_cov['statements'] - scoped_cov['missing']}/{scoped_cov['statements']} stmts)"
    )
    print(f"\n  Full report saved to : {REPORT_JSON}")
    print(f"  JUnit XML saved to   : {JUNIT_XML}")
    print("=" * 65)

    return report


if __name__ == "__main__":
    main()
