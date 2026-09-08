# Claims Intake Service: API Contract

Version 0.5. Owned by the claims intake team. Consumed by the claims portal team.

This document is the authority on what the service accepts, what it returns, and under what conditions it refuses. Where the code and this document disagree, the document is correct and the code is a defect.

Sections 1 through 3 are fixed. Do not edit them.

## 1. Purpose and scope

The claims intake service accepts a first notice of loss from the claims portal, validates it against the policy master and a table of business rules, and either records a notification and issues a claim reference or refuses the submission with a specific reason.

**In scope.** Accepting a notification, validating it, and recording it. Issuing a claim reference. Reporting the reason a notification was refused.

**Out of scope.** Adjusting, reserving, payment, and any decision about coverage beyond the rules in section 4. The service decides whether a notification is well formed and admissible. It does not decide whether the claim will be paid.

**The policy master is a dependency, not part of this service.** The service reads policy records from it and does not write to it. A policy that cannot be read is a condition this contract specifies, and it is specified separately from a policy that does not exist, because the two require different action from the caller.

**Compatibility.** Adding a field to a response is a compatible change and callers must ignore fields they do not recognize. Adding a new error code is a compatible change and callers must fall through to default handling for a code they do not recognize. Changing the meaning of an existing code, removing a field, or changing a status code for an existing condition is not compatible and does not happen without a version increment agreed with the portal team.

## 2. Request

### 2.1 Endpoint

```
POST /notifications
Content-Type: application/json
```

### 2.2 Body

| Field | Type | Required | Notes |
| --- | --- | --- | --- |
| `policy_number` | string | yes | Identifier as held in the policy master. Not empty. |
| `loss_date` | string | yes | Calendar date, `YYYY-MM-DD`. |
| `claim_type` | string | yes | One of the values in 2.3. Not empty. |
| `estimated_amount` | decimal | yes | United States dollars, two decimal places. Greater than zero. |
| `description` | string | no | Free text. Absent and `null` are equivalent. |

The service rejects a body carrying a field not listed above. A misspelled field name is a defect in the caller's code, and accepting the payload with the field ignored would record a notification built from data the caller did not send.

### 2.3 Claim type vocabulary

`collision`, `theft`, `glass`, `liability`, `weather`.

Which of these are admissible on a given notification depends on the product the policy is written on. The vocabulary is fixed by this contract. The permitted subset is a property of the policy record and is evaluated by rule `V-5`.

### 2.4 Well formed against acceptable

A request that cannot be interpreted is refused with status `400`. This means the body was not valid JSON, a required field was absent, a field carried a value of the wrong type, or a field was present that this contract does not define. The caller's code is wrong.

A request that was interpreted and whose content is not admissible is refused with status `422`. The caller's data is wrong, and a person needs to see the reason.

This split is stated here once and holds without exception everywhere else in this document.

## 3. Success response

A notification that passes every rule in section 4 is recorded and the service responds:

```
201 Created
Content-Type: application/json

{
  "claim_reference": "CLM-2026-000317",
  "status": "recorded"
}
```

**`claim_reference`** matches the pattern `CLM-YYYY-NNNNNN`, where `YYYY` is the calendar year in which the notification was recorded and `NNNNNN` is a zero padded sequence. A claim reference is unique across all recorded notifications and is never reissued. It is the value the claims handler quotes and the value every downstream system keys on.

**`status`** is `recorded` on every success response this contract defines. It exists because the portal displays it and because a future state that is not `recorded` is foreseeable. Callers must not treat it as constant.

A refused notification is never recorded and no claim reference is issued. There is no partial outcome: either a notification exists with a reference, or nothing was written.

## 4. Validation

### 4.1 Evaluation order

A request is evaluated in two stages. Stage A decides whether the body
can be interpreted. Stage B decides whether the interpreted content is
admissible. Stage B does not run if Stage A fails. Within Stage B,
evaluation stops at the first failure. The caller receives exactly one
error: that failure's `code` and the status mapped to it in section 6.
Remaining rules are not evaluated. The envelope never contains a list of
failures.

**Stage A, identifier `W-1`.** The well-formedness checks in section 2.4.
`W-1` is not a row in the rule table because it does not compare a
notification against a policy or against recorded notifications. If it
fails, the caller receives `MALFORMED_REQUEST` at status `400`, no policy
is read, and nothing is recorded.

