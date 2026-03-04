"""
reporting.py — Aggregation and terminal display helpers.

aggregate_reports(reports)          → Dict   (pass rates, avg scores, per-check stats)
print_section(title)                → None
print_summary_block(label, agg)     → None
print_check_table(per_check)        → None
print_accuracy_banner(combined_agg) → None
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
