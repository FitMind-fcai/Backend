import logging
from typing import Optional, TYPE_CHECKING

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
        self.llm   = LLMClient(provider=provider, api_key=api_key, base_url=base_url, model=model)
        self.judge = PlanJudge(self.llm)

        logger.info(
            "AI Coach initialised — provider=%s model=%s judge_model=%s",
            self.llm.provider, self.llm.model, self.llm.judge_model,
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
    ) -> NutritionPlanDTO:
        """
        Generate a personalised 7-day nutrition plan.

        Workflow: Generate → Judge → Fix once (if failed) → Allergy gate → Return

        medical_rules is a pre-built, KB-grounded rule block from ContextBuilder
        (runs in a parallel thread in plan_generation_service).  It replaces both
        the inline Channel C medical block and the general RAG Channel A.
        """
        target_calories = calculate_target_calories(user_profile, preferences.custom_calorie_target)
        macros          = calculate_macro_guidance(user_profile, target_calories)
        logger.info(
            "Portion-sizing guidance — calories=%d protein=%dg fat=%dg carbs=%dg",
            target_calories, macros["protein_g"], macros["fat_g"], macros["carb_g"],
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
            "Any allergy violation is a critical failure."
        )

        # ── Generate ──────────────────────────────────────────────────
        logger.info("Nutrition — generating plan (model_override=%s, skip_judge=%s)", model_override, skip_judge)
        plan = self._generate_nutrition_once(
            system_prompt, user_profile, preferences, duration_weeks,
            medical_rules, existing_plan, allowed_foods_str, planning_output,
            language=language,
            model_override=model_override,
        )

        # ── Judge once → Fix once if failed ──────────────────────────
        if skip_judge:
            logger.info("Nutrition — judge skipped (skip_judge=True)")
        else:
            passed, feedback = self.judge.judge_nutrition_plan(plan, user_profile, preferences, planning_output)
            if passed:
                logger.info("Nutrition — judge passed on first try")
            elif not feedback:
                logger.info("Nutrition — judge failed but gave no feedback; skipping fix pass")
            else:
                logger.info("Nutrition — judge failed, applying one-time fix pass")
                fixed = self._generate_nutrition_once(
                    system_prompt, user_profile, preferences, duration_weeks,
                    medical_rules, existing_plan, allowed_foods_str, planning_output,
                    judge_feedback=feedback,
                    language=language,
                    model_override=model_override,
                )
                if fixed is not None:
                    plan = fixed
                else:
                    logger.warning("Nutrition — fix pass produced invalid output; keeping original plan")

        # ── Allergy safety gate (last-resort deterministic check) ─────
        plan_validator.validate_nutrition_semantics(plan, user_profile)

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
    ) -> WorkoutPlanDTO:
        """
        Generate a personalised workout plan.

        Workflow: Generate → Judge → Fix once (if failed) → Return

        medical_rules is a pre-built, KB-grounded rule block from ContextBuilder.
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
            "Never suggest exercises that could harm the user."
        )

        # ── Generate ──────────────────────────────────────────────────
        logger.info("Workout — generating plan (model_override=%s, skip_judge=%s)", model_override, skip_judge)
        plan = self._generate_workout_once(
            system_prompt, user_profile, preferences, duration_weeks,
            medical_rules, existing_plan, allowed_exercises_str, planning_output,
            language=language,
            model_override=model_override,
        )

        # ── Judge once → Fix once if failed ──────────────────────────
        if skip_judge:
            logger.info("Workout — judge skipped (skip_judge=True)")
        else:
            passed, feedback = self.judge.judge_workout_plan(plan, user_profile, preferences, planning_output)
            if passed:
                logger.info("Workout — judge passed on first try")
            elif not feedback:
                logger.info("Workout — judge failed but gave no feedback; skipping fix pass")
            else:
                logger.info("Workout — judge failed, applying one-time fix pass")
                fixed = self._generate_workout_once(
                    system_prompt, user_profile, preferences, duration_weeks,
                    medical_rules, existing_plan, allowed_exercises_str, planning_output,
                    judge_feedback=feedback,
                    language=language,
                    model_override=model_override,
                )
                if fixed is not None:
                    plan = fixed
                else:
                    logger.warning("Workout — fix pass produced invalid output; keeping original plan")

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
Workout sessions logged today: {snapshot_data.get('workout_sessions_logged', 0)}
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
        n  = features_data["nutrition"]
        w  = features_data["workout"]
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
            "\n".join(prog_lines) if prog_lines
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
## Client Progress Analysis — {features_data['period_label']}
Period: {features_data['period_start']} → {features_data['period_end']} ({features_data['period_days']} days)
Goal: {features_data['user_goal']}
Overall consistency score: {features_data['overall_consistency_score']:.0%}
On-track flag: {features_data['on_track']}

{user_profile_context}

## ENGINEERED NUTRITION FEATURES
- Logging consistency: {n['days_with_logs']} / {features_data['period_days']} days ({n['logging_consistency_pct']:.1f}%)
- Avg daily calories: {n['avg_daily_calories']:.0f} kcal | Target: {n.get('target_daily_calories') or 'N/A'} kcal | Adherence: {calorie_adherence}
- Avg daily protein: {n['avg_daily_protein_g']:.1f}g | Target: {n.get('target_daily_protein_g') or 'N/A'}g | Adherence: {protein_adherence}
- Avg daily carbs: {n['avg_daily_carbs_g']:.1f}g | Avg daily fats: {n['avg_daily_fats_g']:.1f}g
- Calorie trend slope: {n['calorie_trend_slope']:+.2f} kcal/day (positive = increasing intake)
- Macro balance score: {n['macro_balance_score']:.1f}/100

## ENGINEERED WORKOUT FEATURES
- Sessions: {w['total_sessions']} actual | {w.get('planned_sessions') or 'N/A'} planned | Adherence: {freq_adherence}
- Avg sets/session: {w['avg_sets_per_session']:.1f} | Avg reps/session: {w['avg_reps_per_session']:.1f}
- Total training volume: {w['total_volume_kg']:.1f} kg (Σ sets×reps×weight)
- Volume trend slope: {w['volume_trend_slope']:+.2f} kg/week (positive = progressive overload)
- Unique exercises: {w['unique_exercises_count']}
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
  "projection": "1 quantified sentence: what the client should expect if the current trend continues."
}}
""".strip()

        system_prompt = (
            "You are an expert certified personal trainer and sports nutritionist. "
            "Analyse the engineered feature data and write a coaching progress report. "
            "Output ONLY the JSON object. No markdown fences. No extra text. "
            "Reference actual numbers. Be direct. Max 25 words per bullet."
        )

        raw = self.llm.call_llm(system_prompt, user_prompt, json_mode=True)
        result = self.llm.parse_json_response(raw)

        def _to_list(v, max_n: int = 3):
            if isinstance(v, list):
                return [str(x) for x in v[:max_n]]
            return [str(v)] if v else []

        return {
            "assessment":   str(result.get("assessment", "")),
            "positives":    _to_list(result.get("positives", [])),
            "improvements": _to_list(result.get("improvements", [])),
            "suggestions":  _to_list(result.get("suggestions", [])),
            "projection":   str(result.get("projection", "")),
        }

    def ask_coach(
        self,
        question: str,
        user_profile: Optional[UserProfileDTO] = None,
        language: str = "auto",
    ) -> str:
        """Answer a free-text fitness or nutrition question with RAG-augmented coaching advice."""
        tags = ""
        if user_profile:
            tags = " ".join(filter(None, [
                user_profile.injuries           and f"injuries:{user_profile.injuries}",
                user_profile.medical_conditions and f"condition:{user_profile.medical_conditions}",
                user_profile.allergies          and f"allergies:{user_profile.allergies}",
                user_profile.fitness_goal       and f"goal:{user_profile.fitness_goal}",
            ]))

        query       = f"{question} {tags}".strip()
        rag_context = self.vector_db.get_context(query, k=min(self.rag_top_k, 3))
        rag_context = self.llm.trim_rag_context(rag_context, "ask_coach")

        user_context = (
            user_profile.to_context_string() if user_profile
            else "No user profile available — give general evidence-based advice."
        )

        language_instruction = {
            "auto": "Respond in the SAME LANGUAGE as the user's question.",
            "ar":   "Respond in Arabic (Egyptian dialect preferred).",
        }.get(language, "Respond in English.")

        system_prompt = (
            f"You are an experienced personal fitness coach with deep knowledge in exercise science and nutrition.\n\n"
            f"{language_instruction}\n\n"
            f"{user_context}\n\n"
            "YOUR COACHING STYLE:\n"
            "• Speak as a coach — direct, practical, encouraging.\n"
            '• Never say "according to the handbook/guide/source" — give advice from YOUR expertise.\n'
            "• Always account for the user's medical conditions, injuries, and medications.\n"
            "• Give specific rep ranges, exercise names, food quantities, and timing — not vague guidance.\n"
            "• Flag any safety concern before giving the main advice.\n"
            "• End with one clear action the user can take TODAY."
        )

        user_prompt = (
            f"Supporting fitness & nutrition knowledge:\n{rag_context}\n\n"
            f"User question: {question}\n\n"
            "Give your professional coaching advice. Be specific and practical.\n"
            "When you reference a specific study or guideline, cite it inline as [SOURCE: title]."
        )

        return self.llm.call_llm(system_prompt, user_prompt, json_mode=False)

    # ------------------------------------------------------------------
    # Private generation helpers
    # ------------------------------------------------------------------

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
        language: str = "en",
        model_override: Optional[str] = None,
    ) -> Optional[NutritionPlanDTO]:
        """Single generation attempt. Returns None on parse/validation failure during fix-pass."""
        is_fix_pass = bool(judge_feedback)

        user_prompt = prompt_builder.build_nutrition_prompt(
            user_profile, preferences, duration_weeks,
            medical_rules, existing_plan, allowed_foods_str,
            planning_output=planning_output,
            judge_feedback=judge_feedback,
            lang=language,
        )

        response = self.llm.call_llm(system_prompt, user_prompt, model=model_override)
        logger.info("Nutrition LLM output (first 3000 chars): %s", response[:3000])

        try:
            plan_data = self.llm.parse_json_response(response)
        except ValueError as err:
            if is_fix_pass:
                logger.warning("Fix-pass nutrition plan not valid JSON — keeping original. %s", err)
                return None
            raise ValueError(
                "Nutrition plan generation failed: model output was not valid JSON. "
                f"Raw output preview: {response[:1500]!r}"
            ) from err

        try:
            return plan_validator.validate_nutrition_plan(plan_data)
        except ValueError as err:
            if is_fix_pass:
                logger.warning("Fix-pass nutrition plan failed schema validation — keeping original. %s", err)
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
        language: str = "en",
        model_override: Optional[str] = None,
    ) -> Optional[WorkoutPlanDTO]:
        """Single generation attempt. Returns None on parse/validation failure during fix-pass."""
        is_fix_pass = bool(judge_feedback)

        user_prompt = prompt_builder.build_workout_prompt(
            user_profile, preferences, duration_weeks,
            medical_rules, existing_plan, allowed_exercises_str,
            planning_output=planning_output,
            judge_feedback=judge_feedback,
            lang=language,
        )

        response = self.llm.call_llm(system_prompt, user_prompt, model=model_override)
        logger.info("Workout LLM output (first 3000 chars): %s", response[:3000])

        try:
            plan_data = self.llm.parse_json_response(response)
        except ValueError as err:
            if is_fix_pass:
                logger.warning("Fix-pass workout plan not valid JSON — keeping original. %s", err)
                return None
            raise ValueError(
                "Workout plan generation failed: model output was not valid JSON. "
                f"Raw output preview: {response[:1500]!r}"
            ) from err

        try:
            return plan_validator.validate_workout_plan(plan_data)
        except ValueError as err:
            if is_fix_pass:
                logger.warning("Fix-pass workout plan failed schema validation — keeping original. %s", err)
                return None
            raise



# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------

_ai_coach_service: Optional[AICoachService] = None


def get_ai_coach_service() -> AICoachService:
    global _ai_coach_service
    if _ai_coach_service is None:
        _ai_coach_service = AICoachService()
    return _ai_coach_service
