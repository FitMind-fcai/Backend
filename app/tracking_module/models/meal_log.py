from sqlalchemy import Column, Integer, String, Date, DateTime, ForeignKey, Float, Index
from sqlalchemy.sql import func

from app.db.database import Base


class MealLog(Base):
    __tablename__ = "meal_logs"
    __table_args__ = (
        Index("idx_meal_logs_user_date", "user_id", "log_date"),
        Index("idx_meal_logs_user_date_type", "user_id", "log_date", "meal_type"),
    )

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    central_food_id = Column(Integer, ForeignKey("central_foods.id"), nullable=True, index=True)

    log_date = Column(Date, nullable=False)
    meal_type = Column(String(50), nullable=False)
    meal_name = Column(String(255), nullable=False)
    servings = Column(Float, nullable=False, default=1.0)
    serving_size_g_snapshot = Column(Float, nullable=True)
    serving_description_snapshot = Column(String(100), nullable=True)

    calories = Column(Float, nullable=False)
    protein_g = Column(Float, nullable=False)
    carbs_g = Column(Float, nullable=False)
    fats_g = Column(Float, nullable=False)

    log_method = Column(String(20), nullable=False)
    image_url = Column(String(500), nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
