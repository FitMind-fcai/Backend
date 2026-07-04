"""
Prompt construction for the AI Coach generation step.

All functions are pure — they take data, return strings, and have no side effects.
The prompts use a channel system:
  Channel P — Planning Engine output (macro/training targets, authoritative)
  Channel C — KB-grounded safety rules from ContextBuilder (replaces inline medical block + RAG)
  Channel B — Database food/exercise constraints (only allowed IDs)

Channel A (general RAG) has been removed: the ContextBuilder already performs
targeted per-condition RAG queries and synthesizes the results into Channel C.
Sending a second general RAG pass would be redundant noise in the prompt.
"""
from typing import Optional, TYPE_CHECKING

from app.ai_services.ai_coach.calorie_calculator import (
    calculate_macro_guidance,
    calculate_target_calories,
)
from app.ai_services.ai_coach.dtos import (
    NutritionPlanDTO,
    NutritionPreferencesDTO,
    UserProfileDTO,
    WorkoutPlanDTO,
    WorkoutPreferencesDTO,
)

if TYPE_CHECKING:
    from app.planning_module.core.planning_engine import PlanningEngineOutput


# ---------------------------------------------------------------------------
# Medical / safety context blocks
# ---------------------------------------------------------------------------

_PLACEHOLDER_VALUES = {
    "none", "n/a", "na", "nil", "null", "no specific preference",
    "no allergies", "no medications", "no injuries", "no medical conditions",
    "not applicable", "no known", "no known allergies", "no known conditions",
}


def _clean_field(value: Optional[str]) -> str:
    """Return '' for placeholder values like 'None'/'N/A' so they don't get
    treated as real medical content."""
    stripped = (value or "").strip()
    if stripped.lower() in _PLACEHOLDER_VALUES:
        return ""
    return stripped


def build_medical_nutrition_block(user_profile: UserProfileDTO) -> str:
    """
    Dynamic medical nutrition guidance block.

    Passes the user's raw health profile to the LLM instead of matching
    against a hardcoded condition list. The LLM applies all known evidence-based
    dietary rules, drug-food interactions, and nutrient thresholds for every
    condition and medication listed — handling any condition without a lookup table.
    """
    conditions  = _clean_field(user_profile.medical_conditions)
    medications = _clean_field(user_profile.medications)
    allergies   = _clean_field(user_profile.allergies)

    if not conditions and not medications and not allergies:
        return "No medical conditions, medications, or allergies reported for this user."

    lines = []
    if conditions:
        lines.append(f"Medical conditions: {conditions}")
    if medications:
        lines.append(f"Current medications: {medications}")
    if allergies:
        lines.append(f"Food allergies (ABSOLUTE zero-tolerance): {allergies}")

    profile_text = "\n".join(lines)

    return f"""=== CHANNEL C: MEDICAL & MEDICATION DIETARY RULES (OVERRIDE EVERYTHING ELSE) ===
This user has the following health profile that MUST drive every food and portion decision:

{profile_text}

For EVERY condition and medication listed above, apply ALL known evidence-based dietary guidelines:
• EXCLUSIONS  — foods that worsen the condition, trigger symptoms, or interact with medications
• INCLUSIONS  — foods that actively support management of the condition
• LIMITS      — specific nutrient thresholds (e.g. sodium < 2000 mg/day for hypertension)
• PREPARATION — required cooking methods or modifications (e.g. no-salt-added, low-GI only)
• DRUG-FOOD INTERACTIONS — specific foods that affect medication efficacy or safety
  (e.g. grapefruit + calcium channel blockers / statins, vitamin K + warfarin,
   tyramine-rich foods + MAOIs, high-potassium foods + ACE inhibitors at toxic doses)
• DISTRIBUTION — meal timing or macro distribution requirements (e.g. even carb spread for diabetes)

These rules are NON-NEGOTIABLE and override all cuisine preferences.
Any violation of a medical dietary requirement or food-drug interaction is a CRITICAL FAILURE."""


