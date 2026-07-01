"""
Master evaluation runner
========================
Runs all evaluation scripts and produces a combined report.

Usage:
    GROQ_API_KEY=your_key python tests/evaluation/run_evaluations.py

Optional env vars:
    GROQ_MODEL       Groq model (default: llama-3.3-70b-versatile)
    EVAL_PROFILES    'default' (3 safety profiles) or 'extended' (23 profiles)
    RESULTS_DIR      Output directory (default: tests/evaluation/results)
"""
import json
import os
import sys
from datetime import datetime
from pathlib import Path

# Make sure sibling modules are importable when run directly
sys.path.insert(0, str(Path(__file__).parent))

try:
    from groq import Groq
except ImportError:
    print("ERROR: groq package not installed. Run: pip install groq")
    sys.exit(1)

from profiles import DIABETIC_PROFILE, KNEE_INJURY_PROFILE, ASTHMA_PROFILE, EXTENDED_PROFILES
from eval_plan_safety import run_safety_evaluation, print_summary as print_safety_summary
from eval_coaching_relevance import (
    LOG_SCENARIOS, run_coaching_evaluation, print_summary as print_coaching_summary
)

RESULTS_DIR = Path(os.environ.get("RESULTS_DIR", Path(__file__).parent / "results"))
RESULTS_DIR.mkdir(parents=True, exist_ok=True)
GROQ_MODEL = os.environ.get("GROQ_MODEL", "llama-3.3-70b-versatile")


def main():
    api_key = os.environ.get("GROQ_API_KEY")
    if not api_key or api_key == "test-groq-key":
        print("ERROR: GROQ_API_KEY environment variable must be set to a real API key.")
        print("  Example: GROQ_API_KEY=gsk_... python tests/evaluation/run_evaluations.py")
        sys.exit(1)

    groq_client = Groq(api_key=api_key)

    profile_mode = os.environ.get("EVAL_PROFILES", "default")
    safety_profiles = [
        DIABETIC_PROFILE, KNEE_INJURY_PROFILE, ASTHMA_PROFILE
    ]
    if profile_mode == "extended":
        safety_profiles += EXTENDED_PROFILES

    print("#" * 65)
    print("#  FITMIND AI EVALUATION SUITE")
    print(f"#  Model: {GROQ_MODEL}")
    print(f"#  Run at: {datetime.utcnow().isoformat()}Z")
    print("#" * 65)

    # -----------------------------------------------------------------------
    # 1. Plan Safety Evaluation
    # -----------------------------------------------------------------------
    print("\n[1/2] PLAN SAFETY EVALUATION")
    print(f"      Testing {len(safety_profiles)} health profiles for safe plan generation...\n")
    safety_results = run_safety_evaluation(safety_profiles, groq_client)
    print_safety_summary(safety_results)

    # -----------------------------------------------------------------------
    # 2. Coaching Relevance Evaluation
    # -----------------------------------------------------------------------
    print("\n[2/2] COACHING RELEVANCE EVALUATION")
    print(f"      Testing {len(LOG_SCENARIOS)} daily log scenarios...\n")
    coaching_results = run_coaching_evaluation(LOG_SCENARIOS, groq_client)
    print_coaching_summary(coaching_results)

    # -----------------------------------------------------------------------
    # Combined report
    # -----------------------------------------------------------------------
    safety_pass = sum(1 for r in safety_results if r.get("overall") == "PASS")
    coaching_pass = sum(1 for r in coaching_results if r.get("overall") == "PASS")

    combined = {
        "run_at": datetime.utcnow().isoformat() + "Z",
        "model": GROQ_MODEL,
        "plan_safety": {
            "profiles_tested": len(safety_results),
            "passed": safety_pass,
            "failed": len(safety_results) - safety_pass,
            "pass_rate_pct": round(100 * safety_pass / len(safety_results), 1) if safety_results else 0,
            "results": safety_results,
        },
        "coaching_relevance": {
            "scenarios_tested": len(coaching_results),
            "passed": coaching_pass,
            "failed": len(coaching_results) - coaching_pass,
            "average_score_pct": round(
                sum(r.get("score_pct", 0) for r in coaching_results) / len(coaching_results), 1
            ) if coaching_results else 0,
            "results": coaching_results,
        },
    }

    out_file = RESULTS_DIR / "combined_evaluation_report.json"
    out_file.write_text(json.dumps(combined, indent=2))

    print("\n" + "#" * 65)
    print("#  COMBINED RESULTS")
    print("#" * 65)
    print(f"  Plan safety:         {safety_pass}/{len(safety_results)} profiles PASS "
          f"({combined['plan_safety']['pass_rate_pct']}%)")
    print(f"  Coaching relevance:  {coaching_pass}/{len(coaching_results)} scenarios PASS "
          f"(avg {combined['coaching_relevance']['average_score_pct']}%)")
    print(f"\n  Full report: {out_file}")
    print("#" * 65)


if __name__ == "__main__":
    main()
