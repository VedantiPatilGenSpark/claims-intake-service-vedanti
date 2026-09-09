"""HTTP surface for the claims intake service.

This layer does three things and no more: it parses the request, it calls the
service, and it maps the outcome to a status code. It holds no rule logic. A rule
that appears here is a rule the service layer cannot be tested for.

Day 4 lab. Implement against `docs/api-contract.md` sections 5 and 6.
"""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from claims.models import NotificationRequest
from claims.policy_client import PolicyClient, PolicyLookupFailed, StubPolicyClient
from claims.repository import NotificationRepository
from claims.service import ValidationOutcome, submit_notification

CODE_TO_STATUS: dict[str, int] = {
    "MALFORMED_REQUEST": 400,
    "DUPLICATE_NOTIFICATION": 409,
    "POLICY_NOT_FOUND": 422,
    "LOSS_BEFORE_INCEPTION": 422,
    "LOSS_AFTER_EXPIRY": 422,
    "AMOUNT_EXCEEDS_LIMIT": 422,
    "TYPE_NOT_COVERED": 422,
    "POLICY_CANCELLED": 422,
    "POLICY_MASTER_UNPARSABLE": 502,
    "POLICY_MASTER_UNREACHABLE": 503,
    "POLICY_MASTER_TIMEOUT": 504,
}

MESSAGES: dict[str, str] = {
    "MALFORMED_REQUEST": "The request body could not be interpreted.",
    "DUPLICATE_NOTIFICATION": "A notification for this loss is already recorded.",
    "POLICY_NOT_FOUND": "No policy exists for the submitted policy number.",
    "LOSS_BEFORE_INCEPTION": "The loss date precedes the policy effective date.",
    "LOSS_AFTER_EXPIRY": "The loss date falls after the policy expiry date.",
    "AMOUNT_EXCEEDS_LIMIT": "The estimated amount exceeds the policy limit.",
    "TYPE_NOT_COVERED": "The claim type is not covered on this policy.",
    "POLICY_CANCELLED": "The policy is cancelled on or before the loss date.",
    "POLICY_MASTER_UNPARSABLE": (
        "The policy master returned a response this service could not parse."
    ),
    "POLICY_MASTER_UNREACHABLE": "The policy master could not be reached.",
    "POLICY_MASTER_TIMEOUT": "The policy master did not respond in time.",
}

LOOKUP_FAILURE: dict[str, tuple[str, int]] = {
    "unparsable": ("POLICY_MASTER_UNPARSABLE", 502),
    "unreachable": ("POLICY_MASTER_UNREACHABLE", 503),
    "timeout": ("POLICY_MASTER_TIMEOUT", 504),
}

_WRONG_TYPE_SUFFIX = "_type"


def _envelope(code: str, detail: dict[str, Any]) -> dict[str, Any]:
    return {"code": code, "message": MESSAGES[code], "detail": detail}


def _field_from_loc(loc: tuple[object, ...]) -> str | None:
    parts = [part for part in loc if part not in {"body", "query", "path", "header"}]
    if not parts:
        return None
    last = parts[-1]
    return last if isinstance(last, str) else None


def _malformed_detail(error: dict[str, Any]) -> dict[str, Any]:
    err_type = str(error.get("type", ""))
    loc = tuple(error.get("loc", ()))
    field = _field_from_loc(loc)
    if err_type in {"json_invalid", "json_decode"} or err_type.startswith("json"):
        return {"reason": "invalid_json"}
    if err_type == "missing":
        reason = "missing_field"
    elif err_type == "extra_forbidden":
        reason = "unknown_field"
    elif err_type.endswith(_WRONG_TYPE_SUFFIX):
        reason = "wrong_type"
    else:
        reason = "invalid_value"
    detail: dict[str, Any] = {"reason": reason}
    if field is not None:
        detail["field"] = field
    return detail


def _failed_response(outcome: ValidationOutcome) -> JSONResponse:
    code = outcome.code
    if code is None:
        raise RuntimeError("failed validation outcome is missing a contract code")
    return JSONResponse(
        status_code=CODE_TO_STATUS[code],
        content=_envelope(code, outcome.detail),
    )


def create_app(
    policy_client: PolicyClient | None = None,
    repository: NotificationRepository | None = None,
) -> FastAPI:
    """Build the HTTP app.

    Defaults are the Week 1 stub client and an in-memory repository. Tests pass
    replacements so a lookup failure or a fresh store does not require a network.
    """
    app = FastAPI(title="Claims Intake Service")
    client = policy_client or StubPolicyClient()
    store = repository or NotificationRepository()

    @app.exception_handler(RequestValidationError)
    async def malformed_request(
        _request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        errors = exc.errors()
        detail = _malformed_detail(errors[0]) if errors else {"reason": "invalid_json"}
        return JSONResponse(
            status_code=CODE_TO_STATUS["MALFORMED_REQUEST"],
            content=_envelope("MALFORMED_REQUEST", detail),
        )

    @app.exception_handler(PolicyLookupFailed)
    async def policy_master_unavailable(
        _request: Request, exc: PolicyLookupFailed
    ) -> JSONResponse:
        code, status = LOOKUP_FAILURE[exc.reason]
        return JSONResponse(
            status_code=status,
            content=_envelope(code, {"dependency": "policy_master"}),
        )

    @app.post("/notifications")
    def post_notification(notification: NotificationRequest) -> JSONResponse:
        outcome = submit_notification(notification, client, store)
        if outcome.passed:
            return JSONResponse(
                status_code=201,
                content={
                    "claim_reference": outcome.claim_reference,
                    "status": "recorded",
                },
            )
        return _failed_response(outcome)

    return app


app = create_app()
