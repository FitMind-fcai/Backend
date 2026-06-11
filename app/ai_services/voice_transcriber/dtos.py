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
# VECTOR SEARCH RESULT DTOs
# ========================================

class MatchedFoodDTO(BaseModel):
    """Central food matched by semantic similarity to spoken food items."""
    id: int
    food_name: str
    food_category: Optional[str] = None
    calories_per_100g: float
    protein_per_100g: float
    carbs_per_100g: float
    fats_per_100g: float
    fiber_per_100g: Optional[float] = None
    serving_size_g: Optional[float] = None
    serving_description: Optional[str] = None
    similarity_score: float = Field(..., ge=0, le=1)


class MatchedExerciseDTO(BaseModel):
    """Central exercise matched by semantic similarity to spoken exercise name."""
    id: int
    name: str
    exercise_type: str
    primary_muscle_group: str
    secondary_muscles: Optional[str] = None
    equipment_required: str
    difficulty_level: str
    location: str
    similarity_score: float = Field(..., ge=0, le=1)


# ========================================
# PARSED LOG DTOs
# ========================================

class MealLogTranscriptionDTO(BaseModel):
    """Structured meal data extracted from transcription + vector matches."""
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
    matched_foods: List[MatchedFoodDTO] = Field(default_factory=list, description="Top-5 similar foods from central catalog")
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
    matched_exercises: List[MatchedExerciseDTO] = Field(default_factory=list, description="Top-5 similar exercises from central catalog")


class WorkoutLogTranscriptionDTO(BaseModel):
    """Structured workout data extracted from transcription + per-exercise vector matches."""
    raw_text: str
    exercises: List[ParsedExerciseDTO] = Field(default_factory=list)
    duration_mentioned: Optional[str] = Field(None, description="Total session duration if mentioned")
    tags: List[str] = Field(default_factory=list, description="Semantic workout tags (muscle groups, equipment, etc.)")
    parse_successful: bool = True
    notes: Optional[str] = None
