from fastapi import Depends
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.planning_module.services.plan_generation_service import PlanGenerationService


def get_plan_generation_service(db: Session = Depends(get_db)) -> PlanGenerationService:
    return PlanGenerationService(db)