The type of each field is the Type column in section 2.2 together with
the constraints in that row's Notes column:

- `policy_number` is a non-empty string.
- `loss_date` is a calendar date of the form `YYYY-MM-DD`.
- `claim_type` is a non-empty string that is exactly one of the five
  values in section 2.3. A string that is not in that vocabulary is not
  a value of the type this contract defines. It is refused here, not by
  V-5. V-5 decides whether a vocabulary member is permitted on the
  product. It does not decide whether a string is a vocabulary member.
- `estimated_amount` is a decimal number of United States dollars with
  exactly two digits after the decimal point and a value greater than
  zero. A value with three decimal places is not that type. The service
  does not round it and does not store it.
- A body that is not valid JSON, that omits a required field, that
  carries a field not listed in section 2.2, or that carries a value of
  the wrong JSON type, is refused here.

**Stage B, the rule table.** Rules are not evaluated in identifier
order. They are evaluated in this sequence:

`V-1`, `V-2`, `V-7`, `V-3`, `V-4`, `V-5`, `V-6`.

V-1 short-circuits: if it fails, no later rule runs. Every later rule
either reads a policy field or inspects recorded notifications, and a
policy number that does not exist has no policy fields and was never
recorded (WI-0142 AC-4, WI-0151 AC-3).

The sequence places V-7 before V-3 so that a notification whose
`loss_date` is both `>=` the policy `cancellation_date` and `>` the
policy `expiry_date` is refused as `POLICY_CANCELLED`, not as
`LOSS_AFTER_EXPIRY` (WI-0158 AC-4). Reporting expiry would send the
handler to the wrong system.

This is a deliberate replacement of the identifier-order rule this
section shipped with. Keeping V-6 as the duplicate rule (status 409) and
V-7 as the cancellation rule (status 422) and evaluating by ascending
identifier would run V-3 before V-7 and violate WI-0158 AC-4. Renumbering
so that cancellation occupied V-3 would have preserved identifier order
only by changing the meaning of an identifier the shipped table already
assigned to expiry. The identifiers stay; the order is the sequence
above.

When several Stage B rules would fail on the same notification, the
caller still receives one envelope with one `code`: the earliest failure
in the sequence. The other failures are not reported.

### 4.2 Rule table

| ID  | Condition                                      | Code                    | Status |
| --- | ---------------------------------------------- | ----------------------- | ------ |
| V-1 | `policy_number` equals a `policy_number` in the policy master (exact match, case-sensitive) | `POLICY_NOT_FOUND`      | 422    |
| V-2 | `loss_date` >= policy `effective_date`         | `LOSS_BEFORE_INCEPTION` | 422    |
| V-3 | `loss_date` <= policy `expiry_date`            | `LOSS_AFTER_EXPIRY`     | 422    |
| V-4 | `estimated_amount` <= policy `limit`           | `AMOUNT_EXCEEDS_LIMIT`  | 422    |
| V-5 | `claim_type` is a member of the policy's `permitted_claim_types` | `TYPE_NOT_COVERED`      | 422    |
| V-6 | no recorded notification exists with the same `policy_number` AND `loss_date` AND `claim_type` | `DUPLICATE_NOTIFICATION` | 409    |
| V-7 | policy `cancellation_date` is null OR `loss_date` < policy `cancellation_date` | `POLICY_CANCELLED`      | 422    |

The condition is what must hold. When it does not hold, the service
returns that row's code and status and does not record a notification.

Boundaries are inclusive as written for V-2, V-3, and V-4. A loss on the
inception date is covered (WI-0142 AC-3). A loss on the expiry date is
covered. An amount equal to the limit is within cover.

V-1 compares `policy_number` to the identifier as held in the policy
master. The comparison is exact and case-sensitive: `mot-4471` does not
equal `MOT-4471`. The service does not fold case, trim whitespace, or
otherwise normalise the value before the comparison.

V-5 is evaluated only for a `claim_type` that already passed W-1, which
means it is one of the five values in section 2.3. A string outside that
vocabulary never reaches V-5.

