import logging
import threading
from typing import Dict, Optional, TYPE_CHECKING

from app.ai_services.ai_coach import plan_validator, prompt_builder
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
from app.ai_services.ai_coach.llm_client import LLMClient
from app.ai_services.ai_coach.plan_judge import PlanJudge
from app.core import config

if TYPE_CHECKING:
    from app.planning_module.core.planning_engine import PlanningEngineOutput

logger = logging.getLogger(__name__)


class AICoachService:
    def __init__(
        self,
        provider: Optional[str] = None,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        model: Optional[str] = None,
    ):
        self.llm = LLMClient(
            provider=provider, api_key=api_key, base_url=base_url, model=model
        )
        self.judge = PlanJudge(self.llm)

        logger.info(
            "AI Coach initialised — provider=%s model=%s judge_model=%s",
            self.llm.provider,
            self.llm.model,
            self.llm.judge_model,
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
        planning_output: Optional["PlanningEngineOutput"] = None,
        medical_rules: str = "",
        language: str = "en",
        model_override: Optional[str] = None,
        skip_judge: bool = False,
        coach_feedback: str = "",
        food_id_to_name: Optional[Dict[int, str]] = None,
    ) -> NutritionPlanDTO:
        """
        Generate a personalised 7-day nutrition plan.

        Workflow: Generate → Judge → Fix once (if failed) → Allergy gate → Return
        """
        target_calories = calculate_target_calories(
            user_profile, preferences.custom_calorie_target
        )
        macros = calculate_macro_guidance(user_profile, target_calories)
        logger.info(
            "Portion-sizing guidance — calories=%d protein=%dg fat=%dg carbs=%dg",
            target_calories,
            macros["protein_g"],
            macros["fat_g"],
            macros["carb_g"],
        )

        logger.info("===================================")
        logger.info("INJECTED DB FOODS STRING:")
        logger.info(allowed_foods_str)
        logger.info("===================================")

        system_prompt = (
            "You are an expert registered dietitian and sports nutritionist. "
            "Think carefully inside <think>...</think> first, then output a single valid "
            "JSON object — no markdown, no extra text. "
            "Strictly respect all allergy, medical, and portion-sizing constraints. "
            "Never write macro or calorie numbers into the JSON output — the backend "
            "computes those from database records. "
            "Any allergy violation is a critical failure. "
            "The output language is specified below and is STRICT: every text field must be "
            "entirely in that one language, with zero mixing — this includes dish/meal names, "
            "which must be translated or localized into the required language rather than left "
            "in their original language (e.g. never leave an Arabic dish name untranslated in an "
            "English-language plan, or vice versa)."
        )

        # ── Generate (regenerates on malformed/invalid output) ────────
        logger.info(
            "Nutrition — generating plan (model_override=%s, skip_judge=%s)",
            model_override,
            skip_judge,
        )
        plan = self._generate_nutrition_with_retries(
            system_prompt,
            user_profile,
            preferences,
            duration_weeks,
            medical_rules,
            existing_plan,
            allowed_foods_str,
            planning_output,
            language=language,
            model_override=model_override,
            coach_feedback=coach_feedback,
        )

        # ── Judge once → Fix once if failed ──────────────────────────
        if skip_judge:
            logger.info("Nutrition — judge skipped (skip_judge=True)")
        else:
            passed, feedback, _issues = self.judge.judge_nutrition_plan(
                plan, user_profile, preferences, planning_output, food_id_to_name
            )
            if passed:
                logger.info("Nutrition — judge passed on first try")
            elif not feedback:
                logger.info(
                    "Nutrition — judge failed but gave no feedback; skipping fix pass"
                )
            else:
                logger.info("Nutrition — judge failed, applying one-time fix pass")
                fixed = self._generate_nutrition_once(
                    system_prompt,
                    user_profile,
                    preferences,
                    duration_weeks,
                    medical_rules,
                    existing_plan,
                    allowed_foods_str,
                    planning_output,
                    judge_feedback=feedback,
                    coach_feedback=coach_feedback,
                    language=language,
                    model_override=model_override,
                )
                if fixed is not None:
                    plan = fixed
                else:
                    logger.warning(
                        "Nutrition — fix pass produced invalid output; keeping original plan"
                    )

        # ── Allergy safety gate (last-resort deterministic check) ─────
        plan_validator.validate_nutrition_semantics(plan, user_profile, food_id_to_name)

        # ── Meal/ingredient consistency check (log-only diagnostic) ──
        mismatches = plan_validator.check_meal_ingredient_consistency(
            plan, food_id_to_name
        )
        if mismatches:
            logger.warning(
                "Nutrition — meal/ingredient consistency check found %d issue(s):",
                len(mismatches),
            )
            for mismatch in mismatches:
                logger.warning("  %s", mismatch)

        return plan

    def generate_workout_plan(
        self,
        user_profile: UserProfileDTO,
        preferences: WorkoutPreferencesDTO,
        duration_weeks: int = 4,
        existing_plan: Optional[WorkoutPlanDTO] = None,
        allowed_exercises_str: str = "",
        planning_output: Optional["PlanningEngineOutput"] = None,
        medical_rules: str = "",
        language: str = "en",
        model_override: Optional[str] = None,
        skip_judge: bool = False,
        coach_feedback: str = "",
    ) -> WorkoutPlanDTO:
        """
        Generate a personalised workout plan.

        Workflow: Generate → Judge → Fix once (if failed) → Return
        """
        logger.info("===================================")
        logger.info("INJECTED DB EXERCISES STRING:")
        logger.info(allowed_exercises_str)
        logger.info("===================================")

        system_prompt = (
            "You are an expert certified personal trainer and strength & conditioning coach. "
            "Think carefully inside <think>...</think> first, then output a single valid "
            "JSON object — no markdown, no extra text. "
            "Strictly respect all injury and medical exercise restrictions. "
            "Never suggest exercises that could harm the user. "
            "The output language is specified below and is STRICT: every text field must be "
            "entirely in that one language, with zero mixing — this includes exercise/day names "
            "and coaching notes, which must be translated or localized into the required language "
            "rather than left in their original language."
        )

        # ── Generate (regenerates on malformed/invalid output) ────────
        logger.info(
            "Workout — generating plan (model_override=%s, skip_judge=%s)",
            model_override,
            skip_judge,
        )
        plan = self._generate_workout_with_retries(
            system_prompt,
            user_profile,
            preferences,
            duration_weeks,
            medical_rules,
            existing_plan,
            allowed_exercises_str,
            planning_output,
            language=language,
            model_override=model_override,
            coach_feedback=coach_feedback,
        )

        # ── Judge once → Fix once if failed ──────────────────────────
        if skip_judge:
            logger.info("Workout — judge skipped (skip_judge=True)")
        else:
            passed, feedback, _issues = self.judge.judge_workout_plan(
                plan, user_profile, preferences, planning_output
            )
            if passed:
                logger.info("Workout — judge passed on first try")
            elif not feedback:
                logger.info(
                    "Workout — judge failed but gave no feedback; skipping fix pass"
                )
            else:
                logger.info("Workout — judge failed, applying one-time fix pass")
                fixed = self._generate_workout_once(
                    system_prompt,
                    user_profile,
                    preferences,
                    duration_weeks,
                    medical_rules,
                    existing_plan,
                    allowed_exercises_str,
                    planning_output,
                    judge_feedback=feedback,
                    coach_feedback=coach_feedback,
                    language=language,
                    model_override=model_override,
                )
                if fixed is not None:
                    plan = fixed
                else:
                    logger.warning(
                        "Workout — fix pass produced invalid output; keeping original plan"
                    )

        return plan

    # ------------------------------------------------------------------
    # Progress analysis  (used by recommendation_system)
    # ------------------------------------------------------------------

    def analyze_daily_progress(
        self,
        snapshot_data: dict,
        user_goal: str,
        user_profile_context: str,
    ) -> dict:
        """
        Convert a 24-hour snapshot of engineered features into a short coaching tip.
        Returns {"urgency": str, "suggestion": str}.
        """
        calorie_line = (
            "No active nutrition plan."
            if snapshot_data.get("calories_target") is None
            else (
                f"Calories: {snapshot_data['calories_consumed']:.0f} consumed / "
                f"{snapshot_data['calories_target']} target "
                f"({snapshot_data.get('calorie_gap', 0):+.0f} kcal remaining)"
            )
        )
        protein_line = (
            ""
            if snapshot_data.get("protein_target") is None
            else (
                f"Protein: {snapshot_data['protein_consumed']:.1f}g consumed / "
                f"{snapshot_data['protein_target']}g target "
                f"({snapshot_data.get('protein_gap', 0):+.1f}g remaining)"
            )
        )
        meal_types = ", ".join(snapshot_data.get("meal_types_logged", [])) or "none"
        weight_note = (
            f"yes — {snapshot_data.get('latest_weight_kg')} kg"
            if snapshot_data.get("weight_logged")
            else "no"
        )

        user_prompt = f"""
User goal: {user_goal}

{user_profile_context}

## Last 24-Hour Snapshot (derived from raw logs via feature engineering)
{calorie_line}
{protein_line}
Meals logged today: {meal_types}
Workout sessions logged today: {snapshot_data.get("workout_sessions_logged", 0)}
Weight logged today: {weight_note}

Based ONLY on this snapshot, reply with a JSON object:
{{
  "urgency": "on_track" | "needs_attention" | "off_track",
  "suggestion": "One or two direct, actionable coaching sentences the user can act on RIGHT NOW."
}}

urgency rules:
- "on_track": calories within ±15% of target AND at least one workout or meal logged
- "off_track": calories >30% under/over OR no logs at all today
- "needs_attention": everything else
""".strip()

        system_prompt = (
            "You are a concise, no-nonsense personal fitness coach. "
            "Reply ONLY with the JSON object. No markdown fences. No extra text. "
            "Keep suggestion under 60 words. Be direct and specific."
        )

        raw = self.llm.call_llm(system_prompt, user_prompt, json_mode=True)
        result = self.llm.parse_json_response(raw)
        return {
            "urgency": result.get("urgency", "needs_attention"),
            "suggestion": result.get(
                "suggestion",
                "Keep logging your meals and workouts to get personalised coaching.",
            ),
        }

    def generate_progress_report(
        self,
        features_data: dict,
        user_profile_context: str,
    ) -> dict:
        """
        Convert a fully engineered ProgressFeatures dict into a structured coaching report.
        Returns {assessment, positives, improvements, suggestions, projection}.
        """
        n = features_data["nutrition"]
        w = features_data["workout"]
        wt = features_data["weight"]

        calorie_adherence = (
            f"{n['calorie_adherence_pct']:.1f}%"
            if n.get("calorie_adherence_pct") is not None
            else "N/A (no active plan)"
        )
        protein_adherence = (
            f"{n['protein_adherence_pct']:.1f}%"
            if n.get("protein_adherence_pct") is not None
            else "N/A (no active plan)"
        )
        freq_adherence = (
            f"{w['frequency_adherence_pct']:.1f}%"
            if w.get("frequency_adherence_pct") is not None
            else "N/A (no active plan)"
        )

        prog_lines = []
        for p in (w.get("exercise_progressions") or [])[:5]:
            prog_lines.append(
                f"  • {p['exercise_name']}: {p['sessions_logged']} sessions, "
                f"volume change {p['progression_pct']:+.1f}%"
            )
        progressions_block = (
            "\n".join(prog_lines)
            if prog_lines
            else "  • Not enough data for exercise progressions."
        )

        if wt["measurements_count"] == 0:
            weight_section = "No weight measurements in this period."
        elif wt.get("weight_change_kg") is not None:
            weight_section = (
                f"Measurements: {wt['measurements_count']} | "
                f"Change: {wt['weight_change_kg']:+.2f} kg | "
                f"Trend: {wt['trend_direction']} "
                f"({(wt.get('weight_trend_slope') or 0):+.4f} kg/day)"
            )
        else:
            weight_section = f"Measurements: {wt['measurements_count']}"

        user_prompt = f"""
## Client Progress Analysis — {features_data["period_label"]}
Period: {features_data["period_start"]} → {features_data["period_end"]} ({features_data["period_days"]} days)
Goal: {features_data["user_goal"]}
Overall consistency score: {features_data["overall_consistency_score"]:.0%}
On-track flag: {features_data["on_track"]}

{user_profile_context}

## ENGINEERED NUTRITION FEATURES
- Logging consistency: {n["days_with_logs"]} / {features_data["period_days"]} days ({n["logging_consistency_pct"]:.1f}%)
- Avg daily calories: {n["avg_daily_calories"]:.0f} kcal | Target: {n.get("target_daily_calories") or "N/A"} kcal | Adherence: {calorie_adherence}
- Avg daily protein: {n["avg_daily_protein_g"]:.1f}g | Target: {n.get("target_daily_protein_g") or "N/A"}g | Adherence: {protein_adherence}
- Avg daily carbs: {n["avg_daily_carbs_g"]:.1f}g | Avg daily fats: {n["avg_daily_fats_g"]:.1f}g
- Calorie trend slope: {n["calorie_trend_slope"]:+.2f} kcal/day (positive = increasing intake)
- Macro balance score: {n["macro_balance_score"]:.1f}/100

## ENGINEERED WORKOUT FEATURES
- Sessions: {w["total_sessions"]} actual | {w.get("planned_sessions") or "N/A"} planned | Adherence: {freq_adherence}
- Avg sets/session: {w["avg_sets_per_session"]:.1f} | Avg reps/session: {w["avg_reps_per_session"]:.1f}
- Total training volume: {w["total_volume_kg"]:.1f} kg (Σ sets×reps×weight)
- Volume trend slope: {w["volume_trend_slope"]:+.2f} kg/week (positive = progressive overload)
- Unique exercises: {w["unique_exercises_count"]}
- Exercise progressions:
{progressions_block}

## ENGINEERED WEIGHT FEATURES
{weight_section}

Respond with ONLY this JSON:
{{
  "assessment": "1-2 sentence overall verdict referencing actual numbers.",
  "positives": ["max 3 bullets — what is going well"],
  "improvements": ["max 3 bullets — what needs work"],
  "suggestions": ["max 3 specific, actionable next steps"],
  "projection": "1 quantified sentence: what the client should expect if the current trend continues.",
  "nutrition_plan_adjustment": {{
    "needed": true or false,
    "instructions": "Only if needed=true: exact, specific changes to make to the EXISTING nutrition plan (e.g. 'increase daily protein by ~20g via larger portions of existing protein sources; reduce breakfast calories by 150 kcal — user consistently over target on weekday breakfasts'). Empty string if needed=false."
  }},
  "workout_plan_adjustment": {{
    "needed": true or false,
    "instructions": "Only if needed=true: exact, specific changes to make to the EXISTING workout plan (e.g. 'reduce leg day to 2 exercises — adherence dropping only on leg day for 3 weeks; add a 4th set to bench press — user has plateaued for 2+ weeks at same volume'). Empty string if needed=false."
  }}
}}

RULES for the two *_plan_adjustment fields:
- Only set needed=true when the DATA justifies a plan change (e.g. adherence below 60% for 2+ weeks
  on a specific plan component, a clear plateau, or a target being consistently missed by a wide margin).
  Do NOT set needed=true for a single off week or minor noise — that's what "improvements"/"suggestions" are for.
- instructions must describe CONCRETE, ACTIONABLE changes to specific plan elements, not vague advice.
- If there isn't enough data yet (period_days < 7, or very few logs), default both to needed=false.
""".strip()

        system_prompt = (
            "You are an expert certified personal trainer and sports nutritionist. "
            "Analyse the engineered feature data and write a coaching progress report. "
            "You also decide — strictly from the data, not general advice — whether the "
            "user's actual active plan structure needs to change. "
            "Output ONLY the JSON object. No markdown fences. No extra text. "
            "Reference actual numbers. Be direct. Max 25 words per bullet."
        )

        raw = self.llm.call_llm(system_prompt, user_prompt, json_mode=True)
        result = self.llm.parse_json_response(raw)

        def _to_list(v, max_n: int = 3):
            if isinstance(v, list):
                return [str(x) for x in v[:max_n]]
            return [str(v)] if v else []

        def _to_adjustment(v) -> dict:
            if not isinstance(v, dict):
                return {"needed": False, "instructions": ""}
            needed = bool(v.get("needed", False))
            instructions = str(v.get("instructions", "") or "")
            return {
                "needed": needed and bool(instructions.strip()),
                "instructions": instructions,
            }

        return {
            "assessment": str(result.get("assessment", "")),
            "positives": _to_list(result.get("positives", [])),
            "improvements": _to_list(result.get("improvements", [])),
            "suggestions": _to_list(result.get("suggestions", [])),
            "projection": str(result.get("projection", "")),
            "nutrition_adjustment": _to_adjustment(
                result.get("nutrition_plan_adjustment")
            ),
            "workout_adjustment": _to_adjustment(result.get("workout_plan_adjustment")),
        }

    # ------------------------------------------------------------------
    # Private generation helpers
    # ------------------------------------------------------------------

    def _generate_nutrition_with_retries(
        self,
        system_prompt: str,
        user_profile: UserProfileDTO,
        preferences: NutritionPreferencesDTO,
        duration_weeks: int,
        medical_rules: str,
        existing_plan: Optional[NutritionPlanDTO],
        allowed_foods_str: str,
        planning_output: Optional["PlanningEngineOutput"],
        language: str,
        model_override: Optional[str],
        coach_feedback: str = "",
    ) -> NutritionPlanDTO:
        """
        Wraps the initial generation attempt: if the model returns malformed
        JSON or output that fails schema validation, regenerate instead of
        failing the request. Only applies to the initial (non-fix) pass —
        the post-judge fix pass already has its own fallback-to-original.
        """
        max_attempts = max(1, config.AI_MAX_GENERATION_RETRIES + 1)
        last_err: Optional[ValueError] = None
        for attempt in range(1, max_attempts + 1):
            try:
                return self._generate_nutrition_once(
                    system_prompt,
                    user_profile,
                    preferences,
                    duration_weeks,
                    medical_rules,
                    existing_plan,
                    allowed_foods_str,
                    planning_output,
                    coach_feedback=coach_feedback,
                    language=language,
                    model_override=model_override,
                )
            except ValueError as err:
                last_err = err
                logger.warning(
                    "Nutrition — generation attempt %d/%d failed schema/JSON validation, regenerating: %s",
                    attempt,
                    max_attempts,
                    err,
                )
        raise last_err

    def _generate_workout_with_retries(
        self,
        system_prompt: str,
        user_profile: UserProfileDTO,
        preferences: WorkoutPreferencesDTO,
        duration_weeks: int,
        medical_rules: str,
        existing_plan: Optional[WorkoutPlanDTO],
        allowed_exercises_str: str,
        planning_output: Optional["PlanningEngineOutput"],
        language: str,
        model_override: Optional[str],
        coach_feedback: str = "",
    ) -> WorkoutPlanDTO:
        """Same retry wrapper as nutrition, for the workout generation path."""
        max_attempts = max(1, config.AI_MAX_GENERATION_RETRIES + 1)
        last_err: Optional[ValueError] = None
        for attempt in range(1, max_attempts + 1):
            try:
                return self._generate_workout_once(
                    system_prompt,
                    user_profile,
                    preferences,
                    duration_weeks,
                    medical_rules,
                    existing_plan,
                    allowed_exercises_str,
                    planning_output,
                    coach_feedback=coach_feedback,
                    language=language,
                    model_override=model_override,
                )
            except ValueError as err:
                last_err = err
                logger.warning(
                    "Workout — generation attempt %d/%d failed schema/JSON validation, regenerating: %s",
                    attempt,
                    max_attempts,
                    err,
                )
        raise last_err

    def _generate_nutrition_once(
        self,
        system_prompt: str,
        user_profile: UserProfileDTO,
        preferences: NutritionPreferencesDTO,
        duration_weeks: int,
        medical_rules: str,
        existing_plan: Optional[NutritionPlanDTO],
        allowed_foods_str: str,
        planning_output: Optional["PlanningEngineOutput"],
        judge_feedback: str = "",
        coach_feedback: str = "",
        language: str = "en",
        model_override: Optional[str] = None,
    ) -> Optional[NutritionPlanDTO]:
        """Single generation attempt. Returns None on parse/validation failure during fix-pass."""
        is_fix_pass = bool(judge_feedback)

        user_prompt = prompt_builder.build_nutrition_prompt(
            user_profile,
            preferences,
            duration_weeks,
            medical_rules,
            existing_plan,
            allowed_foods_str,
            planning_output=planning_output,
            judge_feedback=judge_feedback,
            coach_feedback=coach_feedback,
            lang=language,
        )

        response = self.llm.call_llm(system_prompt, user_prompt, model=model_override)
        logger.info("Nutrition LLM output (first 3000 chars): %s", response[:3000])

        try:
            plan_data = self.llm.parse_json_response(response)
        except ValueError as err:
            if is_fix_pass:
                logger.warning(
                    "Fix-pass nutrition plan not valid JSON — keeping original. %s", err
                )
                return None
            raise ValueError(
                "Nutrition plan generation failed: model output was not valid JSON. "
                f"Raw output preview: {response[:1500]!r}"
            ) from err

        try:
            return plan_validator.validate_nutrition_plan(plan_data)
        except ValueError as err:
            if is_fix_pass:
                logger.warning(
                    "Fix-pass nutrition plan failed schema validation — keeping original. %s",
                    err,
                )
                return None
            raise

    def _generate_workout_once(
        self,
        system_prompt: str,
        user_profile: UserProfileDTO,
        preferences: WorkoutPreferencesDTO,
        duration_weeks: int,
        medical_rules: str,
        existing_plan: Optional[WorkoutPlanDTO],
        allowed_exercises_str: str,
        planning_output: Optional["PlanningEngineOutput"],
        judge_feedback: str = "",
        coach_feedback: str = "",
        language: str = "en",
        model_override: Optional[str] = None,
    ) -> Optional[WorkoutPlanDTO]:
        """Single generation attempt. Returns None on parse/validation failure during fix-pass."""
        is_fix_pass = bool(judge_feedback)

        user_prompt = prompt_builder.build_workout_prompt(
            user_profile,
            preferences,
            duration_weeks,
            medical_rules,
            existing_plan,
            allowed_exercises_str,
            planning_output=planning_output,
            judge_feedback=judge_feedback,
            coach_feedback=coach_feedback,
            lang=language,
        )

        response = self.llm.call_llm(system_prompt, user_prompt, model=model_override)
        logger.info("Workout LLM output (first 3000 chars): %s", response[:3000])

        try:
            plan_data = self.llm.parse_json_response(response)
        except ValueError as err:
            if is_fix_pass:
                logger.warning(
                    "Fix-pass workout plan not valid JSON — keeping original. %s", err
                )
                return None
            raise ValueError(
                "Workout plan generation failed: model output was not valid JSON. "
                f"Raw output preview: {response[:1500]!r}"
            ) from err

        try:
            return plan_validator.validate_workout_plan(plan_data)
        except ValueError as err:
            if is_fix_pass:
                logger.warning(
                    "Fix-pass workout plan failed schema validation — keeping original. %s",
                    err,
                )
                return None
            raise


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------

_ai_coach_service: Optional[AICoachService] = None
_ai_coach_service_lock = threading.Lock()


def get_ai_coach_service() -> AICoachService:
    global _ai_coach_service
    if _ai_coach_service is None:
        with _ai_coach_service_lock:
            if _ai_coach_service is None:
                _ai_coach_service = AICoachService()
    return _ai_coach_service
