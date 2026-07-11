# TEST CASE SPEC - Phase 4.5.5-RA

## 1. Scope

Phase 4.5.5-RA closes the Workbench First responsibility alignment:

- Analyst Workbench owns recap data production, AI draft, analyst review, approval snapshot.
- DailyReview / Recap page owns report viewing, refresh, compose trigger, publish.
- Formal report composition consumes only approved workbench snapshots.

## 2. Test Layers And Blocking Rules

Execution order:

1. UT: workbench session, approval gate, formal gate, review merger, generate service.
2. Contract tests: Recap page source contract, snapshot-only compose contract.
3. E2E-style unit flow: AI Draft -> analyst override -> approved snapshot -> final report.

Blocking rules:

- If approval / formal gate tests fail, compose and final report tests are blocked.
- If generate service guard tests fail, Recap responsibility tests are blocked.
- If Recap contract test fails, Phase 4.5.5-RA cannot be closed because Recap may regain production responsibility.

## 3. Requirement To Test Mapping

| Requirement | Test ID | Test File | Expected Result |
|---|---|---|---|
| Workbench generate owns derived-data production entry | TC-P455-01 | `stock_processing_service/tests/unit/test_workbench_phase455_generate.py` | generation steps include `derived_data`; failure stops before draft |
| Analyst override enters approved snapshot | TC-P455-02 | `stock_processing_service/tests/unit/test_workbench_phase455_review_merger.py` | `ai_value`, `analyst_value`, `final_value`, reason are preserved |
| Formal compose is snapshot-only | TC-P455-03 | `stock_processing_service/tests/unit/test_workbench_phase455_compose_gate.py` | newer draft does not override approved snapshot |
| Recap cannot produce derived data | TC-P455-04 | `frontend/scripts/test-recap-workbench-first-contract.mjs` | no `generatePostMarketDerivedData`, no derived endpoint call, no forced rebuild |
| DRAFT_READY cannot compose formal report | TC-P455-05 | `stock_processing_service/tests/unit/test_workbench_phase455_responsibility_contract.py` | `require_formal()` raises `ApprovalRequiredError` |
| Approved snapshot cannot be overwritten by generate | TC-P455-06 | `stock_processing_service/tests/unit/test_workbench_phase455_responsibility_contract.py` | generate returns `failed_precondition`; snapshot hash is unchanged |
| AI Draft -> Analyst Correction -> Final Report | TC-P455-E2E | `stock_processing_service/tests/unit/test_workbench_phase455_responsibility_contract.py` | final report uses analyst `PCB`, not newer draft `机器人` |

## 4. Required Commands

```bash
.venv/bin/python -m pytest \
  stock_processing_service/tests/unit/test_workbench_phase455_generate.py \
  stock_processing_service/tests/unit/test_workbench_phase455_compose_gate.py \
  stock_processing_service/tests/unit/test_workbench_phase455_review_merger.py \
  stock_processing_service/tests/unit/test_workbench_phase455_responsibility_contract.py \
  stock_processing_service/tests/unit/test_workbench_phase454.py \
  stock_processing_service/tests/unit/test_workbench_approval_gate.py \
  stock_processing_service/tests/unit/test_workbench_session.py

cd frontend
node scripts/test-recap-workbench-first-contract.mjs
node scripts/test-recap-default-data-mode-contract.mjs
node scripts/test-recap-daily-review-v2-contract.mjs
```

## 5. Failure Criteria

Any of the following fails Phase 4.5.5-RA:

- Recap imports or calls `generatePostMarketDerivedData`.
- Recap triggers formal report generation with `force=true`.
- `compose-from-workbench` can compose without an approved snapshot.
- A newer AI draft can override an approved snapshot in formal compose.
- A generate call after `APPROVED` can overwrite the approved snapshot.

