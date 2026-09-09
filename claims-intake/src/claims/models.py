"""Typed request, policy, and recorded-claim objects for claims intake."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

ClaimType = Literal["collision", "theft", "glass", "liability", "weather"]


@dataclass(frozen=True)
class RuleFailure:
    """Immutable pair of a rule identifier and its error code."""

    rule: str
    code: str


class NotificationRequest(BaseModel):
    """Parsed first notice of loss; rejects extra fields and invalid types."""

    model_config = ConfigDict(extra="forbid")

    policy_number: str = Field(min_length=1)
    loss_date: date
    claim_type: ClaimType
    estimated_amount: Decimal
    description: str | None = None

    @field_validator("estimated_amount", mode="before")
    @classmethod
    def estimated_amount_is_two_place_decimal(cls, value: object) -> Decimal:
        """Require a Decimal with exactly two places and a value greater than zero."""
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
    """Policy copied from the master; cancellation_date is None if not cancelled."""

    policy_number: str
    product: str
    effective_date: date
    expiry_date: date
    cancellation_date: date | None
    limit: Decimal
    permitted_claim_types: tuple[ClaimType, ...]


class RecordedNotification(BaseModel):
    """Stored notification plus its issued claim reference."""

    claim_reference: str = Field(pattern=r"^CLM-\d{4}-\d{6}$")
    policy_number: str = Field(min_length=1)
    loss_date: date
    claim_type: ClaimType
    estimated_amount: Decimal
    description: str | None = None
