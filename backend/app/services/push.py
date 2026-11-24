"""Push notifications (docs/COMMUNITY.md §10): a reminder to review, once a day.

A browser or installed app subscribes (`push_subscriptions`); the server signs each push with
its VAPID key and hands it to the browser vendor's push service. Off unless PUSH_VAPID_* is
set. The reminder goes out once per local day, from the hour the user chose, when questions
are due and the day's goal isn't reached yet. The loop runs in the API process
(`reminder_job`), every few minutes.
"""

import json
import logging
import uuid
from collections.abc import Callable
from datetime import datetime
from functools import lru_cache
from typing import Protocol

from sqlalchemy import delete, select
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import Settings, get_settings
from app.core.errors import ConflictError
from app.db.types import utc_now
from app.models.community import PushSubscription
from app.models.rewards import DailyActivity
from app.models.user import User
from app.services.mastery import service as mastery
from app.services.rewards.service import local_day, zone

logger = logging.getLogger(__name__)

MAX_SUBSCRIPTIONS = 10

# Title and text of the reminder, in the user's language ({n} questions due).
REMINDER: dict[str, tuple[str, str]] = {
    "en": ("Time to review", "{n} questions are waiting for you."),
    "it": ("È ora di ripassare", "Hai {n} domande da ripassare."),
    "es": ("Hora de repasar", "Tienes {n} preguntas para repasar."),
    "fr": ("C'est l'heure de réviser", "{n} questions vous attendent."),
    "de": ("Zeit zum Wiederholen", "{n} Fragen warten auf dich."),
    "zh": ("该复习了", "有 {n} 个问题等你复习。"),
    "ja": ("復習の時間です", "{n} 問が復習を待っています。"),
    "ar": ("حان وقت المراجعة", "لديك {n} سؤالًا للمراجعة."),
    "hi": ("दोहराने का समय", "{n} प्रश्न आपकी प्रतीक्षा में हैं।"),
}


class PushSender(Protocol):
    def send(self, subscription: PushSubscription, payload: dict[str, str]) -> bool:
        """False when the subscription is gone for good (the browser unsubscribed)."""


class WebPushSender:
    def __init__(self, private_key: str, contact: str) -> None:
        self._private_key = private_key
        self._contact = contact

    def send(self, subscription: PushSubscription, payload: dict[str, str]) -> bool:
        from pywebpush import WebPushException, webpush

        try:
            webpush(
                subscription_info={
                    "endpoint": subscription.endpoint,
                    "keys": {"p256dh": subscription.p256dh, "auth": subscription.auth},
                },
                data=json.dumps(payload),
                vapid_private_key=self._private_key,
                vapid_claims={"sub": self._contact},
                ttl=6 * 3600,
                timeout=10,
            )
        except WebPushException as exc:
            status = exc.response.status_code if exc.response is not None else None
            if status in (404, 410):
                return False
            logger.warning("Push not delivered (status %s)", status)
        except Exception:
            logger.exception("Push not delivered")
        return True


def build_sender(settings: Settings) -> PushSender | None:
    key = settings.push_vapid_private_key.get_secret_value()
    if not (settings.push_vapid_public_key and key and settings.push_contact):
        return None
    return WebPushSender(key, settings.push_contact)


@lru_cache
def _configured_sender() -> PushSender | None:
    return build_sender(get_settings())


def get_push_sender() -> PushSender | None:
    """FastAPI dependency (tests override it). None: push is off on this server."""
    return _configured_sender()


def subscribe(db: Session, user: User, endpoint: str, p256dh: str, auth: str) -> None:
    """Adds this browser (or moves it to this account: a browser has one subscription)."""
    row = db.scalar(select(PushSubscription).where(PushSubscription.endpoint == endpoint))
    if row is None:
        row = PushSubscription(endpoint=endpoint, user_id=user.id, p256dh=p256dh, auth=auth)
        db.add(row)
    row.user_id, row.p256dh, row.auth = user.id, p256dh, auth
    db.flush()
    old = db.scalars(
        select(PushSubscription.id)
        .where(PushSubscription.user_id == user.id)
        .order_by(PushSubscription.created_at.desc(), PushSubscription.id)
        .offset(MAX_SUBSCRIPTIONS)
    ).all()
    if old:
        db.execute(delete(PushSubscription).where(PushSubscription.id.in_(old)))
    db.commit()


def unsubscribe(db: Session, user: User, endpoint: str) -> None:
    db.execute(
        delete(PushSubscription).where(
            PushSubscription.user_id == user.id, PushSubscription.endpoint == endpoint
        )
    )
    db.commit()


def devices(db: Session, user_id: uuid.UUID) -> int:
    return len(
        db.scalars(select(PushSubscription.id).where(PushSubscription.user_id == user_id)).all()
    )


def _send_to(db: Session, sender: PushSender, user_id: uuid.UUID, payload: dict[str, str]) -> int:
    sent = 0
    for row in db.scalars(select(PushSubscription).where(PushSubscription.user_id == user_id)):
        if sender.send(row, payload):
            sent += 1
        else:
            db.delete(row)
    return sent


def send_test(db: Session, user: User, sender: PushSender | None) -> int:
    """A push to every device of the user, so they can see it works. Returns how many."""
    if sender is None:
        raise ConflictError(
            "Push notifications aren't available on this server.",
            details={"reason": "push_unavailable"},
        )
    title, _ = REMINDER.get(user.language, REMINDER["en"])
    sent = _send_to(db, sender, user.id, {"title": "Recallable", "body": title, "url": "/"})
    db.commit()
    return sent


def send_reminders(db: Session, sender: PushSender, now: datetime | None = None) -> int:
    """One pass: everyone whose reminder hour has come today and who has questions due.
    Returns how many people were reminded."""
    now = now or utc_now()
    user_ids = db.scalars(select(PushSubscription.user_id).distinct()).all()
    reminded = 0
    for user in db.scalars(select(User).where(User.id.in_(user_ids), User.is_active)):
        if user.reminder_hour is None:
            continue
        local = now.astimezone(zone(user.timezone))
        today = local_day(user.timezone, now)
        if local.hour < user.reminder_hour or user.last_reminded_on == today:
            continue
        # Decided for today, whatever follows: one look per day and person.
        user.last_reminded_on = today
        done = db.scalar(
            select(DailyActivity.attempts).where(
                DailyActivity.user_id == user.id, DailyActivity.day == today
            )
        )
        delta = local.utcoffset()
        offset = int(delta.total_seconds() // 60) if delta else 0
        due = sum(c.review_load.due_now for c in mastery.home_summary(db, user.id, offset).courses)
        if due > 0 and (done or 0) < user.daily_goal:
            title, body = REMINDER.get(user.language, REMINDER["en"])
            payload = {"title": title, "body": body.format(n=due), "url": "/review"}
            if _send_to(db, sender, user.id, payload):
                reminded += 1
        db.commit()
    return reminded


def reminder_job(
    session_factory: sessionmaker[Session], sender_of: Callable[[], PushSender | None]
) -> None:
    """One pass on its own session. Never raises: the loop must go on."""
    try:
        sender = sender_of()
        if sender is None:
            return
        with session_factory() as db:
            send_reminders(db, sender)
    except Exception:
        logger.exception("Sending review reminders failed")
