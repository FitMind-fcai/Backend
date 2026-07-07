"""
DTOs for Voice Transcriber Service.
"""
from pydantic import BaseModel, Field
from typing import Optional, List
from enum import Enum


class TranscriptionContextType(str, Enum):
    MEAL_LOG = "meal_log"
    WORKOUT_LOG = "workout_log"
    GENERAL = "general"


# ========================================
# INPUT DTOs
# ========================================

class TranscriptionRequestDTO(BaseModel):
    audio_bytes: bytes = Field(..., description="Raw audio bytes")
    audio_format: str = Field(default="mp3", description="mp3 | wav | m4a | webm | ogg | flac")
    language: Optional[str] = Field(None, description="Language code (auto-detected if omitted)")
    context_type: TranscriptionContextType = Field(default=TranscriptionContextType.GENERAL)
    prompt_hint: Optional[str] = Field(None, description="Optional Whisper prompt hint")

    model_config = {"arbitrary_types_allowed": True}


# ========================================
# BASE TRANSCRIPTION RESULT
# ========================================

class TranscriptionResultDTO(BaseModel):
    text: str
    language: str
    duration_seconds: Optional[float] = None
    confidence: Optional[float] = Field(None, ge=0, le=1)
    transcription_successful: bool = True
    error_message: Optional[str] = None


# ========================================
# PARSED LOG DTOs
# ========================================

class MealLogTranscriptionDTO(BaseModel):
    """Structured meal data extracted from transcription."""
    raw_text: str
    meal_name: Optional[str] = Field(None, description="Combined/inferred meal name (e.g. 'Grilled Chicken and Rice')")
    meal_type: Optional[str] = Field(None, description="Breakfast / Lunch / Dinner / Snack")
    food_items: List[str] = Field(default_factory=list, description="Detected food item names")
    portions: List[str] = Field(default_factory=list, description="Detected portion strings (parallel to food_items)")
    tags: List[str] = Field(default_factory=list, description="Semantic tags extracted by LLM for vector search")
    estimated_calories: Optional[float] = Field(None, ge=0)
    estimated_protein_g: Optional[float] = Field(None, ge=0)
    estimated_carbs_g: Optional[float] = Field(None, ge=0)
    estimated_fats_g: Optional[float] = Field(None, ge=0)
    parse_successful: bool = True
    notes: Optional[str] = None


class ParsedExerciseDTO(BaseModel):
    """A single exercise entry parsed from workout transcription."""
    name: str = Field(..., description="Spoken exercise name")
    sets: Optional[int] = Field(None, ge=1)
    reps: Optional[int] = Field(None, ge=1)
    weight_str: Optional[str] = Field(None, description="Weight as spoken, e.g. '50kg', '80 pounds'")
    weight_kg: Optional[float] = Field(None, ge=0, description="Parsed weight in kg (None if not mentioned)")
    duration_seconds: Optional[int] = Field(None, ge=1, description="Duration in seconds if mentioned instead of sets/reps")


class WorkoutLogTranscriptionDTO(BaseModel):
    """Structured workout data extracted from transcription + per-exercise vector matches."""
    raw_text: str
    exercises: List[ParsedExerciseDTO] = Field(default_factory=list)
    duration_mentioned: Optional[str] = Field(None, description="Total session duration if mentioned")
    tags: List[str] = Field(default_factory=list, description="Semantic workout tags (muscle groups, equipment, etc.)")
    parse_successful: bool = True
    notes: Optional[str] = None


class WeightLogTranscriptionDTO(BaseModel):
    """Weight value extracted from a voice recording."""
    raw_text: str
    extracted_weight_kg: Optional[float] = Field(None, ge=0, description="Weight in kg (lbs auto-converted)")
    notes: Optional[str] = None
    parse_successful: bool = True
