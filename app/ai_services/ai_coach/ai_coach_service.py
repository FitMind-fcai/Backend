import os
import json
import logging
import re
from typing import Optional, Dict, Any, List

from openai import OpenAI
from pydantic import ValidationError

from app.ai_services.ai_coach.vector_db_service import get_vector_db_service, VectorDBService
from app.ai_services.ai_coach.dtos import (
    UserProfileDTO,
    WorkoutPreferencesDTO,
    NutritionPreferencesDTO,
    WorkoutPlanDTO,
    NutritionPlanDTO,
    NutritionDayDTO,
    WorkoutDayDTO,
    ExerciseDTO,
    MealDTO,
)
from app.core import config

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Lookup tables
# ---------------------------------------------------------------------------

GOAL_ALIASES: Dict[str, str] = {
    "get bulks":         "build muscle",
    "bulking":           "build muscle",
    "gain muscle":       "build muscle",
    "muscle gain":       "build muscle",
    "hypertrophy":       "build muscle",
    "build muscle":      "build muscle",
    "lose weight":       "lose weight",
    "weight loss":       "lose weight",
    "fat loss":          "lose weight",
    "cut":               "lose weight",
    "cutting":           "lose weight",
    "maintain":          "maintain",
    "maintain weight":   "maintain",
    "maintenance":       "maintain",
    "improve fitness":   "improve fitness",
    "endurance":         "improve fitness",
    "recomposition":     "maintain",
}

ACTIVITY_MULTIPLIERS: Dict[str, float] = {
    "sedentary":          1.20,
    "lightly active":     1.375,
    "moderately active":  1.55,
    "very active":        1.725,
    "extra active":       1.90,
}

GOAL_CALORIE_DELTA: Dict[str, int] = {
    "build muscle":    +450,
    "lose weight":     -400,
    "maintain":           0,
    "improve fitness":    0,
}

# Protein g per kg of bodyweight
GOAL_PROTEIN_PER_KG: Dict[str, float] = {
    "build muscle":    1.8,
    "lose weight":     1.6,
    "maintain":        1.4,
    "improve fitness": 1.4,
}

# Fat as a fraction of total calories
GOAL_FAT_PCT: Dict[str, float] = {
    "build muscle":    0.28,
    "lose weight":     0.30,
    "maintain":        0.28,
    "improve fitness": 0.28,
}

# ---------------------------------------------------------------------------
# Medical rule libraries
# ---------------------------------------------------------------------------

MEDICAL_NUTRITION_RULES: Dict[str, str] = {
    "hypertension": """
HYPERTENSION DIETARY RULES — override everything else, non-negotiable:
• Use ONLY "without salt" or "no salt added" variants of legumes and canned goods.
  Never select any ingredient explicitly labelled "with salt".
• Include at least ONE omega-3 source per day from: salmon, sardines, mackerel,
  trout, herring, flaxseed, chia seeds, walnuts.
  (Shellfish are excluded due to the user's allergy.)
• Include at least ONE potassium-rich food per day:
  sweet potato, spinach, banana, avocado, lentils, kidney beans, yogurt.
• Keep total daily sodium under 2 000 mg — avoid processed, cured, smoked, or pickled items.
• Use olive oil as the primary fat source (cardioprotective + Mediterranean authentic).
  Include at least 1 tbsp (approx. 14 g) per day.
• Completely exclude grapefruit and grapefruit juice (Amlodipine interaction).
""",

    "diabetes": """
DIABETES DIETARY RULES — override everything else, non-negotiable:
• Use only low-GI carbohydrates: legumes, non-starchy vegetables, oats, barley,
  quinoa, sweet potato. Avoid white rice, white bread, and refined-sugar products.
• Distribute carbohydrates evenly across ALL meals — no single meal should supply
  more than 40% of the day's total carbohydrate.
• Avoid honey, maple syrup, agave, and other high-GI sweeteners.
• Limit fruit juice entirely; prefer whole fruit in moderate portions.
""",

    "celiac": """
CELIAC / GLUTEN INTOLERANCE RULES — override everything else, non-negotiable:
• Exclude ALL wheat, barley, rye, spelt, kamut, and triticale ingredients.
• Permitted grains: rice, quinoa, buckwheat, millet, amaranth, sorghum,
  certified gluten-free oats.
""",

    "high cholesterol": """
HIGH CHOLESTEROL DIETARY RULES — override everything else, non-negotiable:
• Limit saturated fat to less than 7% of total calories.
• Exclude processed meats (sausage, bacon, salami, hot dogs).
• Emphasise soluble-fibre sources: oats, barley, legumes, apples, flaxseed.
• Use olive oil or avocado oil as the primary cooking fat.
""",

    "gout": """
GOUT DIETARY RULES — override everything else, non-negotiable:
• Limit high-purine proteins: organ meats, anchovies, sardines, mussels.
• Avoid alcohol and high-fructose corn syrup entirely.
• Prefer lower-purine proteins: chicken breast, turkey, eggs, tofu.
• Note in meal instructions to drink plenty of water throughout the day.
""",
}

