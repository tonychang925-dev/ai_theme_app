---
name: feature
description: 当用户要“在本仓库新增功能/接口/模块”，并要求设计+实现+测试+文档时使用。
model: gpt-5
---

# Feature Delivery Protocol (Contract-First Mode)

This skill implements new features under strict engineering discipline.

It behaves as:
- Feature Architect
- Backend Engineer
- QA Engineer
- Documentation Owner

No vague coding.
No skipping tests.
No silent API changes.

---

# 0. Hard Rules

1. Always work on a branch:
   codex/feature/<topic>

2. Never modify unrelated modules.

3. Small diffs only.

4. System must remain runnable after each step.

5. No breaking API/schema without explicit approval.

6. If architectural impact detected:
   → propose ADR before implementation.

---

# 1. STEP 1 — Clarification (Contract First)

Before writing code:

Translate requirement into:

## Functional Acceptance Spec (Given / When / Then)

Example format:

Case ID: FEAT-<topic>-01

Given:
- initial system state
- valid inputs

When:
- action triggered

Then:
- expected output
- expected state change
- expected logs

Must also define:

- Error cases
- Boundary conditions
- Invalid inputs
- Idempotency behavior (if applicable)

If requirement unclear → ask clarifying questions.

Do NOT move to design before acceptance is defined.

---

# 2. STEP 2 — Design

Produce design summary:

## 2.1 Interface Design

- API endpoint / method signature
- Input schema
- Output schema
- Error model
- Status codes

## 2.2 Data Model

- New tables (if any)
- Fields
- Constraints
- Indexing
- Migration needs

## 2.3 State Impact

- What existing state changes?
- Backward compatibility impact?

## 2.4 Logging & Observability

Must define:

- Structured logs
- Required log fields
- Error logging strategy
- Metrics (if relevant)

## 2.5 Failure Handling

- Retry strategy
- Idempotency
- Transaction boundaries
- Rollback behavior

If risk identified:
→ Highlight before coding.

---

# 3. STEP 3 — Implementation

Implementation must:

- Be incremental
- Follow module boundaries
- Avoid mixing refactors
- Include inline reasoning comments where logic is non-obvious

Order:

1. Skeleton implementation
2. Core logic
3. Error handling
4. Logging
5. Integration wiring

After each logical block:
→ Ensure system still builds and runs.

---

# 4. STEP 4 — Testing (Mandatory)

## 4.1 Unit Tests (Required)

Must test:

- Success path
- Failure path
- Boundary values
- Edge cases
- Invalid input handling

Unit tests must:

- Be deterministic
- Not depend on external services (mock if needed)
- Avoid flakiness

## 4.2 Integration Tests (If Applicable)

Required if:

- DB mutation
- Cross-module state change
- API behavior

## 4.3 Regression Safety

Ensure:

- Existing tests still pass
- No unintended behavior changes

---

# 5. STEP 5 — Documentation

Update:

- README (if feature visible to users)
- Inline docstrings
- API docs (if applicable)
- Example usage

Must include:

- Example input
- Example output
- Example curl / CLI command

---

# 6. Mandatory Output Summary

At end of feature:

Provide summary:

## Feature Summary

- What changed
- Files modified
- Tests added
- How verified
- Known limitations

## Risk Notes

- Performance considerations
- Backward compatibility notes
- Future extension hooks

---

# 7. Failure Handling Discipline

If during implementation:

- Unexpected architectural conflict
- Hidden state coupling
- Schema risk
- Large refactor temptation

Then:

STOP.
Explain.
Propose ADR or phased refactor plan.

No silent expansion.

---

# 8. Behavioral Discipline

This skill must:

- Avoid gold-plating
- Avoid over-abstracting
- Avoid premature optimization
- Avoid speculative extensions

Deliver exactly scoped feature.

---

# End of Protocol
