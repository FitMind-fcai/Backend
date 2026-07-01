"""
Master Evaluation Runner
========================
Runs both evaluation scripts and produces a combined report.

Required env vars
-----------------
  AI_API_KEY          OpenRouter key (the real AI coach)
  EVAL_GROQ_API_KEY   Groq key (plan safety judge)

Usage
-----
  docker exec \\
    -e AI_API_KEY=sk-or-... \\
    -e EVAL_GROQ_API_KEY=gsk_... \\
    FitMind_APIs \\
    python tests/evaluation/run_evaluations.py
"""
import json
import os
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[2]))

from tests.evaluation.eval_plan_safety import run_plan_safety_evaluation
from tests.evaluation.eval_coaching_relevance import run_coaching_relevance_evaluation

RESULTS_DIR = Path(os.environ.get("RESULTS_DIR", Path(__file__).parent / "results"))
RESULTS_DIR.mkdir(parents=True, exist_ok=True)


def main():
    print("#" * 65)
    print("#  FITMIND FULL AI EVALUATION SUITE")
    print(f"#  Run at: {datetime.utcnow().isoformat()}Z")
    print("#" * 65)

    # 1. Plan safety
    print("\n[1/2] PLAN SAFETY EVALUATION")
    print("      Calls the real AI coach (OpenRouter) + evaluates with Groq judge")
    safety_output = run_plan_safety_evaluation()

    # 2. Coaching relevance
    print("\n[2/2] COACHING RELEVANCE EVALUATION")
    print("      Calls AICoachService.analyze_daily_progress() with realistic snapshots")
    coaching_output = run_coaching_relevance_evaluation()

    # Combined report
    s_pass = safety_output.get("profiles_fully_passed", 0)
    s_total = safety_output.get("profiles_tested", 0)
    c_pass = coaching_output.get("scenarios_passed", 0)
    c_total = coaching_output.get("scenarios_tested", 0)

    combined = {
        "run_at": datetime.utcnow().isoformat() + "Z",
        "plan_safety": {
            "profiles_tested": s_total,
            "profiles_fully_passed": s_pass,
            "pass_rate_pct": round(100 * s_pass / max(s_total, 1), 1),
        },
        "coaching_relevance": {
            "scenarios_tested": c_total,
            "scenarios_passed": c_pass,
            "avg_score_pct": coaching_output.get("avg_score_pct", 0),
        },
    }

    out_file = RESULTS_DIR / "combined_evaluation_report.json"
    out_file.write_text(json.dumps(combined, indent=2))

    print("\n" + "#" * 65)
    print("#  COMBINED RESULTS")
    print("#" * 65)
    print(f"  Plan safety         : {s_pass}/{s_total} profiles fully passed")
    print(f"  Coaching relevance  : {c_pass}/{c_total} scenarios passed "
          f"(avg {coaching_output.get('avg_score_pct', 0):.1f}%)")
    print(f"\n  Full report: {out_file}")
    print("#" * 65)


if __name__ == "__main__":
    main()
