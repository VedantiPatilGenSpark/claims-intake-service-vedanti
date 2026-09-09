# Payload Triage

Every payload in `data/fnol_edge.json` classified against `docs/api-contract.md` as you have completed it. The classification records what the contract says the service does, which is not always what the payload obviously violates.

Fill one row per payload. Where a payload is accepted, leave the rule, code, and status columns as `-`.

## Classification

| Payload | Outcome | Rule | Code | Status |
| --- | --- | --- | --- | --- |
| EDGE-01 | accepted | - | - | - |
| EDGE-02 | accepted | - | - | - |
| EDGE-03 | accepted | - | - | - |
| EDGE-04 | rejected | V-7 | POLICY_CANCELLED | 422 |
| EDGE-05 | rejected | V-2 | LOSS_BEFORE_INCEPTION | 422 |
| EDGE-06 | rejected | V-4 | AMOUNT_EXCEEDS_LIMIT | 422 |
| EDGE-07 | rejected | V-1 | POLICY_NOT_FOUND | 422 |
| EDGE-08 | rejected | W-1 | MALFORMED_REQUEST | 400 |
| EDGE-09 | rejected | V-5 | TYPE_NOT_COVERED | 422 |
| EDGE-10 | rejected | V-7 | POLICY_CANCELLED | 422 |
| EDGE-11 | rejected | W-1 | MALFORMED_REQUEST | 400 |
| EDGE-12 | rejected | W-1 | MALFORMED_REQUEST | 400 |

Notes against the contract, for the reader of this table:

- EDGE-01. MOT-4479, `loss_date` `2026-03-15` equals `effective_date`. V-2 holds (WI-0142 AC-3).
- EDGE-02. MOT-4501, `estimated_amount` `50000.00` equals `limit`. V-4 holds.
- EDGE-03. MOT-4489, `loss_date` `2026-02-28` equals `expiry_date`. V-3 holds.
- EDGE-04. MOT-4497, `loss_date` equals `cancellation_date` `2026-01-15`. V-7 fails; the comparison is strict less-than.
- EDGE-05. MOT-4493, `loss_date` is before `effective_date` and `estimated_amount` exceeds `limit`. Section 4.1 returns the first Stage B failure, V-2.
- EDGE-06. MOT-4502, `estimated_amount` `26000.00` exceeds `limit` `10000.00`. V-4 fails. Collision is permitted on the product; V-5 would pass.
- EDGE-07. Submitted `policy_number` `mot-4471` does not equal master `MOT-4471`. See Decision 1.
- EDGE-08. `estimated_amount` is absent. W-1 / section 2.4, required field missing.
- EDGE-09. MOT-4481 is `personal_auto_named_perils`. `collision` is in the section 2.3 vocabulary and is not in `permitted_claim_types`. V-5 fails.
- EDGE-10. MOT-4500 is cancelled on `2025-10-01` and expired on `2025-12-31`; `loss_date` is `2026-01-08`. V-7 is evaluated before V-3, so the code is `POLICY_CANCELLED` (WI-0158 AC-4).
- EDGE-11. `claim_type` `flood` is not in the section 2.3 vocabulary. See Decision 2.
- EDGE-12. `estimated_amount` `3499.999` has three decimal places. See Decision 3.

## Decision log

Three payloads cannot be classified against the contract as it shipped, because the contract left a decision unmade. For each one, record the ambiguity, the decision, its authority, and the alternative you rejected.

A decision recorded here and nowhere else has not been made. Amend `docs/api-contract.md` so that a reader of the contract alone could not arrive at the other reading.

### Decision 1

**Payload.** EDGE-07

**The ambiguity.** V-1 as shipped required that `policy_number` exist in the policy master and did not say how existence is decided. `mot-4471` is the same characters as master identifier `MOT-4471` in a different case. One reading is that the identifier matches and evaluation continues (the loss on MOT-4471 would then pass every subsequent rule). The other reading is that the strings are different identifiers and V-1 fails.

**Decision.** Comparison is exact and case-sensitive. `mot-4471` does not equal `MOT-4471`. EDGE-07 is refused as V-1, `POLICY_NOT_FOUND`, 422. The service does not fold case or otherwise normalise `policy_number` before lookup.

**Authority.** Section 2.2: `policy_number` is the identifier as held in the policy master. Operations procedure OP-4 (WI-0151) matches duplicates on `policy_number` as submitted; folding case on intake and storing the folded form would record a number the master does not hold, and folding on lookup only would make a later retry with the original casing miss the duplicate.

