"""
DTOs (Data Transfer Objects) for Voice Transcriber Service.
These are used to pass data to/from the Voice Transcriber without coupling to any other module.
The Voice Transcriber is completely modular and independent.
"""
from pydantic import BaseModel, Field
from typing import Optional, List
from enum import Enum


class TranscriptionContextType(str, Enum):
    """Context type for transcription to improve accuracy."""
    MEAL_LOG = "meal_log"
    WORKOUT_LOG = "workout_log"
    GENERAL = "general"


# ========================================
# INPUT DTOs - What Voice Transcriber receives
# ========================================

class TranscriptionRequestDTO(BaseModel):
    """DTO for voice transcription request."""
    audio_base64: str = Field(..., description="Base64 encoded audio file")
    audio_format: str = Field(default="mp3", description="Audio format (mp3, wav, m4a, webm, ogg)")
    language: Optional[str] = Field(None, description="Language code (e.g., 'en', 'ar') - auto-detected if not provided")
    context_type: TranscriptionContextType = Field(
        default=TranscriptionContextType.GENERAL,
        description="Context for better transcription accuracy"
    )
    prompt_hint: Optional[str] = Field(
        None,
        description="Optional prompt hint to guide transcription (e.g., food names, exercise names)"
    )


# ========================================
# OUTPUT DTOs - What Voice Transcriber returns
# ========================================

class TranscriptionResultDTO(BaseModel):
    """DTO for transcription result."""
    text: str = Field(..., description="Transcribed text")
    language: str = Field(..., description="Detected or specified language code")
    duration_seconds: Optional[float] = Field(None, description="Audio duration in seconds")
    confidence: Optional[float] = Field(None, ge=0, le=1, description="Transcription confidence if available")
    transcription_successful: bool = Field(default=True, description="Whether transcription was successful")
    error_message: Optional[str] = Field(None, description="Error message if transcription failed")


class MealLogTranscriptionDTO(BaseModel):
    """DTO for parsed meal log from transcription."""
    raw_text: str = Field(..., description="Original transcribed text")
    meal_type: Optional[str] = Field(None, description="Detected meal type: Breakfast, Lunch, Dinner, Snack")
    food_items: List[str] = Field(default_factory=list, description="List of detected food items")
    portions: List[str] = Field(default_factory=list, description="List of detected portions/quantities")
    parse_successful: bool = Field(default=True, description="Whether parsing was successful")
    notes: Optional[str] = Field(None, description="Additional notes or context")


class WorkoutLogTranscriptionDTO(BaseModel):
    """DTO for parsed workout log from transcription."""
    raw_text: str = Field(..., description="Original transcribed text")
    exercises: List[str] = Field(default_factory=list, description="List of detected exercises")
    sets: List[int] = Field(default_factory=list, description="List of detected set counts")
    reps: List[int] = Field(default_factory=list, description="List of detected rep counts")
    weights: List[str] = Field(default_factory=list, description="List of detected weights")
    duration_mentioned: Optional[str] = Field(None, description="Duration if mentioned")
    parse_successful: bool = Field(default=True, description="Whether parsing was successful")
    notes: Optional[str] = Field(None, description="Additional notes or context")