V-6 compares against recorded notifications only. A previous submission
that was refused was never written, so it is not a match (WI-0151 AC-3).
Each of `policy_number`, `loss_date`, and `claim_type` is compared for
equality; `policy_number` equality is the same exact, case-sensitive
comparison as V-1. `estimated_amount` and `description` are not part of
the match. When V-6 fails, `detail` contains the `claim_reference` of
the existing recorded notification (WI-0151 AC-2).

V-7 treats a null `cancellation_date` as "not cancelled": the rule
passes and evaluation continues (WI-0158 AC-3). When `cancellation_date`
is present, cancellation takes effect at the start of that date, so the
comparison is strict less-than. A loss with `loss_date` equal to
`cancellation_date` fails V-7 and is not covered (WI-0158 AC-1, AC-2).
V-7 is evaluated before V-3 (section 4.1).

## 5. Error envelope

Every refused request, and every failure to accept a well-formed request
because a dependency did not answer, returns this body:

```
Content-Type: application/json

{
  "code": "<ERROR_CODE>",
  "message": "<human-readable sentence>",
  "detail": { }
}
```

The HTTP status is on the response line. It is not a field in the body.
Section 6 is the mapping from `code` to status.

**`code` is a stable promise.** It is drawn from the closed set in
section 6. Callers may branch on it. Adding a new code is a compatible
change; callers must fall through to default handling for a code they
do not recognize (section 1). Changing the meaning of an existing code
is not compatible.

**`message` is not a stable promise.** It exists for a person to read.
It may be reworded without a version increment. Callers must not parse
it, match on its text, concatenate it into another string that is then
parsed, or treat two responses with the same `code` and different
`message` text as different conditions.

**`detail` is always a JSON object.** It is never an array, never a
string, and never `null`. It may be empty.

**What a caller may rely on inside `detail`.** For a given `code`, the
keys listed for that code below are present and have the stated types.
Those keys, under that code, are stable promises.

**What a caller may not rely on inside `detail`.** The set of keys is
not a single schema shared across codes. A key that is present for one
code is not therefore present for another. Callers must not iterate
`detail` looking for a field that "ought to be there." Callers must
ignore keys they do not recognize; adding a key under an existing code
is compatible. Callers must not treat the absence of an undocumented
key as meaningful. Callers must not infer the `code` from the shape of
`detail`.

Documented `detail` keys by `code`:

| Code | Keys the caller may read | Types |
| --- | --- | --- |
| `MALFORMED_REQUEST` | `reason`; `field` when the failure is attributable to one named field | `reason` is one of `invalid_json`, `missing_field`, `wrong_type`, `unknown_field`, `invalid_value`. `field` is a string naming a section 2.2 field. `field` is absent when `reason` is `invalid_json`. |
| `POLICY_NOT_FOUND` | `policy_number` | string, the value submitted |
| `LOSS_BEFORE_INCEPTION` | `loss_date`, `effective_date` | strings, `YYYY-MM-DD` |
| `LOSS_AFTER_EXPIRY` | `loss_date`, `expiry_date` | strings, `YYYY-MM-DD` |
| `AMOUNT_EXCEEDS_LIMIT` | `estimated_amount`, `limit` | decimal strings, two decimal places |
| `TYPE_NOT_COVERED` | `claim_type`, `product`, `permitted_claim_types` | `claim_type` and `product` are strings; `permitted_claim_types` is an array of strings |
| `DUPLICATE_NOTIFICATION` | `claim_reference` | string, the existing recorded reference, pattern `CLM-YYYY-NNNNNN` |
| `POLICY_CANCELLED` | `loss_date`, `cancellation_date` | strings, `YYYY-MM-DD` |
| `POLICY_MASTER_TIMEOUT` | `dependency` | the string `policy_master` |
| `POLICY_MASTER_UNREACHABLE` | `dependency` | the string `policy_master` |
| `POLICY_MASTER_UNPARSABLE` | `dependency` | the string `policy_master` |

### 5.1 Worked example: a rule failure

The body was interpreted. The policy master answered. V-2 failed.

```
422 Unprocessable Entity

{
  "code": "LOSS_BEFORE_INCEPTION",
  "message": "The loss date precedes the policy effective date.",
  "detail": {
    "loss_date": "2026-03-02",
    "effective_date": "2026-04-15"
  }
}
```

