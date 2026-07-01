"""
Coaching Relevance Evaluation
==============================
Tests whether the FitMind AI coach produces relevant, data-specific
coaching messages when given different daily log snapshots.

How it works
------------
1. Defines realistic daily log scenarios (snapshot_data dicts)
   that represent what a user would have logged in 24 hours.
2. Calls the REAL AICoachService.analyze_daily_progress() — the
   same method called by RecommendationService.get_daily_suggestion()
   which is triggered by the coaching endpoints.
3. Evaluates each response against 4 criteria:
   - Urgency correctness  : does urgency match the scenario?
   - Numeric specificity  : does the suggestion mention actual numbers?
   - Actionability        : is the suggestion concrete (verb + action)?
   - Not generic boilerplate: avoids phrases like "great job", "as your AI"

Required env vars
-----------------
  AI_API_KEY   OpenRouter key (used by the real AI coach)

Usage
-----
  docker exec -e AI_API_KEY=sk-or-... FitMind_APIs \\
    python tests/evaluation/eval_coaching_relevance.py
"""
import json
import os
import sys
from datetime import datetime
from pathlib import Path

from app.ai_services.ai_coach.ai_coach_service import AICoachService
from app.ai_services.ai_coach.dtos import UserProfileDTO

RESULTS_DIR = Path(os.environ.get("RESULTS_DIR", Path(__file__).parent / "results"))
RESULTS_DIR.mkdir(parents=True, exist_ok=True)


# ---------------------------------------------------------------------------
# Profiles (context passed to the coach)
# ---------------------------------------------------------------------------

_STANDARD_PROFILE = UserProfileDTO(
    age=30, gender="Male", height=178.0, weight=80.0,
    fitness_goal="Lose Weight", activity_level="Moderately Active",
    dietary_preference=None, medical_conditions=None,
    allergies=None, injuries=None, medications=None,
)

_DIABETIC_PROFILE = UserProfileDTO(
    age=45, gender="Male", height=175.0, weight=92.0,
    fitness_goal="Lose Weight", activity_level="Lightly Active",
    dietary_preference="Diabetic-friendly",
    medical_conditions="Type 2 Diabetes",
    allergies=None, injuries=None,
    medications="Metformin 1000mg daily",
)


# ---------------------------------------------------------------------------
# Daily log scenarios
# Each dict maps directly to the snapshot_data format consumed by
# AICoachService.analyze_daily_progress()
# ---------------------------------------------------------------------------

