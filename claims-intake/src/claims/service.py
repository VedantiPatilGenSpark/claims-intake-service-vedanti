"""Rule evaluation and notification submission.

This module owns the decision. It does not know it was reached over HTTP, which
is why it can be tested by calling a function with a typed object and asserting on
the result with no server running. It does not know where notifications are
stored either. It knows the rules.

`evaluate_policy_exists` ships written. It is the pattern every other rule
follows: take the notification and whatever it needs, decide, and return a
`ValidationOutcome` that names the rule and carries the values the decision was
made on. Nothing prints, nothing raises for an ordinary refusal, and nothing
reaches for a status code, because a status code is a fact about HTTP and this
module does not know about HTTP.

Day 3 assignment. Build the remaining rules test-first against
`docs/api-contract.md` section 4.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, cast

from claims.models import ClaimType, NotificationRequest, Policy, RuleFailure
from claims.policy_client import PolicyClient, PolicyNotFound, PolicyRecord
from claims.repository import NotificationRepository


@dataclass(frozen=True)
class ValidationOutcome:
    """The result of evaluating one rule, or of evaluating them all.

    `passed` is the only thing a caller has to branch on. When it is false, `rule`
    names the rule that decided it, `code` is the stable contract code, and
    `detail` carries the values that produced the decision so that the person
    reading the eventual error can see which input was wrong.

    There is no status code here. Contract section 6 maps a code to a status, and
    that mapping is applied at the HTTP boundary.
    """

    passed: bool
    rule: str | None = None
    code: str | None = None
    detail: dict[str, Any] = field(default_factory=dict)
    claim_reference: str | None = None

    @classmethod
    def ok(cls, claim_reference: str | None = None) -> ValidationOutcome:
        return cls(passed=True, claim_reference=claim_reference)

    @classmethod
    def failed(cls, rule: str, code: str, **detail: Any) -> ValidationOutcome:
        return cls(passed=False, rule=rule, code=code, detail=detail)


def evaluate_policy_exists(
    notification: NotificationRequest,
    policy_client: PolicyClient,
) -> ValidationOutcome:
    """V-1. The policy must exist in the policy master.

    This rule is different from the others in one way that matters: it is the only
    one that reaches outside the service, so it is the only one that can fail for
    a reason that is not the caller's fault. `PolicyNotFound` is caught here and
    turned into an ordinary refusal, because a policy that does not exist is a
    fact about the caller's data. `PolicyLookupFailed` is deliberately not caught,
    because the caller did nothing wrong and the HTTP layer has to be able to tell
    the two apart. Contract section 6 fixes what each becomes.

    V-1 short circuits. Every other rule compares against a field on a policy, and
    if there is no policy there is nothing to compare against. Reporting
    LOSS_BEFORE_INCEPTION for a policy number that does not exist is not merely
    unhelpful, it is a false statement about the client's data (WI-0142, AC-4).
    """
    try:
        policy_client.get_policy(notification.policy_number)
    except PolicyNotFound:
        return ValidationOutcome.failed(
            rule="V-1",
            code="POLICY_NOT_FOUND",
            policy_number=notification.policy_number,
        )
    return ValidationOutcome.ok()


def evaluate_loss_after_inception(
    notification: NotificationRequest,
    policy: Policy,
) -> ValidationOutcome:
    """V-2. The loss must not precede policy inception.

    The boundary is stated in contract section 4.2 and in WI-0142 AC-3. A loss on
    the inception date is covered.
    """
    if notification.loss_date < policy.effective_date:
        return ValidationOutcome.failed(
            rule="V-2",
            code="LOSS_BEFORE_INCEPTION",
            loss_date=notification.loss_date.isoformat(),
            effective_date=policy.effective_date.isoformat(),
        )
    return ValidationOutcome.ok()


def evaluate_loss_before_expiry(
    notification: NotificationRequest,
    policy: Policy,
) -> ValidationOutcome:
    """V-3. The loss must not fall after the policy expiry date."""
    if notification.loss_date > policy.expiry_date:
        return ValidationOutcome.failed(
            rule="V-3",
            code="LOSS_AFTER_EXPIRY",
            loss_date=notification.loss_date.isoformat(),
            expiry_date=policy.expiry_date.isoformat(),
        )
    return ValidationOutcome.ok()


def evaluate_amount_within_limit(
    notification: NotificationRequest,
    policy: Policy,
) -> ValidationOutcome:
    """V-4. The estimated amount must not exceed the policy limit.

    An amount equal to the limit is within cover, per contract section 4.2.
    """
    if notification.estimated_amount > policy.limit:
        return ValidationOutcome.failed(
            rule="V-4",
            code="AMOUNT_EXCEEDS_LIMIT",
            estimated_amount=str(notification.estimated_amount),
            limit=str(policy.limit),
        )
    return ValidationOutcome.ok()


def evaluate_claim_type_covered(
    notification: NotificationRequest,
    policy: Policy,
) -> ValidationOutcome:
    """V-5. The claim type must be permitted on the policy's product."""
    if notification.claim_type not in policy.permitted_claim_types:
        return ValidationOutcome.failed(
            rule="V-5",
            code="TYPE_NOT_COVERED",
            claim_type=notification.claim_type,
            product=policy.product,
            permitted_claim_types=list(policy.permitted_claim_types),
        )
    return ValidationOutcome.ok()