MEDICAL_WORKOUT_RULES: Dict[str, str] = {
    "hypertension": """
HYPERTENSION EXERCISE RULES — override everything else, non-negotiable:
• Keep all aerobic work at moderate intensity (RPE 4-6 / 50-70% HRmax).
• Avoid heavy Valsalva manoeuvre — cue exhale on exertion for every resistance exercise.
• Avoid isometric holds longer than 10 seconds at high intensity (e.g. plank over 30 s, wall-sit).
• Warm-up and cool-down must each be at least 5 minutes — state this in the day notes field.
• Do NOT programme HIIT or max-effort sprint intervals.
""",

    "right shoulder impingement": """
RIGHT SHOULDER IMPINGEMENT RULES — override everything else, non-negotiable:
• Exclude ALL overhead pressing: overhead press, push press, Arnold press,
  landmine press above shoulder height.
• Exclude behind-the-neck pull-downs and behind-the-neck presses.
• Exclude upright rows.
• Allowed shoulder work: lateral raises (controlled, below 90 degrees), face pulls,
  band external rotation, prone Y/T/W, reverse flyes.
• For chest: prefer dumbbell floor press or cable fly over barbell bench press.
• Always cue: keep shoulder blades retracted and depressed throughout the movement.
""",

    "lower back pain": """
LOWER BACK PAIN RULES — override everything else, non-negotiable:
• Exclude conventional deadlifts and good mornings.
• Replace barbell squats with goblet squats, leg press, or box squats
  with a neutral-spine cue.
• Exclude sit-ups and full Roman-chair hyperextensions.
• Include at least one core-stability exercise per session:
  dead bugs, bird dogs, pallof press, or suitcase carry.
• Cue bracing, neutral spine, and hip hinge mechanics in every relevant instruction.
""",
}


