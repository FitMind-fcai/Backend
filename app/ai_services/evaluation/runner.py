"""
runner.py — Main evaluation loop.

run_evaluation(num_samples, plan_type, output_path, delay_seconds) → Dict

Generates test cases, calls the AI Coach service to produce plans, evaluates
each plan with the LLM judge, aggregates results, and saves to JSON.
"""
from __future__ import annotations

import json
import os
import time
import traceback
from datetime import datetime
from typing import Any, Dict, List

from app.ai_services.ai_coach.ai_coach_service import AICoachService
from app.ai_services.evaluation.evaluators import (
    evaluate_nutrition_plan,
    evaluate_workout_plan,
)
from app.ai_services.evaluation.reporting import (
    aggregate_reports,
    generate_markdown_report,
    print_accuracy_banner,
    print_check_table,
    print_section,
    print_summary_block,
)
from app.ai_services.evaluation.test_cases import (
    make_nutrition_test_cases,
    make_workout_test_cases,
)


def run_evaluation(
    num_samples: int = 100,
    plan_type: str = "both",
    output_path: str = "",
    delay_seconds: float = 1.5,
    report_path: str = "",
) -> Dict[str, Any]:
    """
    Run the full evaluation pipeline.

    Args:
        num_samples:    Total number of test cases.
        plan_type:      "workout", "nutrition", or "both".
        output_path:    File path for the JSON results. Defaults to
                        app/ai_services/evaluation/results/eval_results.json.
        delay_seconds:  Sleep between API calls to avoid rate limiting.
        report_path:    File path for the Markdown report. Defaults to same
                        directory as output_path with a .md extension.

    Returns:
        Full results dict (also written to output_path).
    """
    print_section("AI Coach  —  RAG + Prompt Engineering  (LLM-as-Judge Evaluation)")
    print(f"  Samples       : {num_samples}")
    print(f"  Plan type     : {plan_type}")
    print(f"  Judge method  : LLM-as-judge  (semantic constraint verification)")
    print(f"  Pass threshold: 70%")
    print(f"  Started       : {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(
        "\n  NOTE: Each test case makes 2 LLM calls — one to generate the plan,\n"
        "        one for the judge to verify constraints semantically."
    )

    # ── Init service ──────────────────────────────────────────────────────
    print("\n  Initialising AI Coach Service …", end=" ", flush=True)
    service = AICoachService(model="llama-3.3-70b-versatile")
    groq_client = service.client
    model = service.model
    print("ready ✓")

    # ── Build test cases ──────────────────────────────────────────────────
    if plan_type == "both":
        n_workout = num_samples // 2
        n_nutrition = num_samples - n_workout
    elif plan_type == "workout":
        n_workout, n_nutrition = num_samples, 0
    else:
        n_workout, n_nutrition = 0, num_samples

    workout_cases = make_workout_test_cases(n_workout)
    nutrition_cases = make_nutrition_test_cases(n_nutrition)
    print(f"\n  Test cases: {len(workout_cases)} workout  +  {len(nutrition_cases)} nutrition")

    workout_reports: List[Dict[str, Any]] = []
    nutrition_reports: List[Dict[str, Any]] = []
    errors: List[Dict[str, Any]] = []

    # ── Workout loop ──────────────────────────────────────────────────────
    if workout_cases:
        print_section(f"Workout Evaluations  ({len(workout_cases)} cases)")
        total_w = len(workout_cases)
        for i, (profile, prefs) in enumerate(workout_cases, 1):
            label = (
                f"  [{i:3d}/{total_w}] "
                f"goal={profile.fitness_goal:<22} "
                f"equip={prefs.equipment_availability:<18} "
                f"cond={(profile.medical_conditions or '—')[:20]}"
            )
            print(label, end=" … ", flush=True)
            try:
                plan = service.generate_workout_plan(profile, prefs)
                report = evaluate_workout_plan(plan, profile, prefs, groq_client, model)
                rdict = report.to_dict()
                rdict["_meta"] = {
                    "case_index": i,
                    "goal": profile.fitness_goal,
                    "medical": profile.medical_conditions,
                    "injuries": profile.injuries,
                    "equipment": prefs.equipment_availability,
                    "days_requested": prefs.workout_days_per_week,
                    "difficulty": prefs.workout_difficulty,
                }
                workout_reports.append(rdict)
                icon = "✅ PASS" if report.passed else "❌ FAIL"
                print(f"{icon}  ({report.overall_score:.1f}%)")
            except Exception as exc:
                print(f"💥 ERROR: {exc}")
                errors.append({
                    "plan_type": "workout", "case_index": i,
                    "error": str(exc), "traceback": traceback.format_exc(),
                })
            if i < total_w:
                time.sleep(delay_seconds)

    # ── Nutrition loop ────────────────────────────────────────────────────
    if nutrition_cases:
        print_section(f"Nutrition Evaluations  ({len(nutrition_cases)} cases)")
        total_n = len(nutrition_cases)
        for i, (profile, prefs) in enumerate(nutrition_cases, 1):
            label = (
                f"  [{i:3d}/{total_n}] "
                f"goal={profile.fitness_goal:<22} "
                f"diet={(profile.dietary_preference or '—'):<14} "
                f"allergy={(profile.allergies or '—')[:18]}"
            )
            print(label, end=" … ", flush=True)
            try:
                plan = service.generate_nutrition_plan(profile, prefs)
                report = evaluate_nutrition_plan(plan, profile, prefs, groq_client, model)
                rdict = report.to_dict()
                rdict["_meta"] = {
                    "case_index": i,
                    "goal": profile.fitness_goal,
                    "dietary": profile.dietary_preference,
                    "allergies": profile.allergies,
                    "meals_requested": prefs.meals_per_day,
                    "calorie_pref": prefs.calorie_preference,
                    "exclude": prefs.exclude_ingredients,
                }
                nutrition_reports.append(rdict)
                icon = "✅ PASS" if report.passed else "❌ FAIL"
                print(f"{icon}  ({report.overall_score:.1f}%)")
            except Exception as exc:
                print(f"💥 ERROR: {exc}")
                errors.append({
                    "plan_type": "nutrition", "case_index": i,
                    "error": str(exc), "traceback": traceback.format_exc(),
                })
            if i < total_n:
                time.sleep(delay_seconds)

    # ── Aggregate ─────────────────────────────────────────────────────────
    workout_agg = aggregate_reports(workout_reports)
    nutrition_agg = aggregate_reports(nutrition_reports)
    all_reports = workout_reports + nutrition_reports
    combined_agg = aggregate_reports(all_reports)

    # ── Print results ─────────────────────────────────────────────────────
    print_section("EVALUATION RESULTS SUMMARY")

    if workout_agg:
        print_summary_block("WORKOUT PLANS", workout_agg)
        print()
        print_check_table(workout_agg["per_check"])

    if nutrition_agg:
        print_summary_block("NUTRITION PLANS", nutrition_agg)
        print()
        print_check_table(nutrition_agg["per_check"])

    if errors:
        print(f"\n  ⚠️  {len(errors)} error(s):")
        for err in errors:
            print(f"    • [{err['plan_type']} case {err['case_index']}] {err['error']}")

    print_section("WEAKEST CHECKS  (bottom 3)")
    all_check_rates: Dict[str, float] = {}
    for tag, agg in [("workout", workout_agg), ("nutrition", nutrition_agg)]:
        for chk_name, stats in (agg.get("per_check") or {}).items():
            all_check_rates[f"[{tag}] {chk_name}"] = stats["pass_rate_pct"]
    for rank, (name, pr) in enumerate(
        sorted(all_check_rates.items(), key=lambda x: x[1])[:3], 1
    ):
        icon = "❌" if pr < 60 else "⚠️ "
        print(f"  {rank}. {icon} {name}  →  {pr:.1f}% pass rate")

    # ── Overall accuracy banner ───────────────────────────────────────────
    overall_agg = combined_agg if combined_agg else (workout_agg or nutrition_agg or {})
    print_accuracy_banner(overall_agg)

    # ── Save to JSON ──────────────────────────────────────────────────────
    # evaluation/results/ lives next to this file (runner.py)
    _eval_dir = os.path.dirname(os.path.abspath(__file__))
    _results_dir = os.path.join(_eval_dir, "results")
    os.makedirs(_results_dir, exist_ok=True)

    project_root = os.path.dirname(
        os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    )

    if output_path:
        abs_output = (
            os.path.join(project_root, output_path)
            if not os.path.isabs(output_path) else output_path
        )
    else:
        abs_output = os.path.join(_results_dir, "eval_results.json")

    overall_score = overall_agg.get("avg_score_pct", 0.0)
    grade = (
        "EXCELLENT"         if overall_score >= 90 else
        "GOOD"              if overall_score >= 80 else
        "FAIR"              if overall_score >= 70 else
        "NEEDS IMPROVEMENT"
    )

    results: Dict[str, Any] = {
        "metadata": {
            "timestamp": datetime.now().isoformat(),
            "num_requested": num_samples,
            "num_completed": len(all_reports),
            "num_errors": len(errors),
            "plan_type": plan_type,
            "judge_method": "llm_as_judge",
            "pass_threshold_pct": 70.0,
        },
        "overall_accuracy": {
            "avg_score_pct": overall_score,
            "pass_rate_pct": overall_agg.get("pass_rate_pct", 0.0),
            "grade": grade,
            "total_plans": overall_agg.get("total", 0),
            "plans_passed": overall_agg.get("passed", 0),
        },
        "workout": {"aggregate": workout_agg, "reports": workout_reports},
        "nutrition": {"aggregate": nutrition_agg, "reports": nutrition_reports},
        "combined_aggregate": combined_agg,
        "errors": errors,
    }

    with open(abs_output, "w", encoding="utf-8") as fh:
        json.dump(results, fh, indent=2, ensure_ascii=False)
    print(f"  💾 Full results saved → {abs_output}")

    # ── Markdown report ───────────────────────────────────────────────────
    if report_path:
        md_output = (
            os.path.join(project_root, report_path)
            if not os.path.isabs(report_path) else report_path
        )
    else:
        md_output = os.path.splitext(abs_output)[0] + ".md"
    generate_markdown_report(results, md_output)
    print(f"  📄 Markdown report saved → {md_output}")

    print_section("Done")
    return results
