import os
import json
import logging
import re
from typing import Optional, Dict, Any
from groq import Groq

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
    MealDTO
)

# Configure logger
logger = logging.getLogger(__name__)


class AICoachService:    
    # LLM Configuration
    DEFAULT_MODEL = "openai/gpt-oss-120b"
    DEFAULT_TEMPERATURE = 0.0
    DEFAULT_MAX_TOKENS = 8000
    
    def __init__(
        self,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
        vector_db_service: Optional[VectorDBService] = None
    ):
        """
        Initialize the AI Coach Service.
        
        Args:
            api_key: Groq API key (falls back to GROQ_API_KEY env variable)
            model: LLM model to use
            vector_db_service: Optional VectorDBService instance
        """
        self.api_key = api_key or os.getenv("GROQ_API_KEY")
        if not self.api_key:
            raise ValueError(
                "Groq API key not provided. Set GROQ_API_KEY environment variable "
                "or pass api_key parameter."
            )
        
        self.model = model or self.DEFAULT_MODEL
        self.client = Groq(api_key=self.api_key)
        self.vector_db = vector_db_service or get_vector_db_service()
    
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
        existing_plan: Optional[NutritionPlanDTO] = None
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
                    "ingredients": "List of ingredients with quantities",
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
    
    def _call_llm(self, system_prompt: str, user_prompt: str) -> str:
        """
        Call the Groq LLM with the given prompts.
        
        Args:
            system_prompt: System instruction for the LLM
            user_prompt: User prompt/query
            
        Returns:
            LLM response content
        """
        chat_completion = self.client.chat.completions.create(
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            model=self.model,
            temperature=self.DEFAULT_TEMPERATURE,
            max_tokens=self.DEFAULT_MAX_TOKENS
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

        # Fallback: extract the first {...} block (handles leading/trailing prose
        # and partially-truncated responses where the outermost object is intact)
        match = re.search(r"\{.*\}", cleaned, re.DOTALL)
        if match:
            try:
                return json.loads(match.group())
            except json.JSONDecodeError:
                pass

        raise ValueError(
            f"Could not parse LLM response as JSON "
            f"(response length: {len(cleaned)} chars). "
            f"Preview: {cleaned[:300]!r}"
        )
    
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
        rag_context = self.vector_db.get_context(query, k=5)
        
        # Build and send prompt
        prompt = self._build_workout_prompt(
            user_profile, preferences, duration_weeks, rag_context, existing_plan
        )
        
        system_prompt = """You are an expert fitness coach. Generate workout plans in valid JSON format only.
Consider user safety, limitations, and goals. Never suggest exercises that could harm the user."""
        
        response = self._call_llm(system_prompt, prompt)
        plan_data = self._parse_json_response(response)
        
        # Convert to WorkoutPlanDTO
        workout_days = []
        for day_data in plan_data.get("workout_days", []):
            exercises = [
                ExerciseDTO(
                    exercise_name=ex.get("exercise_name"),
                    exercise_type=ex.get("exercise_type"),
                    sets=ex.get("sets"),
                    reps=ex.get("reps"),
                    weight_kg=ex.get("weight_kg"),
                    duration_seconds=ex.get("duration_seconds"),
                    rest_seconds=ex.get("rest_seconds"),
                    instructions=ex.get("instructions"),
                    video_url=ex.get("video_url"),
                    image_url=ex.get("image_url"),
                    order_index=ex.get("order_index", idx)
                )
                for idx, ex in enumerate(day_data.get("exercises", []))
            ]
            
            workout_days.append(WorkoutDayDTO(
                day_name=day_data.get("day_name"),
                day_number=day_data.get("day_number"),
                focus_area=day_data.get("focus_area"),
                estimated_duration=day_data.get("estimated_duration"),
                notes=day_data.get("notes"),
                exercises=exercises
            ))
        
        plan = WorkoutPlanDTO(
            plan_name=plan_data.get("plan_name", "AI Generated Workout Plan"),
            description=plan_data.get("description"),
            frequency=plan_data.get("frequency"),
            difficulty_level=plan_data.get("difficulty_level"),
            estimated_duration_per_session=plan_data.get("estimated_duration_per_session"),
            workout_days=workout_days
        )

        return plan

    def generate_nutrition_plan(
        self,
        user_profile: UserProfileDTO,
        preferences: NutritionPreferencesDTO,
        duration_weeks: int = 4,
        existing_plan: Optional[NutritionPlanDTO] = None,
    ) -> NutritionPlanDTO:
        """
        Generate a personalized nutrition plan.
        
        Args:
            user_profile: UserProfileDTO with user's profile data
            preferences: NutritionPreferencesDTO with nutrition preferences
            duration_weeks: Plan duration in weeks
            existing_plan: Optional existing plan to update/regenerate from
            
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
        rag_context = self.vector_db.get_context(query, k=5)
        
        # Build and send prompt
        prompt = self._build_nutrition_prompt(
            user_profile, preferences, duration_weeks, rag_context, existing_plan
        )
        
        system_prompt = """You are an expert nutritionist. Generate meal plans in valid JSON format only.
Consider user allergies, dietary restrictions, and fitness goals. Ensure balanced macronutrients."""
        
        response = self._call_llm(system_prompt, prompt)
        plan_data = self._parse_json_response(response)
        
        # Convert to NutritionPlanDTO
        days = [
            NutritionDayDTO(
                day_name=day.get("day_name", f"Day {day.get('day_number', idx + 1)}"),
                day_number=day.get("day_number", idx + 1),
                notes=day.get("notes"),
                meals=[
                    MealDTO(
                        meal_type=meal.get("meal_type"),
                        meal_name=meal.get("meal_name"),
                        calories=meal.get("calories", 0),
                        protein_g=meal.get("protein_g", 0),
                        carbs_g=meal.get("carbs_g", 0),
                        fats_g=meal.get("fats_g", 0),
                        ingredients=meal.get("ingredients"),
                        instructions=meal.get("instructions"),
                        prep_time_minutes=meal.get("prep_time_minutes"),
                        cook_time_minutes=meal.get("cook_time_minutes"),
                        servings=meal.get("servings", 1),
                        image_url=meal.get("image_url"),
                        order_index=meal.get("order_index", meal_idx)
                    )
                    for meal_idx, meal in enumerate(day.get("meals", []))
                ]
            )
            for idx, day in enumerate(plan_data.get("days", []))
        ]

        plan = NutritionPlanDTO(
            plan_name=plan_data.get("plan_name", "AI Generated Nutrition Plan"),
            description=plan_data.get("description"),
            daily_calories=plan_data.get("daily_calories", 2000),
            daily_protein_g=plan_data.get("daily_protein_g", 150),
            daily_carbs_g=plan_data.get("daily_carbs_g", 200),
            daily_fats_g=plan_data.get("daily_fats_g", 65),
            days=days
        )

        return plan
    
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
        rag_context = self.vector_db.get_context(query, k=3)
        
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
        
        return self._call_llm(system_prompt, user_prompt)


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
