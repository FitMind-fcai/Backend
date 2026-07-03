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

Env vars
--------
  AI_API_KEY        OpenRouter key — the SAME key AICoachService already uses
                     in production. No separate testing key needed.
  EVAL_TEST_MODEL    Model to use for THIS eval run only (default:
                     openai/gpt-4o-mini). Production's AI_MODEL
                     default is untouched.

Usage
-----
  docker exec FitMind_APIs python tests/evaluation/eval_coaching_relevance.py
"""
import json
import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path

from app.ai_services.ai_coach.ai_coach_service import AICoachService
from app.ai_services.ai_coach.dtos import UserProfileDTO

# How many scenarios to evaluate concurrently (bounded to stay under
# OpenRouter rate limits while still cutting wall-clock time substantially).
MAX_WORKERS = int(os.environ.get("EVAL_MAX_WORKERS", "5"))

# Model used for THIS eval run only — production's AI_MODEL is untouched.
TEST_MODEL = os.environ.get("EVAL_TEST_MODEL", "openai/gpt-4o-mini")

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

_ATHLETE_PROFILE = UserProfileDTO(
    age=24, gender="Female", height=170.0, weight=62.0,
    fitness_goal="Improve Endurance", activity_level="Very Active",
    dietary_preference=None, medical_conditions=None,
    allergies=None, injuries=None, medications=None,
)

_BEGINNER_PROFILE = UserProfileDTO(
    age=52, gender="Male", height=176.0, weight=98.0,
    fitness_goal="Lose Weight", activity_level="Sedentary",
    dietary_preference=None, medical_conditions="Hypertension",
    allergies=None, injuries=None, medications="Lisinopril 10mg daily",
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
    {
        "name": "Slightly Under Calories, Workout Done",
        "expected_urgency": "on_track",
        "profile": _STANDARD_PROFILE,
        "snapshot": {
            "calories_target": 1800,
            "calories_consumed": 1650,
            "calorie_gap": 150,
            "protein_target": 140,
            "protein_consumed": 130.0,
            "protein_gap": 10.0,
            "meal_types_logged": ["Breakfast", "Lunch", "Dinner"],
            "workout_sessions_logged": 1,
            "weight_logged": True,
            "latest_weight_kg": 79.8,
        },
        "expected_concepts": ["track", "goal", "protein"],
        "forbidden_concepts": ["as your AI", "I am an AI"],
    },
    {
        "name": "Endurance Athlete — Long Run Logged, Under-fueled",
        "expected_urgency": "needs_attention",
        "profile": _ATHLETE_PROFILE,
        "snapshot": {
            "calories_target": 2600,
            "calories_consumed": 1900,
            "calorie_gap": 700,
            "protein_target": 130,
            "protein_consumed": 80.0,
            "protein_gap": 50.0,
            "meal_types_logged": ["Breakfast", "Lunch"],
            "workout_sessions_logged": 1,
            "weight_logged": False,
            "latest_weight_kg": None,
        },
        "expected_concepts": ["calorie", "fuel", "eat", "protein"],
        "forbidden_concepts": ["great job", "perfect"],
    },
    {
        "name": "Athlete — Two Workouts, Fully Fueled",
        "expected_urgency": "on_track",
        "profile": _ATHLETE_PROFILE,
        "snapshot": {
            "calories_target": 2600,
            "calories_consumed": 2580,
            "calorie_gap": 20,
            "protein_target": 130,
            "protein_consumed": 128.0,
            "protein_gap": 2.0,
            "meal_types_logged": ["Breakfast", "Lunch", "Dinner", "Snack"],
            "workout_sessions_logged": 2,
            "weight_logged": True,
            "latest_weight_kg": 61.8,
        },
        "expected_concepts": ["track", "goal", "keep"],
        "forbidden_concepts": ["as your AI", "I am an AI"],
    },
    {
        "name": "Hypertensive Beginner — Missed Workout, Over Sodium-Risk Meals",
        "expected_urgency": "off_track",
        "profile": _BEGINNER_PROFILE,
        "snapshot": {
            "calories_target": 1900,
            "calories_consumed": 2400,
            "calorie_gap": -500,
            "protein_target": 110,
            "protein_consumed": 70.0,
            "protein_gap": 40.0,
            "meal_types_logged": ["Breakfast", "Lunch", "Dinner", "Snack"],
            "workout_sessions_logged": 0,
            "weight_logged": False,
            "latest_weight_kg": None,
        },
        "expected_concepts": ["calorie", "workout", "over"],
        "forbidden_concepts": ["great job", "well done"],
    },
    {
        "name": "Hypertensive Beginner — First Workout Completed",
        "expected_urgency": "on_track",
        "profile": _BEGINNER_PROFILE,
        "snapshot": {
            "calories_target": 1900,
            "calories_consumed": 1880,
            "calorie_gap": 20,
            "protein_target": 110,
            "protein_consumed": 105.0,
            "protein_gap": 5.0,
            "meal_types_logged": ["Breakfast", "Lunch", "Dinner"],
            "workout_sessions_logged": 1,
            "weight_logged": True,
            "latest_weight_kg": 97.5,
        },
        "expected_concepts": ["track", "workout", "great start"],
        "forbidden_concepts": ["as your AI", "I am an AI"],
    },
    {
        "name": "Diabetic — Skipped Meals, No Workout, No Logs Late Day",
        "expected_urgency": "off_track",
        "profile": _DIABETIC_PROFILE,
        "snapshot": {
            "calories_target": 1600,
            "calories_consumed": 300,
            "calorie_gap": 1300,
            "protein_target": 120,
            "protein_consumed": 15.0,
            "protein_gap": 105.0,
            "meal_types_logged": ["Breakfast"],
            "workout_sessions_logged": 0,
            "weight_logged": False,
            "latest_weight_kg": None,
        },
        "expected_concepts": ["log", "meal", "eat"],
        "forbidden_concepts": ["great job"],
    },
    {
        "name": "Diabetic — Slight Calorie Overage, Workout Done",
        "expected_urgency": "needs_attention",
        "profile": _DIABETIC_PROFILE,
        "snapshot": {
            "calories_target": 1600,
            "calories_consumed": 1780,
            "calorie_gap": -180,
            "protein_target": 120,
            "protein_consumed": 115.0,
            "protein_gap": 5.0,
            "meal_types_logged": ["Breakfast", "Lunch", "Dinner"],
            "workout_sessions_logged": 1,
            "weight_logged": True,
            "latest_weight_kg": 91.5,
        },
        "expected_concepts": ["calorie", "over", "workout"],
        "forbidden_concepts": ["as your AI", "I am an AI"],
    },
    {
        "name": "Weight Loss Goal — Small Protein Deficit",
        "expected_urgency": "needs_attention",
        "profile": _STANDARD_PROFILE,
        "snapshot": {
            "calories_target": 1800,
            "calories_consumed": 1750,
            "calorie_gap": 50,
            "protein_target": 140,
            "protein_consumed": 90.0,
            "protein_gap": 50.0,
            "meal_types_logged": ["Breakfast", "Lunch", "Dinner"],
            "workout_sessions_logged": 1,
            "weight_logged": True,
            "latest_weight_kg": 79.2,
        },
        "expected_concepts": ["protein", "increase", "goal"],
        "forbidden_concepts": ["great job", "perfect"],
    },
    {
        "name": "No Meals, But Workout Logged",
        "expected_urgency": "needs_attention",
        "profile": _STANDARD_PROFILE,
        "snapshot": {
            "calories_target": 1800,
            "calories_consumed": 0,
            "calorie_gap": 1800,
            "protein_target": 140,
            "protein_consumed": 0.0,
            "protein_gap": 140.0,
            "meal_types_logged": [],
            "workout_sessions_logged": 1,
            "weight_logged": False,
            "latest_weight_kg": None,
        },
        "expected_concepts": ["log", "meal", "eat", "track"],
        "forbidden_concepts": ["great job"],
    },
    {
        "name": "Weight Regression Logged Despite Good Adherence",
        "expected_urgency": "needs_attention",
        "profile": _STANDARD_PROFILE,
        "snapshot": {
            "calories_target": 1800,
            "calories_consumed": 1790,
            "calorie_gap": 10,
            "protein_target": 140,
            "protein_consumed": 138.0,
            "protein_gap": 2.0,
            "meal_types_logged": ["Breakfast", "Lunch", "Dinner"],
            "workout_sessions_logged": 1,
            "weight_logged": True,
            "latest_weight_kg": 81.2,  # up from previous readings
        },
        "expected_concepts": ["weight", "consistency", "patience"],
        "forbidden_concepts": ["as your AI", "I am an AI"],
    },
    {
        "name": "Massive Overeating, No Workout",
        "expected_urgency": "off_track",
        "profile": _STANDARD_PROFILE,
        "snapshot": {
            "calories_target": 1800,
            "calories_consumed": 3400,
            "calorie_gap": -1600,
            "protein_target": 140,
            "protein_consumed": 110.0,
            "protein_gap": 30.0,
            "meal_types_logged": ["Breakfast", "Lunch", "Dinner", "Snack", "Snack"],
            "workout_sessions_logged": 0,
            "weight_logged": False,
            "latest_weight_kg": None,
        },
        "expected_concepts": ["calorie", "over", "deficit"],
        "forbidden_concepts": ["great job", "well done", "perfect"],
    },
    {
        "name": "Athlete — Rest Day, No Workout Expected",
        "expected_urgency": "on_track",
        "profile": _ATHLETE_PROFILE,
        "snapshot": {
            "calories_target": 2200,
            "calories_consumed": 2180,
            "calorie_gap": 20,
            "protein_target": 130,
            "protein_consumed": 125.0,
            "protein_gap": 5.0,
            "meal_types_logged": ["Breakfast", "Lunch", "Dinner"],
            "workout_sessions_logged": 0,
            "weight_logged": True,
            "latest_weight_kg": 61.5,
        },
        "expected_concepts": ["recovery", "rest", "nutrition"],
        "forbidden_concepts": ["as your AI", "I am an AI"],
    },
    {
        "name": "Beginner — Two Consecutive Missed Workouts",
        "expected_urgency": "off_track",
        "profile": _BEGINNER_PROFILE,
        "snapshot": {
            "calories_target": 1900,
            "calories_consumed": 2100,
            "calorie_gap": -200,
            "protein_target": 110,
            "protein_consumed": 60.0,
            "protein_gap": 50.0,
            "meal_types_logged": ["Breakfast", "Lunch", "Dinner"],
            "workout_sessions_logged": 0,
            "weight_logged": False,
            "latest_weight_kg": None,
        },
        "expected_concepts": ["workout", "start", "move"],
        "forbidden_concepts": ["great job", "well done"],
    },
    {
        "name": "Standard Profile — Only Water/Hydration Logged",
        "expected_urgency": "needs_attention",
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
            "weight_logged": True,
            "latest_weight_kg": 80.1,
        },
        "expected_concepts": ["log", "meal", "eat", "track"],
        "forbidden_concepts": ["great job"],
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
    print(f"  AI Coach (this run) : {TEST_MODEL}")
    print(f"  Scenarios           : {len(SCENARIOS)}  (running {MAX_WORKERS} concurrently)")
    print("=" * 65)

    print("\nInitialising AI Coach Service ...", end=" ", flush=True)
    coach = AICoachService(model=TEST_MODEL)   # uses AI_API_KEY; only the model is overridden
    print("ready")

    def _evaluate_scenario(scenario: dict) -> dict:
        name = scenario["name"]
        profile = scenario["profile"]
        lines = [f"\n[{name}]"]

        try:
            response = coach.analyze_daily_progress(
                snapshot_data=scenario["snapshot"],
                user_goal=profile.fitness_goal,
                user_profile_context=profile.to_context_string(),
            )
            suggestion = response.get("suggestion", "")
            urgency = response.get("urgency", "")

            lines.append(f"  urgency   : {urgency}")
            lines.append(
                f"  suggestion: {suggestion[:120]}..." if len(suggestion) > 120
                else f"  suggestion: {suggestion}"
            )

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

            lines.append(f"  checks    : {passed_count}/{len(checks)} passed  ->  {overall} ({score_pct}%)")
            for chk in checks:
                icon = "OK  " if chk["passed"] else "FAIL"
                lines.append(f"    [{icon}] {chk['name']}: {chk['reasoning']}")

            print("\n".join(lines))

            return {
                "scenario": name,
                "overall": overall,
                "score_pct": score_pct,
                "urgency_returned": urgency,
                "expected_urgency": scenario["expected_urgency"],
                "suggestion": suggestion,
                "checks": checks,
            }

        except Exception as exc:
            import traceback as tb
            lines.append(f"  ERROR: {exc}")
            print("\n".join(lines))
            return {
                "scenario": name,
                "overall": "ERROR",
                "error": str(exc),
                "traceback": tb.format_exc(),
            }

    results_by_name = {}
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = {executor.submit(_evaluate_scenario, s): s["name"] for s in SCENARIOS}
        for future in as_completed(futures):
            result = future.result()
            results_by_name[result["scenario"]] = result

    # Preserve original SCENARIOS order in the final report
    results = [results_by_name[s["name"]] for s in SCENARIOS]

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
