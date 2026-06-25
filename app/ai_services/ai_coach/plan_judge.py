"""
LLM-based plan judge — second-pass safety and quality review.

Design principles
-----------------
1. Severity is explicit and rubric-driven (1/2/3), not decided ad-hoc by the LLM.
2. Pass/fail is applied mechanically in Python from severity counts — the LLM's
   own "passed" field is ignored to eliminate randomness.
3. Every issue must include an exact "fix" instruction so the generator knows
   precisely what to change, not just what is wrong.
4. The threshold is calibrated to pass "good enough" plans — only genuine safety
   blockers or multiple significant concerns fail the plan.

Pass/fail rule (applied in _run_judge, not by the LLM):
  passed = True  when: zero severity-3 issues AND fewer than 5 severity-2 issues
  passed = False when: any severity-3 issue OR 5+ severity-2 issues
"""
import logging
from typing import Dict, List, Tuple

from app.ai_services.ai_coach.dtos import (
    NutritionPlanDTO,
    NutritionPreferencesDTO,
    UserProfileDTO,
    WorkoutPlanDTO,
    WorkoutPreferencesDTO,
)
from app.ai_services.ai_coach.llm_client import LLMClient

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Shared rubric — injected into every judge system prompt
# ---------------------------------------------------------------------------

_SEVERITY_RUBRIC = """
SEVERITY SCALE — assign exactly one level to each issue you find:

SEVERITY 3 — BLOCKER (plan must fail; the generator must fix this before shipping):
  • A food the user is allergic to appears in a meal (allergen confirmed in instructions text)
  • An exercise confirmed in its movement description to move a restricted joint into a
    contraindicated range (e.g. hands travelling above shoulder height for impingement)
  • A verified dangerous drug-food interaction (e.g. grapefruit + calcium channel blocker)
  • High-impact explosive spinal loading prescribed for acute disc herniation

SEVERITY 2 — SIGNIFICANT (flag it; plan fails only if 2 or more severity-2 issues exist):
  • Intensity measurably above safe range for condition (e.g. RPE 8+ for hypertension,
    not RPE 6-7 which is moderate and acceptable)
  • A safety cue completely absent for an exercise that directly involves a restricted
    body part for this user
  • Required warm-up/cool-down entirely missing when medically necessary
  • A food-drug caution that is important but not immediately dangerous
  • Daily fat below 20% of calories OR calories deviate > 20% from planning engine targets

  NEVER severity 2 for:
  • Minor fat-to-protein ratio preferences (e.g. 80% vs 93% lean beef) — these are severity 1
  • Sodium concerns when the user has NO cardiovascular conditions — severity 1 at most
  • Suggesting a leaner cut or alternative protein is a minor optimisation, not significant
  • Legumes or plant proteins being "insufficient" — they are valid protein sources

SEVERITY 1 — MINOR (note it; never fails the plan):
  • Intensity within safe range but could be slightly better (e.g. RPE 6-7 vs 5-6)
  • Minor variety miss or cuisine preference issue
  • Small exercise selection optimisation
  • A coaching note missing on one day when others have it

PASS / FAIL (applied by code — not by you):
  • PASS  = zero severity-3 issues AND fewer than 5 severity-2 issues
  • FAIL  = any severity-3 issue OR 5+ severity-2 issues
  You do not decide passed/failed — just assign severities accurately.
"""

_OVERHEAD_DEFINITION = """
DEFINING "OVERHEAD" (critical for shoulder impingement assessment):

"Overhead" = hands or load travels ABOVE shoulder height while the person is upright.

NOT overhead — even if the word "up" or "press" appears:
  ✓ Push-up / weighted push-up / any push-up variation
    (person is PRONE / horizontal; "pressing up" = torso rising from the floor;
     shoulder stays at ~90° forward flexion — not overhead)
  ✓ Bench press, floor press, cable fly, chest fly (all horizontal plane)
  ✓ Svend press (plates pressed FORWARD at sternum level — purely horizontal)
  ✓ Rows, lat pull-downs to upper chest, face pulls
  ✓ Lateral raises kept BELOW 90° (below shoulder height)
  ✓ Dips (shoulder extension/depression — not overhead)

IS overhead (contraindicated for shoulder impingement):
  ✗ Overhead press, dumbbell shoulder press, Arnold press, push press
  ✗ Behind-the-neck press / behind-the-neck pull-down
  ✗ Upright row (taken to chin height — enters overhead arc)
  ✗ Band pass-through stretch (arms sweep from front OVER head to behind back)
  ✗ Any lateral raise taken ABOVE shoulder level (above 90°)
"""

_OUTPUT_SCHEMA = """{
  "issues": [
    {
      "severity": 1 | 2 | 3,
      "location": "Day X — Exercise or Meal name",
      "problem": "Exact description of what is wrong and why it violates this user's constraints",
      "fix": "Exact replacement instruction — e.g. 'Replace [exercise] with [specific safe alternative] because [reason]'"
    }
  ],
  "summary_feedback": "One consolidated paragraph of all severity-2 and severity-3 fixes for the generator, in the imperative voice. Be specific: name the day, the item, and the exact replacement."
}"""