def evaluate_not_cancelled(
    notification: NotificationRequest,
    policy: Policy,
) -> ValidationOutcome:
    """V-7. The loss must fall before cancellation when the policy is cancelled."""
    if policy.cancellation_date is not None and notification.loss_date >= policy.cancellation_date:
        return ValidationOutcome.failed(
            rule="V-7",
            code="POLICY_CANCELLED",
            loss_date=notification.loss_date.isoformat(),
            cancellation_date=policy.cancellation_date.isoformat(),
        )
    return ValidationOutcome.ok()


# Policy-field rules only, in contract section 4.1 order: V-2, V-7, V-3, V-4, V-5.
# V-1 uses the policy client and V-6 uses the repository, so they are not in this
# list. submit_notification runs V-1, then this list, then V-6.
POLICY_RULES = (
    evaluate_loss_after_inception,
    evaluate_not_cancelled,
    evaluate_loss_before_expiry,
    evaluate_amount_within_limit,
    evaluate_claim_type_covered,
)


def evaluate_not_duplicate(
    notification: NotificationRequest,
    repository: NotificationRepository,
) -> ValidationOutcome:
    """V-6. The loss event must not already be recorded."""
    existing = repository.find_matching(
        notification.policy_number,
        notification.loss_date,
        notification.claim_type,
    )
    if existing is not None:
        return ValidationOutcome.failed(
            rule="V-6",
            code="DUPLICATE_NOTIFICATION",
            claim_reference=existing.claim_reference,
        )
    return ValidationOutcome.ok()


def evaluate_notification(
    notification: NotificationRequest,
    policy: Policy,
) -> RuleFailure | None:
    """Evaluate policy-field rules in contract order and return the first failure."""
    for rule in POLICY_RULES:
        outcome = rule(notification, policy)
        if not outcome.passed:
            assert outcome.rule is not None
            assert outcome.code is not None
            return RuleFailure(rule=outcome.rule, code=outcome.code)
    return None


def _policy_from_record(record: PolicyRecord) -> Policy:
    return Policy(
        policy_number=record.policy_number,
        product=record.product,
        effective_date=record.effective_date,
        expiry_date=record.expiry_date,
        cancellation_date=record.cancellation_date,
        limit=record.limit,
        permitted_claim_types=cast(tuple[ClaimType, ...], record.permitted_claim_types),
    )


def submit_notification(
    notification: NotificationRequest,
    policy_client: PolicyClient,
    repository: NotificationRepository,
) -> ValidationOutcome:
    """Resolve the policy, evaluate, and record only if every rule passed.

    PolicyLookupFailed is not caught: the caller did nothing wrong and Day 4
    maps reason to 502/503/504. PolicyNotFound is V-1.
    """
    try:
        record = policy_client.get_policy(notification.policy_number)
    except PolicyNotFound:
        return ValidationOutcome.failed(
            rule="V-1",
            code="POLICY_NOT_FOUND",
            policy_number=notification.policy_number,
        )
    failure = evaluate_notification(notification, _policy_from_record(record))
    if failure is not None:
        return ValidationOutcome.failed(rule=failure.rule, code=failure.code)
    duplicate = evaluate_not_duplicate(notification, repository)
    if not duplicate.passed:
        return duplicate
    recorded = repository.record(notification)
    return ValidationOutcome.ok(claim_reference=recorded.claim_reference)

import json
