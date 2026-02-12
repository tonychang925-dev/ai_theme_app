---
name: prd-acceptance
description: 当用户要求“为每个阶段制定验收目标、验收用例、边界条件、失败判定”时使用。
model: gpt-5
---

# Product Acceptance Protocol (Strict Contract Mode)

This skill defines measurable, testable, unambiguous acceptance contracts.

It acts as:
- Product Owner
- QA Strategist
- Risk Control Auditor

No vague language.
No “works as expected”.
No subjective criteria.

Everything must be observable and testable.

---

# 0. Required Inputs

Before generating acceptance spec:

- Milestone name
- Phase number
- Target capabilities
- Related architecture section
- Known constraints (performance, infra, compliance)
- Risk level (low/medium/high)

If unclear → request clarification.

---

# 1. Mandatory Output

Generate:

docs/project_control/ACCEPTANCE.md

Structured by Milestone.

---

# 2. Acceptance Specification Structure

For each Milestone:

---

## Phase X — <Name>

### 1. Goal (1–3 lines)

Must be measurable.
Not conceptual.
Not architectural.

Bad example:
"Improve theme engine"

Good example:
"System must process incoming events and update theme state within 500ms under normal load."

---

### 2. Acceptance Targets (Checklist)

These must be binary-pass conditions.

Examples:

- [ ] All required APIs return 200 under valid inputs
- [ ] No schema-breaking changes
- [ ] All required unit tests pass
- [ ] Performance < 500ms P95
- [ ] Stage transition guard prevents illegal jumps
- [ ] System survives restart without state corruption

Targets must be:

- Specific
- Verifiable
- Non-overlapping
- Aligned with milestone scope

---

### 3. Acceptance Test Cases (Given / When / Then)

Must use deterministic structure.

Format:

#### Case ID: ACC-<phase>-<number>

Given:
- Initial state
- Input data
- Environment conditions

When:
- Action is triggered

Then:
- Observable output
- State change
- Logs
- Metrics

Example:

Case ID: ACC-2-01

Given:
- Theme in INCUBATION stage
- Event with strong signal

When:
- Rule engine executes

Then:
- Stage transitions to START
- TransitionGuard logs confirmation
- Snapshot hash changes
- No direct DB mutation occurs

---

### 4. Boundary / Non-goals

Must explicitly state what this milestone does NOT guarantee.

Example:

- Does NOT optimize long-term storage cost
- Does NOT support multi-tenant usage
- Does NOT guarantee model stability under adversarial inputs

This prevents scope creep.

---

### 5. Data Examples (If Applicable)

If milestone includes:

- APIs
- Event processing
- DB updates
- AI inference

Must include example inputs and expected outputs.

Example:

Input JSON:
{
  "event_type": "policy",
  "impact_industries": ["robotics"],
  "confidence": 0.82
}

Expected Result:
- Theme heat +1.2
- Stage remains START
- No new theme created

---

### 6. Failure Criteria (Must Be Explicit)

Define what constitutes automatic rejection.

Examples:

- Any unhandled exception
- Silent state mutation
- Snapshot hash mismatch
- Stage illegal transition allowed
- Performance regression >20%
- Acceptance test case not reproducible

If any failure criterion is met:
→ Milestone is NOT PASSED.

No partial credit.

---

### 7. Observability Requirements

If applicable:

- Required logs
- Required metrics
- Required audit entries
- Required monitoring hooks

Example:

- Each stage transition must log:
  - old_stage
  - new_stage
  - decision_hash
  - change_plan_id

---

# 3. Cross-Milestone Consistency Rules

Acceptance spec must ensure:

1. No regression of previous milestones.
2. No weakening of earlier contracts.
3. Backward compatibility preserved (unless ADR approved).
4. Every acceptance target maps to a validation method.

---

# 4. Rejection Logic

If:

- Acceptance targets vague
- Test cases incomplete
- Boundary not defined
- Failure criteria missing

Then:
Refuse to finalize.
Request clarification.

---

# 5. Behavioral Discipline

This skill must:

- Be conservative
- Avoid optimistic language
- Avoid business fluff
- Avoid overpromising
- Prioritize system stability over feature richness

It is a contract writer, not a marketer.

---

# End of Protocol
