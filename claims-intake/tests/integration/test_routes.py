"""HTTP integration tests for POST /notifications against the API contract."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from claims.api.routes import create_app
from claims.policy_client import LookupFailureReason, StubPolicyClient
from claims.repository import NotificationRepository

DATA_DIR = Path(__file__).resolve().parents[2] / "data"
CLAIM_REFERENCE = re.compile(r"^CLM-\d{4}-\d{6}$")

RULE_CASES = (
    pytest.param(
        "INVALID-01",
        422,
        "POLICY_NOT_FOUND",
        ("policy_number",),
        id="v1_policy_not_found",
    ),
    pytest.param(
        "INVALID-02",
        422,
        "LOSS_BEFORE_INCEPTION",
        ("loss_date", "effective_date"),
        id="v2_loss_before_inception",
    ),
    pytest.param(
        "INVALID-03",
        422,
        "LOSS_AFTER_EXPIRY",
        ("loss_date", "expiry_date"),
        id="v3_loss_after_expiry",
    ),
    pytest.param(
        "INVALID-04",
        422,
        "AMOUNT_EXCEEDS_LIMIT",
        ("estimated_amount", "limit"),
        id="v4_amount_exceeds_limit",
    ),
    pytest.param(
        "INVALID-05",
        422,
        "TYPE_NOT_COVERED",
        ("claim_type", "product", "permitted_claim_types"),
        id="v5_type_not_covered",
    ),
    pytest.param(
        "INVALID-07",
        422,
        "POLICY_CANCELLED",
        ("loss_date", "cancellation_date"),
        id="v7_policy_cancelled",
    ),
)

LOOKUP_CASES = (
    pytest.param("unparsable", 502, "POLICY_MASTER_UNPARSABLE", id="unparsable"),
    pytest.param("unreachable", 503, "POLICY_MASTER_UNREACHABLE", id="unreachable"),
    pytest.param("timeout", 504, "POLICY_MASTER_TIMEOUT", id="timeout"),
)


def _payloads(filename: str) -> dict[str, dict[str, Any]]:
    rows = json.loads((DATA_DIR / filename).read_text())
    return {row["id"]: row["payload"] for row in rows}


VALID = _payloads("fnol_valid.json")
INVALID = _payloads("fnol_invalid.json")


@pytest.fixture
def client() -> TestClient:
    return TestClient(create_app())


def test_valid_notification_returns_201_with_claim_reference(client: TestClient) -> None:
    """A well-formed admissible FNOL is recorded and returns 201 with a claim reference."""
    response = client.post("/notifications", json=VALID["VALID-01"])
    assert response.status_code == 201
    body = response.json()
    assert CLAIM_REFERENCE.match(body["claim_reference"])
    assert body["status"] == "recorded"


@pytest.mark.parametrize(
    ("payload_id", "status", "code", "detail_keys"),
    RULE_CASES,
)
def test_rule_rejection_returns_contract_status_code_and_detail(
    client: TestClient,
    payload_id: str,
    status: int,
    code: str,
    detail_keys: tuple[str, ...],
) -> None:
    """Each INVALID payload that is not a duplicate fails the named rule over HTTP."""
    response = client.post("/notifications", json=INVALID[payload_id])
    assert response.status_code == status
    body = response.json()
    assert body["code"] == code
    for key in detail_keys:
        assert key in body["detail"]


def test_duplicate_notification_returns_409_with_existing_reference(
    client: TestClient,
) -> None:
    """A second POST of the same triple returns 409 and the first claim reference."""
    first = client.post("/notifications", json=VALID["VALID-01"])
    assert first.status_code == 201
    recorded = first.json()["claim_reference"]
    second = client.post("/notifications", json=INVALID["INVALID-06"])
    assert second.status_code == 409
    body = second.json()
    assert body["code"] == "DUPLICATE_NOTIFICATION"
    assert body["detail"]["claim_reference"] == recorded


def test_missing_required_field_returns_400_malformed_request(client: TestClient) -> None:
    """Omitting a required field is Stage A: 400 MALFORMED_REQUEST, not a rule code."""
    payload = dict(VALID["VALID-01"])
    del payload["estimated_amount"]
    response = client.post("/notifications", json=payload)
    assert response.status_code == 400
    body = response.json()
    assert body["code"] == "MALFORMED_REQUEST"
    assert body["detail"]["reason"] == "missing_field"
    assert body["detail"]["field"] == "estimated_amount"


def test_extra_field_returns_400_malformed_request(client: TestClient) -> None:
    """An unknown field is rejected rather than accepted with the field ignored."""
    payload = dict(VALID["VALID-01"])
    payload["bonus"] = True
    response = client.post("/notifications", json=payload)
    assert response.status_code == 400
    body = response.json()
    assert body["code"] == "MALFORMED_REQUEST"
    assert body["detail"]["reason"] == "unknown_field"
    assert body["detail"]["field"] == "bonus"


@pytest.mark.parametrize(("reason", "status", "code"), LOOKUP_CASES)
def test_policy_lookup_failed_returns_distinct_5xx(
    reason: LookupFailureReason,
    status: int,
    code: str,
) -> None:
    """Each PolicyLookupFailed reason maps to its own 5xx code, never a 4xx."""
    client = TestClient(
        create_app(
            policy_client=StubPolicyClient(fail_with=reason),
            repository=NotificationRepository(),
        )
    )
    response = client.post("/notifications", json=VALID["VALID-01"])
    assert response.status_code == status
    assert response.status_code >= 500
    body = response.json()
    assert body["code"] == code
    assert body["detail"]["dependency"] == "policy_master"
