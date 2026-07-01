"""
AI Coaching Relevance Evaluation Script
========================================
Tests whether the AI coach generates messages that are actually
grounded in the user's logged activity data (not generic advice).

Usage:
    GROQ_API_KEY=your_key python tests/evaluation/eval_coaching_relevance.py

Optional env vars:
    GROQ_MODEL    Groq model to use (default: llama-3.3-70b-versatile)
    RESULTS_DIR   Directory to save JSON results (default: tests/evaluation/results)

Output:
    - Prints relevance scores to stdout
    - Saves full results to RESULTS_DIR/coaching_relevance_results.json
"""
import json
import os
import sys
from datetime import datetime
from pathlib import Path

try:
    from groq import Groq
except ImportError:
    print("ERROR: groq package not installed. Run: pip install groq")
    sys.exit(1)

GROQ_MODEL = os.environ.get("GROQ_MODEL", "llama-3.3-70b-versatile")
RESULTS_DIR = Path(os.environ.get("RESULTS_DIR", Path(__file__).parent / "results"))
RESULTS_DIR.mkdir(parents=True, exist_ok=True)


# ---------------------------------------------------------------------------
# Sample daily log scenarios used for evaluation
# ---------------------------------------------------------------------------

LOG_SCENARIOS = [
    {
        "name": "Missed workout, over calories",
        "profile": "28yo male, goal: Lose Weight, target 1800 kcal/day",
        "logs": {
            "date": "yesterday",
            "meals": ["breakfast: oatmeal with banana", "lunch: pizza (2 slices)", "dinner: fried chicken, fries"],
            "calories_consumed": 2650,
            "calorie_target": 1800,
            "workouts": [],
            "water_ml": 800,
            "water_target_ml": 2000,
            "sleep_hours": 6.5,
            "weight_kg": 88.5,
        },
        "expected_mentions": ["calories", "workout", "water", "pizza"],
        "expected_tone": "motivating but honest about missing workout and exceeding calories",
    },
    {
        "name": "Perfect adherence day",
        "profile": "35yo female, goal: Build Muscle, target 2100 kcal/day",
        "logs": {
            "date": "yesterday",
            "meals": ["breakfast: eggs and avocado toast", "lunch: grilled salmon with quinoa", "dinner: chicken breast with vegetables"],
            "calories_consumed": 2080,
            "calorie_target": 2100,
            "workouts": ["Upper body strength 60 min - chest press, rows, shoulder press"],
            "water_ml": 2200,
            "water_target_ml": 2000,
            "sleep_hours": 8.0,
            "weight_kg": 65.0,
        },
        "expected_mentions": ["workout", "protein", "sleep"],
        "expected_tone": "celebratory and encouraging, highlighting the great performance",
    },
    {
        "name": "Partial adherence, logged exercise only",
        "profile": "45yo male diabetic, goal: Lose Weight, target 1600 kcal/day",
        "logs": {
            "date": "yesterday",
            "meals": [],
            "calories_consumed": 0,
            "calorie_target": 1600,
            "workouts": ["30 min walking at moderate pace"],
            "water_ml": 1500,
            "water_target_ml": 2500,
            "sleep_hours": 7.0,
            "weight_kg": 92.0,
        },
        "expected_mentions": ["walk", "nutrition", "log"],
        "expected_tone": "positive about the walk, encourages logging meals next time",
    },
]


SYSTEM_PROMPT = """You are FitMind's personal AI coach. Generate a short, personalized daily coaching message (under 150 words).

Your message MUST:
1. Reference specific foods, exercises, or metrics from yesterday's log
2. Comment on how well the user met their calorie and water targets
3. Mention at least one specific item they logged (food name or exercise name)
4. Give one concrete, actionable suggestion for today
5. Be encouraging but honest

Do NOT give generic advice that ignores the actual logged data.
"""


def build_coaching_prompt(scenario: dict) -> str:
    logs = scenario["logs"]
    meals_str = ", ".join(logs["meals"]) if logs["meals"] else "No meals logged"
    workouts_str = ", ".join(logs["workouts"]) if logs["workouts"] else "No workouts logged"

    return f"""Generate a personalized coaching message for this user.

User profile: {scenario['profile']}

Yesterday's activity log:
- Date: {logs['date']}
- Meals: {meals_str}
- Total calories: {logs['calories_consumed']} kcal (target: {logs['calorie_target']} kcal)
- Workouts: {workouts_str}
- Water intake: {logs['water_ml']} ml (target: {logs['water_target_ml']} ml)
- Sleep: {logs['sleep_hours']} hours
- Morning weight: {logs['weight_kg']} kg

Write a coaching message that references specific items from their log.
"""