def build_cultural_meal_pattern_block(cuisine_preference: str) -> str:
    """
    Cultural meal-timing/appropriateness rules for Egyptian/Arabic cuisine.

    The generic "authentic {cuisine} spices and cooking methods" instruction
    doesn't stop the model from putting culturally-wrong foods at the wrong
    meal (e.g. grilled chicken breast for breakfast, which no Egyptian
    household actually eats) — this block encodes which foods go with which
    meal, not just which spices/ingredients to use.
    """
    cuisine_lower = (cuisine_preference or "").lower()
    if not any(k in cuisine_lower for k in ("egypt", "arab", "middle east")):
        return ""

    return (
        "=== CULTURAL MEAL-PATTERN RULES (Egyptian / Arabic) — FOLLOW STRICTLY ===\n"
        "Authenticity means matching what people actually eat at each meal, not just using\n"
        "regional spices. Apply these real Egyptian/Arabic eating patterns:\n\n"
        "• BREAKFAST is light and does NOT normally include chicken, red meat, or fish.\n"
        "  Typical Egyptian breakfast foods: ful medames (fava beans), taameya (falafel),\n"
        "  boiled or fried eggs, white cheese (gebna beida), cream cheese (areesh/istanbouli),\n"
        "  aish baladi (balady bread), olives, honey, jam, tahini, dukkah, tomato and cucumber.\n"
        "• LUNCH is culturally the largest meal of the day and is where poultry/meat/fish\n"
        "  most commonly appear — e.g. grilled chicken, kofta, or fish with rice, molokhia,\n"
        "  bamya (okra stew), fasolya (green bean stew), or koshari.\n"
        "• DINNER is typically lighter than lunch — often similar to breakfast items, a light\n"
        "  sandwich, soup, or a smaller portion of a lunch-style dish. Avoid making dinner a\n"
        "  heavy meat-centric meal unless the user's goal (e.g. Build Muscle with a late\n"
        "  training session) specifically calls for extra protein at dinner.\n"
        "• Staple carbohydrates are rice and aish baladi (bread); pasta appears in dishes like\n"
        "  macarona bechamel and koshari.\n"
        "• Common vegetables/legumes: molokhia, bamya, fasolya, ful, eggplant (batenjan),\n"
        "  zucchini (koosa), spinach (sabanekh).\n"
        "• Do NOT default to Western high-protein breakfast tropes (e.g. chicken breast,\n"
        "  turkey/chicken sausage, protein pancakes) unless the user's goal or preferences\n"
        "  explicitly call for a Western-style or bodybuilding-style breakfast.\n"
    )


def build_medical_workout_block(user_profile: UserProfileDTO) -> str:
    """
    Dynamic medical workout guidance block.

    Passes raw conditions and injuries to the LLM so it can apply comprehensive,
    evidence-based exercise restrictions for any condition — not just a fixed list.
    """
    conditions = _clean_field(user_profile.medical_conditions)
    injuries   = _clean_field(user_profile.injuries)

    if not conditions and not injuries:
        return "No specific medical conditions or injuries reported for this user."

    lines = []
    if conditions:
        lines.append(f"Medical conditions: {conditions}")
    if injuries:
        lines.append(f"Injuries / physical limitations: {injuries}")

    profile_text = "\n".join(lines)

    return f"""=== CHANNEL C: INJURY & MEDICAL EXERCISE RULES (OVERRIDE EVERYTHING ELSE) ===
This user has the following health profile that MUST drive every exercise selection decision:

{profile_text}

For EVERY condition and injury listed above, apply ALL known evidence-based exercise guidelines:
• COMPLETE EXCLUSIONS  — movements that are contraindicated and must never appear in the plan
• SAFE ALTERNATIVES    — substitute exercises that achieve the same training stimulus safely
• INTENSITY LIMITS     — maximum safe RPE / heart rate / load for cardiovascular conditions
• TECHNIQUE CUES       — mandatory safety instructions for every exercise involving the affected area
• VALSALVA / BREATHING — breathing patterns required to prevent dangerous pressure responses
• WARM-UP / COOL-DOWN  — minimum duration and type required for the condition
• MONITORING CUES      — pain signals or vitals the user must watch during the session

These rules are NON-NEGOTIABLE and override all preference and difficulty settings.
Any exercise that could aggravate the user's condition or injury is a CRITICAL FAILURE."""


