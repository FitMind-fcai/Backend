from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel


class CoachingMessageResponse(BaseModel):
    id: int
    category: str
    urgency: str
    title: str
    body: str
    is_read: bool
    created_at: datetime

    model_config = {"from_attributes": True}


class CoachingMessageListResponse(BaseModel):
    messages: List[CoachingMessageResponse]
    unread_count: int


class CoachingStatusResponse(BaseModel):
    urgency: str
    overall_score: float
    on_track: bool
    calorie_adherence_pct: Optional[float] = None
    workout_frequency_adherence_pct: Optional[float] = None
    suggestion: str
    generated_at: datetime
