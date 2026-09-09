# Agent decision log

Engineering judgment during Day 3. Each entry names what the agent produced, what we decided, and a reason tied to an acceptance criterion or a failure that would have followed.

## 1. Rejected / corrected — implement every remaining rule in one change

**What the agent produced.** After the failing tests were committed, the agent proposed filling V-2, V-7, V-3, V-4, V-5, and V-6 in a single implementation step and a single commit, leaving `evaluate_notification` / `submit_notification` for later.

**What we decided.** Implement **one rule at a time**: write the function, run that rule’s parametrized tests, commit, then move to the next. Order: V-2, V-7, V-3, V-4, V-5, V-6, then the orchestrators.

**Reason.** Day 3 AC: `git log` must show a commit containing the tests **for a rule** before any commit containing **that rule’s** implementation. One combined rules commit still puts tests first globally, but it does not show which rule landed when, and a single bad comparison (for example V-7 treating `loss_date == cancellation_date` as covered) would land in the same commit as unrelated green rules. Incremental commits keep each boundary failure (`test_v2[before_inception]`, `test_v7[on_cancellation]`, …) pinned to the change that claimed to fix it. That is the TDD evidence the assignment grades, not a style preference.