# ---------------------------------------------------------------------------
# Nutrition prompt
# ---------------------------------------------------------------------------

def build_nutrition_prompt(
    user_profile: UserProfileDTO,
    preferences: NutritionPreferencesDTO,
    duration_weeks: int,
    medical_rules: str,
    existing_plan: Optional[NutritionPlanDTO] = None,
    allowed_foods_str: str = "",
    planning_output: Optional["PlanningEngineOutput"] = None,
    judge_feedback: str = "",
    coach_feedback: str = "",
    lang: str = "en",
) -> str:

    user_context  = user_profile.to_context_string()
    prefs_context = preferences.to_context_string()

    # ── Macro targets ─────────────────────────────────────────────────
    if planning_output is not None:
        macro_guidance_block = planning_output.nutrition.to_prompt_block()
    else:
        target_calories = calculate_target_calories(user_profile, preferences.custom_calorie_target)
        macros          = calculate_macro_guidance(user_profile, target_calories)
        protein_pct     = round(macros["protein_g"] * 4 / target_calories * 100)
        fat_pct_val     = round(macros["fat_g"]     * 9 / target_calories * 100)
        carb_pct        = round(macros["carb_g"]    * 4 / target_calories * 100)
        macro_guidance_block = (
            "PORTION-SIZING TARGETS — use these to decide the amount_g values for each ingredient.\n"
            "Do NOT copy these numbers into the JSON output; the backend computes all macros from DB records.\n\n"
            f"  Daily energy  : ~{target_calories} kcal\n"
            f"  Protein       : ~{macros['protein_g']}g  ({protein_pct}% of calories)\n"
            f"  Fat           : ~{macros['fat_g']}g  ({fat_pct_val}% of calories)  — must be at least 25%\n"
            f"  Carbohydrates : ~{macros['carb_g']}g  ({carb_pct}% of calories)\n\n"
            "If fat would fall below 25% of the day's energy, raise the amount_g of olive oil,\n"
            "nuts (not peanuts), seeds, avocado, or fatty fish in that day's meals."
        )

    # ── Channel C — KB-grounded safety rules (from ContextBuilder) ───
    if medical_rules:
        channel_c_block = (
            "=== CHANNEL C: KB-GROUNDED NUTRITION SAFETY RULES (NON-NEGOTIABLE) ===\n"
            "The following rules were extracted from peer-reviewed clinical guidelines\n"
            "specifically for this user's conditions, medications, and allergies.\n"
            "Every rule MUST be followed. Any violation is a CRITICAL FAILURE.\n\n"
            + medical_rules
        )
    else:
        channel_c_block = (
            "=== CHANNEL C: MEDICAL & SAFETY RULES ===\n"
            + build_medical_nutrition_block(user_profile)
        )

    allergy_block = (
        "ALLERGY SAFETY — zero tolerance, any violation is a critical failure:\n"
        f"The user is allergic to: {user_profile.allergies or 'None'}\n"
        "Before finalising each meal, check EVERY ingredient name AND the instructions text against this list.\n"
        "This includes ingredient family members (e.g. prawn/shrimp/crab all count as shellfish)."
    )

    cuisine = preferences.cuisine_preference
    diversity_block = (
        "VARIETY & DIVERSITY RULES (mandatory for long-term adherence):\n"
        "• No breakfast template may be identical more than 2 times across the 7 days.\n"
        "• No snack may be identical more than 3 times across the 7 days.\n"
        "• Each day's dinner must use a different primary protein source than the previous day.\n"
        "• Across the full 7-day plan use at least 4 distinct protein sources.\n"
        "• Across the full 7-day plan use at least 4 distinct carbohydrate sources.\n"
        "• Do NOT use the same grain in more than 2 consecutive meals.\n"
        f"• Cuisine style must feel authentically {cuisine} — use characteristic herbs,\n"
        "  spices, and cooking methods typical of that cuisine."
    )

    cultural_block = build_cultural_meal_pattern_block(cuisine)

    existing_ctx = ""
    regen_block  = ""
    if existing_plan:
        existing_ctx = f"\n\nEXISTING NUTRITION PLAN TO UPDATE:\n{existing_plan.to_context_string()}"
        regen_block  = (
            "REGENERATION RULES:\n"
            "• Keep meals that still satisfy the current preferences and restrictions.\n"
            "• Only replace meals that violate new preferences, allergen rules, or macro targets.\n"
            "• Adjust ingredient amounts (amount_g) to fix macro deviations before replacing whole meals."
        )

    judge_block = ""
    if judge_feedback:
        judge_block = (
            "=== JUDGE FEEDBACK — YOU MUST FIX EVERY ISSUE LISTED BELOW ===\n"
            "The previous version of this plan was reviewed and FAILED. Fix ALL of the following:\n\n"
            f"{judge_feedback}\n\n"
            "Do NOT reproduce any of the violations identified above. Address each issue explicitly."
        )

    coach_block = ""
    if coach_feedback:
        coach_block = (
            "=== COACHING ADJUSTMENT — APPLY THESE CHANGES ===\n"
            "Weekly progress analysis of this user's actual logged data found that the\n"
            "existing plan needs updating. Apply ALL of the following changes:\n\n"
            f"{coach_feedback}\n\n"
            "Keep everything else from the existing plan unchanged unless a change above requires it."
        )

    thinking_scaffold = (
        "Before writing the JSON, reason through these steps inside a <think> block.\n"
        "The <think> block must NOT appear in the final JSON output.\n\n"
        "  1. Accept the pre-computed targets above — do NOT recalculate calories or macros.\n"
        "  2. List ALL dietary exclusions from the medical block: conditions, medications, allergies, drug-food interactions.\n"
        "  3. List 7 distinct breakfasts that fit the cuisine, the cultural meal-pattern rules\n"
        "     (if provided above), portion targets, and ALL medical rules.\n"
        "  4. List 7 distinct lunches.\n"
        "  5. List 7 distinct dinners, each with a different primary protein source.\n"
        "  6. List snack options (at most 3 repeats across the week).\n"
        "  7. For each meal verify: no allergens present, all medical rules respected, fat at least 25%.\n"
        "  8. For each ingredient, set amount_g so the day's total approaches the target calories.\n"
        "  9. Only after completing the above write the final JSON."
    )

    sections = [
        "You are an expert registered dietitian and sports nutritionist acting as the REFINEMENT LAYER.",
        "The Planning Engine has already determined the macro targets and meal structure below.",
        "Your job is to SELECT appropriate foods, SET ingredient amounts (amount_g), WRITE coaching instructions,",
        "and EXPLAIN the nutritional reasoning — NOT to recalculate targets.",
        "",
        "Reason first inside <think>...</think>, then output ONLY a single valid JSON object.",
        "No markdown fences. No text before or after the JSON.",
        "",
        user_context,
        prefs_context + existing_ctx,
        "",
        f"PLAN DURATION: {duration_weeks} week(s)",
        "",
        "=== CHANNEL P: PLANNING ENGINE OUTPUT (authoritative — do NOT override) ===",
        macro_guidance_block,
        "",
        channel_c_block,
        "",
        allergy_block,
        "",
        diversity_block,
        "",
    ]

    if cultural_block:
        sections += [cultural_block, ""]

    if regen_block:
        sections += [regen_block, ""]
    if judge_block:
        sections += [judge_block, ""]
    if coach_block:
        sections += [coach_block, ""]

    sections += [
        "=== CHANNEL B: DATABASE FOOD CONSTRAINTS ===",
        "Use ONLY the food IDs listed below. Never invent a central_food_id.",
        allowed_foods_str,
        "",
        "=== REASONING SCAFFOLD ===",
        thinking_scaffold,
        "",
        "=== FINAL OUTPUT FORMAT ===",
        f"Generate a complete 7-day meal plan with EXACTLY {preferences.meals_per_day} meals per day.",
        "Every ingredient mentioned in the instructions field MUST appear in the ingredients array.",
        "Do NOT include any macro or calorie numbers in the JSON output.",
        "",
        '{',
        '  "plan_name": "Descriptive name reflecting cuisine and goal",',
        '  "description": "2-3 sentences covering cuisine style, fitness goal, and medical considerations",',
        '  "days": [',
        '    {',
        '      "day_name": "Monday",',
        '      "day_number": 1,',
        '      "notes": "Optional coaching note, e.g. high-protein day or omega-3 focus",',
        '      "meals": [',
        '        {',
        '          "meal_type": "Breakfast",',
        '          "meal_name": "Creative specific meal name",',
        '          "ingredients": [',
        '            {"central_food_id": 123, "amount_g": 80.0},',
        '            {"central_food_id": 456, "amount_g": 15.0}',
        '          ],',
        '          "instructions": "Step-by-step instructions that name every ingredient with coaching cues",',
        '          "prep_time_minutes": 10,',
        '          "cook_time_minutes": 20,',
        '          "servings": 1,',
        '          "order_index": 0',
        '        }',
        '      ]',
        '    }',
        '  ]',
        '}',
        "",
        "CRITICAL: Output ONLY the JSON object. No markdown fences. No text before or after.",
        "",
        f"LANGUAGE: {'Write ALL text fields (plan_name, description, meal_name, instructions, day_name, notes) in Arabic.' if lang == 'ar' else 'Write ALL text fields in English.'}",
    ]

    return "\n".join(sections).strip()


