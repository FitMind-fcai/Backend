import logging
import os
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
from app.ai_services.ai_coach.vector_db_service import VectorDBService, get_vector_db_service

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
        vector_db_service: Optional[VectorDBService] = None,
    ):
        self.llm    = LLMClient(provider=provider, api_key=api_key, base_url=base_url, model=model)
        self.judge  = PlanJudge(self.llm)
        self.vector_db = vector_db_service or get_vector_db_service()

        self.rag_top_k = int(os.getenv("AI_RAG_TOP_K", "3"))
        # Max judge-fix iterations after the initial generation.
        # 2 means: generate → judge → fix → judge → fix → judge → done (3 generations, 3 judge calls max).
        self.max_judge_iterations = int(os.getenv("AI_JUDGE_MAX_ITERATIONS", "2"))

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
    ) -> NutritionPlanDTO:
        """
        Generate a personalised 7-day nutrition plan.

        Workflow: Generate → Judge → Fix (if failed) → Allergy gate → Return

        The AI uses portion-sizing guidance (TDEE-based calorie + macro targets) to
        decide ingredient amounts. It does NOT write macro/calorie numbers into JSON;
        the backend recomputes those from exact CentralFood DB records.
        """
        target_calories = calculate_target_calories(user_profile, preferences.custom_calorie_target)
        macros          = calculate_macro_guidance(user_profile, target_calories)
        logger.info(
            "Portion-sizing guidance — calories=%d protein=%dg fat=%dg carbs=%dg",
            target_calories, macros["protein_g"], macros["fat_g"], macros["carb_g"],
        )

        rag_context = self._fetch_nutrition_rag(user_profile, preferences)

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

        # ── Generate → Judge → Fix loop ──────────────────────────────
        # Initial generation (no feedback yet).
        logger.info("Nutrition — iteration 0: generating plan")
        plan = self._generate_nutrition_once(
            system_prompt, user_profile, preferences, duration_weeks,
            rag_context, existing_plan, allowed_foods_str, planning_output,
        )

        # Up to max_judge_iterations judge-fix cycles.
        # Each iteration judges the *current* plan so the feedback always reflects
        # whatever issues remain — no stale or already-resolved complaints.
        for iteration in range(1, self.max_judge_iterations + 1):
            passed, feedback = self.judge.judge_nutrition_plan(plan, user_profile, preferences)
            if passed:
                logger.info("Nutrition — judge passed on iteration %d", iteration)
                break
            if not feedback:
                logger.info("Nutrition — judge failed but gave no feedback; stopping loop")
                break
            logger.info("Nutrition — iteration %d: judge failed, regenerating with feedback", iteration)
            fixed = self._generate_nutrition_once(
                system_prompt, user_profile, preferences, duration_weeks,
                rag_context, existing_plan, allowed_foods_str, planning_output,
                judge_feedback=feedback,
            )
            if fixed is not None:
                plan = fixed
            else:
                logger.warning("Nutrition — fix-pass iteration %d produced invalid output; keeping current plan", iteration)
                break
        else:
            # Loop exhausted — judge the final plan once more just for logging.
            passed, _ = self.judge.judge_nutrition_plan(plan, user_profile, preferences)
            logger.info("Nutrition — max iterations reached, final judge passed=%s", passed)

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
    ) -> WorkoutPlanDTO:
        """
        Generate a personalised workout plan.

        Workflow: Generate → Judge → Fix (if failed) → Return
        """
        rag_context = self._fetch_workout_rag(user_profile, preferences)

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

        # ── Generate → Judge → Fix loop ──────────────────────────────
        logger.info("Workout — iteration 0: generating plan")
        plan = self._generate_workout_once(
            system_prompt, user_profile, preferences, duration_weeks,
            rag_context, existing_plan, allowed_exercises_str, planning_output,
        )

        for iteration in range(1, self.max_judge_iterations + 1):
            passed, feedback = self.judge.judge_workout_plan(plan, user_profile, preferences)
            if passed:
                logger.info("Workout — judge passed on iteration %d", iteration)
                break
            if not feedback:
                logger.info("Workout — judge failed but gave no feedback; stopping loop")
                break
            logger.info("Workout — iteration %d: judge failed, regenerating with feedback", iteration)
            fixed = self._generate_workout_once(
                system_prompt, user_profile, preferences, duration_weeks,
                rag_context, existing_plan, allowed_exercises_str, planning_output,
                judge_feedback=feedback,
            )
            if fixed is not None:
                plan = fixed
            else:
                logger.warning("Workout — fix-pass iteration %d produced invalid output; keeping current plan", iteration)
                break
        else:
            passed, _ = self.judge.judge_workout_plan(plan, user_profile, preferences)
            logger.info("Workout — max iterations reached, final judge passed=%s", passed)

        return plan

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
        rag_context: str,
        existing_plan: Optional[NutritionPlanDTO],
        allowed_foods_str: str,
        planning_output: Optional["PlanningEngineOutput"],
        judge_feedback: str = "",
    ) -> Optional[NutritionPlanDTO]:
        """Single generation attempt. Returns None on parse/validation failure during fix-pass."""
        is_fix_pass = bool(judge_feedback)

        user_prompt = prompt_builder.build_nutrition_prompt(
            user_profile, preferences, duration_weeks,
            rag_context, existing_plan, allowed_foods_str,
            planning_output=planning_output,
            judge_feedback=judge_feedback,
        )

        response = self.llm.call_llm(system_prompt, user_prompt)
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
        rag_context: str,
        existing_plan: Optional[WorkoutPlanDTO],
        allowed_exercises_str: str,
        planning_output: Optional["PlanningEngineOutput"],
        judge_feedback: str = "",
    ) -> Optional[WorkoutPlanDTO]:
        """Single generation attempt. Returns None on parse/validation failure during fix-pass."""
        is_fix_pass = bool(judge_feedback)

        user_prompt = prompt_builder.build_workout_prompt(
            user_profile, preferences, duration_weeks,
            rag_context, existing_plan, allowed_exercises_str,
            planning_output=planning_output,
            judge_feedback=judge_feedback,
        )

        response = self.llm.call_llm(system_prompt, user_prompt)
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

    # ------------------------------------------------------------------
    # RAG helpers
    # ------------------------------------------------------------------

    def _fetch_nutrition_rag(
        self,
        user_profile: UserProfileDTO,
        preferences: NutritionPreferencesDTO,
    ) -> str:
        profile_tags = " ".join(filter(None, [
            user_profile.allergies          and f"allergies:{user_profile.allergies}",
            user_profile.medical_conditions and f"condition:{user_profile.medical_conditions}",
            user_profile.fitness_goal       and f"goal:{user_profile.fitness_goal}",
        ]))
        query = (
            f"nutrition meal plan {preferences.cuisine_preference} "
            f"{preferences.calorie_preference} {profile_tags}"
        )
        logger.info("Nutrition RAG query: %s", query)
        raw = self.vector_db.get_context(query, k=self.rag_top_k, domain="nutrition")
        return self.llm.trim_rag_context(raw, "nutrition")

    def _fetch_workout_rag(
        self,
        user_profile: UserProfileDTO,
        preferences: WorkoutPreferencesDTO,
    ) -> str:
        profile_tags = " ".join(filter(None, [
            user_profile.injuries           and f"injuries:{user_profile.injuries}",
            user_profile.medical_conditions and f"condition:{user_profile.medical_conditions}",
            user_profile.fitness_goal       and f"goal:{user_profile.fitness_goal}",
        ]))
        query = (
            f"workout plan {preferences.workout_focus} {preferences.workout_difficulty} "
            f"{preferences.workout_location} {profile_tags}"
        )
        logger.info("Workout RAG query: %s", query)
        raw = self.vector_db.get_context(query, k=self.rag_top_k, domain="workout")
        return self.llm.trim_rag_context(raw, "workout")


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------

_ai_coach_service: Optional[AICoachService] = None


def get_ai_coach_service() -> AICoachService:
    global _ai_coach_service
    if _ai_coach_service is None:
        _ai_coach_service = AICoachService()
    return _ai_coach_service
