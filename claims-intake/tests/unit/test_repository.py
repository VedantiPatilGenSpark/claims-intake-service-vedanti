"""Unit tests for recording, unique references, and duplicate matching."""

from __future__ import annotations

import re
from datetime import date
from decimal import Decimal

import pytest

from claims.models import NotificationRequest
from claims.repository import NotificationRepository

CLAIM_REFERENCE = re.compile(r"^CLM-\d{4}-\d{6}$")


@pytest.fixture
def repository() -> NotificationRepository:
    return NotificationRepository()


def _request(**overrides: object) -> NotificationRequest:
    body: dict[str, object] = {
        "policy_number": "MOT-4471",
        "loss_date": date(2026, 4, 2),
        "claim_type": "collision",
        "estimated_amount": Decimal("4200.00"),
        "description": "Rear ended at a junction.",
    }
    body.update(overrides)
    return NotificationRequest.model_validate(body)


def test_record_writes_notification_and_issues_reference(
    repository: NotificationRepository,
) -> None:
    request = _request()
    recorded = repository.record(request)
    assert CLAIM_REFERENCE.match(recorded.claim_reference)
    assert recorded.policy_number == request.policy_number
    assert recorded.loss_date == request.loss_date
    assert recorded.claim_type == request.claim_type
    assert recorded.estimated_amount == request.estimated_amount
    assert recorded.description == request.description


def test_record_issues_unique_references(repository: NotificationRepository) -> None:
    first = repository.record(_request())
    second = repository.record(
        _request(
            policy_number="MOT-4472",
            loss_date=date(2026, 3, 18),
            claim_type="theft",
            estimated_amount=Decimal("12500.00"),
        )
    )
    assert CLAIM_REFERENCE.match(first.claim_reference)
    assert CLAIM_REFERENCE.match(second.claim_reference)
    assert first.claim_reference != second.claim_reference


def test_find_matching_returns_recorded_triple(repository: NotificationRepository) -> None:
    recorded = repository.record(_request())
    found = repository.find_matching(
        policy_number="MOT-4471",
        loss_date=date(2026, 4, 2),
        claim_type="collision",
    )
    assert found is not None
    assert found.claim_reference == recorded.claim_reference


@pytest.mark.parametrize(
    ("policy_number", "loss_date", "claim_type"),
    [
        pytest.param("MOT-4472", date(2026, 4, 2), "collision", id="different_policy_number"),
        pytest.param("MOT-4471", date(2026, 4, 3), "collision", id="different_loss_date"),
        pytest.param("MOT-4471", date(2026, 4, 2), "theft", id="different_claim_type"),
    ],
)
def test_find_matching_requires_all_three_fields(
    repository: NotificationRepository,
    policy_number: str,
    loss_date: date,
    claim_type: str,
) -> None:
    repository.record(_request())
    assert (
        repository.find_matching(
            policy_number=policy_number,
            loss_date=loss_date,
            claim_type=claim_type,
        )
        is None
    )


def test_rejected_notification_is_not_a_duplicate(repository: NotificationRepository) -> None:
    request = _request()
    assert (
        repository.find_matching(
            request.policy_number,
            request.loss_date,
            request.claim_type,
        )
        is None
    )
    recorded = repository.record(request)
    assert recorded.claim_reference is not None
