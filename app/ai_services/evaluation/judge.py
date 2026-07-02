"""
judge.py — LLM-as-judge calls.

Why LLM-as-judge instead of keyword matching?
----------------------------------------------
Keyword matching misses indirect violations:
  • Egg allergy  → "Hollandaise sauce"  (keyword "egg" absent)
  • Tomato allergy → "Marinara Pasta"   (keyword "tomato" absent)
  • Knee injury  → "Box Jumps"          (keyword "knee" absent)

The LLM judge understands ingredient composition and exercise biomechanics,
catching every violation a naive scan would miss.

Public API
----------
  judge_workout_plan(plan, profile, prefs, groq_client, model)  → Dict
  judge_nutrition_plan(plan, profile, prefs, groq_client, model) → Dict
"""
from __future__ import annotations

import json
import re
from typing import Any, Dict

from app.ai_services.ai_coach.dtos import (
    NutritionPlanDTO,
    NutritionPreferencesDTO,
    UserProfileDTO,
    WorkoutPlanDTO,
    WorkoutPreferencesDTO,
)


# ---------------------------------------------------------------------------
# Plan summarizers  (compact text fed into the judge prompt)
# ---------------------------------------------------------------------------

def _summarize_workout(plan: WorkoutPlanDTO) -> str:
    lines = [f"Plan: {plan.plan_name}  |  Difficulty: {plan.difficulty_level}"]
    for day in plan.workout_days:
        ex_list = ", ".join(ex.exercise_name for ex in day.exercises if ex.exercise_name)
        lines.append(f"  Day {day.day_number} ({day.focus_area}): {ex_list}")
    return "\n".join(lines)


def _summarize_nutrition(plan: NutritionPlanDTO) -> str:
    """Produce a compact, judge-readable summary of the meal plan.

    NutritionPlanDTO stores meals inside days (plan.days[i].meals).
    meal.instructions contains the human-readable preparation text
    (ingredient list + cooking method) which is what the judge needs
    to detect hidden allergens and dietary violations.
    """
    lines = [
        f"Plan: {plan.plan_name}",
        f"Daily calories: {plan.daily_calories} kcal  |  "
        f"Protein: {plan.daily_protein_g}g  Carbs: {plan.daily_carbs_g}g  "
        f"Fats: {plan.daily_fats_g}g",
    ]
    for day in plan.days:
        lines.append(f"--- {day.day_name} ---")
        for meal in day.meals:
            prep = (meal.instructions or "").strip()
            lines.append(
                f"  {meal.meal_type} — {meal.meal_name}  "
                f"({meal.calories} kcal | P:{meal.protein_g}g C:{meal.carbs_g}g F:{meal.fats_g}g)\n"
                f"    Preparation: {prep or 'no details provided'}"
            )
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Raw LLM call
# ---------------------------------------------------------------------------

def _call_judge(groq_client, model: str, system: str, prompt: str) -> Dict[str, Any]:
    """Call the LLM judge and parse the JSON response.

    Always injects ``_judge_prompt`` and ``_judge_raw_response`` into the
    returned dict so callers can log / display them for fact-checking.
    """
    try:
        response = groq_client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user",   "content": prompt},
            ],
            temperature=0.0,
            max_tokens=2000,
        )
        raw_original = (response.choices[0].message.content or "").strip()
        raw = re.sub(r"^```(?:json)?\s*", "", raw_original)
        raw = re.sub(r"\s*```$", "", raw)
        raw = raw.strip()

        if not raw:
            return {
                "_judge_error": "Empty response from judge LLM",
                "_judge_prompt": prompt,
                "_judge_raw_response": raw_original,
            }

        # Direct parse
        try:
            result = json.loads(raw)
            result["_judge_prompt"] = prompt
            result["_judge_raw_response"] = raw_original
            return result
        except json.JSONDecodeError:
            pass

        # Fallback: extract the first {...} block from prose-wrapped responses
        match = re.search(r"\{.*\}", raw, re.DOTALL)
        if match:
            try:
                result = json.loads(match.group())
                result["_judge_prompt"] = prompt
                result["_judge_raw_response"] = raw_original
                return result
            except json.JSONDecodeError:
                pass

        return {
            "_judge_error": f"Could not parse judge response: {raw[:200]!r}",
            "_judge_prompt": prompt,
            "_judge_raw_response": raw_original,
        }
    except Exception as exc:
        return {
            "_judge_error": str(exc),
            "_judge_prompt": prompt,
            "_judge_raw_response": "",
        }


# ---------------------------------------------------------------------------
# Workout judge
# ---------------------------------------------------------------------------

_WORKOUT_SYSTEM = (
    "You are a fitness safety expert whose job is to audit AI-generated workout plans "
    "for constraint violations. Flag an exercise only if it would CLEARLY AND "
    "MEANINGFULLY risk aggravating the stated injury or condition, or clearly breaks an "
    "equipment rule — not merely because it is theoretically conceivable in an unrelated "
    "context. Give the plan the benefit of the doubt on borderline, low-impact, or "
    "commonly-cleared movements (e.g. controlled hip-hinge work, low step-ups) unless the "
    "user's stated restrictions explicitly rule them out. Respond ONLY with the JSON "
    "object requested."
)


