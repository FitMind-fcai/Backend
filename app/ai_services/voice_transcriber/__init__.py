"""
Voice Transcriber Service
Handles AI-powered speech-to-text using Groq API with Whisper model.
This module is completely modular and has NO dependencies on other app modules.
"""
from app.ai_services.voice_transcriber.voice_transcriber_service import (
    VoiceTranscriberService,
    get_voice_transcriber_service
)
from app.ai_services.voice_transcriber.dtos import (
    # Enums
    TranscriptionContextType,
    # Input DTOs
    TranscriptionRequestDTO,
    # Output DTOs
    TranscriptionResultDTO,
    MealLogTranscriptionDTO,
    WorkoutLogTranscriptionDTO
)

__all__ = [
    # Service
    "VoiceTranscriberService",
    "get_voice_transcriber_service",
    # Enums
    "TranscriptionContextType",
    # Input DTOs
    "TranscriptionRequestDTO",
    # Output DTOs
    "TranscriptionResultDTO",
    "MealLogTranscriptionDTO",
    "WorkoutLogTranscriptionDTO"
]
