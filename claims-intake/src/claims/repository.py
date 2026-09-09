"""In-memory store for recorded notifications."""

from __future__ import annotations

from datetime import date

from claims.models import NotificationRequest, RecordedNotification


class NotificationRepository:
    """Stores recorded notifications and issues unique claim references."""

    def __init__(self) -> None:
        self._records: list[RecordedNotification] = []
        self._next_sequence: int = 1

    def record(self, notification: NotificationRequest) -> RecordedNotification:
        """Write a notification and return it with a new claim reference."""
        recorded = RecordedNotification(
            claim_reference=f"CLM-{date.today().year}-{self._next_sequence:06d}",
            policy_number=notification.policy_number,
            loss_date=notification.loss_date,
            claim_type=notification.claim_type,
            estimated_amount=notification.estimated_amount,
            description=notification.description,
        )
        self._next_sequence += 1
        self._records.append(recorded)
        return recorded

    def find_matching(
        self,
        policy_number: str,
        loss_date: date,
        claim_type: str,
    ) -> RecordedNotification | None:
        """Return the stored notification matching all three fields, or None."""
        for recorded in self._records:
            if (
                recorded.policy_number == policy_number
                and recorded.loss_date == loss_date
                and recorded.claim_type == claim_type
            ):
                return recorded
        return None
