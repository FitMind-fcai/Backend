import os
import json
import logging
import re
from typing import Optional, Dict, Any
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

# Configure logger
logger = logging.getLogger(__name__)


class AICoachService:    
    # LLM Configuration
    DEFAULT_PROVIDER = "groq"
    DEFAULT_MODEL = "openai/gpt-oss-120b"
    DEFAULT_TEMPERATURE = 0.0
    DEFAULT_MAX_TOKENS = 6000

    PROVIDER_BASE_URLS = {
        "groq": "https://api.groq.com/openai/v1",
        "openrouter": "https://openrouter.ai/api/v1",
        "openai": "https://api.openai.com/v1",
        "together": "https://api.together.xyz/v1",
        "deepinfra": "https://api.deepinfra.com/v1/openai",
        "fireworks": "https://api.fireworks.ai/inference/v1",
    }
    
    def __init__(
        self,
        provider: Optional[str] = None,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        model: Optional[str] = None,
        vector_db_service: Optional[VectorDBService] = None
    ):
        """
        Initialize the AI Coach Service.
        
        Args:
            provider: LLM provider (groq/openrouter/openai/together/deepinfra/fireworks)
            api_key: LLM API key (falls back to env based on selected provider)
            base_url: Optional custom OpenAI-compatible endpoint URL
            model: LLM model to use
            vector_db_service: Optional VectorDBService instance
        """
        self.provider = (provider or os.getenv("AI_PROVIDER") or config.AI_PROVIDER or self.DEFAULT_PROVIDER).lower()

        self.api_key = (
            api_key
            or os.getenv("AI_API_KEY")
            or config.AI_API_KEY
            or self._get_provider_api_key(self.provider)
        )
        if not self.api_key:
            raise ValueError(
                f"No API key found for provider '{self.provider}'. "
                "Set AI_API_KEY or provider-specific key in environment, or pass api_key parameter."
            )

        self.base_url = (
            base_url
            or os.getenv("AI_BASE_URL")
            or config.AI_BASE_URL
            or self.PROVIDER_BASE_URLS.get(self.provider)
        )
        if not self.base_url:
            raise ValueError(
                f"No base URL configured for provider '{self.provider}'. "
                "Set AI_BASE_URL or use a supported provider."
            )

        self.model = model or os.getenv("AI_MODEL") or config.AI_MODEL or self.DEFAULT_MODEL
        self.temperature = float(
            os.getenv("AI_COACH_TEMPERATURE") or str(config.AI_COACH_TEMPERATURE or self.DEFAULT_TEMPERATURE)
        )
        self.max_tokens = int(
            os.getenv("AI_COACH_MAX_TOKENS") or str(config.AI_COACH_MAX_TOKENS or self.DEFAULT_MAX_TOKENS)
        )
        self.rag_top_k = int(os.getenv("AI_RAG_TOP_K", "3"))
        self.rag_max_context_chars = int(os.getenv("AI_RAG_MAX_CONTEXT_CHARS", "1800"))
        self.client = OpenAI(
            api_key=self.api_key,
            base_url=self.base_url,
            default_headers=self._build_provider_headers(self.provider),
        )
        self.vector_db = vector_db_service or get_vector_db_service()

        logger.info(
            "AI Coach initialized with provider=%s model=%s base_url=%s max_tokens=%s",
            self.provider,
            self.model,
            self.base_url,
            self.max_tokens,
        )

    def _trim_rag_context(self, rag_context: str, context_name: str) -> str:
        """Trim long RAG context to keep total prompt size under control."""
        context = rag_context or ""
        
        # Log the full retrieved context (or a preview if desired)
        logger.info(f"📚 Full retrieved {context_name} context:\n{context}\n{'-'*50}")

        if len(context) <= self.rag_max_context_chars:
            return context

        trimmed = context[:self.rag_max_context_chars].rstrip()
        logger.info(
            "✂️ Trimmed %s context from %s to %s chars",
            context_name,
            len(context),
            len(trimmed),
        )
        return trimmed

    def _get_provider_api_key(self, provider: str) -> str:
        """Resolve provider-specific API key fallback."""
        if provider == "groq":
            return os.getenv("GROQ_API_KEY") or config.GROQ_API_KEY
        if provider == "openrouter":
            return os.getenv("OPENROUTER_API_KEY") or config.OPENROUTER_API_KEY
        if provider == "openai":
            return os.getenv("OPENAI_API_KEY") or config.OPENAI_API_KEY
        if provider == "together":
            return os.getenv("TOGETHER_API_KEY") or config.TOGETHER_API_KEY
        if provider == "deepinfra":
            return os.getenv("DEEPINFRA_API_KEY") or config.DEEPINFRA_API_KEY
        if provider == "fireworks":
            return os.getenv("FIREWORKS_API_KEY") or config.FIREWORKS_API_KEY
        return ""

    def _build_provider_headers(self, provider: str) -> Optional[Dict[str, str]]:
        """Build optional provider-specific headers."""
        if provider != "openrouter":
            return None

        headers: Dict[str, str] = {}
        site_url = os.getenv("OPENROUTER_SITE_URL") or config.OPENROUTER_SITE_URL
        app_name = os.getenv("OPENROUTER_APP_NAME") or config.OPENROUTER_APP_NAME

        if site_url:
            headers["HTTP-Referer"] = site_url
        if app_name:
            headers["X-Title"] = app_name

        return headers or None
    
    def _build_workout_prompt(
        self,
        user_profile: UserProfileDTO,
        preferences: WorkoutPreferencesDTO,
        duration_weeks: int,
        rag_context: str,
        existing_plan: Optional[WorkoutPlanDTO] = None
    ) -> str:
        """Build the prompt for workout plan generation."""
        user_context = user_profile.to_context_string()
        prefs_context = preferences.to_context_string()
        
        existing_plan_context = ""
        regeneration_instruction = ""
        if existing_plan:
            existing_plan_context = f"""\n\nEXISTING WORKOUT PLAN TO UPDATE:
{existing_plan.to_context_string()}
"""
            regeneration_instruction = """\n\nREGENERATION MODE IF YOU HAVE AN EXISTING PLAN ONLY:
- The user has an EXISTING plan and wants to UPDATE it based on NEW preferences
- KEEP everything that still matches the new preferences
- ONLY MODIFY parts that conflict with or don't align with the new preferences
- Maintain progression and familiarity where appropriate
- If the new preferences are very similar, make minimal changes
"""
        
        return f"""You are an expert fitness coach creating a personalized workout plan.

{user_context}
{prefs_context}{existing_plan_context}

PLAN DURATION: {duration_weeks} week(s)

REFERENCE FITNESS KNOWLEDGE:
{rag_context}{regeneration_instruction}

IMPORTANT INSTRUCTIONS:
1. Consider the user's medical conditions, injuries, and limitations
2. Provide safe alternatives for exercises that might be problematic
3. Match the difficulty level to the user's fitness goal and activity level
4. Include proper warm-up and cool-down recommendations
5. Ensure exercises are appropriate for the available equipment and location

Generate a complete {preferences.workout_days_per_week}-day workout plan in the following JSON format:
{{
    "plan_name": "Descriptive plan name",
    "description": "Brief description of the plan and its goals",
    "frequency": "{preferences.workout_days_per_week} days per week",
    "difficulty_level": "{preferences.workout_difficulty}",
    "estimated_duration_per_session": {preferences.session_duration_minutes},
    "workout_days": [
        {{
            "day_name": "Day 1 - Focus Area",
            "day_number": 1,
            "focus_area": "e.g., Upper Body",
            "estimated_duration": {preferences.session_duration_minutes},
            "notes": "Any special instructions for this day",
            "exercises": [
                {{
                    "exercise_name": "Exercise Name",
                    "exercise_type": "Strength/Cardio/Flexibility",
                    "sets": 3,
                    "reps": 12,
                    "weight_kg": null,
                    "duration_seconds": null,
                    "rest_seconds": 60,
                    "instructions": "How to perform the exercise safely",
                    "order_index": 0
                }}
            ]
        }}
    ]
}}

CRITICAL: Return ONLY valid JSON, no additional text or markdown formatting."""
    
    def _build_nutrition_prompt(
        self,
        user_profile: UserProfileDTO,
        preferences: NutritionPreferencesDTO,
        duration_weeks: int,
        rag_context: str,
        existing_plan: Optional[NutritionPlanDTO] = None,
        allowed_foods_str: str = ""
    ) -> str:
        """Build the prompt for nutrition plan generation."""
        user_context = user_profile.to_context_string()
        prefs_context = preferences.to_context_string()
        
        # Calculate estimated daily calories based on profile
        base_calories = 2000
        if user_profile.fitness_goal == 'Lose Weight':
            calorie_adjustment = -300
        elif user_profile.fitness_goal == 'Build Muscle':
            calorie_adjustment = 300
        else:
            calorie_adjustment = 0
        
        target_calories = preferences.custom_calorie_target or (base_calories + calorie_adjustment)
        
        existing_plan_context = ""
        regeneration_instruction = ""
        if existing_plan:
            existing_plan_context = f"""\n\nEXISTING NUTRITION PLAN TO UPDATE:
{existing_plan.to_context_string()}
"""
            regeneration_instruction = """\n\nREGENERATION MODE IF YOU HAVE AN EXISTING PLAN ONLY:
- The user has an EXISTING meal plan and wants to UPDATE it based on NEW preferences
- KEEP meals that still match the new dietary preferences and restrictions
- ONLY MODIFY meals that conflict with new preferences (allergies, cuisine, restrictions)
- If calorie target changed slightly, adjust portions rather than replacing entire meals
- If the new preferences are very similar, make minimal changes
"""
        
        return f"""You are an expert nutritionist creating a personalized 7-day meal plan.

{user_context}
{prefs_context}{existing_plan_context}

PLAN DURATION: {duration_weeks} week(s)
TARGET DAILY CALORIES: {target_calories}

{allowed_foods_str}

REFERENCE NUTRITION KNOWLEDGE:
{rag_context}{regeneration_instruction}

IMPORTANT INSTRUCTIONS:
1. Generate a FULL 7-day plan (Monday through Sunday)
2. Each day must have exactly {preferences.meals_per_day} meals
3. Vary the meals across days — do not repeat the same meal every day
4. Consider the user\'s dietary preferences and allergies
5. Exclude any ingredients the user wants to avoid
6. Match meal complexity to the user\'s preference
7. Ensure meals align with the user\'s fitness goals
8. Balance macronutrients appropriately for the fitness goal

Generate a complete 7-day meal plan in the following JSON format:
{{
    "plan_name": "Descriptive plan name",
    "description": "Brief description of the nutrition plan",
    "daily_calories": {target_calories},
    "daily_protein_g": calculated_protein,
    "daily_carbs_g": calculated_carbs,
    "daily_fats_g": calculated_fats,
    "days": [
        {{
            "day_name": "Monday",
            "day_number": 1,
            "notes": "Optional note (e.g., high-carb day, rest day)",
            "meals": [
                {{
                    "meal_type": "Breakfast",
                    "meal_name": "Meal Name",
                    "calories": meal_calories,
                    "protein_g": protein_amount,
                    "carbs_g": carbs_amount,
                    "fats_g": fats_amount,
                    "ingredients": [
                        {{
                            "central_food_id": 123,
                            "amount_g": 100.5
                        }}
                    ],
                    "instructions": "Step by step cooking instructions",
                    "prep_time_minutes": 10,
                    "cook_time_minutes": 20,
                    "servings": 1,
                    "order_index": 0
                }}
            ]
        }},
        ... (repeat for Tuesday through Sunday)
    ]
}}

CRITICAL: Return ONLY valid JSON, no additional text or markdown formatting."""
    
    def _call_llm(self, system_prompt: str, user_prompt: str, json_mode: bool = True) -> str:
        """
        Call the LLM with the given prompts.
        
        Args:
            system_prompt: System instruction for the LLM
            user_prompt: User prompt/query
            json_mode: If True, instructs the model to respond with a JSON object.
                       Set to False for free-text endpoints like ask_coach.
            
        Returns:
            LLM response content
        """
        call_kwargs: Dict[str, Any] = dict(
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            model=self.model,
            temperature=self.temperature,
            max_tokens=self.max_tokens,
        )
        if json_mode:
            call_kwargs["response_format"] = {"type": "json_object"}

        chat_completion = self.client.chat.completions.create(**call_kwargs)

        finish_reason = None
        if chat_completion.choices:
            finish_reason = chat_completion.choices[0].finish_reason

        usage = getattr(chat_completion, "usage", None)
        prompt_tokens = getattr(usage, "prompt_tokens", None) if usage else None
        completion_tokens = getattr(usage, "completion_tokens", None) if usage else None
        total_tokens = getattr(usage, "total_tokens", None) if usage else None

        logger.info(
            "LLM usage finish_reason=%s prompt_tokens=%s completion_tokens=%s total_tokens=%s",
            finish_reason,
            prompt_tokens,
            completion_tokens,
            total_tokens,
        )
        
        return chat_completion.choices[0].message.content
    
    def _parse_json_response(self, response: str) -> Dict[str, Any]:
        """
        Parse JSON response from LLM, handling potential formatting issues.

        Args:
            response: Raw LLM response

        Returns:
            Parsed JSON dictionary
        """
        cleaned = (response or "").strip()
        # Strip markdown code fences
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
        cleaned = re.sub(r"\s*```$", "", cleaned)
        cleaned = cleaned.strip()

        # Direct parse
        try:
            return json.loads(cleaned)
        except json.JSONDecodeError:
            pass

        # Fallback: extract the first balanced top-level JSON object.
        # This is more reliable than a greedy regex when the model adds stray
        # text before/after the JSON payload.
        start = cleaned.find("{")
        if start != -1:
            in_string = False
            escape = False
            depth = 0
            end = -1

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
                        end = idx + 1
                        candidate = cleaned[start:end]
                        try:
                            return json.loads(candidate)
                        except json.JSONDecodeError:
                            break

        raise ValueError(
            f"Could not parse LLM response as JSON "
            f"(response length: {len(cleaned)} chars). "
            f"Preview: {cleaned[:300]!r}"
        )

    def _format_validation_error(self, error: ValidationError) -> str:
        """Create a compact validation error summary for API error responses."""
        details = []
        for item in error.errors():
            loc = ".".join(str(part) for part in item.get("loc", []))
            msg = item.get("msg", "invalid value")
            details.append(f"{loc}: {msg}" if loc else msg)
        return "; ".join(details)

    def _validate_workout_plan_response(self, plan_data: Dict[str, Any]) -> WorkoutPlanDTO:
        """Validate workout response strictly against DTO schema."""
        if not isinstance(plan_data, dict):
            raise ValueError("Workout plan response must be a JSON object")

        try:
            return WorkoutPlanDTO.model_validate(plan_data)
        except ValidationError as error:
            raise ValueError(
                f"Workout plan schema validation failed: {self._format_validation_error(error)}"
            ) from error

    def _validate_nutrition_plan_response(self, plan_data: Dict[str, Any]) -> NutritionPlanDTO:
        """Validate nutrition response strictly against DTO schema."""
        if not isinstance(plan_data, dict):
            raise ValueError("Nutrition plan response must be a JSON object")

        try:
            return NutritionPlanDTO.model_validate(plan_data)
        except ValidationError as error:
            raise ValueError(
                f"Nutrition plan schema validation failed: {self._format_validation_error(error)}"
            ) from error

    def generate_workout_plan(
        self,
        user_profile: UserProfileDTO,
        preferences: WorkoutPreferencesDTO,
        duration_weeks: int = 4,
        existing_plan: Optional[WorkoutPlanDTO] = None,
    ) -> WorkoutPlanDTO:
        """
        Generate a personalized workout plan.
        
        Args:
            user_profile: UserProfileDTO with user's profile data
            preferences: WorkoutPreferencesDTO with workout preferences
            duration_weeks: Plan duration in weeks
            existing_plan: Optional existing plan to update/regenerate from
            
        Returns:
            WorkoutPlanDTO with the generated plan
        """
        # Get relevant context from fitness knowledge base
        # Include user profile information for better context retrieval
        profile_context = []
        if user_profile.injuries:
            profile_context.append(f"injuries: {user_profile.injuries}")
        if user_profile.medical_conditions:
            profile_context.append(f"medical conditions: {user_profile.medical_conditions}")
        if user_profile.fitness_goal:
            profile_context.append(f"goal: {user_profile.fitness_goal}")
        
        profile_str = " ".join(profile_context) if profile_context else ""
        query = f"workout plan {preferences.workout_focus} {preferences.workout_difficulty} {preferences.workout_location} {profile_str}"
        logger.info(f"🏋️ Generating workout plan - RAG query: {query}")
        rag_context = self.vector_db.get_context(query, k=self.rag_top_k, domain="workout")
        rag_context = self._trim_rag_context(rag_context, "workout")
        
        # Build and send prompt
        prompt = self._build_workout_prompt(
            user_profile, preferences, duration_weeks, rag_context, existing_plan
        )
        
        system_prompt = """You are an expert fitness coach. Generate workout plans as a single valid JSON object only.
    Consider user safety, limitations, and goals. Never suggest exercises that could harm the user.
    Do not wrap the output in markdown or add any extra text."""
        
        response = self._call_llm(system_prompt, prompt)
        logger.info("Raw workout LLM output (first 3000 chars): %s", response[:3000])
        try:
            plan_data = self._parse_json_response(response)
        except ValueError as error:
            raise ValueError(
                "Workout plan generation failed: model output was not valid JSON. "
                f"Raw output preview: {response[:1500]!r}"
            ) from error
        return self._validate_workout_plan_response(plan_data)

    def generate_nutrition_plan(
        self,
        user_profile: UserProfileDTO,
        preferences: NutritionPreferencesDTO,
        duration_weeks: int = 4,
        existing_plan: Optional[NutritionPlanDTO] = None,
        allowed_foods_str: str = ""
    ) -> NutritionPlanDTO:
        """
        Generate a personalized nutrition plan.
        
        Args:
            user_profile: UserProfileDTO with user's profile data
            preferences: NutritionPreferencesDTO with nutrition preferences
            duration_weeks: Plan duration in weeks
            existing_plan: Optional existing plan to update/regenerate from
            allowed_foods_str: Strict constraint payload of allowed central_foods
            
        Returns:
            NutritionPlanDTO with the generated plan
        """
        # Get relevant context from nutrition knowledge base
        # Include user profile information for better context retrieval
        profile_context = []
        if user_profile.allergies:
            profile_context.append(f"allergies: {user_profile.allergies}")
        if user_profile.medical_conditions:
            profile_context.append(f"medical conditions: {user_profile.medical_conditions}")
        if user_profile.fitness_goal:
            profile_context.append(f"goal: {user_profile.fitness_goal}")
        
        profile_str = " ".join(profile_context) if profile_context else ""
        query = f"nutrition meal plan {preferences.cuisine_preference} {preferences.calorie_preference} {profile_str}"
        logger.info(f"🍽️ Generating nutrition plan - RAG query: {query}")
        rag_context = self.vector_db.get_context(query, k=self.rag_top_k, domain="nutrition")
        rag_context = self._trim_rag_context(rag_context, "nutrition")
        
        logger.info("===================================")
        logger.info("🥗 INJECTED DB FOODS STRING:")
        logger.info(allowed_foods_str)
        logger.info("===================================")
        
        # Build and send prompt
        prompt = self._build_nutrition_prompt(
            user_profile, preferences, duration_weeks, rag_context, existing_plan, allowed_foods_str
        )
        
        system_prompt = """You are an expert nutritionist. Generate meal plans as a single valid JSON object only.
    Consider user allergies, dietary restrictions, and fitness goals. Ensure balanced macronutrients.
    Do not wrap the output in markdown or add any extra text."""
        
        response = self._call_llm(system_prompt, prompt)
        logger.info("Raw nutrition LLM output (first 3000 chars): %s", response[:3000])
        try:
            plan_data = self._parse_json_response(response)
        except ValueError as error:
            raise ValueError(
                "Nutrition plan generation failed: model output was not valid JSON. "
                f"Raw output preview: {response[:1500]!r}"
            ) from error
        return self._validate_nutrition_plan_response(plan_data)
    
    def ask_coach(
        self,
        question: str,
        user_profile: Optional[UserProfileDTO] = None,
        language: str = "auto"
    ) -> str:
        """
        Ask the AI coach a fitness or nutrition related question.
        Uses RAG to provide informed, personalized answers.
        
        Args:
            question: User's question
            user_profile: Optional UserProfileDTO for personalization
            language: Response language (auto, en, ar)
            
        Returns:
            AI coach response
        """
        # Get relevant context from knowledge base
        # Include user profile information for better context retrieval
        query = question
        if user_profile:
            profile_context = []
            if user_profile.injuries:
                profile_context.append(f"injuries: {user_profile.injuries}")
            if user_profile.medical_conditions:
                profile_context.append(f"medical conditions: {user_profile.medical_conditions}")
            if user_profile.allergies:
                profile_context.append(f"allergies: {user_profile.allergies}")
            if user_profile.fitness_goal:
                profile_context.append(f"goal: {user_profile.fitness_goal}")
            
            if profile_context:
                profile_str = " ".join(profile_context)
                query = f"{question} {profile_str}"
        
        logger.info(f"💬 Ask Coach - Question: {question}")
        logger.info(f"💬 Enhanced query with profile: {query}")
        rag_context = self.vector_db.get_context(query, k=min(self.rag_top_k, 3))
        rag_context = self._trim_rag_context(rag_context, "ask_coach")
        
        # Build user context if available
        user_context = ""
        if user_profile:
            user_context = user_profile.to_context_string()
        
        language_instruction = ""
        if language == "auto":
            language_instruction = "Respond in the SAME LANGUAGE as the user's question."
        elif language == "ar":
            language_instruction = "Respond in Arabic (Egyptian dialect)."
        else:
            language_instruction = "Respond in English."
        
        system_prompt = f"""You are an experienced personal fitness coach with years of training experience.

{language_instruction}

{user_context if user_context else "No user profile available - give general advice."}

YOUR APPROACH:
- Speak as a coach, NOT as someone reading from a book or manual
- Never mention "the handbook", "according to the guide", or similar references
- Give advice based on YOUR professional experience and expertise
- Be conversational, encouraging, and supportive like a real trainer
- Always consider the user's medical conditions and restrictions if known
- Provide safe alternatives and modifications when needed
- Use specific exercise names, rep ranges, and practical tips
- Be direct and actionable - give clear steps they can follow today

Remember: You're their trusted coach who is here to help them succeed safely."""
        
        user_prompt = f"""Reference fitness knowledge:
{rag_context}

Question: {question}

Give me your professional advice as my coach. Be practical and specific."""
        
        return self._call_llm(system_prompt, user_prompt, json_mode=False)


# Singleton instance
_ai_coach_service: Optional[AICoachService] = None


def get_ai_coach_service() -> AICoachService:
    """
    Get the singleton AICoachService instance.
    
    Returns:
        AICoachService instance
    """
    global _ai_coach_service
    if _ai_coach_service is None:
        _ai_coach_service = AICoachService()
    return _ai_coach_service
