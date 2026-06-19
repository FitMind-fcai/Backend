from typing import List, Optional

from sqlalchemy.orm import Session

from app.recommendation_system.models.coaching_message import CoachingMessage


class CoachingMessageRepository:
    def __init__(self, db: Session):
        self.db = db

    def create(self, user_id: int, category: str, urgency: str, title: str, body: str) -> CoachingMessage:
        msg = CoachingMessage(
            user_id=user_id,
            category=category,
            urgency=urgency,
            title=title,
            body=body,
        )
        self.db.add(msg)
        self.db.commit()
        self.db.refresh(msg)
        return msg

    def list_for_user(
        self,
        user_id: int,
        skip: int = 0,
        limit: int = 20,
        category: Optional[str] = None,
        unread_only: bool = False,
    ) -> List[CoachingMessage]:
        q = self.db.query(CoachingMessage).filter(
            CoachingMessage.user_id == user_id,
            CoachingMessage.is_dismissed == False,
        )
        if category:
            q = q.filter(CoachingMessage.category == category)
        if unread_only:
            q = q.filter(CoachingMessage.is_read == False)
        return q.order_by(CoachingMessage.created_at.desc()).offset(skip).limit(limit).all()

    def count_unread(self, user_id: int) -> int:
        return self.db.query(CoachingMessage).filter(
            CoachingMessage.user_id == user_id,
            CoachingMessage.is_read == False,
            CoachingMessage.is_dismissed == False,
        ).count()

    def mark_read(self, message_id: int, user_id: int) -> Optional[CoachingMessage]:
        msg = self.db.query(CoachingMessage).filter(
            CoachingMessage.id == message_id,
            CoachingMessage.user_id == user_id,
        ).first()
        if msg:
            msg.is_read = True
            self.db.commit()
            self.db.refresh(msg)
        return msg

    def mark_all_read(self, user_id: int) -> int:
        count = self.db.query(CoachingMessage).filter(
            CoachingMessage.user_id == user_id,
            CoachingMessage.is_read == False,
        ).update({"is_read": True})
        self.db.commit()
        return count

    def dismiss(self, message_id: int, user_id: int) -> Optional[CoachingMessage]:
        msg = self.db.query(CoachingMessage).filter(
            CoachingMessage.id == message_id,
            CoachingMessage.user_id == user_id,
        ).first()
        if msg:
            msg.is_dismissed = True
            self.db.commit()
            self.db.refresh(msg)
        return msg