**Rejected alternative.** Case-insensitive match, treating `mot-4471` as MOT-4471 and accepting the notification. That reading treats an identifier as a display string. It would write a recorded `policy_number` that is not the master's key, so V-6 could not recognise a retry typed the other way, and it would silently correct a portal keying error instead of showing the handler the value they sent.

**Contract amended.** Section 4.2, V-1 condition now states exact, case-sensitive equality. The notes under the table repeat that `mot-4471` does not equal `MOT-4471`, and that V-6 uses the same comparison.

### Decision 2

**Payload.** EDGE-11

**The ambiguity.** `claim_type` is `flood`. Section 2.3 fixes the vocabulary as five values and says the permitted subset on a product is V-5. Section 2.4 splits uninterpretable requests (400) from inadmissible content (422). Both readings were available: `flood` is a string, so the body can be interpreted and V-5 returns `TYPE_NOT_COVERED` at 422; or `flood` is not a value of the type section 2.2 defines, so W-1 returns `MALFORMED_REQUEST` at 400.

**Decision.** A `claim_type` that is not one of the five section 2.3 values fails W-1. EDGE-11 is refused as `MALFORMED_REQUEST`, 400. V-5 is never evaluated for it. V-5 applies only to a vocabulary member that the product does not permit (EDGE-09).

**Authority.** Section 2.2 notes: `claim_type` is one of the values in 2.3. Section 2.3: the vocabulary is fixed by this contract; the permitted subset is a property of the policy and is V-5. Section 2.4: a value that is not of the specified type is a defect in the caller's code (400), not data a person should take to product investigation (422).

**Rejected alternative.** Run V-5 and return `TYPE_NOT_COVERED`. That code tells the handler the product does not cover this type, which sends them to underwriting. `flood` is not a type the service recognizes; the portal emitted a value outside the contract. Reporting it as a cover decision would also require a policy lookup for a request Stage A has not accepted.

**Contract amended.** Section 4.1 Stage A now states that `claim_type` must be exactly one of the five vocabulary values and that a string outside the vocabulary is `MALFORMED_REQUEST`, not V-5. Section 4.2 notes that V-5 is evaluated only for a `claim_type` that passed W-1.

### Decision 3

**Payload.** EDGE-12

**The ambiguity.** Section 2.2 says `estimated_amount` is United States dollars, two decimal places, greater than zero. `3499.999` is a decimal greater than zero with three places. The shipped contract did not say whether that is a type failure (400), a content failure (422, with no rule in the table for scale), or a value the service accepts, perhaps by rounding. If it were accepted, MOT-4476 would pass every Stage B rule.

**Decision.** Exactly two decimal places is part of the type, not a business rule. EDGE-12 fails W-1 and is refused as `MALFORMED_REQUEST`, 400. The service does not round, truncate, or store a three-place value.

**Authority.** Section 2.2 Notes on `estimated_amount`. Section 2.4: a field carrying a value of the wrong type is uninterpretable (400). The same table requires `loss_date` to be `YYYY-MM-DD`; a date the parser would have to coerce is refused there, and money scale is the same kind of constraint. There is no work item that introduces a scale rule in section 4.2.

**Rejected alternative.** Accept the payload, or round to `3500.00` / `3499.99`, or invent a 422 code. Rounding would record an amount the caller did not send, which is the reason section 2.2 already refuses unknown fields rather than ignoring them. A 422 would tell a person to change the data, but milles are a serialization defect in the caller, and no row in the rule table names that condition.

**Contract amended.** Section 4.1 Stage A now states that `estimated_amount` has exactly two digits after the decimal point, that a three-place value is not that type, and that the service does not round it.

## Assignment 2 reconciliation

Compared every refusal `NotificationRequest` can raise to contract section 6. Nothing was missing. No amendment to `docs/api-contract.md`.

**How we checked.** Listed the model's constraints against the unit cases in `tests/unit/test_models.py`: extra field; missing `policy_number`, `loss_date`, `claim_type`, or `estimated_amount`; empty `policy_number`; invalid `loss_date`; `claim_type` outside the vocabulary; `estimated_amount` with the wrong scale, `<= 0`, or a non-decimal type. Each of those is Stage A (W-1). Section 6 already maps that to `MALFORMED_REQUEST` at 400. Day 4 will turn `ValidationError` into that code; we did not add per-constraint codes because they all mean the same thing: the body could not be interpreted.

`Policy` and `RecordedNotification` can also fail construction (omitted `cancellation_date`; `claim_reference` that is not `CLM-YYYY-NNNNNN`). Those objects are not built from a portal payload. They are not HTTP responses, so they do not belong in section 6.
