import json
import logging
import os
from typing import Dict, List, Optional

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


def send_push(token: str, title: str, body: str, data: Optional[Dict] = None) -> bool:
    """Send a single FCM push notification. Returns True on success."""
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
        # Optionally mark token as invalid here
        return False


def send_push_multi(tokens: List[str], title: str, body: str, data: Optional[Dict] = None) -> int:
    """Send to multiple tokens. Returns count of successful sends."""
    return sum(send_push(t, title, body, data) for t in tokens)