SCENARIOS = [
    {
        "name": "Missed Workout + Significantly Over Calories",
        "expected_urgency": "off_track",
        "profile": _STANDARD_PROFILE,
        "snapshot": {
            "calories_target": 1800,
            "calories_consumed": 2850,  # 58% over target
            "calorie_gap": -1050,
            "protein_target": 140,
            "protein_consumed": 95.0,
            "protein_gap": 45.0,
            "meal_types_logged": ["Breakfast", "Lunch", "Dinner", "Snack"],
            "workout_sessions_logged": 0,   # skipped
            "weight_logged": False,
            "latest_weight_kg": None,
        },
        "expected_concepts": ["calorie", "workout", "over", "deficit"],
        "forbidden_concepts": ["great job", "well done", "perfect"],
    },
    {
        "name": "Perfect Adherence Day",
        "expected_urgency": "on_track",
        "profile": _STANDARD_PROFILE,
        "snapshot": {
            "calories_target": 1800,
            "calories_consumed": 1820,   # within 1%
            "calorie_gap": -20,
            "protein_target": 140,
            "protein_consumed": 142.0,
            "protein_gap": -2.0,
            "meal_types_logged": ["Breakfast", "Lunch", "Dinner"],
            "workout_sessions_logged": 1,
            "weight_logged": True,
            "latest_weight_kg": 79.5,
        },
        "expected_concepts": ["track", "goal", "keep"],
        "forbidden_concepts": ["as your AI", "I am an AI"],
    },
    {
        "name": "No Logs At All",
        "expected_urgency": "off_track",
        "profile": _STANDARD_PROFILE,
        "snapshot": {
            "calories_target": 1800,
            "calories_consumed": 0,
            "calorie_gap": 1800,
            "protein_target": 140,
            "protein_consumed": 0.0,
            "protein_gap": 140.0,
            "meal_types_logged": [],
            "workout_sessions_logged": 0,
            "weight_logged": False,
            "latest_weight_kg": None,
        },
        "expected_concepts": ["log", "track"],
        "forbidden_concepts": ["great job"],
    },
    {
        "name": "Diabetic — Good Nutrition But No Workout",
        "expected_urgency": "needs_attention",
        "profile": _DIABETIC_PROFILE,
        "snapshot": {
            "calories_target": 1600,
            "calories_consumed": 1580,
            "calorie_gap": 20,
            "protein_target": 120,
            "protein_consumed": 118.0,
            "protein_gap": 2.0,
            "meal_types_logged": ["Breakfast", "Lunch", "Dinner"],
            "workout_sessions_logged": 0,
            "weight_logged": True,
            "latest_weight_kg": 91.8,
        },
        "expected_concepts": ["workout", "exercise", "physical"],
        "forbidden_concepts": ["as your AI", "I am an AI"],
    },
    {
        "name": "Partial Day — Only Breakfast Logged, Afternoon",
        "expected_urgency": "needs_attention",
        "profile": _STANDARD_PROFILE,
        "snapshot": {
            "calories_target": 1800,
            "calories_consumed": 420,   # only breakfast
            "calorie_gap": 1380,
            "protein_target": 140,
            "protein_consumed": 28.0,
            "protein_gap": 112.0,
            "meal_types_logged": ["Breakfast"],
            "workout_sessions_logged": 0,
            "weight_logged": False,
            "latest_weight_kg": None,
        },
        "expected_concepts": ["meal", "lunch", "log", "eat"],
        "forbidden_concepts": ["great job", "perfect day"],
    },
]


# ---------------------------------------------------------------------------
# Evaluation helpers
# ---------------------------------------------------------------------------

def _check_urgency(result: dict, scenario: dict) -> tuple:
    """Returns (passed, reasoning)."""
    got = result.get("urgency", "")
    expected = scenario["expected_urgency"]
    if got == expected:
        return True, f"urgency='{got}' as expected"
    # partial credit: needs_attention accepted in place of off_track
    if expected == "off_track" and got == "needs_attention":
        return True, f"urgency='{got}' (acceptable — close to expected off_track)"
    return False, f"expected '{expected}', got '{got}'"


def _check_specificity(suggestion: str, snapshot: dict) -> tuple:
    """Returns (passed, reasoning). Checks whether suggestion cites actual numbers."""
    cal_consumed = str(int(snapshot["calories_consumed"]))
    cal_target = str(int(snapshot.get("calories_target") or 0))
    suggestion_lower = suggestion.lower()
    # Either an exact calorie number OR general numeric terms
    has_number = (
        cal_consumed in suggestion
        or cal_target in suggestion
        or any(c.isdigit() for c in suggestion)
    )
    if has_number:
        return True, "suggestion references at least one numeric value"
    return False, "suggestion contains no specific numbers"


def _check_actionability(suggestion: str) -> tuple:
    """Returns (passed, reasoning). Checks that suggestion has an actionable verb."""
    action_words = [
        "eat", "log", "drink", "train", "work out", "workout", "add",
        "reduce", "increase", "track", "aim", "try", "hit", "focus",
        "avoid", "start", "finish", "complete", "cut", "boost",
        "record", "get",
    ]
    sl = suggestion.lower()
    found = [w for w in action_words if w in sl]
    if found:
        return True, f"actionable verb(s) found: {found[:3]}"
    return False, "no concrete action verb found"


