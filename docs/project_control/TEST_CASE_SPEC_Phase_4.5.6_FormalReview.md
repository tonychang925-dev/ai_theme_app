# TEST CASE SPEC - Phase 4.5.6 Formal Review

## 1. Scope

Phase 4.5.6 stabilizes the DailyReview Formal Review projection:

- `FormalReviewProjectionCompiler` outputs the frozen six-chapter Formal Review v1 model.
- `FormalReviewView` consumes only `formal_review`.
- Legacy DailyReviewV2 fields remain available during dual-track observation.
- PR5 validates schema stability across representative market conditions before legacy removal.

## 2. Test Layers And Blocking Rules

Execution order:

1. Projection schema contract.
2. 2026-07-09 Projection Diff golden semantic test.
3. PR5 five-scenario stabilization test.
4. Frontend FormalReviewView contract.
5. Recap Workbench First contract.

Blocking rules:

- If schema contract fails, PR4/PR5 are blocked.
- If Projection Diff fails, FormalReview v1 cannot be frozen.
- If FormalReviewView contract fails, frontend is still reading legacy fields and PR4 is blocked.
- If real five-trading-day approved snapshot observation is incomplete, PR6 Legacy Removal is blocked.

## 3. Requirement To Test Mapping

| Requirement | Test ID | Test File | Expected Result |
|---|---|---|---|
| Freeze six-chapter Formal Review v1 schema | TC-P456-01 | `stock_processing_service/tests/unit/test_projection_formal_schema.py` | Six chapters exist; removed legacy fields do not return |
| Preserve business semantics during projection | TC-P456-02 | `stock_processing_service/tests/unit/test_projection_diff_20260709.py` | FACT/ENTITY/ASSESSMENT/PLAN semantic diff passes |
| Stabilize model across representative market states | TC-P456-03 | `stock_processing_service/tests/unit/test_projection_stabilization_scenarios.py` | 5 scenarios compile with stable schema and no duplicate entity keys |
| FormalReviewView reads only projection model | TC-P456-04 | `frontend/scripts/test-formal-review-view-contract.mjs` | Component renders only `formal_review`, not legacy fields |
| Recap remains Workbench First | TC-P456-05 | `frontend/scripts/test-recap-workbench-first-contract.mjs` | Recap does not produce derived data or force legacy generation |

## 4. Required Commands

```bash
/opt/miniconda3/envs/theme_matcher_env/bin/python -m pytest \
  stock_processing_service/tests/unit/test_projection_stabilization_scenarios.py \
  stock_processing_service/tests/unit/test_projection_formal_schema.py \
  stock_processing_service/tests/unit/test_projection_diff_20260709.py \
  stock_processing_service/tests/unit/test_projection_capital_plan.py \
  stock_processing_service/tests/unit/test_projection_theme_stock_merge.py -q

cd frontend
node scripts/test-formal-review-view-contract.mjs
node scripts/test-recap-workbench-first-contract.mjs
node scripts/test-workbench-generate-flow-contract.mjs
npm run build
```

## 5. Failure Criteria

Any of the following fails Phase 4.5.6 stabilization:

- Formal Review adds a seventh chapter without architecture approval.
- `FormalReviewView` reads `theme_reviews`, `strong_stock_reviews`, `watchlist_reviews`, `post_market_decision_v2`, or other legacy fields directly.
- FACT fields are overwritten by analyst/AI assessment data.
- `watch_themes/watch_stocks` display AI/legacy values after analyst watch override.
- Duplicate `subject_key` or `stock_code` appears in compiled entities.
- PR6 starts before at least five real trading days of dual-track observation are recorded.
