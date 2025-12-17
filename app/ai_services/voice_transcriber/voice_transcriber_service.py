import os
import json
import base64
import logging
import tempfile
from typing import Optional, Dict, Any
from groq import Groq

from app.ai_services.voice_transcriber.dtos import (
    TranscriptionRequestDTO,
    TranscriptionResultDTO,
    TranscriptionContextType,
    MealLogTranscriptionDTO,
    WorkoutLogTranscriptionDTO
)

# Configure logger
logger = logging.getLogger(__name__)


class VoiceTranscriberService:
    """
    AI-powered voice transcription service using Whisper.
    Transcribes audio to text with context-aware parsing.
    """
    
    # Whisper Configuration
    WHISPER_MODEL = "whisper-large-v3"
    
    # LLM for parsing (to extract structured data from transcription)
    PARSER_MODEL = "llama-3.3-70b-versatile"
    PARSER_TEMPERATURE = 0.0
    PARSER_MAX_TOKENS = 1000
    
    # Supported audio formats
    SUPPORTED_FORMATS = ["mp3", "wav", "m4a", "webm", "ogg", "flac"]
    
    def __init__(
        self,
        api_key: Optional[str] = None,
        whisper_model: Optional[str] = None,
        parser_model: Optional[str] = None
    ):
        """
        Initialize the Voice Transcriber Service.
        
        Args:
            api_key: Groq API key (falls back to GROQ_API_KEY env variable)
            whisper_model: Whisper model to use for transcription
            parser_model: LLM model to use for parsing transcriptions
        """
        self.api_key = api_key or os.getenv("GROQ_API_KEY")
        if not self.api_key:
            raise ValueError(
                "Groq API key not provided. Set GROQ_API_KEY environment variable "
                "or pass api_key parameter."
            )
        
        self.whisper_model = whisper_model or self.WHISPER_MODEL
        self.parser_model = parser_model or self.PARSER_MODEL
        self.client = Groq(api_key=self.api_key)
    
    def _get_context_prompt(self, context_type: TranscriptionContextType, prompt_hint: Optional[str]) -> str:
        """Get context-specific prompt for Whisper."""
        base_prompts = {
            TranscriptionContextType.MEAL_LOG: "Food logging: breakfast, lunch, dinner, snack, calories, protein, carbs, portions, servings, grams, cups, pieces",
            TranscriptionContextType.WORKOUT_LOG: "Workout logging: sets, reps, weight, kilograms, pounds, minutes, seconds, bench press, squat, deadlift, curl, pushups, pullups",
            TranscriptionContextType.GENERAL: ""
        }
        
        prompt = base_prompts.get(context_type, "")
        if prompt_hint:
            prompt = f"{prompt}, {prompt_hint}" if prompt else prompt_hint
        
        return prompt
    
    def transcribe(self, request: TranscriptionRequestDTO) -> TranscriptionResultDTO:
        """
        Transcribe audio to text.
        
        Args:
            request: TranscriptionRequestDTO with audio and context
            
        Returns:
            TranscriptionResultDTO with transcription result
        """
        logger.info(f"🎤 Transcribing audio (format: {request.audio_format}, context: {request.context_type})")
        
        # Validate format
        if request.audio_format.lower() not in self.SUPPORTED_FORMATS:
            return TranscriptionResultDTO(
                text="",
                language="unknown",
                transcription_successful=False,
                error_message=f"Unsupported audio format: {request.audio_format}. Supported: {', '.join(self.SUPPORTED_FORMATS)}"
            )
        
        try:
            # Decode base64 audio
            audio_bytes = base64.b64decode(request.audio_base64)
            
            # Create temporary file for the audio
            suffix = f".{request.audio_format}"
            with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as temp_file:
                temp_file.write(audio_bytes)
                temp_file_path = temp_file.name
            
            try:
                # Get context prompt
                context_prompt = self._get_context_prompt(request.context_type, request.prompt_hint)
                
                # Open and transcribe
                with open(temp_file_path, "rb") as audio_file:
                    transcription_params = {
                        "file": (f"audio{suffix}", audio_file),
                        "model": self.whisper_model,
                        "response_format": "verbose_json"
                    }
                    
                    # Add optional parameters
                    if request.language:
                        transcription_params["language"] = request.language
                    if context_prompt:
                        transcription_params["prompt"] = context_prompt
                    
                    transcription = self.client.audio.transcriptions.create(**transcription_params)
                
                # Extract results
                text = transcription.text if hasattr(transcription, 'text') else str(transcription)
                language = getattr(transcription, 'language', request.language or 'en')
                duration = getattr(transcription, 'duration', None)
                
                logger.info(f"✅ Transcription successful: {len(text)} characters, language: {language}")
                
                return TranscriptionResultDTO(
                    text=text,
                    language=language,
                    duration_seconds=duration,
                    confidence=None,  # Whisper doesn't provide overall confidence
                    transcription_successful=True,
                    error_message=None
                )
                
            finally:
                # Clean up temp file
                os.unlink(temp_file_path)
                
        except Exception as e:
            logger.error(f"❌ Transcription failed: {e}")
            return TranscriptionResultDTO(
                text="",
                language="unknown",
                transcription_successful=False,
                error_message=str(e)
            )
    
    def _call_parser_llm(self, system_prompt: str, user_prompt: str) -> str:
        """Call LLM for parsing transcribed text."""
        chat_completion = self.client.chat.completions.create(
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            model=self.parser_model,
            temperature=self.PARSER_TEMPERATURE,
            max_tokens=self.PARSER_MAX_TOKENS
        )
        
        return chat_completion.choices[0].message.content
    
    def _parse_json_response(self, response: str) -> Dict[str, Any]:
        """Parse JSON response from LLM."""
        cleaned = response.strip()
        if cleaned.startswith("```json"):
            cleaned = cleaned[7:]
        elif cleaned.startswith("```"):
            cleaned = cleaned[3:]
        if cleaned.endswith("```"):
            cleaned = cleaned[:-3]
        
        return json.loads(cleaned.strip())
    
    def transcribe_and_parse_meal_log(
        self,
        request: TranscriptionRequestDTO
    ) -> MealLogTranscriptionDTO:
        """
        Transcribe audio and parse as meal log.
        
        Args:
            request: TranscriptionRequestDTO with audio
            
        Returns:
            MealLogTranscriptionDTO with parsed meal data
        """
        # First transcribe
        request.context_type = TranscriptionContextType.MEAL_LOG
        transcription = self.transcribe(request)
        
        if not transcription.transcription_successful:
            return MealLogTranscriptionDTO(
                raw_text="",
                parse_successful=False,
                notes=transcription.error_message
            )
        
        logger.info(f"🍽️ Parsing meal log from transcription: {transcription.text[:100]}...")
        
        try:
            # Parse with LLM
            system_prompt = """You are a meal logging assistant. Extract food information from the user's voice transcription.
Return ONLY valid JSON, no additional text."""
            
            user_prompt = f"""Parse this meal log transcription and extract structured data:

Transcription: "{transcription.text}"

Return JSON in this format:
{{
    "meal_type": "Breakfast/Lunch/Dinner/Snack or null if unclear",
    "food_items": ["item1", "item2"],
    "portions": ["portion1", "portion2"],
    "notes": "any additional context"
}}

CRITICAL: Return ONLY valid JSON."""
            
            response = self._call_parser_llm(system_prompt, user_prompt)
            parsed = self._parse_json_response(response)
            
            return MealLogTranscriptionDTO(
                raw_text=transcription.text,
                meal_type=parsed.get("meal_type"),
                food_items=parsed.get("food_items", []),
                portions=parsed.get("portions", []),
                parse_successful=True,
                notes=parsed.get("notes")
            )
            
        except Exception as e:
            logger.error(f"❌ Meal log parsing failed: {e}")
            return MealLogTranscriptionDTO(
                raw_text=transcription.text,
                parse_successful=False,
                notes=f"Transcription successful but parsing failed: {str(e)}"
            )
    
    def transcribe_and_parse_workout_log(
        self,
        request: TranscriptionRequestDTO
    ) -> WorkoutLogTranscriptionDTO:
        """
        Transcribe audio and parse as workout log.
        
        Args:
            request: TranscriptionRequestDTO with audio
            
        Returns:
            WorkoutLogTranscriptionDTO with parsed workout data
        """
        # First transcribe
        request.context_type = TranscriptionContextType.WORKOUT_LOG
        transcription = self.transcribe(request)
        
        if not transcription.transcription_successful:
            return WorkoutLogTranscriptionDTO(
                raw_text="",
                parse_successful=False,
                notes=transcription.error_message
            )
        
        logger.info(f"💪 Parsing workout log from transcription: {transcription.text[:100]}...")
        
        try:
            # Parse with LLM
            system_prompt = """You are a workout logging assistant. Extract exercise information from the user's voice transcription.
Return ONLY valid JSON, no additional text."""
            
            user_prompt = f"""Parse this workout log transcription and extract structured data:

Transcription: "{transcription.text}"

Return JSON in this format:
{{
    "exercises": ["exercise1", "exercise2"],
    "sets": [3, 4],
    "reps": [10, 12],
    "weights": ["50kg", "60kg"],
    "duration_mentioned": "30 minutes or null",
    "notes": "any additional context"
}}

CRITICAL: 
- Return ONLY valid JSON
- Match exercises with their corresponding sets, reps, and weights by index
- If a value isn't mentioned, use null for that specific item
- Keep arrays aligned (same length where data is available)"""
            
            response = self._call_parser_llm(system_prompt, user_prompt)
            parsed = self._parse_json_response(response)
            
            return WorkoutLogTranscriptionDTO(
                raw_text=transcription.text,
                exercises=parsed.get("exercises", []),
                sets=parsed.get("sets", []),
                reps=parsed.get("reps", []),
                weights=parsed.get("weights", []),
                duration_mentioned=parsed.get("duration_mentioned"),
                parse_successful=True,
                notes=parsed.get("notes")
            )
            
        except Exception as e:
            logger.error(f"❌ Workout log parsing failed: {e}")
            return WorkoutLogTranscriptionDTO(
                raw_text=transcription.text,
                parse_successful=False,
                notes=f"Transcription successful but parsing failed: {str(e)}"
            )


# Singleton instance
_voice_transcriber_service: Optional[VoiceTranscriberService] = None


def get_voice_transcriber_service() -> VoiceTranscriberService:
    """
    Get the singleton VoiceTranscriberService instance.
    
    Returns:
        VoiceTranscriberService instance
    """
    global _voice_transcriber_service
    if _voice_transcriber_service is None:
        _voice_transcriber_service = VoiceTranscriberService()
    return _voice_transcriber_service