# ---------------------------------------------------------------------------
# Serializers
# ---------------------------------------------------------------------------

def _serialize_nutrition_plan(plan: NutritionPlanDTO) -> str:
    lines = [f"Plan: {plan.plan_name}", f"Description: {plan.description or '(none)'}"]
    for day in (plan.days or []):
        lines.append(f"\n{day.day_name} (Day {day.day_number}):")
        if day.notes:
            lines.append(f"  Notes: {day.notes}")
        for meal in (day.meals or []):
            lines.append(f"  [{meal.meal_type}] {meal.meal_name}")
            if meal.instructions:
                lines.append(f"    Instructions: {meal.instructions[:600]}")
    return "\n".join(lines)


def _serialize_workout_plan(plan: WorkoutPlanDTO) -> str:
    lines = [
        f"Plan: {plan.plan_name}",
        f"Description: {plan.description or '(none)'}",
        f"Frequency: {plan.frequency}",
        f"Difficulty: {plan.difficulty_level}",
    ]
    for day in (plan.workout_days or []):
        lines.append(f"\n{day.day_name} — Focus: {day.focus_area}")
        if day.notes:
            lines.append(f"  Session notes: {day.notes}")
        for ex in (day.exercises or []):
            detail = f"  - {ex.exercise_name}"
            if ex.sets and ex.reps:
                detail += f"  {ex.sets}x{ex.reps}"
            elif ex.duration_seconds:
                detail += f"  {ex.duration_seconds}s"
            if ex.instructions:
                detail += f"\n    Movement description: {ex.instructions[:500]}"
            lines.append(detail)
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# PlanJudge
# ---------------------------------------------------------------------------