class AICoachService:

    DEFAULT_PROVIDER    = "openrouter"
    DEFAULT_MODEL       = "qwen/qwen3-235b-a22b-2507"
    DEFAULT_TEMPERATURE = 0.25
    DEFAULT_MAX_TOKENS  = 8000

    PROVIDER_BASE_URLS = {
        "groq":       "https://api.groq.com/openai/v1",
        "openrouter": "https://openrouter.ai/api/v1",
        "openai":     "https://api.openai.com/v1",
        "together":   "https://api.together.xyz/v1",
        "deepinfra":  "https://api.deepinfra.com/v1/openai",
        "fireworks":  "https://api.fireworks.ai/inference/v1",
    }

    def __init__(
        self,
        provider: Optional[str] = None,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        model: Optional[str] = None,
        vector_db_service: Optional[VectorDBService] = None,
    ):
        self.provider = (
            provider or os.getenv("AI_PROVIDER") or config.AI_PROVIDER or self.DEFAULT_PROVIDER
        ).lower()

        self.api_key = (
            api_key
            or os.getenv("AI_API_KEY")
            or config.AI_API_KEY
            or self._get_provider_api_key(self.provider)
        )
        if not self.api_key:
            raise ValueError(
                f"No API key found for provider '{self.provider}'. "
                "Set AI_API_KEY or a provider-specific key in environment."
            )

        self.base_url = (
            base_url
            or os.getenv("AI_BASE_URL")
            or config.AI_BASE_URL
            or self.PROVIDER_BASE_URLS.get(self.provider)
        )
        if not self.base_url:
            raise ValueError(f"No base URL configured for provider '{self.provider}'.")

        self.model = model or os.getenv("AI_MODEL") or config.AI_MODEL or self.DEFAULT_MODEL
        self.temperature = float(
            os.getenv("AI_COACH_TEMPERATURE")
            or str(config.AI_COACH_TEMPERATURE or self.DEFAULT_TEMPERATURE)
        )
        self.max_tokens = int(
            os.getenv("AI_COACH_MAX_TOKENS")
            or str(config.AI_COACH_MAX_TOKENS or self.DEFAULT_MAX_TOKENS)
        )
        self.rag_top_k             = int(os.getenv("AI_RAG_TOP_K", "3"))
        self.rag_max_context_chars = int(os.getenv("AI_RAG_MAX_CONTEXT_CHARS", "2400"))

        self.client = OpenAI(
            api_key=self.api_key,
            base_url=self.base_url,
            default_headers=self._build_provider_headers(self.provider),
        )
        self.vector_db = vector_db_service or get_vector_db_service()

        logger.info(
            "AI Coach initialised — provider=%s model=%s base_url=%s max_tokens=%s",
            self.provider, self.model, self.base_url, self.max_tokens,
        )

    # ------------------------------------------------------------------
    # Provider helpers
    # ------------------------------------------------------------------

    def _get_provider_api_key(self, provider: str) -> str:
        mapping = {
            "groq":       ("GROQ_API_KEY",      getattr(config, "GROQ_API_KEY",      "")),
            "openrouter": ("OPENROUTER_API_KEY", getattr(config, "OPENROUTER_API_KEY", "")),
            "openai":     ("OPENAI_API_KEY",     getattr(config, "OPENAI_API_KEY",     "")),
            "together":   ("TOGETHER_API_KEY",   getattr(config, "TOGETHER_API_KEY",   "")),
            "deepinfra":  ("DEEPINFRA_API_KEY",  getattr(config, "DEEPINFRA_API_KEY",  "")),
            "fireworks":  ("FIREWORKS_API_KEY",  getattr(config, "FIREWORKS_API_KEY",  "")),
        }
        if provider in mapping:
            env_key, cfg_val = mapping[provider]
            return os.getenv(env_key) or cfg_val or ""
        return ""

    def _build_provider_headers(self, provider: str) -> Optional[Dict[str, str]]:
        if provider != "openrouter":
            return None
        headers: Dict[str, str] = {}
        site_url = os.getenv("OPENROUTER_SITE_URL") or getattr(config, "OPENROUTER_SITE_URL", "")
        app_name = os.getenv("OPENROUTER_APP_NAME") or getattr(config, "OPENROUTER_APP_NAME", "")
        if site_url:
            headers["HTTP-Referer"] = site_url
        if app_name:
            headers["X-Title"] = app_name
        return headers or None

    def _trim_rag_context(self, rag_context: str, context_name: str) -> str:
        context = (rag_context or "").strip()
        preview = context[:800]
        if len(context) > 800:
            preview += "..."
        logger.info(
            "📚 Retrieved %s context preview (%s chars): %s",
            context_name, len(context), preview,
        )
        if len(context) <= self.rag_max_context_chars:
            return context
        trimmed = context[: self.rag_max_context_chars].rstrip()
        logger.info(
            "✂️ Trimmed %s context from %s to %s chars",
            context_name, len(context), len(trimmed),
        )
        return trimmed

    # ------------------------------------------------------------------
    # Goal & calorie helpers
    # ------------------------------------------------------------------

    def _normalize_goal(self, raw_goal: str) -> str:
        """Map any free-text fitness goal to a canonical lowercase key."""
        return GOAL_ALIASES.get((raw_goal or "").lower().strip(), "maintain")

    def _calculate_tdee(self, user_profile: UserProfileDTO) -> float:
        """Mifflin-St Jeor BMR multiplied by activity multiplier to get TDEE kcal/day."""
        weight = user_profile.weight or 70.0
        height = user_profile.height or 170.0
        age    = user_profile.age    or 25
        gender = (user_profile.gender or "male").lower()

        if gender == "male":
            bmr = 10 * weight + 6.25 * height - 5 * age + 5
        else:
            bmr = 10 * weight + 6.25 * height - 5 * age - 161

        level      = (user_profile.activity_level or "lightly active").lower()
        multiplier = ACTIVITY_MULTIPLIERS.get(level, 1.375)
        return round(bmr * multiplier, 1)

    def _calculate_target_calories(
        self,
        user_profile: UserProfileDTO,
        custom_target: Optional[int],
    ) -> int:
        """
        Return the daily calorie target used exclusively as PORTION-SIZING GUIDANCE
        in the prompt.

        This number tells the AI how many grams of each ingredient to prescribe so
        that the meal totals land near the right energy level.

        IMPORTANT: The authoritative macro numbers stored in the database are ALWAYS
        computed by the backend (_hydrate_nutrition_macros_from_ingredients) from
        the exact per-100g values in CentralFood records — never from anything the
        AI writes in the JSON.
        """
        if custom_target:
            return int(custom_target)

        tdee   = self._calculate_tdee(user_profile)
        goal   = self._normalize_goal(user_profile.fitness_goal)
        delta  = GOAL_CALORIE_DELTA.get(goal, 0)
        target = int(tdee + delta)
        target = max(1200, min(target, 5000))   # hard safety floor / ceiling

        logger.info(
            "🔢 Calorie guidance — goal=%s TDEE=%.0f delta=%+d target=%d kcal",
            goal, tdee, delta, target,
        )
        return target

    def _calculate_macro_guidance(
        self,
        user_profile: UserProfileDTO,
        target_calories: int,
    ) -> Dict[str, int]:
        """
        Return approximate macro gram targets used ONLY to guide ingredient portion
        sizes in the prompt.

        The backend always recomputes the real macro totals from DB records.
        """
        goal      = self._normalize_goal(user_profile.fitness_goal)
        weight    = user_profile.weight or 70.0

        protein_g = round(weight * GOAL_PROTEIN_PER_KG.get(goal, 1.4))
        fat_pct   = GOAL_FAT_PCT.get(goal, 0.28)
        fat_g     = round((target_calories * fat_pct) / 9)
        carb_g    = max(50, round((target_calories - protein_g * 4 - fat_g * 9) / 4))

        return {"protein_g": protein_g, "fat_g": fat_g, "carb_g": carb_g}

    # ------------------------------------------------------------------
    # Medical rule builders
    # ------------------------------------------------------------------

    def _build_medical_nutrition_rules(self, user_profile: UserProfileDTO) -> str:
        """Translate medical_conditions and medications into hard dietary rules."""
        conditions = (user_profile.medical_conditions or "").lower()
        meds       = (user_profile.medications or "").lower()

        # Amlodipine implies hypertension management even if the condition field is vague
        if ("amlodipine" in meds or "calcium channel" in meds) and "hypertension" not in conditions:
            conditions += " hypertension"

        rules = [
            rule_text
            for key, rule_text in MEDICAL_NUTRITION_RULES.items()
            if key in conditions
        ]
        return "\n".join(rules).strip()

    def _build_medical_workout_rules(self, user_profile: UserProfileDTO) -> str:
        """Translate medical_conditions and injuries into hard exercise exclusions."""
        combined = " ".join(filter(None, [
            (user_profile.medical_conditions or "").lower(),
            (user_profile.injuries or "").lower(),
        ]))
        rules = [
            rule_text
            for key, rule_text in MEDICAL_WORKOUT_RULES.items()
            if key in combined
        ]
        return "\n".join(rules).strip()

    # ------------------------------------------------------------------
    # Prompt builders
    # ------------------------------------------------------------------

    def _build_nutrition_prompt(
        self,
        user_profile: UserProfileDTO,
        preferences: NutritionPreferencesDTO,
        duration_weeks: int,
        rag_context: str,
        existing_plan: Optional[NutritionPlanDTO] = None,
        allowed_foods_str: str = "",
    ) -> str:

        user_context  = user_profile.to_context_string()
        prefs_context = preferences.to_context_string()

        # ── Portion-sizing guidance (NOT written into JSON output) ────
        target_calories = self._calculate_target_calories(
            user_profile, preferences.custom_calorie_target
        )
        macros = self._calculate_macro_guidance(user_profile, target_calories)

        protein_pct = round(macros["protein_g"] * 4 / target_calories * 100)
        fat_pct_val = round(macros["fat_g"]     * 9 / target_calories * 100)
        carb_pct    = round(macros["carb_g"]    * 4 / target_calories * 100)

        macro_guidance_block = f"""
PORTION-SIZING TARGETS — use these to decide the amount_g values for each ingredient.
Do NOT copy these numbers into the JSON output; the backend computes all macros from DB records.

  Daily energy  : ~{target_calories} kcal
  Protein       : ~{macros['protein_g']}g  ({protein_pct}% of calories)
  Fat           : ~{macros['fat_g']}g  ({fat_pct_val}% of calories)  — must be at least 25%
  Carbohydrates : ~{macros['carb_g']}g  ({carb_pct}% of calories)

If fat would fall below 25% of the day's energy, raise the amount_g of olive oil,
nuts (not peanuts), seeds, avocado, or fatty fish in that day's meals.
""".strip()

        # ── Medical dietary rules ─────────────────────────────────────
        medical_rules = self._build_medical_nutrition_rules(user_profile)
        medical_block = f"""
=== CHANNEL C: MEDICAL & MEDICATION DIETARY RULES (OVERRIDE EVERYTHING ELSE) ===
{medical_rules if medical_rules else "No specific medical dietary rules for this user."}
""".strip()

        # ── Allergy block ─────────────────────────────────────────────
        allergies = user_profile.allergies or "None"
        allergy_block = f"""
ALLERGY SAFETY — zero tolerance, any violation is a critical failure:
The user is allergic to: {allergies}
Before finalising each meal, check every ingredient name against this allergy list.
""".strip()

        # ── Diversity / variety rules ─────────────────────────────────
        cuisine = preferences.cuisine_preference
        diversity_block = f"""
VARIETY & DIVERSITY RULES (mandatory for long-term adherence):
• No breakfast template may be identical more than 2 times across the 7 days.
• No snack may be identical more than 3 times across the 7 days.
• Each day's dinner must use a different primary protein source than the previous day.
• Across the full 7-day plan use at least 4 distinct protein sources.
• Across the full 7-day plan use at least 4 distinct carbohydrate sources.
• Do NOT use the same grain in more than 2 consecutive meals.
• Cuisine style must feel authentically {cuisine} — use characteristic herbs,
  spices, and cooking methods typical of that cuisine.
""".strip()

        # ── Existing plan context (regeneration mode) ─────────────────
        existing_ctx = ""
        regen_block  = ""
        if existing_plan:
            existing_ctx = f"\n\nEXISTING NUTRITION PLAN TO UPDATE:\n{existing_plan.to_context_string()}"
            regen_block  = """
REGENERATION RULES:
• Keep meals that still satisfy the current preferences and restrictions.
• Only replace meals that violate new preferences, allergen rules, or macro targets.
• Adjust ingredient amounts (amount_g) to fix macro deviations before replacing whole meals.
""".strip()

        # ── Chain-of-thought scaffold ─────────────────────────────────
        thinking_scaffold = f"""
Before writing the JSON, reason through these steps inside a <think> block.
The <think> block must NOT appear in the final JSON output.

  1. Confirm the target calories ({target_calories} kcal) and macro split.
  2. List 7 distinct breakfasts that fit the cuisine, portion targets, and medical rules.
  3. List 7 distinct lunches.
  4. List 7 distinct dinners, each with a different primary protein source.
  5. List snack options (at most 3 repeats across the week).
  6. For each meal verify: no allergens present, all medical rules respected, fat at least 25%.
  7. Only after completing the above write the final JSON.
""".strip()

        return f"""You are an expert registered dietitian and sports nutritionist.
Reason first inside <think>...</think>, then output ONLY a single valid JSON object.
No markdown fences. No text before or after the JSON.

{user_context}
{prefs_context}{existing_ctx}

PLAN DURATION: {duration_weeks} week(s)

{macro_guidance_block}

{medical_block}

{allergy_block}

{diversity_block}

=== CHANNEL A: EVIDENCE-BASED NUTRITION GUIDELINES (RAG) ===
{rag_context}

{regen_block}

=== CHANNEL B: DATABASE FOOD CONSTRAINTS ===
Use ONLY the food IDs listed below. Never invent a central_food_id.
{allowed_foods_str}

=== REASONING SCAFFOLD ===
{thinking_scaffold}

=== FINAL OUTPUT FORMAT ===
Generate a complete 7-day meal plan with EXACTLY {preferences.meals_per_day} meals per day.
Every ingredient mentioned in the instructions field MUST appear in the ingredients array.
Do NOT include any macro or calorie numbers in the JSON output.

{{
  "plan_name": "Descriptive name reflecting cuisine and goal",
  "description": "2-3 sentences covering cuisine style, fitness goal, and medical considerations",
  "days": [
    {{
      "day_name": "Monday",
      "day_number": 1,
      "notes": "Optional note, e.g. omega-3 focus day",
      "meals": [
        {{
          "meal_type": "Breakfast",
          "meal_name": "Creative specific meal name",
          "ingredients": [
            {{"central_food_id": 123, "amount_g": 80.0}},
            {{"central_food_id": 456, "amount_g": 15.0}}
          ],
          "instructions": "Step-by-step instructions that name every ingredient",
          "prep_time_minutes": 10,
          "cook_time_minutes": 20,
          "servings": 1,
          "order_index": 0
        }}
      ]
    }}
  ]
}}

CRITICAL: Output ONLY the JSON object. No markdown fences. No text before or after.
""".strip()

    def _build_workout_prompt(
        self,
        user_profile: UserProfileDTO,
        preferences: WorkoutPreferencesDTO,
        duration_weeks: int,
        rag_context: str,
        existing_plan: Optional[WorkoutPlanDTO] = None,
        allowed_exercises_str: str = "",
    ) -> str:

        user_context  = user_profile.to_context_string()
        prefs_context = preferences.to_context_string()

        # ── Medical / injury rules ────────────────────────────────────
        medical_rules = self._build_medical_workout_rules(user_profile)
        medical_block = f"""
=== CHANNEL C: INJURY & MEDICAL EXERCISE RULES (OVERRIDE EVERYTHING ELSE) ===
{medical_rules if medical_rules else "No specific injury or medical exercise restrictions for this user."}
""".strip()

        # ── Existing plan (regeneration mode) ────────────────────────
        existing_ctx = ""
        regen_block  = ""
        if existing_plan:
            existing_ctx = f"\n\nEXISTING WORKOUT PLAN TO UPDATE:\n{existing_plan.to_context_string()}"
            regen_block  = """
REGENERATION RULES:
• Keep exercises that still match the new preferences and are safe for the user's conditions.
• Only modify days or exercises that conflict with new preferences or medical rules.
• Maintain progression continuity where appropriate.
""".strip()

        # ── Chain-of-thought scaffold ─────────────────────────────────
        thinking_scaffold = f"""
Before writing the JSON, reason through these steps inside a <think> block.
The <think> block must NOT appear in the final JSON output.

  1. Choose the optimal training split for {preferences.workout_days_per_week} days/week
     given the user's goal, injuries, and conditions.
  2. List every excluded exercise (from CHANNEL C rules above).
  3. For each workout day list candidate exercises and verify none are in the exclusion list.
  4. Confirm the total session fits within {preferences.session_duration_minutes} minutes.
  5. Only after completing the above write the final JSON.
""".strip()

        return f"""You are an expert certified personal trainer and strength & conditioning coach.
Reason first inside <think>...</think>, then output ONLY a single valid JSON object.
No markdown fences. No text before or after the JSON.

{user_context}
{prefs_context}{existing_ctx}

PLAN DURATION: {duration_weeks} week(s)

{medical_block}

=== CHANNEL A: EVIDENCE-BASED TRAINING GUIDELINES (RAG) ===
{rag_context}

{regen_block}

=== CHANNEL B: DATABASE EXERCISE CONSTRAINTS ===
Use ONLY the exercise IDs listed below. Never invent a central_exercise_id.
{allowed_exercises_str}

=== REASONING SCAFFOLD ===
{thinking_scaffold}

=== FINAL OUTPUT FORMAT ===
Generate a {preferences.workout_days_per_week}-day workout plan.

{{
  "plan_name": "Descriptive name reflecting goal and training split",
  "description": "2-3 sentences covering training methodology, goal alignment, and injury modifications",
  "frequency": "{preferences.workout_days_per_week} days per week",
  "difficulty_level": "{preferences.workout_difficulty}",
  "estimated_duration_per_session": {preferences.session_duration_minutes},
  "workout_days": [
    {{
      "day_name": "Day 1 - Focus Area",
      "day_number": 1,
      "focus_area": "e.g. Upper Body Push",
      "estimated_duration": {preferences.session_duration_minutes},
      "notes": "Warm-up, cool-down, and session-specific safety cues",
      "exercises": [
        {{
          "central_exercise_id": 123,
          "exercise_name": "Exercise Name",
          "exercise_type": "Strength",
          "sets": 3,
          "reps": 12,
          "weight_kg": null,
          "duration_seconds": null,
          "rest_seconds": 90,
          "instructions": "Step-by-step cues including safety and form corrections",
          "order_index": 0
        }}
      ]
    }}
  ]
}}

CRITICAL: Output ONLY the JSON object. No markdown fences. No text before or after.
""".strip()

    # ------------------------------------------------------------------
    # LLM call
    # ------------------------------------------------------------------

    def _call_llm(
        self, system_prompt: str, user_prompt: str, json_mode: bool = True
    ) -> str:
        call_kwargs: Dict[str, Any] = dict(
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user",   "content": user_prompt},
            ],
            model=self.model,
            temperature=self.temperature,
            max_tokens=self.max_tokens,
            top_p=0.90,
        )
        if json_mode:
            call_kwargs["response_format"] = {"type": "json_object"}

        chat_completion = self.client.chat.completions.create(**call_kwargs)

        finish_reason     = None
        prompt_tokens     = None
        completion_tokens = None
        total_tokens      = None

        if chat_completion.choices:
            finish_reason = chat_completion.choices[0].finish_reason
        usage = getattr(chat_completion, "usage", None)
        if usage:
            prompt_tokens     = getattr(usage, "prompt_tokens",     None)
            completion_tokens = getattr(usage, "completion_tokens", None)
            total_tokens      = getattr(usage, "total_tokens",      None)

        logger.info(
            "LLM usage finish_reason=%s prompt=%s completion=%s total=%s",
            finish_reason, prompt_tokens, completion_tokens, total_tokens,
        )
        return chat_completion.choices[0].message.content

    # ------------------------------------------------------------------
    # JSON parsing
    # ------------------------------------------------------------------

    def _parse_json_response(self, response: str) -> Dict[str, Any]:
        """
        Parse the LLM response to a dict, handling:
          - Qwen3 <think>...</think> reasoning blocks emitted before the JSON
          - Markdown code fences
          - Stray text before or after the JSON object
        """
        cleaned = (response or "").strip()

        # Strip Qwen3 <think>...</think> reasoning blocks
        cleaned = re.sub(r"<think>.*?</think>", "", cleaned, flags=re.DOTALL).strip()

        # Strip markdown code fences
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
        cleaned = re.sub(r"\s*```$",           "", cleaned)
        cleaned = cleaned.strip()

        # Direct parse
        try:
            return json.loads(cleaned)
        except json.JSONDecodeError:
            pass

        # Fallback: extract the first balanced top-level JSON object
        start = cleaned.find("{")
        if start != -1:
            in_string = False
            escape    = False
            depth     = 0
            for idx in range(start, len(cleaned)):
                char = cleaned[idx]
                if escape:
                    escape = False
                    continue
                if char == "\\":
                    escape = True
                    continue
                if char == '"':
                    in_string = not in_string
                    continue
                if in_string:
                    continue
                if char == "{":
                    depth += 1
                elif char == "}":
                    depth -= 1
                    if depth == 0:
                        candidate = cleaned[start: idx + 1]
                        try:
                            return json.loads(candidate)
                        except json.JSONDecodeError:
                            break

        raise ValueError(
            f"Could not parse LLM response as JSON "
            f"(length: {len(cleaned)} chars). Preview: {cleaned[:300]!r}"
        )

    # ------------------------------------------------------------------
    # DTO validation
    # ------------------------------------------------------------------

    def _format_validation_error(self, error: ValidationError) -> str:
        details = []
        for item in error.errors():
            loc = ".".join(str(p) for p in item.get("loc", []))
            msg = item.get("msg", "invalid value")
            details.append(f"{loc}: {msg}" if loc else msg)
        return "; ".join(details)

    def _validate_workout_plan_response(self, plan_data: Dict[str, Any]) -> WorkoutPlanDTO:
        if not isinstance(plan_data, dict):
            raise ValueError("Workout plan response must be a JSON object")
        try:
            return WorkoutPlanDTO.model_validate(plan_data)
        except ValidationError as err:
            raise ValueError(
                f"Workout plan schema validation failed: {self._format_validation_error(err)}"
            ) from err

    def _validate_nutrition_plan_response(self, plan_data: Dict[str, Any]) -> NutritionPlanDTO:
        if not isinstance(plan_data, dict):
            raise ValueError("Nutrition plan response must be a JSON object")
        try:
            return NutritionPlanDTO.model_validate(plan_data)
        except ValidationError as err:
            raise ValueError(
                f"Nutrition plan schema validation failed: {self._format_validation_error(err)}"
            ) from err

    def _validate_nutrition_semantics(
        self,
        plan: NutritionPlanDTO,
        user_profile: UserProfileDTO,
    ) -> None:
        """
        Allergy safety gate applied after schema validation.

        Raises ValueError immediately if any ingredient name matches a known allergen.
        Caloric / macro accuracy is NOT checked here — the backend recomputes those
        from CentralFood DB records in _hydrate_nutrition_macros_from_ingredients.
        """
        allergy_str = (user_profile.allergies or "").lower()
        if not allergy_str or allergy_str == "none":
            return

        # Build keyword list from the free-text allergies field
        allergen_keywords: List[str] = []
        if "peanut"    in allergy_str:
            allergen_keywords += ["peanut"]
        if "shellfish" in allergy_str:
            allergen_keywords += [
                "shrimp", "prawn", "crab", "lobster",
                "clam", "oyster", "mussel", "scallop", "crawfish",
            ]
        if "gluten"    in allergy_str:
            allergen_keywords += ["wheat", "barley", "rye", "spelt"]
        if "dairy"     in allergy_str:
            allergen_keywords += ["milk", "cheese", "butter", "cream", "yogurt", "whey"]
        if "egg"       in allergy_str:
            allergen_keywords += ["egg"]
        if "tree nut"  in allergy_str:
            allergen_keywords += [
                "almond", "cashew", "walnut", "pecan", "pistachio", "hazelnut",
            ]
        if "soy"       in allergy_str:
            allergen_keywords += ["soy", "tofu", "edamame", "tempeh"]

        if not allergen_keywords:
            return

        violations: List[str] = []
        for day in plan.days:
            for meal in day.meals:
                for ing in (meal.ingredients or []):
                    food_name = (getattr(ing, "food_name", None) or "").lower()
                    for kw in allergen_keywords:
                        if kw in food_name:
                            msg = (
                                f"Day {day.day_number} — {meal.meal_name}: "
                                f"ingredient '{getattr(ing, 'food_name', ing)}' "
                                f"contains allergen '{kw}'"
                            )
                            violations.append(msg)
                            logger.error("ALLERGY VIOLATION: %s", msg)

        if violations:
            raise ValueError(
                "Nutrition plan rejected — allergy violations detected:\n"
                + "\n".join(violations)
            )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def generate_nutrition_plan(
        self,
        user_profile: UserProfileDTO,
        preferences: NutritionPreferencesDTO,
        duration_weeks: int = 4,
        existing_plan: Optional[NutritionPlanDTO] = None,
        allowed_foods_str: str = "",
    ) -> NutritionPlanDTO:
        """
        Generate a personalised 7-day nutrition plan.

        The AI uses portion-sizing guidance (target_calories + macro gram targets)
        to decide how many grams of each ingredient to include.  It does NOT write
        macro or calorie numbers into the JSON.  All authoritative nutrition values
        are computed by the backend from exact CentralFood DB records.
        """
        target_calories = self._calculate_target_calories(
            user_profile, preferences.custom_calorie_target
        )
        macros = self._calculate_macro_guidance(user_profile, target_calories)
        logger.info(
            "Portion-sizing guidance — calories=%d protein=%dg fat=%dg carbs=%dg",
            target_calories, macros["protein_g"], macros["fat_g"], macros["carb_g"],
        )

        profile_tags = " ".join(filter(None, [
            user_profile.allergies          and f"allergies:{user_profile.allergies}",
            user_profile.medical_conditions and f"condition:{user_profile.medical_conditions}",
            user_profile.fitness_goal       and f"goal:{user_profile.fitness_goal}",
        ]))
        query = (
            f"nutrition meal plan {preferences.cuisine_preference} "
            f"{preferences.calorie_preference} {profile_tags}"
        )
        logger.info("Generating nutrition plan — RAG query: %s", query)

        rag_context = self.vector_db.get_context(query, k=self.rag_top_k, domain="nutrition")
        rag_context = self._trim_rag_context(rag_context, "nutrition")

        logger.info("===================================")
        logger.info("INJECTED DB FOODS STRING:")
        logger.info(allowed_foods_str)
        logger.info("===================================")

        prompt = self._build_nutrition_prompt(
            user_profile, preferences, duration_weeks,
            rag_context, existing_plan, allowed_foods_str,
        )

        system_prompt = (
            "You are an expert registered dietitian and sports nutritionist. "
            "Think carefully inside <think>...</think> first, then output a single valid "
            "JSON object — no markdown, no extra text. "
            "Strictly respect all allergy, medical, and portion-sizing constraints. "
            "Never write macro or calorie numbers into the JSON output — the backend "
            "computes those from database records. "
            "Any allergy violation is a critical failure."
        )

        response = self._call_llm(system_prompt, prompt)
        logger.info("Raw nutrition LLM output (first 3000 chars): %s", response[:3000])

        try:
            plan_data = self._parse_json_response(response)
        except ValueError as err:
            raise ValueError(
                "Nutrition plan generation failed: model output was not valid JSON. "
                f"Raw output preview: {response[:1500]!r}"
            ) from err

        plan = self._validate_nutrition_plan_response(plan_data)

        # Allergy safety gate — raises ValueError if any violation is found
        self._validate_nutrition_semantics(plan, user_profile)

        return plan

    def generate_workout_plan(
        self,
        user_profile: UserProfileDTO,
        preferences: WorkoutPreferencesDTO,
        duration_weeks: int = 4,
        existing_plan: Optional[WorkoutPlanDTO] = None,
        allowed_exercises_str: str = "",
    ) -> WorkoutPlanDTO:
        """Generate a personalised workout plan respecting all injury and medical constraints."""
        profile_tags = " ".join(filter(None, [
            user_profile.injuries           and f"injuries:{user_profile.injuries}",
            user_profile.medical_conditions and f"condition:{user_profile.medical_conditions}",
            user_profile.fitness_goal       and f"goal:{user_profile.fitness_goal}",
        ]))
        query = (
            f"workout plan {preferences.workout_focus} {preferences.workout_difficulty} "
            f"{preferences.workout_location} {profile_tags}"
        )
        logger.info("Generating workout plan — RAG query: %s", query)

        rag_context = self.vector_db.get_context(query, k=self.rag_top_k, domain="workout")
        rag_context = self._trim_rag_context(rag_context, "workout")

        logger.info("===================================")
        logger.info("INJECTED DB EXERCISES STRING:")
        logger.info(allowed_exercises_str)
        logger.info("===================================")

        prompt = self._build_workout_prompt(
            user_profile, preferences, duration_weeks,
            rag_context, existing_plan, allowed_exercises_str,
        )

        system_prompt = (
            "You are an expert certified personal trainer and strength & conditioning coach. "
            "Think carefully inside <think>...</think> first, then output a single valid "
            "JSON object — no markdown, no extra text. "
            "Strictly respect all injury and medical exercise restrictions. "
            "Never suggest exercises that could harm the user."
        )

        response = self._call_llm(system_prompt, prompt)
        logger.info("Raw workout LLM output (first 3000 chars): %s", response[:3000])

        try:
            plan_data = self._parse_json_response(response)
        except ValueError as err:
            raise ValueError(
                "Workout plan generation failed: model output was not valid JSON. "
                f"Raw output preview: {response[:1500]!r}"
            ) from err

        return self._validate_workout_plan_response(plan_data)

    def ask_coach(
        self,
        question: str,
        user_profile: Optional[UserProfileDTO] = None,
        language: str = "auto",
    ) -> str:
        """Answer a free-text fitness or nutrition question with RAG-augmented coaching advice."""
        query = question
        if user_profile:
            tags = " ".join(filter(None, [
                user_profile.injuries           and f"injuries:{user_profile.injuries}",
                user_profile.medical_conditions and f"condition:{user_profile.medical_conditions}",
                user_profile.allergies          and f"allergies:{user_profile.allergies}",
                user_profile.fitness_goal       and f"goal:{user_profile.fitness_goal}",
            ]))
            query = f"{question} {tags}"

        logger.info("Ask Coach — question: %s", question)
        logger.info("Ask Coach — enhanced query: %s", query)

        rag_context = self.vector_db.get_context(query, k=min(self.rag_top_k, 3))
        rag_context = self._trim_rag_context(rag_context, "ask_coach")

        user_context = (
            user_profile.to_context_string() if user_profile
            else "No user profile available — give general evidence-based advice."
        )

        language_instruction = {
            "auto": "Respond in the SAME LANGUAGE as the user's question.",
            "ar":   "Respond in Arabic (Egyptian dialect preferred).",
        }.get(language, "Respond in English.")

        system_prompt = f"""You are an experienced personal fitness coach with deep knowledge in exercise science and nutrition.

{language_instruction}

{user_context}

YOUR COACHING STYLE:
• Speak as a coach — direct, practical, encouraging.
• Never say "according to the handbook/guide/source" — give advice from YOUR expertise.
• Always account for the user's medical conditions, injuries, and medications.
• Give specific rep ranges, exercise names, food quantities, and timing — not vague guidance.
• Flag any safety concern before giving the main advice.
• End with one clear action the user can take TODAY."""

        user_prompt = f"""Supporting fitness & nutrition knowledge:
{rag_context}

User question: {question}

Give your professional coaching advice. Be specific and practical.
When you reference a specific study or guideline, cite it inline as [SOURCE: title]."""

        return self._call_llm(system_prompt, user_prompt, json_mode=False)


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------

_ai_coach_service: Optional[AICoachService] = None


def get_ai_coach_service() -> AICoachService:
    global _ai_coach_service
    if _ai_coach_service is None:
        _ai_coach_service = AICoachService()
    return _ai_coach_service