`detail` holds the two dates the rule compared. This envelope is
produced after Stage B has a policy in hand. The HTTP layer is mapping a
validation outcome; it is not reporting a parse problem and it is not
reporting a dependency failure.

### 5.2 Worked example: a request the service could not interpret

The body omitted a required field. Stage A failed. No policy was read.

```
400 Bad Request

{
  "code": "MALFORMED_REQUEST",
  "message": "The request body could not be interpreted.",
  "detail": {
    "reason": "missing_field",
    "field": "estimated_amount"
  }
}
```

`detail` holds a structural diagnosis: which constraint failed and,
where it applies, which field. It does not hold policy dates, a limit, a
claim reference, or a dependency name, because none of those were
consulted. This envelope is produced at the parse boundary, before any
row in section 4.2 runs.

The same `code` is returned for the other Stage A failures. The `reason`
and the presence or absence of `field` are what distinguish them from
each other. They are not distinguished by `message`.

### 5.3 Worked example: a policy master that did not answer

The body was interpreted. During V-1 the policy master was called and
did not produce a usable answer. The caller did nothing wrong.

```
504 Gateway Timeout

{
  "code": "POLICY_MASTER_TIMEOUT",
  "message": "The policy master did not respond in time.",
  "detail": {
    "dependency": "policy_master"
  }
}
```

`detail` names the dependency. It does not hold the compared business
values of a rule failure, and it does not hold a parse `reason` or
`field`. This envelope is produced when the policy client raises a
lookup failure rather than a not-found. A policy master that answered
and held no match is `POLICY_NOT_FOUND` (section 5 keys above, status
422), which is a statement about the caller's data and is not this
example.

These three envelopes cannot be produced by one handling path: 5.1 is a
failed Stage B rule, 5.2 is a failed Stage A parse, and 5.3 is a
dependency that did not answer. Collapsing them into one `code` or one
`detail` shape would hide which action the caller should take.

## 6. Status code mapping

Each `code` this service can produce maps to exactly one HTTP status.
The reverse is not one-to-one: several codes share 422 because they are
different statements about the caller's data. No two codes that mean the
same thing share a row.

| Code | Status | Produced when |
| --- | --- | --- |
| `MALFORMED_REQUEST` | 400 | W-1. The request could not be interpreted (section 2.4 and section 4.1 Stage A). |
| `DUPLICATE_NOTIFICATION` | 409 | V-6. A recorded notification already exists with the same `policy_number`, `loss_date`, and `claim_type`. |
| `POLICY_NOT_FOUND` | 422 | V-1. The policy master answered and holds no policy whose `policy_number` equals the submitted value. This is the "no match" case at the policy master boundary. |
| `LOSS_BEFORE_INCEPTION` | 422 | V-2. `loss_date` < policy `effective_date`. |
| `LOSS_AFTER_EXPIRY` | 422 | V-3. `loss_date` > policy `expiry_date`. |
| `AMOUNT_EXCEEDS_LIMIT` | 422 | V-4. `estimated_amount` > policy `limit`. |
| `TYPE_NOT_COVERED` | 422 | V-5. `claim_type` is a section 2.3 vocabulary member that is not in the policy's `permitted_claim_types`. |
| `POLICY_CANCELLED` | 422 | V-7. Policy `cancellation_date` is not null and `loss_date` >= `cancellation_date`. |
| `POLICY_MASTER_UNPARSABLE` | 502 | The policy master returned a response this service could not parse. The caller did nothing wrong. |
| `POLICY_MASTER_UNREACHABLE` | 503 | The policy master could not be reached. The caller did nothing wrong. |
| `POLICY_MASTER_TIMEOUT` | 504 | The policy master did not answer within the time this service waits. The caller did nothing wrong. |

A successful submission is `201` and is not an error code. It is
specified in section 3.

The four policy master boundary conditions are `POLICY_NOT_FOUND` (the
master answered: no match, caller's data, 422) and the three codes in
the 5xx family (the master did not produce a usable answer: not the
caller's fault). Those three are distinct conditions and have distinct
statuses so that a caller who retries can tell a timeout from an
unreachable host from a response that will not become valid by waiting.

No other failure produces a response. A notification is either recorded
with a `201` or refused with one of the rows above.