# ---------------------------------------------------------------------------
# Workout prompt
# ---------------------------------------------------------------------------

def build_workout_prompt(
    user_profile: UserProfileDTO,
    preferences: WorkoutPreferencesDTO,
    duration_weeks: int,
    medical_rules: str,
    existing_plan: Optional[WorkoutPlanDTO] = None,
    allowed_exercises_str: str = "",
    planning_output: Optional["PlanningEngineOutput"] = None,
    judge_feedback: str = "",
    coach_feedback: str = "",
    lang: str = "en",
) -> str:

    user_context  = user_profile.to_context_string()
    prefs_context = preferences.to_context_string()

    # ── Training targets ──────────────────────────────────────────────
    if planning_output is not None:
        training_block   = planning_output.training.to_prompt_block()
        days_per_week    = planning_output.training.training_days
        session_duration = planning_output.training.session_duration_minutes
    else:
        training_block   = (
            f"Training days/week : {preferences.workout_days_per_week}\n"
            f"Session duration   : {preferences.session_duration_minutes} minutes"
        )
        days_per_week    = preferences.workout_days_per_week
        session_duration = preferences.session_duration_minutes

    # ── Channel C — KB-grounded safety rules (from ContextBuilder) ───
    if medical_rules:
        channel_c_block = (
            "=== CHANNEL C: KB-GROUNDED WORKOUT SAFETY RULES (NON-NEGOTIABLE) ===\n"
            "The following rules were extracted from peer-reviewed clinical guidelines\n"
            "specifically for this user's injuries, conditions, and limitations.\n"
            "Every rule MUST be followed. Any violation is a CRITICAL FAILURE.\n\n"
            + medical_rules
        )
    else:
        channel_c_block = (
            "=== CHANNEL C: INJURY & MEDICAL EXERCISE RULES ===\n"
            + build_medical_workout_block(user_profile)
        )

    existing_ctx = ""
    regen_block  = ""
    if existing_plan:
        existing_ctx = f"\n\nEXISTING WORKOUT PLAN TO UPDATE:\n{existing_plan.to_context_string()}"
        regen_block  = (
            "REGENERATION RULES:\n"
            "• Keep exercises that still match the new preferences and are safe for the user's conditions.\n"
            "• Only modify days or exercises that conflict with new preferences or medical rules.\n"
            "• Maintain progression continuity where appropriate."
        )

    judge_block = ""
    if judge_feedback:
        judge_block = (
            "=== JUDGE FEEDBACK — YOU MUST FIX EVERY ISSUE LISTED BELOW ===\n"
            "The previous version of this plan was reviewed and FAILED. Fix ALL of the following:\n\n"
            f"{judge_feedback}\n\n"
            "Do NOT reproduce any of the violations identified above. Address each issue explicitly."
        )

    coach_block = ""
    if coach_feedback:
        coach_block = (
            "=== COACHING ADJUSTMENT — APPLY THESE CHANGES ===\n"
            "Weekly progress analysis of this user's actual logged data found that the\n"
            "existing plan needs updating. Apply ALL of the following changes:\n\n"
            f"{coach_feedback}\n\n"
            "Keep everything else from the existing plan unchanged unless a change above requires it."
        )

    thinking_scaffold = (
        "Before writing the JSON, reason through these steps inside a <think> block.\n"
        "The <think> block must NOT appear in the final JSON output.\n\n"
        "  1. Accept the pre-computed training targets above — do NOT change the split or days.\n"
        "  2. List EVERY excluded exercise from the medical/injury block — be exhaustive.\n"
        "     Include all movement variations that stress the affected area, not just the named ones.\n"
        f"  3. Map out each of the {days_per_week} workout days according to the split.\n"
        "  4. For each day, select exercises from the catalog that fit the focus area and avoid ALL exclusions.\n"
        f"  5. Confirm each session fits within {session_duration} minutes.\n"
        "  6. Verify that every exercise involving a restricted area has explicit safety cues in its instructions.\n"
        "  7. Only after completing the above write the final JSON."
    )

    parts = [
        "You are an expert certified personal trainer and strength & conditioning coach "
        "acting as the REFINEMENT LAYER.",
        "The Planning Engine has already determined the training structure below.",
        "Your job is to SELECT appropriate exercises from the catalog, WRITE form cues and coaching",
        "instructions, and EXPLAIN the programming rationale — NOT to change the training structure.",
        "",
        "Reason first inside <think>...</think>, then output ONLY a single valid JSON object.",
        "No markdown fences. No text before or after the JSON.",
        "",
        user_context,
        prefs_context + existing_ctx,
        "",
        f"PLAN DURATION: {duration_weeks} week(s)",
        "",
        "=== CHANNEL P: PLANNING ENGINE OUTPUT (authoritative — do NOT override) ===",
        training_block,
        "",
        channel_c_block,
        "",
    ]

    if regen_block:
        parts += [regen_block, ""]
    if judge_block:
        parts += [judge_block, ""]
    if coach_block:
        parts += [coach_block, ""]

    parts += [
        "=== CHANNEL B: DATABASE EXERCISE CONSTRAINTS ===",
        "Use ONLY the exercise IDs listed below. Never invent a central_exercise_id.",
        allowed_exercises_str,
        "",
        "=== REASONING SCAFFOLD ===",
        thinking_scaffold,
        "",
        "=== FINAL OUTPUT FORMAT ===",
        f"Generate a {days_per_week}-day workout plan.",
        "",
        "{",
        '  "plan_name": "Descriptive name reflecting goal and training split",',
        '  "description": "2-3 sentences covering training methodology, goal alignment, and injury modifications",',
        f'  "frequency": "{days_per_week} days per week",',
        f'  "difficulty_level": "{preferences.workout_difficulty}",',
        f'  "estimated_duration_per_session": {session_duration},',
        '  "workout_days": [',
        "    {",
        '      "day_name": "Day 1 - Focus Area",',
        '      "day_number": 1,',
        '      "focus_area": "e.g. Upper Body Push",',
        f'      "estimated_duration": {session_duration},',
        '      "notes": "Warm-up, cool-down, and session-specific safety cues",',
        '      "exercises": [',
        "        {",
        '          "central_exercise_id": 123,',
        '          "exercise_name": "Exercise Name",',
        '          "exercise_type": "Strength",',
        '          "sets": 3,',
        '          "reps": 12,',
        '          "weight_kg": null,',
        '          "duration_seconds": null,',
        '          "rest_seconds": 90,',
        '          "instructions": "Step-by-step cues including safety and form corrections",',
        '          "order_index": 0',
        "        }",
        "      ]",
        "    }",
        "  ]",
        "}",
        "",
        "CRITICAL: Output ONLY the JSON object. No markdown fences. No text before or after.",
        "",
        f"LANGUAGE: {'Write ALL text fields (plan_name, description, day_name, focus_area, notes, instructions) in Arabic.' if lang == 'ar' else 'Write ALL text fields in English.'}",
    ]

    return "\n".join(parts).strip()
