# Agent decision log

Engineering judgment during Days 3 and 4. Each entry names what the agent produced, what we decided, and a reason tied to an acceptance criterion or a failure that would have followed.

## 1. Rejected / corrected — implement every remaining rule in one change

**What the agent produced.** After the failing tests were committed, the agent proposed filling V-2, V-7, V-3, V-4, V-5, and V-6 in a single implementation step and a single commit, leaving `evaluate_notification` / `submit_notification` for later.

**What we decided.** Implement **one rule at a time**: write the function, run that rule’s parametrized tests, commit, then move to the next. Order: V-2, V-7, V-3, V-4, V-5, V-6, then the orchestrators.

**Reason.** Day 3 AC: `git log` must show a commit containing the tests **for a rule** before any commit containing **that rule’s** implementation. One combined rules commit still puts tests first globally, but it does not show which rule landed when, and a single bad comparison (for example V-7 treating `loss_date == cancellation_date` as covered) would land in the same commit as unrelated green rules. Incremental commits keep each boundary failure (`test_v2[before_inception]`, `test_v7[on_cancellation]`, …) pinned to the change that claimed to fix it. That is the TDD evidence the assignment grades, not a style preference.

## 2. Accepted — probe the CI gate with an unused import

**What the agent produced.** For assignment step 8 (“push a commit that deliberately fails one check”), the agent proposed appending `import json` to `src/claims/service.py` so ruff fails, then reverting after observing whether merge is blocked.

**What we decided.** Accept that method. The brief does not specify *how* to fail; it only requires that one check on the PR fails.

**Reason.** `checks.yaml` runs ruff as a job step that can fail the job. An unused import is a ruff failure of that step, which is a real check the gate defines. Breaking `tests/unit/test_validation.py` instead would fail pytest too, but it would also violate the AC that no test in that file is modified after the implementation was written. Changing `service.py` by one unused import, then reverting it, probes the gate without rewriting a rule or that test file.

## 3. Step 8 observation — failing check did not block merge

**What we did.** Pushed `test(ci): deliberate ruff failure to probe the gate` (unused `import json`). The **checks** job failed.

**What we observed.** Merge remained **clickable**. The button was grey, not green, and the PR reported no conflicts with the base branch, but **Merge pull request** was still available. The failing check was **marked** on the PR; it did **not** block merge.

**Finding.** This is repository configuration, not a defect in `checks.yaml`. Branch protection does not require the `checks` job to pass before merge. Per the assignment we report that rather than working around it (for example by weakening the workflow).

## 4. Challenged — put `detail` on `RuleFailure` so HTTP can read compared facts

**What the agent produced.** Day 4 step 1: keep section 5 `detail` keys on the `ValidationOutcome` that `submit_notification` returns. The agent planned to add a `detail` field to `RuleFailure`, copy it in `evaluate_notification`, and unpack it when rebuilding `ValidationOutcome.failed(...)`.

**What we decided.** Do not grow `RuleFailure`. Change `evaluate_notification` to return the failed `ValidationOutcome` (already populated by the rule function). `submit_notification` returns that object instead of constructing a new failure from `rule` and `code` only.

**Reason.** `RuleFailure` was a `(rule, code)` squeeze. Putting `detail` on it would duplicate `ValidationOutcome` so a Day 3 return type could stay unchanged. V-1 and V-6 already leave the pipeline as `ValidationOutcome`; V-2…V-5 and V-7 should too, or HTTP would have to invent compared facts (forbidden in `routes.py`) or ship empty `detail` (contract section 5). `RuleFailure` remains the Day 2 model and is no longer created on the submit path.