def _check_not_generic(suggestion: str, scenario: dict) -> tuple:
    """Returns (passed, reasoning). Checks it avoids known boilerplate."""
    boilerplate = scenario.get("forbidden_concepts", [])
    sl = suggestion.lower()
    found = [p for p in boilerplate if p.lower() in sl]
    if found:
        return False, f"generic/forbidden phrase found: {found}"
    # Also check for the ultra-generic opener
    if suggestion.lower().startswith(("great job", "well done", "amazing")):
        return False, "starts with boilerplate praise"
    return True, "no generic boilerplate detected"


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def run_coaching_relevance_evaluation() -> dict:
    print("=" * 65)
    print("  FITMIND COACHING RELEVANCE EVALUATION")
    print(f"  Scenarios : {len(SCENARIOS)}")
    print("=" * 65)

    print("\nInitialising AI Coach Service ...", end=" ", flush=True)
    coach = AICoachService()
    print("ready")

    results = []
    for i, scenario in enumerate(SCENARIOS, 1):
        name = scenario["name"]
        profile = scenario["profile"]
        print(f"\n[{i}/{len(SCENARIOS)}] {name}")

        try:
            response = coach.analyze_daily_progress(
                snapshot_data=scenario["snapshot"],
                user_goal=profile.fitness_goal,
                user_profile_context=profile.to_context_string(),
            )
            suggestion = response.get("suggestion", "")
            urgency = response.get("urgency", "")

            print(f"  urgency   : {urgency}")
            print(f"  suggestion: {suggestion[:120]}..." if len(suggestion) > 120 else f"  suggestion: {suggestion}")

            u_pass, u_reason = _check_urgency(response, scenario)
            s_pass, s_reason = _check_specificity(suggestion, scenario["snapshot"])
            a_pass, a_reason = _check_actionability(suggestion)
            g_pass, g_reason = _check_not_generic(suggestion, scenario)

            checks = [
                {"name": "urgency_correct",   "passed": u_pass, "reasoning": u_reason},
                {"name": "numeric_specificity","passed": s_pass, "reasoning": s_reason},
                {"name": "actionability",      "passed": a_pass, "reasoning": a_reason},
                {"name": "not_generic",        "passed": g_pass, "reasoning": g_reason},
            ]

            passed_count = sum(1 for c in checks if c["passed"])
            score_pct = round(100 * passed_count / len(checks), 1)
            overall = "PASS" if passed_count >= 3 else "FAIL"   # 3 of 4 required

            print(f"  checks    : {passed_count}/{len(checks)} passed  ->  {overall} ({score_pct}%)")
            for chk in checks:
                icon = "OK  " if chk["passed"] else "FAIL"
                print(f"    [{icon}] {chk['name']}: {chk['reasoning']}")

            results.append({
                "scenario": name,
                "overall": overall,
                "score_pct": score_pct,
                "urgency_returned": urgency,
                "expected_urgency": scenario["expected_urgency"],
                "suggestion": suggestion,
                "checks": checks,
            })

        except Exception as exc:
            import traceback as tb
            print(f"  ERROR: {exc}")
            results.append({
                "scenario": name,
                "overall": "ERROR",
                "error": str(exc),
                "traceback": tb.format_exc(),
            })

    # -- summary ----------------------------------------------------------
    passed = sum(1 for r in results if r.get("overall") == "PASS")
    avg_score = sum(r.get("score_pct", 0) for r in results) / max(len(results), 1)
    print("\n" + "=" * 65)
    print("  SUMMARY")
    print("=" * 65)
    for r in results:
        icon = r.get("overall", "ERROR")
        print(f"  {r['scenario']:<45} {icon} ({r.get('score_pct', 0):.0f}%)")
    print(f"\n  Scenarios passing: {passed} / {len(results)}")
    print(f"  Average score    : {avg_score:.1f}%")

    output = {
        "run_at": datetime.utcnow().isoformat() + "Z",
        "scenarios_tested": len(results),
        "scenarios_passed": passed,
        "avg_score_pct": round(avg_score, 1),
        "results": results,
    }
    out_file = RESULTS_DIR / "coaching_relevance_results.json"
    out_file.write_text(json.dumps(output, indent=2))
    print(f"\n  Full results saved to: {out_file}")
    return output


if __name__ == "__main__":
    run_coaching_relevance_evaluation()
