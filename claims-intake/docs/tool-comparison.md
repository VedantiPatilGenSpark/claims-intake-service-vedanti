# Tool comparison

Compared this week's **chat agent** (plan and implement in the thread) with **Cursor the editor** (files, terminal, git, and the running app on my Mac). I did not run two models on the same prompt.

The bounded piece I did in Cursor rather than in the agent: **build and run the `linux/amd64` image locally, open Swagger, and POST a VALID-01 body.** The agent wrote the Dockerfile; Cursor was where Docker Desktop, the platform warning, and `/docs` actually existed.

## What the chat agent made easy

Walking a contract into code without losing the split between Stage A, Stage B, and 5xx. `routes.py` is a mapping layer: the agent kept rule logic out of it, reused `submit_notification`, and named the FastAPI default-422 trap before we hit it. Same for `evaluate_notification` returning `ValidationOutcome` so `detail` survived to HTTP. Multi-file context (contract section 6, `StubPolicyClient.fail_with`, integration table) stayed in one thread.

## What the chat agent made awkward

It cannot see my Mac. There is no `docker` in the remote environment, so "the image runs" was a command I had to execute myself. It also cannot click Swagger. For "does uvicorn actually listen on 8000?" the agent can only tell me what to run. Long call-stack explanations are useful, but they are slower than putting a breakpoint or hitting Try it out.

## What Cursor made easy

The editor is where the repo, the terminal, and Docker Desktop meet. `docker buildx build --platform linux/amd64` and `docker run -p 8000:8000` only make sense on the machine that has the daemon. The amd64-vs-arm64 warning showed up there; `/docs` showed the one `POST /notifications` route; I could paste a body and see 201 then 409 without writing another test. Git add/commit from the same cwd as `Dockerfile` was ordinary.

## What Cursor made awkward

Cursor does not hold the contract in its head across days. If I had implemented `routes.py` only as inline edits, it would have been easy to ship FastAPI's 422 body or drop `detail` on field rules. The editor is also a weak place to decide evaluation order or V-1 vs `PolicyLookupFailed`: those are design questions, and the file view does not argue back with section 6.

## When I would reach for which

I would use the **chat agent** for **mapping a written API contract onto an HTTP adapter** (status codes, envelopes, exception handlers, tests that assert JSON). I would use **Cursor** for **running and probing the service on my machine** (Docker platform builds, Swagger, confirming a warning is harmless). I would not swap those: the agent cannot complete the amd64 run AC, and the editor is the wrong tool to invent the 400-vs-422 split from a blank `routes.py`.
