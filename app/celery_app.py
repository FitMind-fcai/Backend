from celery import Celery
from celery.schedules import crontab

from app.core.config import REDIS_HOST, REDIS_PORT, REDIS_PASSWORD

_auth   = f":{REDIS_PASSWORD}@" if REDIS_PASSWORD else ""
BROKER  = f"redis://{_auth}{REDIS_HOST}:{REDIS_PORT}/1"
BACKEND = f"redis://{_auth}{REDIS_HOST}:{REDIS_PORT}/2"

celery_app = Celery(
    "fitmind",
    broker=BROKER,
    backend=BACKEND,
    include=["app.notification_module.tasks"],
)

celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="UTC",
    enable_utc=True,
    # ── Periodic schedule ────────────────────────────────────────────────────
    beat_schedule={
        # Every 30 minutes during the day — service filters to waking hours
        "hydration-reminders": {
            "task": "app.notification_module.tasks.send_hydration_reminders",
            "schedule": crontab(minute="*/30"),
        },
        # Every 15 minutes — service fires only within the reminder window per meal
        "meal-reminders": {
            "task": "app.notification_module.tasks.send_meal_reminders",
            "schedule": crontab(minute="*/15"),
        },
        # Every hour — service filters by each user's preferred UTC hour
        "workout-reminders": {
            "task": "app.notification_module.tasks.send_workout_reminders",
            "schedule": crontab(minute="0"),
        },
        # Every hour — service filters by each user's preferred UTC hour
        "sleep-reminders": {
            "task": "app.notification_module.tasks.send_sleep_reminders",
            "schedule": crontab(minute="0"),
        },
    },
)