def judge_workout_plan(
    plan: WorkoutPlanDTO,
    profile: UserProfileDTO,
    prefs: WorkoutPreferencesDTO,
    groq_client,
    model: str,
) -> Dict[str, Any]:
    plan_text = _summarize_workout(plan)
    prompt = f"""USER CONSTRAINTS:
- Fitness Goal: {profile.fitness_goal}
- Injuries: {profile.injuries or "None"}
- Medical Conditions: {profile.medical_conditions or "None"}
- Equipment Available: {prefs.equipment_availability}
- Requested Workout Days per Week: {prefs.workout_days_per_week}

GENERATED WORKOUT PLAN:
{plan_text}

EVALUATION RULES:
injury_safety — Does ANY exercise clearly and meaningfully risk aggravating the stated
  injury? Only flag exercises that directly conflict with the stated restriction
  (e.g. box jumps for a "no high-impact / no plyometrics" knee restriction, overhead
  press for a shoulder impingement, heavy spinal loading for acute lower back pain).
  Do not flag mild or moderate movements that are commonly cleared in rehab
  (e.g. controlled Romanian deadlifts, low step-ups, bodyweight squats) unless the
  user's injury notes explicitly rule them out.

medical_condition_safety — Does ANY exercise pose a clear medical risk?
  Examples: high-intensity cardio / HIIT for heart disease, impact exercises for
  osteoporosis, maximal effort for hypertension. Do not flag normal moderate-intensity
  training just because the user has a managed, stable condition.

equipment_compliance — Does the plan ONLY use equipment the user has?
  "No Equipment" = STRICTLY bodyweight only.
    NO dumbbells, barbells, kettlebells, resistance bands, pull-up bars, cables.
  "Basic Equipment" = dumbbells, resistance bands, yoga mat. No gym machines.
  "Full Gym" = anything is allowed.

goal_alignment — Does the plan's structure support the stated fitness goal?

Respond with ONLY this JSON (no markdown, no extra text):
{{
  "injury_safety":            {{"passed": true, "violations": [], "reasoning": "..."}},
  "medical_condition_safety": {{"passed": true, "violations": [], "reasoning": "..."}},
  "equipment_compliance":     {{"passed": true, "violations": [], "reasoning": "..."}},
  "goal_alignment":           {{"passed": true, "violations": [], "reasoning": "..."}}
}}"""
    return _call_judge(groq_client, model, _WORKOUT_SYSTEM, prompt)


# ---------------------------------------------------------------------------
# Nutrition judge
# ---------------------------------------------------------------------------

_NUTRITION_SYSTEM = (
    "You are a nutrition safety expert whose job is to audit AI-generated meal plans "
    "for dietary violations. Watch for hidden ingredient sources that genuinely contain "
    "an allergen or excluded item (e.g. 'egg fried rice' contains eggs, 'marinara sauce' "
    "contains tomatoes, 'cheese sauce' contains dairy, 'soy sauce' contains gluten). "
    "Do NOT flag a food merely because it shares a general category with an excluded "
    "item — only flag it if it actually contains the specific excluded ingredient or a "
    "direct synonym of it (e.g. excluding 'white bread' does not mean flagging whole "
    "grain or seeded bread, which are different products with a different nutritional "
    "profile). Respond ONLY with the JSON object requested."
)


def judge_nutrition_plan(
    plan: NutritionPlanDTO,
    profile: UserProfileDTO,
    prefs: NutritionPreferencesDTO,
    groq_client,
    model: str,
) -> Dict[str, Any]:
    plan_text = _summarize_nutrition(plan)
    excl = ", ".join(prefs.exclude_ingredients) if prefs.exclude_ingredients else "None"
    prompt = f"""USER CONSTRAINTS:
- Fitness Goal: {profile.fitness_goal}
- Allergies: {profile.allergies or "None"}
- Dietary Preference: {profile.dietary_preference or "None"}
- Explicitly Excluded Ingredients: {excl}
- Medical Conditions: {profile.medical_conditions or "None"}

GENERATED MEAL PLAN:
{plan_text}

EVALUATION RULES:
allergen_safety — Does ANY meal contain the user's allergen, including hidden sources?
  Critical examples:
  • Egg allergy     → flag: egg fried rice, mayonnaise, hollandaise, quiche
  • Dairy allergy   → flag: cheese sauce, butter, yogurt dressing, cream, ghee
  • Nut allergy     → flag: pesto (pine nuts), satay sauce, mole sauce, praline
  • Gluten allergy  → flag: soy sauce (wheat), pasta, bread, couscous, most cereals
  • Shellfish allergy → flag: seafood stock, paella, bouillabaisse
  • Tomato allergy  → flag: marinara sauce, ketchup, salsa, pizza sauce, tomato paste

dietary_preference_respected — Are ALL meals compliant with the preference?
  Vegan: NO meat, fish, dairy, eggs, honey, gelatin.
  Vegetarian: NO meat or fish (dairy and eggs OK).
  Keto: NO bread, pasta, rice, sugar, starchy carbs, most fruit.
  Gluten-Free: NO wheat, barley, rye, regular soy sauce, most bread and pasta.

exclusion_compliance — Do ANY meals contain the SPECIFIC explicitly excluded
  ingredients (or a direct synonym / hidden source of the same ingredient)?
  Do not flag a different but related food just because it belongs to the same broad
  category as an excluded item.

goal_alignment — Does the meal plan (calories, macros, food types) support the
  stated fitness goal?

Respond with ONLY this JSON (no markdown, no extra text):
{{
  "allergen_safety":              {{"passed": true, "violations": [], "reasoning": "..."}},
  "dietary_preference_respected": {{"passed": true, "violations": [], "reasoning": "..."}},
  "exclusion_compliance":         {{"passed": true, "violations": [], "reasoning": "..."}},
  "goal_alignment":               {{"passed": true, "violations": [], "reasoning": "..."}}
}}"""
    return _call_judge(groq_client, model, _NUTRITION_SYSTEM, prompt)
