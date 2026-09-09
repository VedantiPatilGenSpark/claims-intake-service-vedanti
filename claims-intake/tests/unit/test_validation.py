"""Unit tests for Stage B rules, written from the contract before the engine exists."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from claims.models import NotificationRequest, Policy, RuleFailure
from claims.policy_client import LookupFailureReason, PolicyLookupFailed, StubPolicyClient
from claims.repository import NotificationRepository
from claims.service import (
    evaluate_amount_within_limit,
    evaluate_claim_type_covered,
    evaluate_loss_after_inception,
    evaluate_loss_before_expiry,
    evaluate_not_cancelled,
    evaluate_not_duplicate,
    evaluate_notification,
    evaluate_policy_exists,
    submit_notification,
)

STANDARD_TYPES = ("collision", "theft", "glass", "liability", "weather")
NAMED_PERILS_TYPES = ("theft", "glass", "weather", "liability")


def _request(**overrides: object) -> NotificationRequest:
    body: dict[str, object] = {
        "policy_number": "MOT-4471",
        "loss_date": date(2026, 4, 2),
        "claim_type": "collision",
        "estimated_amount": Decimal("4200.00"),
    }
    body.update(overrides)
    return NotificationRequest.model_validate(body)


def _policy(**overrides: object) -> Policy:
    body: dict[str, object] = {
        "policy_number": "MOT-4471",
        "product": "personal_auto_standard",
        "effective_date": date(2026, 3, 1),
        "expiry_date": date(2027, 2, 28),
        "cancellation_date": None,
        "limit": Decimal("50000.00"),
        "permitted_claim_types": STANDARD_TYPES,
    }
    body.update(overrides)
    return Policy.model_validate(body)


@pytest.fixture
def policy_client() -> StubPolicyClient:
    return StubPolicyClient()


@pytest.fixture
def repository() -> NotificationRepository:
    return NotificationRepository()


@pytest.mark.parametrize(
    ("policy_number", "passed"),
    [
        pytest.param("MOT-4471", True, id="policy_exists"),
        pytest.param("MOT-9999", False, id="policy_missing"),
        pytest.param("mot-4471", False, id="policy_number_case_sensitive"),
    ],
)
def test_v1_policy_exists(
    policy_client: StubPolicyClient,
    policy_number: str,
    passed: bool,
) -> None:
    outcome = evaluate_policy_exists(_request(policy_number=policy_number), policy_client)
    assert outcome.passed is passed
    if not passed:
        assert outcome.rule == "V-1"
        assert outcome.code == "POLICY_NOT_FOUND"


@pytest.mark.parametrize(
    ("loss_date", "passed"),
    [
        pytest.param(date(2026, 3, 14), False, id="before_inception"),
        pytest.param(date(2026, 3, 15), True, id="on_inception"),
        pytest.param(date(2026, 3, 16), True, id="after_inception"),
    ],
)
def test_v2_loss_after_inception(loss_date: date, passed: bool) -> None:
    policy = _policy(effective_date=date(2026, 3, 15))
    outcome = evaluate_loss_after_inception(_request(loss_date=loss_date), policy)
    assert outcome.passed is passed
    if not passed:
        assert outcome.rule == "V-2"
        assert outcome.code == "LOSS_BEFORE_INCEPTION"


@pytest.mark.parametrize(
    ("cancellation_date", "loss_date", "passed"),
    [
        pytest.param(None, date(2026, 3, 1), True, id="cancellation_date_absent"),
        pytest.param(date(2026, 1, 15), date(2026, 1, 14), True, id="before_cancellation"),
        pytest.param(date(2026, 1, 15), date(2026, 1, 15), False, id="on_cancellation"),
        pytest.param(date(2026, 1, 15), date(2026, 1, 16), False, id="after_cancellation"),
    ],
)
def test_v7_not_cancelled(
    cancellation_date: date | None,
    loss_date: date,
    passed: bool,
) -> None:
    policy = _policy(cancellation_date=cancellation_date)
    outcome = evaluate_not_cancelled(_request(loss_date=loss_date), policy)
    assert outcome.passed is passed
    if not passed:
        assert outcome.rule == "V-7"
        assert outcome.code == "POLICY_CANCELLED"


@pytest.mark.parametrize(
    ("loss_date", "passed"),
    [
        pytest.param(date(2026, 2, 27), True, id="before_expiry"),
        pytest.param(date(2026, 2, 28), True, id="on_expiry"),
        pytest.param(date(2026, 3, 1), False, id="after_expiry"),
    ],
)
def test_v3_loss_before_expiry(loss_date: date, passed: bool) -> None:
    policy = _policy(expiry_date=date(2026, 2, 28))
    outcome = evaluate_loss_before_expiry(_request(loss_date=loss_date), policy)
    assert outcome.passed is passed
    if not passed:
        assert outcome.rule == "V-3"
        assert outcome.code == "LOSS_AFTER_EXPIRY"


@pytest.mark.parametrize(
    ("estimated_amount", "passed"),
    [
        pytest.param(Decimal("9999.99"), True, id="below_limit"),
        pytest.param(Decimal("10000.00"), True, id="equal_to_limit"),
        pytest.param(Decimal("10000.01"), False, id="above_limit"),
    ],
)
def test_v4_amount_within_limit(estimated_amount: Decimal, passed: bool) -> None:
    policy = _policy(limit=Decimal("10000.00"))
    outcome = evaluate_amount_within_limit(
        _request(estimated_amount=estimated_amount),
        policy,
    )
    assert outcome.passed is passed
    if not passed:
        assert outcome.rule == "V-4"
        assert outcome.code == "AMOUNT_EXCEEDS_LIMIT"


@pytest.mark.parametrize(
    ("claim_type", "permitted", "passed"),
    [
        pytest.param("theft", NAMED_PERILS_TYPES, True, id="type_permitted"),
        pytest.param("collision", NAMED_PERILS_TYPES, False, id="type_not_on_product"),
    ],
)
def test_v5_claim_type_covered(
    claim_type: str,
    permitted: tuple[str, ...],
    passed: bool,
) -> None:
    policy = _policy(product="personal_auto_named_perils", permitted_claim_types=permitted)
    outcome = evaluate_claim_type_covered(_request(claim_type=claim_type), policy)
    assert outcome.passed is passed
    if not passed:
        assert outcome.rule == "V-5"
        assert outcome.code == "TYPE_NOT_COVERED"


@pytest.mark.parametrize(
    "setup",
    [
        pytest.param("none_recorded", id="no_existing_record"),
        pytest.param("same_triple", id="duplicate_of_recorded"),
        pytest.param("two_fields", id="only_two_fields_match"),
        pytest.param("never_recorded", id="rejected_is_not_duplicate"),
    ],
)
def test_v6_not_duplicate(repository: NotificationRepository, setup: str) -> None:
    request = _request()
    if setup == "same_triple":
        repository.record(request)
    elif setup == "two_fields":
        repository.record(_request(claim_type="theft"))
    outcome = evaluate_not_duplicate(request, repository)
    if setup == "same_triple":
        assert outcome.passed is False
        assert outcome.rule == "V-6"
        assert outcome.code == "DUPLICATE_NOTIFICATION"
        return
    assert outcome.passed is True


def test_evaluate_notification_prefers_cancellation_over_expiry() -> None:
    notification = _request(loss_date=date(2026, 1, 8), policy_number="MOT-4500")
    policy = _policy(
        policy_number="MOT-4500",
        effective_date=date(2025, 1, 1),
        expiry_date=date(2025, 12, 31),
        cancellation_date=date(2025, 10, 1),
    )
    failure = evaluate_notification(notification, policy)
    assert isinstance(failure, RuleFailure)
    assert failure.rule == "V-7"
    assert failure.code == "POLICY_CANCELLED"


def test_submit_policy_not_found_is_v1(
    policy_client: StubPolicyClient,
    repository: NotificationRepository,
) -> None:
    outcome = submit_notification(_request(policy_number="MOT-9999"), policy_client, repository)
    assert outcome.passed is False
    assert outcome.rule == "V-1"
    assert outcome.code == "POLICY_NOT_FOUND"


@pytest.mark.parametrize("reason", ["timeout", "unreachable", "unparsable"])
def test_submit_propagates_policy_lookup_failed(
    repository: NotificationRepository,
    reason: LookupFailureReason,
) -> None:
    client = StubPolicyClient(fail_with=reason)
    with pytest.raises(PolicyLookupFailed) as caught:
        submit_notification(_request(), client, repository)
    assert caught.value.reason == reason
