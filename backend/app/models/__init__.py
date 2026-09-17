"""
Import every model here so that a single `from app.models import Base`
(or Alembic's env.py importing this package) registers all tables against
the shared metadata. Alembic autogenerate silently produces empty
migrations if a model exists but was never imported anywhere.
"""

from app.db.base import Base
from app.models.dead_letter_job import DeadLetterJob
from app.models.event import Event
from app.models.notification_delivery import NotificationDelivery
from app.models.notification_job import NotificationJob
from app.models.notification_template import NotificationTemplate

__all__ = [
    "Base",
    "Event",
    "NotificationJob",
    "NotificationDelivery",
    "NotificationTemplate",
    "DeadLetterJob",
]
