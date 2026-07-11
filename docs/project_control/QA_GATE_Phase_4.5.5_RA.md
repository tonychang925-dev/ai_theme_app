# QA Gate - Phase 4.5.5-RA

## 1. Definition Of Done

- [x] Workbench generate owns the recap data production entry.
- [x] Analyst review is merged into approved snapshot.
- [x] Formal compose requires approved snapshot metadata and hash.
- [x] Recap page no longer produces derived data.
- [x] Responsibility boundary regression tests are in place.
- [x] Phase architecture document is updated.

## 2. Required Checks

### 2.1 Backend Regression

Command:

```bash
.venv/bin/python -m pytest \
  stock_processing_service/tests/unit/test_workbench_phase455_generate.py \
  stock_processing_service/tests/unit/test_workbench_phase455_compose_gate.py \
  stock_processing_service/tests/unit/test_workbench_phase455_review_merger.py \
  stock_processing_service/tests/unit/test_workbench_phase455_responsibility_contract.py \
  stock_processing_service/tests/unit/test_workbench_phase454.py \
  stock_processing_service/tests/unit/test_workbench_approval_gate.py \
  stock_processing_service/tests/unit/test_workbench_session.py
```

Expected: all tests pass.

Actual result on 2026-07-10: `39 passed`.

### 2.2 Frontend Contract

Command:

```bash
cd frontend
node scripts/test-recap-workbench-first-contract.mjs
node scripts/test-recap-default-data-mode-contract.mjs
node scripts/test-recap-daily-review-v2-contract.mjs
```

Expected: all contract scripts pass.

Actual result on 2026-07-10:

- `recap workbench-first contract passed`
- `recap default data_mode contract passed`
- `recap daily_review_v2 contract passed`

### 2.3 Business E2E Replay

Command:

```bash
.venv/bin/python scripts/phase455_e2e_20260709.py
```

Actual result on 2026-07-11:

- 2026-07-09 charts/emotion/workspace inputs loaded.
- Workbench draft generated in isolated run directory.
- Analyst correction `人形机器人延续主线 -> PCB成为资金承接方向` entered approved snapshot.
- Formal compose used the approved snapshot hash.
- Newer draft did not pollute formal report.
- Approved snapshot blocked later generate.

Evidence: `docs/test_reports/phase455_e2e_20260709.md`.

### 2.4 Build Check

Command:

```bash
cd frontend
npm run build
```

Current result: failed due to existing TypeScript debt in `AnalystWorkspacePage.tsx` and `EmotionDashboard.tsx`.

Gate decision: not counted as a Phase 4.5.5-RA regression because `RecapPage.tsx` is no longer in the failing set. Track separately as `Frontend Type Cleanup`.

## 3. Final Review Checklist

- [x] Formal report path does not consume newer AI draft over approved snapshot.
- [x] Recap page does not trigger derived-data generation.
- [x] Approved snapshot is not overwritten by a later generate request.
- [x] `snapshot_hash` remains the audit key in formal report metadata.

## 4. Gate Result

Phase 4.5.5-RA: Passed for responsibility alignment.

Residual risk: frontend global build remains blocked by unrelated type debt; keep it outside this phase and resolve before broader release packaging.
