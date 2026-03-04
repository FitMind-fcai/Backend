"""
models.py — Evaluation result dataclasses.

CheckResult  : result of a single constraint check (rule-based or LLM judge).
EvalReport   : aggregates all checks for one generated plan, computes overall score.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List


@dataclass
class CheckResult:
    """Result of one constraint check."""
    name: str
    applicable: bool    # False when this constraint doesn't exist on the profile
    passed: bool
    score: float        # 0.0 or 1.0  (binary per check)
    weight: float       # importance weight used in the overall score
    violations: List[str]   # specific violations found by the judge
    reasoning: str          # judge explanation


@dataclass
class EvalReport:
    """Full evaluation report for one generated plan."""
    checks: List[CheckResult] = field(default_factory=list)

    @property
    def applicable_checks(self) -> List[CheckResult]:
        return [c for c in self.checks if c.applicable]

    @property
    def overall_score(self) -> float:
        """Weighted score (0–100) computed over applicable checks only."""
        applicable = self.applicable_checks
        if not applicable:
            return 100.0
        total_weight = sum(c.weight for c in applicable)
        if total_weight == 0:
            return 0.0
        return round(
            sum(c.score * c.weight for c in applicable) / total_weight * 100, 1
        )

    @property
    def passed(self) -> bool:
        return self.overall_score >= 70.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "overall_score_pct": self.overall_score,
            "passed": self.passed,
            "checks": [
                {
                    "name": c.name,
                    "applicable": c.applicable,
                    "passed": c.passed,
                    "score": c.score,
                    "weight": c.weight,
                    "violations": c.violations,
                    "reasoning": c.reasoning,
                }
                for c in self.checks
            ],
        }
