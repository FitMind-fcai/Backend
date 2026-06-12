import os
import json
import logging
import tempfile
from typing import Optional, Dict, Any, List

from groq import Groq
from openai import OpenAI

from app.ai_services.embedding_utils import embed_text, embed_texts, vec_to_pg_str
from app.ai_services.voice_transcriber.dtos import (
    TranscriptionRequestDTO,
    TranscriptionResultDTO,
    TranscriptionContextType,
    MealLogTranscriptionDTO,
    WorkoutLogTranscriptionDTO,
    WeightLogTranscriptionDTO,
    MatchedFoodDTO,
    MatchedExerciseDTO,
    ParsedExerciseDTO,
)

logger = logging.getLogger(__name__)


_OPENROUTER_BASE = "https://openrouter.ai/api/v1"
_OPENROUTER_PARSER_MODEL = "meta-llama/llama-3.3-70b-instruct"


class VoiceTranscriberService:
    """
    Voice transcription + structured parsing service.

    Pipeline:
    1. Groq Whisper          — speech → raw text  (always Groq; no alternative)
    2. LLM parser            — raw text → structured JSON
       • OpenRouter/OpenAI-compatible if AI_API_KEY or OPENROUTER_API_KEY is set
       • Falls back to Groq LLaMA otherwise
    3. pgvector              — embed tags → top-5 central_foods or central_exercises
    """

    WHISPER_MODEL = "whisper-large-v3"
    GROQ_PARSER_MODEL = "llama-3.3-70b-versatile"
    PARSER_TEMPERATURE = 0.0
    PARSER_MAX_TOKENS = 1500
    SUPPORTED_FORMATS = {"mp3", "wav", "m4a", "webm", "ogg", "flac"}

    def __init__(
        self,
        api_key: Optional[str] = None,
        whisper_model: Optional[str] = None,
        parser_model: Optional[str] = None,
    ):
        # --- Whisper client (Groq, mandatory) ---
        groq_key = api_key or os.getenv("GROQ_API_KEY")
        if not groq_key:
            raise ValueError("GROQ_API_KEY not set — required for Whisper transcription.")
        self.whisper_model = whisper_model or self.WHISPER_MODEL
        self.client = Groq(api_key=groq_key)

        # --- LLM parser client (OpenRouter, same AI_API_KEY as the AI Coach) ---
        parser_api_key = os.getenv("AI_API_KEY")

        if parser_api_key:
            self._parser_client = OpenAI(
                api_key=parser_api_key,
                base_url=_OPENROUTER_BASE,
                default_headers={
                    "HTTP-Referer": os.getenv("OPENROUTER_SITE_URL", "http://localhost:8000"),
                    "X-Title":      os.getenv("OPENROUTER_APP_NAME", "FitMind"),
                },
            )
            self.parser_model = parser_model or os.getenv("LLM_PARSER_MODEL", _OPENROUTER_PARSER_MODEL)
            self._parser_uses_openai_compat = True
            logger.info("LLM parser: OpenRouter — %s", self.parser_model)
        else:
            # Fall back to Groq when AI_API_KEY is not set.
            self._parser_client = None
            self.parser_model = parser_model or os.getenv("LLM_PARSER_MODEL", self.GROQ_PARSER_MODEL)
            self._parser_uses_openai_compat = False
            logger.info("LLM parser: Groq fallback — %s", self.parser_model)

    # ------------------------------------------------------------------
    # Whisper transcription
    # ------------------------------------------------------------------

    def transcribe(self, request: TranscriptionRequestDTO) -> TranscriptionResultDTO:
        """Transcribe base64-encoded audio using Groq Whisper."""
        if request.audio_format.lower() not in self.SUPPORTED_FORMATS:
            return TranscriptionResultDTO(
                text="",
                language="unknown",
                transcription_successful=False,
                error_message=f"Unsupported format '{request.audio_format}'. Supported: {sorted(self.SUPPORTED_FORMATS)}",
            )

        context_hints = {
            TranscriptionContextType.MEAL_LOG: (
                "Food logging: breakfast, lunch, dinner, snack, calories, protein, carbs, "
                "portions, servings, grams, cups, pieces"
            ),
            TranscriptionContextType.WORKOUT_LOG: (
                "Workout logging: sets, reps, weight, kilograms, pounds, minutes, seconds, "
                "bench press, squat, deadlift, curl, pushups, pullups"
            ),
            TranscriptionContextType.GENERAL: "",
        }
        prompt = context_hints.get(request.context_type, "")
        if request.prompt_hint:
            prompt = f"{prompt}, {request.prompt_hint}" if prompt else request.prompt_hint

        try:
            audio_bytes = request.audio_bytes
            suffix = f".{request.audio_format.lower()}"
            with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
                tmp.write(audio_bytes)
                tmp_path = tmp.name
            try:
                params: Dict[str, Any] = {
                    "file": (f"audio{suffix}", open(tmp_path, "rb")),
                    "model": self.whisper_model,
                    "response_format": "verbose_json",
                }
                if request.language:
                    params["language"] = request.language
                if prompt:
                    params["prompt"] = prompt
                result = self.client.audio.transcriptions.create(**params)
                params["file"][1].close()
            finally:
                os.unlink(tmp_path)

            text = getattr(result, "text", str(result))
            language = getattr(result, "language", request.language or "en")
            duration = getattr(result, "duration", None)
            logger.info("Transcription OK: %d chars, lang=%s", len(text), language)
            return TranscriptionResultDTO(
                text=text,
                language=language,
                duration_seconds=duration,
                transcription_successful=True,
            )
        except Exception as exc:
            logger.error("Transcription failed: %s", exc)
            return TranscriptionResultDTO(
                text="", language="unknown", transcription_successful=False, error_message=str(exc)
            )

    # ------------------------------------------------------------------
    # LLM parser helpers
    # ------------------------------------------------------------------

    def _llm(self, system: str, user: str) -> str:
        client = self._parser_client if self._parser_uses_openai_compat else self.client
        resp = client.chat.completions.create(
            messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
            model=self.parser_model,
            temperature=self.PARSER_TEMPERATURE,
            max_tokens=self.PARSER_MAX_TOKENS,
        )
        return resp.choices[0].message.content

    @staticmethod
    def _parse_json(raw: str) -> Dict[str, Any]:
        s = raw.strip()
        for fence in ("```json", "```"):
            if s.startswith(fence):
                s = s[len(fence):]
        if s.endswith("```"):
            s = s[:-3]
        return json.loads(s.strip())

    # ------------------------------------------------------------------
    # pgvector helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _search_foods(query_text: str, db, limit: int = 5) -> List[MatchedFoodDTO]:
        """Cosine similarity search against central_foods."""
        if db is None:
            return []
        try:
            from sqlalchemy import text as sql_text
            vec = vec_to_pg_str(embed_text(query_text))
            rows = db.execute(
                sql_text("""
                    SELECT id, food_name, food_category,
                           calories_per_100g, protein_per_100g, carbs_per_100g,
                           fats_per_100g, fiber_per_100g, serving_size_g, serving_description,
                           1 - (name_embedding <=> :vec::vector) AS similarity
                    FROM central_foods
                    WHERE is_active = true AND name_embedding IS NOT NULL
                    ORDER BY name_embedding <=> :vec::vector
                    LIMIT :lim
                """),
                {"vec": vec, "lim": limit},
            ).fetchall()
            return [
                MatchedFoodDTO(
                    id=r.id, food_name=r.food_name, food_category=r.food_category,
                    calories_per_100g=r.calories_per_100g, protein_per_100g=r.protein_per_100g,
                    carbs_per_100g=r.carbs_per_100g, fats_per_100g=r.fats_per_100g,
                    fiber_per_100g=r.fiber_per_100g, serving_size_g=r.serving_size_g,
                    serving_description=r.serving_description, similarity_score=float(r.similarity),
                )
                for r in rows
            ]
        except Exception as exc:
            logger.warning("Food vector search failed: %s", exc)
            return []

    @staticmethod
    def _search_exercises(query_text: str, db, limit: int = 5) -> List[MatchedExerciseDTO]:
        """Cosine similarity search against central_exercises."""
        if db is None:
            return []
        try:
            from sqlalchemy import text as sql_text
            vec = vec_to_pg_str(embed_text(query_text))
            rows = db.execute(
                sql_text("""
                    SELECT id, name, exercise_type, primary_muscle_group,
                           secondary_muscles, equipment_required, difficulty_level, location,
                           1 - (name_embedding <=> :vec::vector) AS similarity
                    FROM central_exercises
                    WHERE is_active = true AND name_embedding IS NOT NULL
                    ORDER BY name_embedding <=> :vec::vector
                    LIMIT :lim
                """),
                {"vec": vec, "lim": limit},
            ).fetchall()
            return [
                MatchedExerciseDTO(
                    id=r.id, name=r.name, exercise_type=r.exercise_type,
                    primary_muscle_group=r.primary_muscle_group,
                    secondary_muscles=r.secondary_muscles,
                    equipment_required=r.equipment_required,
                    difficulty_level=r.difficulty_level, location=r.location,
                    similarity_score=float(r.similarity),
                )
                for r in rows
            ]
        except Exception as exc:
            logger.warning("Exercise vector search failed: %s", exc)
            return []

    # ------------------------------------------------------------------
    # Meal parsing
    # ------------------------------------------------------------------

    def transcribe_and_parse_meal_log(
        self,
        request: TranscriptionRequestDTO,
        db=None,
    ) -> MealLogTranscriptionDTO:
        """
        Whisper → LLM meal parser → pgvector food search.

        Returns full nutrition estimates + top-5 matched central_foods.
        """
        request.context_type = TranscriptionContextType.MEAL_LOG
        transcription = self.transcribe(request)

        if not transcription.transcription_successful:
            return MealLogTranscriptionDTO(
                raw_text="",
                parse_successful=False,
                notes=transcription.error_message,
            )

        logger.info("Parsing meal from: %s…", transcription.text[:80])

        try:
            system = (
                "You are a nutrition-aware meal logging assistant. "
                "Extract and estimate food data from voice transcriptions. "
                "Return ONLY valid JSON, no extra text."
            )
            user = f"""Parse this meal log transcription and return structured data.

Transcription: "{transcription.text}"

Return JSON:
{{
    "meal_name": "Human-friendly combined name, e.g. 'Grilled Chicken and Rice'",
    "meal_type": "Breakfast|Lunch|Dinner|Snack or null",
    "food_items": ["item1", "item2"],
    "portions": ["portion1", "portion2"],
    "tags": ["tag1", "tag2"],
    "estimated_calories": 500,
    "estimated_protein_g": 35.0,
    "estimated_carbs_g": 55.0,
    "estimated_fats_g": 12.0,
    "notes": "any relevant context or null"
}}

Rules:
- tags: 4-8 short English keywords (ingredients, cuisine, cooking method, nutritional profile) — used for semantic search
- macros: realistic estimates based on portions; use null if impossible to estimate
- food_items and portions arrays must have the same length
- Return ONLY valid JSON"""

            data = self._parse_json(self._llm(system, user))
        except Exception as exc:
            logger.error("Meal parse failed: %s", exc)
            return MealLogTranscriptionDTO(
                raw_text=transcription.text,
                parse_successful=False,
                notes=f"Parse error: {exc}",
            )

        tags: List[str] = data.get("tags", [])
        search_text = " ".join(tags) or transcription.text
        matched_foods = self._search_foods(search_text, db)

        return MealLogTranscriptionDTO(
            raw_text=transcription.text,
            meal_name=data.get("meal_name"),
            meal_type=data.get("meal_type"),
            food_items=data.get("food_items", []),
            portions=data.get("portions", []),
            tags=tags,
            estimated_calories=data.get("estimated_calories"),
            estimated_protein_g=data.get("estimated_protein_g"),
            estimated_carbs_g=data.get("estimated_carbs_g"),
            estimated_fats_g=data.get("estimated_fats_g"),
            matched_foods=matched_foods,
            parse_successful=True,
            notes=data.get("notes"),
        )

    # ------------------------------------------------------------------
    # Workout parsing
    # ------------------------------------------------------------------

    def transcribe_and_parse_workout_log(
        self,
        request: TranscriptionRequestDTO,
        db=None,
    ) -> WorkoutLogTranscriptionDTO:
        """
        Whisper → LLM workout parser → per-exercise pgvector search.

        Returns a list of ParsedExerciseDTO, each with top-5 matched central_exercises.
        """
        request.context_type = TranscriptionContextType.WORKOUT_LOG
        transcription = self.transcribe(request)

        if not transcription.transcription_successful:
            return WorkoutLogTranscriptionDTO(
                raw_text="",
                parse_successful=False,
                notes=transcription.error_message,
            )

        logger.info("Parsing workout from: %s…", transcription.text[:80])

        try:
            system = (
                "You are a workout logging assistant. "
                "Extract structured exercise data from voice transcriptions. "
                "Return ONLY valid JSON, no extra text."
            )
            user = f"""Parse this workout log transcription.

Transcription: "{transcription.text}"

Return JSON:
{{
    "exercises": [
        {{
            "name": "Exercise name as spoken",
            "sets": 3,
            "reps": 10,
            "weight_str": "50kg",
            "weight_kg": 50.0,
            "duration_seconds": null
        }}
    ],
    "duration_mentioned": "30 minutes or null",
    "tags": ["chest", "push", "barbell"],
    "notes": "any relevant context or null"
}}

Rules:
- Each exercise gets its own object; keep arrays parallel
- weight_kg: numeric kg value (convert lbs × 0.453592 if needed); null if not mentioned
- duration_seconds: for cardio/timed sets instead of reps; null otherwise
- sets / reps: null if not mentioned
- tags: 4-8 keywords (muscle groups, equipment, style) — used for semantic search
- Return ONLY valid JSON"""

            data = self._parse_json(self._llm(system, user))
        except Exception as exc:
            logger.error("Workout parse failed: %s", exc)
            return WorkoutLogTranscriptionDTO(
                raw_text=transcription.text,
                parse_successful=False,
                notes=f"Parse error: {exc}",
            )

        raw_exercises: List[Dict] = data.get("exercises", [])
        parsed_exercises: List[ParsedExerciseDTO] = []

        for ex in raw_exercises:
            name = ex.get("name", "")
            matches = self._search_exercises(name, db) if name else []
            parsed_exercises.append(
                ParsedExerciseDTO(
                    name=name,
                    sets=ex.get("sets"),
                    reps=ex.get("reps"),
                    weight_str=ex.get("weight_str"),
                    weight_kg=ex.get("weight_kg"),
                    duration_seconds=ex.get("duration_seconds"),
                    matched_exercises=matches,
                )
            )

        return WorkoutLogTranscriptionDTO(
            raw_text=transcription.text,
            exercises=parsed_exercises,
            duration_mentioned=data.get("duration_mentioned"),
            tags=data.get("tags", []),
            parse_successful=True,
            notes=data.get("notes"),
        )


    # ------------------------------------------------------------------
    # Weight parsing
    # ------------------------------------------------------------------

    def transcribe_and_parse_weight_log(
        self,
        request: TranscriptionRequestDTO,
    ) -> WeightLogTranscriptionDTO:
        """
        Whisper → LLM weight extractor.

        Extracts a numeric weight value (kg) from a voice recording such as
        "I weigh 75 kilos" or "just hit 165 pounds".
        """
        request.context_type = TranscriptionContextType.GENERAL
        transcription = self.transcribe(request)

        if not transcription.transcription_successful:
            return WeightLogTranscriptionDTO(
                raw_text="",
                parse_successful=False,
                notes=transcription.error_message,
            )

        try:
            system = (
                "You are a weight-tracking assistant. "
                "Extract a numeric body weight from the user's voice input. "
                "Return ONLY valid JSON, no extra text."
            )
            user = f"""Extract the body weight from this transcription.

Transcription: "{transcription.text}"

Return JSON:
{{
    "extracted_weight_kg": 75.5,
    "notes": "any relevant context or null"
}}

Rules:
- extracted_weight_kg: numeric kg value; convert lbs × 0.453592 if needed; null if no weight found
- Return ONLY valid JSON"""

            data = self._parse_json(self._llm(system, user))
        except Exception as exc:
            logger.error("Weight parse failed: %s", exc)
            return WeightLogTranscriptionDTO(
                raw_text=transcription.text,
                parse_successful=False,
                notes=f"Parse error: {exc}",
            )

        weight = data.get("extracted_weight_kg")
        return WeightLogTranscriptionDTO(
            raw_text=transcription.text,
            extracted_weight_kg=float(weight) if weight is not None else None,
            notes=data.get("notes"),
            parse_successful=weight is not None,
        )


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------

_voice_transcriber_service: Optional[VoiceTranscriberService] = None


def get_voice_transcriber_service() -> VoiceTranscriberService:
    global _voice_transcriber_service
    if _voice_transcriber_service is None:
        _voice_transcriber_service = VoiceTranscriberService()
    return _voice_transcriber_service