def evaluate_relevance(scenario: dict, message: str) -> dict:
    """Score how relevant the coaching message is to the actual logged data."""
    msg_lower = message.lower()
    logs = scenario["logs"]

    checks = []

    # Check 1: mentions specific logged foods or exercises
    all_logged_items = logs["meals"] + logs["workouts"]
    specific_mention = False
    mentioned_items = []
    for item in all_logged_items:
        # extract key words from each log entry
        words = [w.strip(",.:;'") for w in item.lower().split() if len(w) > 4]
        for word in words:
            if word in msg_lower:
                specific_mention = True
                mentioned_items.append(word)
                break
    checks.append({
        "rule": "References a specific logged item (food or exercise)",
        "pass": specific_mention,
        "detail": f"Matched: {mentioned_items[:3]}" if mentioned_items else "No matches found",
    })

    # Check 2: mentions any expected keyword
    expected_found = [kw for kw in scenario["expected_mentions"] if kw.lower() in msg_lower]
    checks.append({
        "rule": f"Mentions expected concepts: {scenario['expected_mentions']}",
        "pass": len(expected_found) >= max(1, len(scenario["expected_mentions"]) // 2),
        "detail": f"Found: {expected_found}",
    })

    # Check 3: message is not too short (< 30 words = too generic)
    word_count = len(message.split())
    checks.append({
        "rule": "Message is substantive (>= 30 words)",
        "pass": word_count >= 30,
        "detail": f"{word_count} words",
    })

    # Check 4: does NOT contain generic filler only
    generic_only_phrases = [
        "stay hydrated", "keep up the good work", "you can do it", "every step counts"
    ]
    is_generic = all(phrase in msg_lower for phrase in generic_only_phrases[:2]) and not specific_mention
    checks.append({
        "rule": "Not purely generic boilerplate",
        "pass": not is_generic,
    })

    passed = sum(1 for c in checks if c["pass"])
    total = len(checks)
    score_pct = round(100 * passed / total, 1)
    
    return {
        "scenario": scenario["name"],
        "checks": checks,
        "passed": passed,
        "failed": total - passed,
        "score_pct": score_pct,
        "overall": "PASS" if passed >= 3 else "FAIL",
        "generated_message": message,
    }


def run_coaching_evaluation(scenarios: list, client: Groq) -> list:
    all_results = []
    for i, scenario in enumerate(scenarios, 1):
        print(f"  [{i}/{len(scenarios)}] Scenario: {scenario['name']} ...", flush=True)
        try:
            prompt = build_coaching_prompt(scenario)
            response = client.chat.completions.create(
                model=GROQ_MODEL,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": prompt},
                ],
                max_tokens=300,
                temperature=0.7,
            )
            message = response.choices[0].message.content
            result = evaluate_relevance(scenario, message)
            all_results.append(result)
            print(f"         [{result['overall']}] {result['score_pct']}% relevance")
            print(f"         Generated: {message[:120].strip()}...")
        except Exception as exc:
            print(f"         [ERROR] {exc}")
            all_results.append({
                "scenario": scenario["name"],
                "overall": "ERROR",
                "error": str(exc),
                "score_pct": 0.0,
            })
    return all_results


def print_summary(results: list) -> None:
    passed = sum(1 for r in results if r.get("overall") == "PASS")
    total = len(results)
    print("\n" + "=" * 60)
    print("COACHING RELEVANCE EVALUATION SUMMARY")
    print("=" * 60)
    print(f"Total scenarios evaluated : {total}")
    print(f"PASS (>= 75% relevance)   : {passed}")
    print(f"FAIL / ERROR              : {total - passed}")
    avg_score = sum(r.get("score_pct", 0) for r in results) / total if total else 0
    print(f"Average relevance score   : {avg_score:.1f}%")
    print("=" * 60)
    for r in results:
        icon = "OK" if r.get("overall") == "PASS" else "!!"
        print(f"  [{icon}] {r.get('scenario', '?'):45s}  {r.get('score_pct', 0):.1f}%")


if __name__ == "__main__":
    api_key = os.environ.get("GROQ_API_KEY")
    if not api_key or api_key == "test-groq-key":
        print("ERROR: set GROQ_API_KEY environment variable to a real key")
        sys.exit(1)

    groq_client = Groq(api_key=api_key)

    print(f"Starting coaching relevance evaluation with model: {GROQ_MODEL}")
    print(f"Evaluating {len(LOG_SCENARIOS)} scenario(s)...\n")

    results = run_coaching_evaluation(LOG_SCENARIOS, groq_client)
    print_summary(results)

    output = {
        "run_at": datetime.utcnow().isoformat() + "Z",
        "model": GROQ_MODEL,
        "total_scenarios": len(results),
        "pass_count": sum(1 for r in results if r.get("overall") == "PASS"),
        "average_score_pct": round(
            sum(r.get("score_pct", 0) for r in results) / len(results), 1
        ) if results else 0,
        "results": results,
    }
    out_file = RESULTS_DIR / "coaching_relevance_results.json"
    out_file.write_text(json.dumps(output, indent=2))
    print(f"\nFull results saved to: {out_file}")
