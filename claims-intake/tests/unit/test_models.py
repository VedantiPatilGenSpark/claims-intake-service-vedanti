"""Unit tests for request, policy, rule-failure, and recorded-notification models."""

from __future__ import annotations

import json
from dataclasses import FrozenInstanceError
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from claims.models import (
    NotificationRequest,
    Policy,
    RecordedNotification,
    RuleFailure,
)

DATA_DIR = Path(__file__).resolve().parents[2] / "data"
MODEL_REJECT_IDS = frozenset({"EDGE-08", "EDGE-11", "EDGE-12"})


def _load_fnol(filename: str) -> list[tuple[str, dict[str, Any]]]:
    rows = json.loads((DATA_DIR / filename).read_text())
    return [(row["id"], row["payload"]) for row in rows]


_VALID_PAYLOADS = _load_fnol("fnol_valid.json")
_EDGE_PAYLOADS = _load_fnol("fnol_edge.json")
_INVALID_PAYLOADS = _load_fnol("fnol_invalid.json")

_ACCEPT_CASES = [
    *_VALID_PAYLOADS,
    *[
        (payload_id, payload)
        for payload_id, payload in _EDGE_PAYLOADS + _INVALID_PAYLOADS
        if payload_id not in MODEL_REJECT_IDS
    ],
]
_BOUNDARY_CASES = [
    (payload_id, payload, payload_id not in MODEL_REJECT_IDS)
    for payload_id, payload in _EDGE_PAYLOADS + _INVALID_PAYLOADS
]


def _request_body(**overrides: object) -> dict[str, object]:
    body: dict[str, object] = {
        "policy_number": "MOT-4471",
        "loss_date": "2026-04-02",
        "claim_type": "collision",
        "estimated_amount": "4200.00",
    }
    body.update(overrides)
    return body


@pytest.mark.parametrize(
    ("payload_id", "payload"),
    _ACCEPT_CASES,
    ids=[payload_id for payload_id, _ in _ACCEPT_CASES],
)
def test_notification_request_accepts_well_formed_payloads(
    payload_id: str,
    payload: dict[str, Any],
) -> None:
    notification = NotificationRequest.model_validate(payload)
    assert notification.loss_date == date.fromisoformat(str(payload["loss_date"]))
    assert isinstance(notification.estimated_amount, Decimal)
    assert notification.policy_number == payload["policy_number"]


@pytest.mark.parametrize(
    "payload",
    [
        pytest.param(_request_body(extra="unexpected"), id="extra_field"),
        pytest.param(
            {
                "loss_date": "2026-04-02",
                "claim_type": "collision",
                "estimated_amount": "4200.00",
            },
            id="missing_policy_number",
        ),
        pytest.param(
            {
                "policy_number": "MOT-4471",
                "claim_type": "collision",
                "estimated_amount": "4200.00",
            },
            id="missing_loss_date",
        ),
        pytest.param(
            {
                "policy_number": "MOT-4471",
                "loss_date": "2026-04-02",
                "estimated_amount": "4200.00",
            },
            id="missing_claim_type",
        ),
        pytest.param(
            {
                "policy_number": "MOT-4471",
                "loss_date": "2026-04-02",
                "claim_type": "collision",
                "description": "Amount omitted by the portal.",
            },
            id="missing_estimated_amount",
        ),
        pytest.param(_request_body(policy_number=""), id="empty_policy_number"),
        pytest.param(_request_body(loss_date="04-02-2026"), id="invalid_loss_date"),
        pytest.param(_request_body(claim_type="flood"), id="unknown_claim_type"),
        pytest.param(
            _request_body(estimated_amount="3499.999"),
            id="amount_three_places",
        ),
        pytest.param(_request_body(estimated_amount="10.0"), id="amount_one_place"),
        pytest.param(
            _request_body(estimated_amount="5000"),
            id="amount_integer_string",
        ),
        pytest.param(_request_body(estimated_amount="0.00"), id="amount_zero"),
        pytest.param(_request_body(estimated_amount="-1.00"), id="amount_negative"),
        pytest.param(_request_body(estimated_amount=4200.00), id="amount_float"),
        pytest.param(_request_body(estimated_amount=4200), id="amount_int"),
    ],
)
def test_notification_request_rejects_malformed_payloads(payload: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        NotificationRequest.model_validate(payload)


@pytest.mark.parametrize(
    ("payload_id", "payload", "should_parse"),
    _BOUNDARY_CASES,
    ids=[payload_id for payload_id, _, _ in _BOUNDARY_CASES],
)
def test_fnol_payload_model_boundary(
    payload_id: str,
    payload: dict[str, Any],
    should_parse: bool,
) -> None:
    if should_parse:
        NotificationRequest.model_validate(payload)
        return
    with pytest.raises(ValidationError):
        NotificationRequest.model_validate(payload)


@pytest.mark.parametrize(
    "cancellation_date",
    [
        pytest.param(None, id="not_cancelled"),
        pytest.param(date(2026, 1, 15), id="cancelled"),
    ],
)
def test_policy_accepts_required_fields(cancellation_date: date | None) -> None:
    policy = Policy(
        policy_number="MOT-4471",
        product="personal_auto_standard",
        effective_date=date(2026, 3, 1),
        expiry_date=date(2027, 2, 28),
        cancellation_date=cancellation_date,
        limit=Decimal("50000.00"),
        permitted_claim_types=("collision", "theft", "glass", "liability", "weather"),
    )
    assert isinstance(policy.limit, Decimal)
    assert policy.cancellation_date == cancellation_date


def test_policy_rejects_omitted_cancellation_date() -> None:
    with pytest.raises(ValidationError):
        Policy.model_validate(
            {
                "policy_number": "MOT-4471",
                "product": "personal_auto_standard",
                "effective_date": date(2026, 3, 1),
                "expiry_date": date(2027, 2, 28),
                "limit": Decimal("50000.00"),
                "permitted_claim_types": (
                    "collision",
                    "theft",
                    "glass",
                    "liability",
                    "weather",
                ),
            }
        )


def test_rule_failure_stores_rule_and_code_separately() -> None:
    failure = RuleFailure(rule="V-2", code="LOSS_BEFORE_INCEPTION")
    assert failure.rule == "V-2"
    assert failure.code == "LOSS_BEFORE_INCEPTION"


@pytest.mark.parametrize("field", ["rule", "code"])
def test_rule_failure_is_immutable(field: str) -> None:
    failure = RuleFailure(rule="V-2", code="LOSS_BEFORE_INCEPTION")
    with pytest.raises(FrozenInstanceError):
        setattr(failure, field, "mutated")


@pytest.mark.parametrize(
    "claim_reference",
    [
        pytest.param("CLM-2026-000317", id="valid_reference"),
    ],
)
def test_recorded_notification_accepts_valid_reference(claim_reference: str) -> None:
    recorded = RecordedNotification(
        claim_reference=claim_reference,
        policy_number="MOT-4471",
        loss_date=date(2026, 4, 2),
        claim_type="collision",
        estimated_amount=Decimal("4200.00"),
    )
    assert recorded.claim_reference == claim_reference


@pytest.mark.parametrize(
    "claim_reference",
    [
        pytest.param("NOPE", id="not_a_reference"),
        pytest.param("CLM-26-1", id="wrong_pattern"),
    ],
)
def test_recorded_notification_rejects_invalid_reference(claim_reference: str) -> None:
    with pytest.raises(ValidationError):
        RecordedNotification(
            claim_reference=claim_reference,
            policy_number="MOT-4471",
            loss_date=date(2026, 4, 2),
            claim_type="collision",
            estimated_amount=Decimal("4200.00"),
        )
