"""Boundary models for the claims intake service.

Everything that enters the service is parsed into one of these before any rule
runs. A payload that reaches the rule layer has already been proven well formed,
which is what keeps a shape problem and a content problem from arriving at the
caller as the same status code.

Day 2 assignment. Implement these against `docs/api-contract.md` sections 2 and 3.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

ClaimType = Literal["collision", "theft", "glass", "liability", "weather"]


@dataclass(frozen=True)
class RuleFailure:
    """A single rule decision that refused a notification.

    `rule` is the identifier (V-2). `code` is the contract error code
    (LOSS_BEFORE_INCEPTION). They are separate fields so one cannot be passed
    where the other is expected.
    """

    rule: str
    code: str


class NotificationRequest(BaseModel):
    """A first notice of loss as submitted by the claims portal.

    Fields and their constraints are specified in contract section 2.2. The model
    is responsible for the shape of the request and for nothing else. Whether the
    policy exists, whether the loss falls inside the term, and whether the amount
    is within the limit are rules, and rules live in `service.py`.
    """

    model_config = ConfigDict(extra="forbid")

    policy_number: str = Field(min_length=1)
    loss_date: date
    claim_type: ClaimType
    estimated_amount: Decimal
    description: str | None = None

    @field_validator("estimated_amount", mode="before")
    @classmethod
    def estimated_amount_is_two_place_decimal(cls, value: object) -> Decimal:
        """Accept a Decimal or a decimal string with exactly two places.

        Float is refused because it is not a decimal. Values with any other
        scale are refused rather than rounded, per contract section 4.1.
        """
        if isinstance(value, bool) or not isinstance(value, (str, Decimal)):
            raise ValueError(
                "estimated_amount must be a decimal string with exactly two decimal places"
            )
        try:
            amount = value if isinstance(value, Decimal) else Decimal(value)
        except InvalidOperation as exc:
            raise ValueError("estimated_amount is not a decimal") from exc
        if amount.as_tuple().exponent != -2:
            raise ValueError(
                "estimated_amount must have exactly two decimal places; the service does not round"
            )
        if amount <= 0:
            raise ValueError("estimated_amount must be greater than zero")
        return amount


class Policy(BaseModel):
    """A policy as this service works with it.

    Built from the `PolicyRecord` the policy client returns. The fields the rules
    compare against are the reason this model exists. Every field is required
    because the master always sends it; `cancellation_date` may be `None`.
    """

    policy_number: str
    product: str
    effective_date: date
    expiry_date: date
    cancellation_date: date | None
    limit: Decimal
    permitted_claim_types: tuple[ClaimType, ...]


class RecordedNotification(BaseModel):
    """A notification that passed every rule and was written.

    Carries the claim reference issued at the time it was recorded. Contract
    section 3 fixes the reference format. The remaining fields are the
    notification as stored, including the three keys WI-0151 matches on.
    """

    claim_reference: str = Field(pattern=r"^CLM-\d{4}-\d{6}$")
    policy_number: str = Field(min_length=1)
    loss_date: date
    claim_type: ClaimType
    estimated_amount: Decimal
    description: str | None = None
