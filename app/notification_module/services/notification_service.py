from app.notification_module.repositories.device_token_repository import DeviceTokenRepository
from app.notification_module.repositories.notification_preference_repository import NotificationPreferenceRepository
from app.notification_module.schemas.notifications import NotificationPreferenceUpdate


class NotificationService:
    def __init__(
        self,
        token_repo: DeviceTokenRepository,
        pref_repo: NotificationPreferenceRepository,
    ):
        self.token_repo = token_repo
        self.pref_repo  = pref_repo

    def register_token(self, user_id: int, token: str, platform: str):
        return self.token_repo.upsert(user_id, token, platform)

    def deregister_token(self, token: str) -> None:
        self.token_repo.deactivate(token)

    def get_preferences(self, user_id: int):
        return self.pref_repo.get_or_create(user_id)

    def update_preferences(self, user_id: int, payload: NotificationPreferenceUpdate):
        updates = payload.model_dump(exclude_none=True)
        return self.pref_repo.update(user_id, **updates)