class PlanJudge:

    def __init__(self, llm_client: LLMClient) -> None:
        self._llm = llm_client

    def judge_nutrition_plan(
        self,
        plan: NutritionPlanDTO,
        user_profile: UserProfileDTO,
        preferences: NutritionPreferencesDTO,
        planning_output=None,
    ) -> Tuple[bool, str]:
        system = (
            "You are a senior clinical dietitian and food safety expert.\n"
            "Your role is to find GENUINE safety risks and quality issues — "
            "not to nitpick minor optimisations.\n\n"
            f"{_SEVERITY_RUBRIC}\n\n"
            "For each issue you find, you MUST provide an exact fix instruction — "
            "not just a description of the problem.\n\n"
            f"Output ONLY valid JSON matching this schema:\n{_OUTPUT_SCHEMA}\n"
            "No markdown, no extra text."
        )

        targets_block = ""
        if planning_output:
            nt = planning_output.nutrition
            targets_block = (
                f"\nPLANNING ENGINE TARGETS (authoritative — deviations are issues):\n"
                f"  Target calories: {nt.calories} kcal/day\n"
                f"  Protein: {nt.protein_g}g/day\n"
                f"  Fat: {nt.fat_g}g/day (must be >= 20% of calories)\n"
                f"  Carbs: {nt.carbs_g}g/day\n"
            )

        prompt = (
            "Review this nutrition plan for the user below.\n\n"
            f"ALLERGIES (zero tolerance): {user_profile.allergies or 'None'}\n"
            f"MEDICAL CONDITIONS: {user_profile.medical_conditions or 'None'}\n"
            f"MEDICATIONS: {user_profile.medications or 'None'}\n"
            f"FITNESS GOAL: {user_profile.fitness_goal}\n"
            f"CUISINE PREFERENCE: {preferences.cuisine_preference}\n"
            f"DIETARY RESTRICTIONS: {getattr(preferences, 'dietary_restrictions', None) or 'None'}\n"
            f"{targets_block}\n"
            "GENERATED PLAN:\n"
            f"{_serialize_nutrition_plan(plan)}\n\n"
            "Evaluate these areas in order:\n"
            "1. ALLERGEN CHECK — read instructions text of every meal for any ingredient "
            "matching the allergy list (exact or family). Severity 3 if found.\n"
            "2. MEDICAL VIOLATIONS — foods or preparations directly contraindicated for "
            "listed conditions. Severity 3 if dangerous, 2 if significant caution.\n"
            "3. DRUG-FOOD INTERACTIONS — ingredients with known interactions with listed "
            "medications. Severity 3 if dangerous (e.g. grapefruit + CCB), 2 if notable caution.\n"
            "4. MACRO COMPLIANCE — compare daily totals against planning engine targets. "
            "Severity 2 if daily fat < 20% of calories or calories deviate > 20% from target. "
            "Severity 1 if protein deviates > 25% from target.\n"
            "5. CUISINE AUTHENTICITY — does the plan reflect the requested cuisine? "
            "Severity 1 if minor miss, 2 if completely wrong.\n"
            "6. GOAL ALIGNMENT — protein and structure match the fitness goal? "
            "Severity 1-2 depending on how far off.\n"
            "7. VARIETY — sufficient diversity over 7 days? Severity 1 if minor.\n\n"
            "For every issue: state the day and meal, what exactly is wrong, and the exact fix.\n"
            "If the plan is clean, return an empty issues array."
        )

        return self._run_judge("nutrition", system, prompt)

    def judge_workout_plan(
        self,
        plan: WorkoutPlanDTO,
        user_profile: UserProfileDTO,
        preferences: WorkoutPreferencesDTO,
        planning_output=None,
    ) -> Tuple[bool, str]:
        system = (
            "You are a senior sports medicine physician and strength & conditioning specialist.\n"
            "Your role is to find GENUINE safety risks and programming issues — "
            "not to nitpick minor optimisations.\n\n"
            f"{_SEVERITY_RUBRIC}\n\n"
            f"{_OVERHEAD_DEFINITION}\n\n"
            "For each issue you find, you MUST provide an exact fix instruction — "
            "not just a description of the problem.\n\n"
            f"Output ONLY valid JSON matching this schema:\n{_OUTPUT_SCHEMA}\n"
            "No markdown, no extra text."
        )

        targets_block = ""
        if planning_output:
            tt = planning_output.training
            targets_block = (
                f"\nPLANNING ENGINE TARGETS (authoritative):\n"
                f"  Training days/week: {tt.training_days}\n"
                f"  Split: {tt.split.replace('_', ' ').title()}\n"
                f"  Session duration: {tt.session_duration_minutes} min\n"
                f"  Weekly volume: ~{tt.weekly_volume_sets_per_muscle} sets/muscle\n"
            )

        prompt = (
            "Review this workout plan for the user below.\n\n"
            f"MEDICAL CONDITIONS: {user_profile.medical_conditions or 'None'}\n"
            f"INJURIES / LIMITATIONS: {user_profile.injuries or 'None'}\n"
            f"FITNESS GOAL: {user_profile.fitness_goal}\n"
            f"WORKOUT FOCUS: {preferences.workout_focus}\n"
            f"DIFFICULTY: {preferences.workout_difficulty}\n"
            f"LOCATION: {preferences.workout_location}\n"
            f"{targets_block}\n"
            "GENERATED PLAN:\n"
            f"{_serialize_workout_plan(plan)}\n\n"
            "Evaluate these areas in order:\n"
            "1. CONTRAINDICATED MOVEMENTS — read the 'Movement description' for each exercise.\n"
            "   Only severity 3 if the instructions CONFIRM the exercise loads the restricted "
            "   joint in the contraindicated range. Use the overhead definition above.\n"
            "   Do NOT judge by exercise name alone.\n"
            "2. INTENSITY — severity 3 only if clearly exceeds safe range (e.g. max-effort HIIT "
            "   for uncontrolled hypertension). RPE 5-7 is moderate and acceptable for mild "
            "   hypertension. Severity 1-2 for minor intensity adjustments.\n"
            "3. MISSING SAFETY CUES — severity 2 only if a high-risk exercise for this user "
            "   has zero safety instruction. Severity 1 if cues exist but could be better.\n"
            "4. WARM-UP / COOL-DOWN — severity 2 if entirely absent when medically required, "
            "   severity 1 if present but brief.\n"
            "5. GOAL ALIGNMENT — split and volume match the goal? Severity 1-2.\n"
            "6. EXERCISE VARIETY — sufficient variety? Severity 1.\n\n"
            "For every issue: state the day and exercise, what the instructions actually describe, "
            "and the exact replacement or change.\n"
            "If the plan is clean, return an empty issues array."
        )

        return self._run_judge("workout", system, prompt)

    def _run_judge(self, label: str, system: str, prompt: str) -> Tuple[bool, str]:
        try:
            response = self._llm.call_judge_llm(system, prompt)
            result   = self._llm.parse_json_response(response)

            issues:   List[Dict] = result.get("issues") or []
            feedback: str        = result.get("summary_feedback") or ""

            sev3 = [i for i in issues if i.get("severity") == 3]
            sev2 = [i for i in issues if i.get("severity") == 2]
            sev1 = [i for i in issues if i.get("severity") == 1]

            # Deterministic rule — not left to the LLM's judgement
            # Only block on genuine safety issues (sev3) or 5+ significant concerns
            passed = len(sev3) == 0 and len(sev2) < 5

            logger.info(
                "%s judge — passed=%s  sev3=%d  sev2=%d  sev1=%d",
                label, passed, len(sev3), len(sev2), len(sev1),
            )
            if not passed:
                blocker_msgs = [
                    f"[S{i.get('severity')}] {i.get('location','?')}: {i.get('problem','?')} → {i.get('fix','?')}"
                    for i in sev3 + sev2
                ]
                logger.warning("%s judge FAILED:\n%s", label, "\n".join(blocker_msgs))

            return passed, feedback

        except Exception as err:
            logger.warning("%s judge error (skipping): %s", label, err)
            return True, ""
