"""
generate_markdown_report.py — Renders a summarized Markdown report from
plan_safety_results.json (produced by eval_plan_safety.py).

Summary numbers come first (total accuracy, passed/fixed/failed counts,
severity breakdown, structural compliance), per-profile detail table after.
Markdown converts cleanly to PDF via Word/Google Docs import, pandoc, or any
online md-to-pdf tool.

Usage
-----
  docker exec FitMind_APIs python tests/evaluation/generate_markdown_report.py
"""
import json
from datetime import datetime
from pathlib import Path

RESULTS_DIR = Path(__file__).parent / "results"
INPUT_FILE = RESULTS_DIR / "plan_safety_results.json"
OUTPUT_FILE = RESULTS_DIR / "report.md"


def _verdict(result: dict) -> str:
    if "error" in result:
        return "ERROR"
    if result["judge_passed"]:
        return "PASS (1st try)"
    if "post_regen_passed" in result:
        return "FIXED by regen" if result["post_regen_passed"] else "STILL FAILING"
    return "CAUGHT (not re-verified)"


def _sev(result: dict) -> str:
    if "error" in result:
        return "—"
    s = result["severity_counts"]
    return f"S3={s['severity_3']} S2={s['severity_2']} S1={s['severity_1']}"


def _issues(result: dict) -> str:
    if "error" in result:
        return result.get("error", "")[:100]
    notable = [i for i in result.get("issues", []) if i.get("severity", 0) >= 2]
    if not notable:
        return "—"
    return "<br>".join(
        f"[S{i.get('severity')}] {i.get('location', '?')}: {i.get('problem', '?')}"
        for i in notable[:3]
    )


def generate_report(input_file: Path = INPUT_FILE, output_file: Path = OUTPUT_FILE) -> Path:
    if not input_file.exists():
        raise FileNotFoundError(f"{input_file} not found — run eval_plan_safety.py first.")

    data = json.loads(input_file.read_text())
    m = data["metrics"]
    results = data["results"]

    run_at = data.get("run_at", "")
    try:
        run_at_display = datetime.fromisoformat(run_at.replace("Z", "+00:00")).strftime("%Y-%m-%d %H:%M UTC")
    except Exception:
        run_at_display = run_at

    plans_evaluated = m["plans_evaluated"]
    plans_passed = m["plans_passed"]
    plans_caught = m["plans_needing_regeneration"]
    regen_attempted = m.get("post_regen_attempted", 0)
    regen_fixed = m.get("post_regen_fixed", 0)
    regen_still_failing = regen_attempted - regen_fixed
    total_safe_after_regen = plans_passed + regen_fixed
    overall_accuracy = round(100 * total_safe_after_regen / plans_evaluated, 1) if plans_evaluated else 0.0

    lines = []
    lines.append("# Plan Safety Evaluation Report")
    lines.append("")
    lines.append(f"- **Model**: `{data.get('ai_coach_model', 'unknown')}`")
    lines.append(f"- **Judge**: production `PlanJudge` (reused, not a separate eval judge)")
    lines.append(f"- **Run**: {run_at_display}")
    lines.append(f"- **Profiles tested**: {data['profiles_tested']}")
    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append("## Summary")
    lines.append("")
    lines.append("| Metric | Count | % |")
    lines.append("|---|---|---|")
    lines.append(f"| Plans evaluated | {plans_evaluated} | — |")
    lines.append(f"| Generation errors | {m['errors']} | — |")
    lines.append(f"| **Passed on first try** | {plans_passed} | {m['judge_pass_rate_pct']}% |")
    lines.append(f"| Caught for regeneration | {plans_caught} | {m['regeneration_rate_pct']}% |")
    if regen_attempted:
        lines.append(f"| — of those, fixed by auto-regen | {regen_fixed} | {m.get('post_regen_success_rate_pct', 0)}% of caught |")
        lines.append(f"| — of those, still failing after regen | {regen_still_failing} | {round(100 - (m.get('post_regen_success_rate_pct') or 0), 1)}% of caught |")
    lines.append(f"| **Overall accuracy (safe on 1st try + fixed by regen)** | {total_safe_after_regen} | **{overall_accuracy}%** |")
    lines.append("")

    sev = m["severity_counts"]
    lines.append("### Safety issues found (by severity)")
    lines.append("")
    lines.append("| Severity | Meaning | Count |")
    lines.append("|---|---|---|")
    lines.append(f"| 3 — Blocker | Always fails the plan (e.g. confirmed allergen, contraindicated movement) | {sev['severity_3']} |")
    lines.append(f"| 2 — Significant | Flagged, rarely fails a plan alone | {sev['severity_2']} |")
    lines.append(f"| 1 — Minor | Noted, never fails a plan | {sev['severity_1']} |")
    lines.append("")

    lines.append("### Structural compliance (free, rule-based — no LLM involved)")
    lines.append("")
    lines.append("| Check | Rate |")
    lines.append("|---|---|")
    lines.append(f"| Workout days match request (±1) | {m['workout_days_match_rate_pct']}% |")
    lines.append(f"| Nutrition meals match request (±1) | {m['nutrition_meals_match_rate_pct']}% |")
    lines.append(f"| Calories within 20% of target | {m['calories_within_20pct_rate_pct']}% |")
    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append("## Per-Profile Results")
    lines.append("")
    lines.append("| Profile | Workout Verdict | Workout Severity | Nutrition Verdict | Nutrition Severity | Notable Issues |")
    lines.append("|---|---|---|---|---|---|")
    for r in results:
        w, n = r["workout"], r["nutrition"]
        notable = "<br>".join(x for x in [_issues(w), _issues(n)] if x and x != "—") or "—"
        lines.append(
            f"| {r['profile']} | {_verdict(w)} | {_sev(w)} | {_verdict(n)} | {_sev(n)} | {notable} |"
        )
    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append("## Methodology")
    lines.append("")
    lines.append(
        "Each profile's workout and nutrition plan is first generated via the real "
        "`AICoachService` with automatic regeneration disabled, then judged directly by "
        "FitMind's own production safety judge (`PlanJudge`) — the exact same component "
        "and severity rubric used in the live app. No separate evaluation-only judge "
        "model is used."
    )
    lines.append("")
    lines.append(
        "**A plan \"caught for regeneration\" never reaches a real user.** In the live app, "
        "any plan the judge flags is automatically regenerated once with the judge's "
        "feedback before being served. For every flagged plan in this evaluation, that same "
        "real regenerate-once path was run and the result re-judged, to measure whether the "
        "automatic fix actually resolves the issue."
    )
    lines.append("")

    output_file.parent.mkdir(parents=True, exist_ok=True)
    output_file.write_text("\n".join(lines), encoding="utf-8")
    return output_file


if __name__ == "__main__":
    path = generate_report()
    print(f"Report written to: {path}")
