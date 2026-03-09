#!/usr/bin/env python3
"""
AI Coach Evaluation — CLI entry point.

This is a thin wrapper that delegates all logic to the evaluation package at
app/ai_services/evaluation/.  The package splits the work across:

    models.py      — CheckResult / EvalReport dataclasses
    test_cases.py  — Synthetic profile generators
    judge.py       — LLM-as-judge prompting + parsing
    evaluators.py  — Per-plan evaluation logic (rule-based + LLM judge)
    reporting.py   — Aggregation + pretty-printing + accuracy banner
    runner.py      — Main evaluation loop (run_evaluation)

Why LLM-as-judge?
-----------------
Keyword matching misses indirect violations:
  tomato allergy   → plan includes "Marinara Pasta"      ← keyword miss
  egg allergy      → plan includes "Hollandaise Sauce"   ← keyword miss
  knee injury      → plan includes "Depth Jumps"         ← keyword miss
  Vegan            → plan includes "Greek Yogurt Parfait"← keyword miss

The LLM judge has world knowledge of ingredient composition and exercise
biomechanics, making the accuracy score genuinely meaningful.

Usage
-----
    python3 scripts/evaluate_rag_pipeline.py
    python3 scripts/evaluate_rag_pipeline.py --samples 20 --plan-type workout
    python3 scripts/evaluate_rag_pipeline.py --samples 50 --plan-type nutrition
    python3 scripts/evaluate_rag_pipeline.py --output my_results.json --delay 2.0

Options
-------
  --samples INT     Total test cases to run           (default: 100)
  --plan-type STR   workout | nutrition | both         (default: both)
  --output PATH     JSON output file                  (default: eval_results.json)
  --delay FLOAT     Seconds between API calls         (default: 1.5)
"""
from __future__ import annotations

import argparse
import os
import sys

# Ensure the project root is on the path when running as a plain script.
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from app.ai_services.evaluation.runner import run_evaluation  # noqa: E402


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Evaluate the AI Coach RAG + Prompt Engineering pipeline.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    p.add_argument("--samples",   type=int,   default=10,   help="Total test cases")
    p.add_argument("--plan-type", type=str,   default="both", help="workout | nutrition | both")
    p.add_argument("--output",    type=str,   default="",    help="JSON output path (default: evaluation/results/eval_results.json)")
    p.add_argument("--report",    type=str,   default="",    help="Markdown report path (default: same dir as --output with .md extension)")
    p.add_argument("--delay",     type=float, default=0.5,   help="Seconds between API calls")
    return p.parse_args()


if __name__ == "__main__":
    args = _parse_args()
    run_evaluation(
        num_samples=args.samples,
        plan_type=args.plan_type,
        output_path=args.output,
        delay_seconds=args.delay,
        report_path=args.report,
    )
