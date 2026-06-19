from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.auth_module.core.dependencies import get_current_verified_user
from app.auth_module.models.user import User
from app.db.database import get_db
from app.recommendation_system.core.dependencies import get_recommendation_service
from app.recommendation_system.repositories.coaching_message_repository import CoachingMessageRepository
from app.recommendation_system.schemas.coaching import (
    CoachingMessageListResponse,
    CoachingMessageResponse,
    CoachingStatusResponse,
)
from app.recommendation_system.services.recommendation_service import RecommendationService
from sqlalchemy.orm import Session

coaching_router = APIRouter(prefix="/coaching")


@coaching_router.get(
    "/status",
    response_model=CoachingStatusResponse,
    tags=["Coaching"],
    summary="Get current coaching status",
    description=(
        "Returns a real-time on-track / off-track assessment based on the last 24 hours "
        "of logged data, using the same feature engineering as the daily suggestion endpoint."
    ),
)
def get_coaching_status(
    current_user: User = Depends(get_current_verified_user),
    service: RecommendationService = Depends(get_recommendation_service),
) -> CoachingStatusResponse:
    suggestion = service.get_daily_suggestion(user_id=current_user.id)
    report = service.get_progress_report(user_id=current_user.id, period="week")

    return CoachingStatusResponse(
        urgency=suggestion.urgency,
        overall_score=report.features.overall_consistency_score,
        on_track=report.features.on_track,
        calorie_adherence_pct=report.features.nutrition.calorie_adherence_pct,
        workout_frequency_adherence_pct=report.features.workout.frequency_adherence_pct,
        suggestion=suggestion.suggestion,
        generated_at=datetime.utcnow(),
    )


@coaching_router.get(
    "/messages",
    response_model=CoachingMessageListResponse,
    tags=["Coaching"],
    summary="List coaching messages",
    description=(
        "Returns coaching messages sent by the AI coach, newest first. "
        "Filter by category (`daily`, `weekly`, `alert`) or unread status."
    ),
)
def list_messages(
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    category: Optional[str] = Query(None, description="Filter by category: daily, weekly, alert"),
    unread_only: bool = Query(False),
    current_user: User = Depends(get_current_verified_user),
    db: Session = Depends(get_db),
) -> CoachingMessageListResponse:
    repo = CoachingMessageRepository(db)
    messages = repo.list_for_user(
        user_id=current_user.id,
        skip=skip,
        limit=limit,
        category=category,
        unread_only=unread_only,
    )
    unread_count = repo.count_unread(current_user.id)
    return CoachingMessageListResponse(
        messages=[CoachingMessageResponse.model_validate(m) for m in messages],
        unread_count=unread_count,
    )


@coaching_router.patch(
    "/messages/{message_id}/read",
    response_model=CoachingMessageResponse,
    tags=["Coaching"],
    summary="Mark a coaching message as read",
)
def mark_read(
    message_id: int,
    current_user: User = Depends(get_current_verified_user),
    db: Session = Depends(get_db),
) -> CoachingMessageResponse:
    repo = CoachingMessageRepository(db)
    msg = repo.mark_read(message_id, current_user.id)
    if not msg:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Message not found")
    return CoachingMessageResponse.model_validate(msg)


@coaching_router.post(
    "/messages/read-all",
    tags=["Coaching"],
    summary="Mark all coaching messages as read",
    status_code=status.HTTP_200_OK,
)
def mark_all_read(
    current_user: User = Depends(get_current_verified_user),
    db: Session = Depends(get_db),
):
    repo = CoachingMessageRepository(db)
    count = repo.mark_all_read(current_user.id)
    return {"marked_read": count}


@coaching_router.delete(
    "/messages/{message_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    tags=["Coaching"],
    summary="Dismiss a coaching message",
)
def dismiss_message(
    message_id: int,
    current_user: User = Depends(get_current_verified_user),
    db: Session = Depends(get_db),
):
    repo = CoachingMessageRepository(db)
    msg = repo.dismiss(message_id, current_user.id)
    if not msg:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Message not found")
