"""
reporting.py — Aggregation and terminal display helpers.

aggregate_reports(reports)                          → Dict
print_section(title)                                → None
print_summary_block(label, agg)                     → None
print_check_table(per_check)                        → None
print_accuracy_banner(combined_agg)                 → None
generate_markdown_report(results, output_path)      → None
"""
from __future__ import annotations

from typing import Any, Dict, List

_WIDTH = 72


# ---------------------------------------------------------------------------
# Aggregation
# ---------------------------------------------------------------------------

def aggregate_reports(reports: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Compute pass rate, average score, and per-check stats from a list of to_dict() reports."""
    if not reports:
        return {}

    total = len(reports)
    passed_count = sum(1 for r in reports if r["passed"])
    scores = [r["overall_score_pct"] for r in reports]

    check_stats: Dict[str, Dict[str, Any]] = {}
    for report in reports:
        for chk in report["checks"]:
            if not chk["applicable"]:
                continue
            name: str = chk["name"]
            if name not in check_stats:
                check_stats[name] = {
                    "passed_count": 0,
                    "total_count": 0,
                    "score_sum": 0.0,
                    "weight": chk["weight"],
                }
            check_stats[name]["total_count"] += 1
            check_stats[name]["score_sum"] += chk["score"]
            if chk["passed"]:
                check_stats[name]["passed_count"] += 1

    per_check: Dict[str, Any] = {}
    for name, stats in check_stats.items():
        n = stats["total_count"]
        per_check[name] = {
            "pass_rate_pct": round(stats["passed_count"] / n * 100, 1),
            "avg_score_pct": round(stats["score_sum"] / n * 100, 1),
            "passed": stats["passed_count"],
            "total": n,
            "weight": stats["weight"],
        }

    return {
        "total": total,
        "passed": passed_count,
        "pass_rate_pct": round(passed_count / total * 100, 1),
        "avg_score_pct": round(sum(scores) / total, 1),
        "min_score_pct": round(min(scores), 1),
        "max_score_pct": round(max(scores), 1),
        "per_check": per_check,
    }


# ---------------------------------------------------------------------------
# Terminal display
# ---------------------------------------------------------------------------

def print_section(title: str) -> None:
    divider = "=" * _WIDTH
    print(f"\n{divider}")
    print(f"  {title}")
    print(divider)


def print_summary_block(label: str, agg: Dict[str, Any]) -> None:
    total = agg["total"]
    print(f"\n  {label}  ({total} samples)")
    print(
        f"    Overall pass rate : {agg['pass_rate_pct']:>6.1f}%   "
        f"({agg['passed']} / {total} passed)"
    )
    print(f"    Average score     : {agg['avg_score_pct']:>6.1f}%")
    print(
        f"    Score range       : "
        f"{agg['min_score_pct']:.1f}% – {agg['max_score_pct']:.1f}%"
    )


def print_check_table(per_check: Dict[str, Any]) -> None:
    print(f"  {'Check Name':<42} {'Pass%':>7} {'AvgScore':>9} {'N':>5}")
    print(f"  {'-' * 42} {'-' * 7} {'-' * 9} {'-' * 5}")
    for name, stats in sorted(per_check.items(), key=lambda x: x[1]["pass_rate_pct"]):
        pr = stats["pass_rate_pct"]
        icon = "✅" if pr >= 80 else ("⚠️ " if pr >= 60 else "❌")
        print(
            f"  {icon} {name:<40} {pr:>6.1f}%  "
            f"{stats['avg_score_pct']:>7.1f}%  {stats['total']:>4}"
        )


def print_accuracy_banner(agg: Dict[str, Any]) -> None:
    """Print the prominent overall model accuracy banner."""
    score = agg.get("avg_score_pct", 0.0)
    pass_rate = agg.get("pass_rate_pct", 0.0)
    total = agg.get("total", 0)
    passed = agg.get("passed", 0)

    grade = (
        "EXCELLENT"         if score >= 90 else
        "GOOD"              if score >= 80 else
        "FAIR"              if score >= 70 else
        "NEEDS IMPROVEMENT"
    )

    print(f"\n{'#' * _WIDTH}")
    print(f"#{'OVERALL MODEL ACCURACY':^{_WIDTH - 2}}#")
    print(f"#{'':^{_WIDTH - 2}}#")
    print(f"#  Average constraint score  : {score:>5.1f}%   →  {grade:<18}  #")
    print(f"#  Plans fully passed (≥70%) : {pass_rate:>5.1f}%   ({passed} / {total} plans)  #")
    print(f"#  Total plans evaluated      : {total:<5}                            #")
    print(f"{'#' * _WIDTH}\n")


# ---------------------------------------------------------------------------
# Markdown report
# ---------------------------------------------------------------------------

def _md_check_table(per_check: Dict[str, Any]) -> str:
    """Render a per-check stats dict as a markdown table string."""
    rows = ["| Check | Pass% | Avg Score | N | Status |",
            "|---|---|---|---|---|"]
    for name, stats in sorted(per_check.items(), key=lambda x: x[1]["pass_rate_pct"]):
        pr = stats["pass_rate_pct"]
        status = "✅ PASS" if pr >= 80 else ("⚠️ WARN" if pr >= 60 else "❌ FAIL")
        rows.append(
            f"| {name} | {pr:.1f}% | {stats['avg_score_pct']:.1f}% "
            f"| {stats['total']} | {status} |"
        )
    return "\n".join(rows)


def generate_markdown_report(results: Dict[str, Any], output_path: str) -> None:
    """
    Write a human-readable Markdown evaluation report to output_path.

    Args:
        results:     The full results dict returned by run_evaluation().
        output_path: Absolute path to write the .md file.
    """
    meta = results.get("metadata", {})
    overall = results.get("overall_accuracy", {})
    workout_agg = (results.get("workout") or {}).get("aggregate") or {}
    nutrition_agg = (results.get("nutrition") or {}).get("aggregate") or {}
    errors: List[Dict[str, Any]] = results.get("errors", [])

    score = overall.get("avg_score_pct", 0.0)
    grade = overall.get("grade", "N/A")

    lines: List[str] = []

    # ── Title ────────────────────────────────────────────────────────────
    lines += [
        "# AI Coach — Evaluation Report",
        "",
        f"> Generated: {meta.get('timestamp', 'N/A')}  ",
        f"> Judge method: LLM-as-judge (semantic constraint verification)  ",
        f"> Pass threshold: {meta.get('pass_threshold_pct', 70.0)}%",
        "",
    ]

    # ── Run metadata ─────────────────────────────────────────────────────
    lines += [
        "## Run Metadata",
        "",
        "| Parameter | Value |",
        "|---|---|",
        f"| Samples requested | {meta.get('num_requested', 'N/A')} |",
        f"| Samples completed | {meta.get('num_completed', 'N/A')} |",
        f"| Errors | {meta.get('num_errors', 0)} |",
        f"| Plan type | {meta.get('plan_type', 'N/A')} |",
        "",
    ]

    # ── Overall accuracy ─────────────────────────────────────────────────
    lines += [
        "## Overall Accuracy",
        "",
        f"| Metric | Value |",
        "|---|---|",
        f"| **Grade** | **{grade}** |",
        f"| Average constraint score | {score:.1f}% |",
        f"| Plans fully passed (≥70%) | {overall.get('pass_rate_pct', 0.0):.1f}% "
        f"({overall.get('plans_passed', 0)} / {overall.get('total_plans', 0)}) |",
        "",
    ]

    # ── Workout results ───────────────────────────────────────────────────
    if workout_agg:
        lines += [
            "## Workout Plans",
            "",
            f"- **Samples evaluated:** {workout_agg.get('total', 0)}",
            f"- **Pass rate:** {workout_agg.get('pass_rate_pct', 0.0):.1f}%  "
            f"({workout_agg.get('passed', 0)} / {workout_agg.get('total', 0)} passed)",
            f"- **Average score:** {workout_agg.get('avg_score_pct', 0.0):.1f}%",
            f"- **Score range:** {workout_agg.get('min_score_pct', 0.0):.1f}% – "
            f"{workout_agg.get('max_score_pct', 0.0):.1f}%",
            "",
            "### Per-Check Breakdown",
            "",
            _md_check_table(workout_agg.get("per_check", {})),
            "",
        ]

    # ── Nutrition results ─────────────────────────────────────────────────
    if nutrition_agg:
        lines += [
            "## Nutrition Plans",
            "",
            f"- **Samples evaluated:** {nutrition_agg.get('total', 0)}",
            f"- **Pass rate:** {nutrition_agg.get('pass_rate_pct', 0.0):.1f}%  "
            f"({nutrition_agg.get('passed', 0)} / {nutrition_agg.get('total', 0)} passed)",
            f"- **Average score:** {nutrition_agg.get('avg_score_pct', 0.0):.1f}%",
            f"- **Score range:** {nutrition_agg.get('min_score_pct', 0.0):.1f}% – "
            f"{nutrition_agg.get('max_score_pct', 0.0):.1f}%",
            "",
            "### Per-Check Breakdown",
            "",
            _md_check_table(nutrition_agg.get("per_check", {})),
            "",
        ]

    # ── Weakest checks ────────────────────────────────────────────────────
    all_check_rates: Dict[str, float] = {}
    for tag, agg in [("workout", workout_agg), ("nutrition", nutrition_agg)]:
        for chk_name, stats in (agg.get("per_check") or {}).items():
            all_check_rates[f"[{tag}] {chk_name}"] = stats["pass_rate_pct"]

    if all_check_rates:
        lines += ["## Weakest Checks (Bottom 3)", ""]
        for rank, (name, pr) in enumerate(
            sorted(all_check_rates.items(), key=lambda x: x[1])[:3], 1
        ):
            icon = "❌" if pr < 60 else "⚠️"
            lines.append(f"{rank}. {icon} **{name}** — {pr:.1f}% pass rate")
        lines.append("")

    # ── Errors ────────────────────────────────────────────────────────────
    if errors:
        lines += [
            f"## Errors ({len(errors)})",
            "",
        ]
        for err in errors:
            lines.append(
                f"- **[{err.get('plan_type', '?')} case {err.get('case_index', '?')}]** "
                f"`{err.get('error', 'unknown error')}`"
            )
        lines.append("")

    # ── Per-plan judge fact-check ─────────────────────────────────────────
    for section_label, plan_reports in [
        ("Workout", (results.get("workout") or {}).get("reports") or []),
        ("Nutrition", (results.get("nutrition") or {}).get("reports") or []),
    ]:
        if not plan_reports:
            continue
        lines += [f"## {section_label} — Per-Plan Judge Fact-Check", ""]
        for r in plan_reports:
            meta = r.get("_meta", {})
            idx = meta.get("case_index", "?")
            verdict = "✅ PASS" if r.get("passed") else "❌ FAIL"
            score = r.get("overall_score_pct", 0.0)
            summary_parts = []
            if section_label == "Workout":
                summary_parts = [
                    f"goal={meta.get('goal', '?')}",
                    f"equipment={meta.get('equipment', '?')}",
                    f"condition={meta.get('medical', '—') or '—'}",
                    f"injuries={meta.get('injuries', '—') or '—'}",
                ]
            else:
                summary_parts = [
                    f"goal={meta.get('goal', '?')}",
                    f"diet={meta.get('dietary', '—') or '—'}",
                    f"allergy={meta.get('allergies', '—') or '—'}",
                    f"exclude={meta.get('exclude', '—') or '—'}",
                ]

            lines += [
                f"### Case {idx} — {verdict} ({score:.1f}%)",
                "",
                "  ".join(f"`{p}`" for p in summary_parts),
                "",
            ]

            # Check results table
            checks = r.get("checks", [])
            if checks:
                lines += ["**Check Results:**", ""]
                lines += ["| Check | Applicable | Result | Score | Violations | Reasoning |",
                          "|---|---|---|---|---|---|"]
                for chk in checks:
                    if not chk.get("applicable"):
                        continue
                    chk_icon = "✅" if chk.get("passed") else "❌"
                    raw_violations = chk.get("violations") or []
                    violations = "; ".join(
                        v if isinstance(v, str) else str(v)
                        for v in raw_violations
                    ) or "—"
                    reasoning = (chk.get("reasoning") or "—").replace("\n", " ").replace("|", "\\|")
                    lines.append(
                        f"| {chk['name']} | ✓ | {chk_icon} | {chk.get('score', 0)*100:.0f}% "
                        f"| {violations} | {reasoning} |"
                    )
                lines.append("")

            # Judge prompt (collapsible)
            judge_prompt = r.get("judge_prompt", "")
            judge_response = r.get("judge_raw_response", "")
            if judge_prompt:
                lines += [
                    "<details>",
                    "<summary>📋 Judge Prompt (click to expand)</summary>",
                    "",
                    "```",
                    judge_prompt,
                    "```",
                    "",
                    "</details>",
                    "",
                ]
            if judge_response:
                lines += [
                    "<details>",
                    "<summary>🤖 Judge Raw Response (click to expand)</summary>",
                    "",
                    "```json",
                    judge_response,
                    "```",
                    "",
                    "</details>",
                    "",
                ]
            lines.append("---")
            lines.append("")

    # ── Write file ────────────────────────────────────────────────────────
    with open(output_path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines))

