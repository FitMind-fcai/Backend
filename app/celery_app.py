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
        # Every 2 hours during waking hours (05:00-19:00 UTC = 08:00-22:00 Egypt UTC+3)
        "hydration-reminders": {
            "task": "app.notification_module.tasks.send_hydration_reminders",
            "schedule": crontab(minute="0", hour="5-19/2"),
        },
        # Every hour — service fires only within the reminder window per meal
        "meal-reminders": {
            "task": "app.notification_module.tasks.send_meal_reminders",
            "schedule": crontab(minute="0"),
        },
        # Every hour — service checks if user has logged sleep for yesterday
        "sleep-reminders": {
            "task": "app.notification_module.tasks.send_sleep_reminders",
            "schedule": crontab(minute="0"),
        },
        # Once daily at midnight Egypt time (21:00 UTC = 00:00 UTC+3)
        "daily-coaching": {
            "task": "app.notification_module.tasks.run_daily_coaching",
            "schedule": crontab(hour="21", minute="0"),
        },
        # Once a week on Sunday at 09:00 UTC (12:00 Egypt)
        "weekly-coaching": {
            "task": "app.notification_module.tasks.run_weekly_coaching",
            "schedule": crontab(hour="9", minute="0", day_of_week="0"),
        },
    },
)
