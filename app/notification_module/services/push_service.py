import json
import logging
import os
from typing import Dict, List, Optional

from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

_initialized = False


def _init_firebase() -> bool:
    global _initialized
    if _initialized:
        return True
    try:
        import firebase_admin
        from firebase_admin import credentials

        creds_json = os.getenv("FIREBASE_CREDENTIALS_JSON", "").strip()
        creds_path = os.getenv("FIREBASE_CREDENTIALS_PATH", "").strip()

        if creds_json:
            cred = credentials.Certificate(json.loads(creds_json))
        elif creds_path and os.path.exists(creds_path):
            cred = credentials.Certificate(creds_path)
        else:
            logger.warning("Firebase credentials not set — push notifications will be logged only")
            return False

        if not firebase_admin._apps:
            firebase_admin.initialize_app(cred)

        _initialized = True
        logger.info("Firebase Admin SDK initialised")
        return True
    except Exception as exc:
        logger.error(f"Firebase init failed: {exc}")
        return False


def _is_token_dead(exc: Exception) -> bool:
    from firebase_admin import messaging
    return isinstance(exc, (
        messaging.UnregisteredError,
        messaging.InvalidArgumentError,
        messaging.SenderIdMismatchError,
    ))


def send_push(token: str, title: str, body: str, data: Optional[Dict] = None) -> bool:
    if not _init_firebase():
        logger.info(f"[PUSH-MOCK] {title}: {body}  (token={token[:20]}…)")
        return False
    try:
        from firebase_admin import messaging

        msg = messaging.Message(
            notification=messaging.Notification(title=title, body=body),
            data={k: str(v) for k, v in (data or {}).items()},
            token=token,
            android=messaging.AndroidConfig(priority="high"),
            apns=messaging.APNSConfig(
                payload=messaging.APNSPayload(
                    aps=messaging.Aps(sound="default")
                )
            ),
        )
        messaging.send(msg)
        return True
    except Exception as exc:
        logger.warning(f"Push send failed (token={token[:20]}…): {exc}")
        return False


def send_push_multi(
    tokens: List[str],
    title: str,
    body: str,
    data: Optional[Dict] = None,
    db: Optional[Session] = None,
) -> int:
    """Send to multiple tokens. Returns count of successful sends.
    When a DB session is provided, tokens rejected by Firebase are deactivated."""
    if not _init_firebase():
        for t in tokens:
            logger.info(f"[PUSH-MOCK] {title}: {body}  (token={t[:20]}…)")
        return 0

    from firebase_admin import messaging

    success = 0
    dead_tokens: List[str] = []

    for t in tokens:
        try:
            msg = messaging.Message(
                notification=messaging.Notification(title=title, body=body),
                data={k: str(v) for k, v in (data or {}).items()},
                token=t,
                android=messaging.AndroidConfig(priority="high"),
                apns=messaging.APNSConfig(
                    payload=messaging.APNSPayload(
                        aps=messaging.Aps(sound="default")
                    )
                ),
            )
            messaging.send(msg)
            success += 1
        except Exception as exc:
            logger.warning(f"Push send failed (token={t[:20]}…): {exc}")
            if _is_token_dead(exc):
                dead_tokens.append(t)

    if dead_tokens and db:
        from app.notification_module.repositories.device_token_repository import DeviceTokenRepository
        repo = DeviceTokenRepository(db)
        for t in dead_tokens:
            repo.deactivate(t)
            logger.info(f"Deactivated dead token: {t[:20]}…")

    return success
