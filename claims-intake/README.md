# Claims Intake Service

A service that accepts a first notice of loss from the claims portal, validates it
against the policy master and the rule table in `docs/api-contract.md`, and either
records the notification and issues a claim reference or refuses the submission
with a specific reason.

The HTTP surface is `POST /notifications`. A valid, admissible body returns `201`
with a claim reference. A body that cannot be interpreted returns `400`. A
notification that fails a business rule returns the status and error envelope in
the contract. A policy-master lookup failure returns `502`, `503`, or `504`.

## Where things are

| Path | What it holds |
| --- | --- |
| `docs/api-contract.md` | What the service accepts, returns, and refuses. The authority. |
| `docs/requirements-brief.md` | The open work items and their acceptance criteria. |
| `docs/payload-triage.md` | Day 1 classification of the edge payloads. |
| `data/` | Synthetic policies and notification payloads. |
| `src/claims/` | The service (models, rules, repository, HTTP). |
| `tests/unit/` | Function-level tests. |
| `tests/integration/` | HTTP tests against `POST /notifications`. |
| `Dockerfile` | Image that runs the service. |

## Working in this repository

You are inside a Linux container. Confirm it before you start:

```
uname -sm     # Linux aarch64
pwd           # directory that contains this README and pyproject.toml
```

If you cloned the GitHub repository, that directory is the inner `claims-intake/`
folder (the one with `pyproject.toml`), not the git root above it.

Dependencies are installed when the container is created. There is no install
step. If a tool you need is missing, that is a defect in the image specification
and should be reported rather than worked around.

All commands below are run from this directory.

## Run the service

```
uv run uvicorn claims.api.routes:app --host 0.0.0.0 --port 8000
```

The process listens on port `8000`. Submit a notification:

```
POST /notifications
Content-Type: application/json
```

Interactive docs are at `http://localhost:8000/docs` when the server is running.

Example body (admissible; returns `201`):

```
{
  "policy_number": "MOT-4471",
  "loss_date": "2026-04-02",
  "claim_type": "collision",
  "estimated_amount": "4200.00",
  "description": "Rear ended at a junction."
}
```

`estimated_amount` must be a string with exactly two decimal places.

## Run the tests

```
uv run pytest
uv run ruff check .
uv run mypy src tests
```

`uv run pytest` runs unit tests and the HTTP integration tests.

## Run from the Docker image

Build and run (Docker must already be available on the machine; do not install it
as part of following this README):

```
docker buildx build --platform linux/amd64 -t claims-intake .
docker run --rm -p 8000:8000 claims-intake
```

The service is then at `http://localhost:8000` (same `POST /notifications` as
above).

### Why `--platform linux/amd64`

`linux/amd64` is the platform string for Linux on a 64-bit x86 CPU (what most
servers and CI runners use). The flag is on **build**, so the image is always
that platform even when you build on an Apple Silicon Mac (`linux/arm64`).
Without it, Docker would bake an arm64 image that does not match this lab's
amd64 requirement or a typical production host. When you `docker run` that
amd64 image on an arm64 machine, Docker emulates amd64 and warns that image
and host do not match. That warning is expected; it does not mean the start
failed.

## Data

Everything in `data/` is synthetic and was authored for this program. It contains
no real client data and no named clients.
