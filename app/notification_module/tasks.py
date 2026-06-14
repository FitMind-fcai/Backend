import logging

from app.celery_app import celery_app
from app.db.database import SessionLocal
from app.notification_module.services.reminder_service import ReminderService

logger = logging.getLogger(__name__)


@celery_app.task(name="app.notification_module.tasks.send_hydration_reminders")
def send_hydration_reminders():
    db = SessionLocal()
    try:
        ReminderService(db).send_hydration_reminders()
    except Exception as exc:
        logger.error(f"send_hydration_reminders failed: {exc}", exc_info=True)
    finally:
        db.close()


@celery_app.task(name="app.notification_module.tasks.send_meal_reminders")
def send_meal_reminders():
    db = SessionLocal()
    try:
        ReminderService(db).send_meal_reminders()
    except Exception as exc:
        logger.error(f"send_meal_reminders failed: {exc}", exc_info=True)
    finally:
        db.close()


@celery_app.task(name="app.notification_module.tasks.send_workout_reminders")
def send_workout_reminders():
    db = SessionLocal()
    try:
        ReminderService(db).send_workout_reminders()
    except Exception as exc:
        logger.error(f"send_workout_reminders failed: {exc}", exc_info=True)
    finally:
        db.close()


@celery_app.task(name="app.notification_module.tasks.send_sleep_reminders")
def send_sleep_reminders():
    db = SessionLocal()
    try:
        ReminderService(db).send_sleep_reminders()
    except Exception as exc:
        logger.error(f"send_sleep_reminders failed: {exc}", exc_info=True)
    finally:
        db.close()
