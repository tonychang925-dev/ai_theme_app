# JYHF UI Daily Incremental v1 — Candidate handoff

Task: JYHF-DAILY-UI-INCREMENTAL-V1
Repository: tonychang925-dev/ai_theme_app
Exact frozen base: 8fc936d5d6cd691110318ab9f3794f57f7a29256

## Status / authority

Implementation candidate: CANDIDATE ONLY. NOT ACTIVATED as a scheduled production service.
Merged-main verification and a real current-trading-day write/readback are required before activation. On Saturday 2026-10-10, no genuine current-day market capture can exist; weekend execution must fail closed.

## Why old sync cannot be turned on

Old Token file produced business 401. The App's logged-in ordinary session still successfully calls subject/list/v2 and stock/realtime-by-subject/v2. Original daily_jyhf_sync.py includes potentially destructive and synthetic-event paths. Do not schedule it.

## New reader and evidence contract

1. Operates only while the authorized user is logged in and the JYHF App is already on /subject/all.
2. Calls the App's native list sort/refresh handler and requires a fresh HTTP-200 subject/list/v2 request. Reads the normal Vue list; does not inspect session credentials, cookies, hidden fields, or VIP endpoints.
3. Validates all visible subject IDs; prioritizes every newly missing ID, first 25 visible ranking positions, and 35 known IDs via a deterministic rolling cursor. Full App list is checked each run; existing constituents are intentionally **not all scanned daily**.
4. Each selected subject uses the normal UI row-selection callback. Its normal stock/realtime-by-subject/v2 JSON must have code=200, exactly one matching request, total=number of returned rows=number of visible stock codes, one requested trade_date, no invalid or masked stock codes, and no duplicates. Any failure blocks the batch; no fallback data.
5. For truly new subjects only, the ordinary detail page supplies first-level visible branch names. Child IDs are explicitly local-derived; never official IDs, and no branch-to-stock guesses.
6. Every capture is immutable evidence stored in ~/rea-analysis/jiuyinghengfeng/daily_sync_state/captures/YYYY-MM-DD/run-id. Mode plan and capture are read-only with respect to PostgreSQL.
7. Apply is allowed only from exact checked-out canonical main equal to origin/main, with no tracked modifications, on the current Asia/Shanghai weekday, with a complete real source capture dated the same day.
8. In a DB transaction, append only new nodes, visible first-level branch edges, and stock/member candidate mapping rows. No DELETE/UPDATE of existing mappings.
9. Two additive tables preserve date-scoped observations: jyhf_subject_member_capture (one row per subject per day, immutable roster hash) and jyhf_subject_member_observation (one row per subject, stock, trade date). Conflict of previously saved roster hash blocks the entire transaction.
10. Serving and staging table coverage is reconciled pair-by-pair before COMMIT. No historical membership substitution. Ended/removed members are recognizable by comparing dated observations, but do NOT delete serving rows.

## Commands

Run from the candidate worktree:

    /opt/miniconda3/envs/theme_matcher_env/bin/python -m pytest tests/jyhf_daily_sync_v1 -q

Real historical preview (never writes DB):

    /opt/miniconda3/envs/theme_matcher_env/bin/python -m tools.jyhf_daily_sync_v1.runner --mode plan --trade-date 2026-10-09 --historical-preview
    /opt/miniconda3/envs/theme_matcher_env/bin/python -m tools.jyhf_daily_sync_v1.runner --mode capture --trade-date 2026-10-09 --historical-preview --max-targets 3

After a reviewed PR is merged to main and real E2E is authorized, current-trading-day admission:

    /opt/miniconda3/envs/theme_matcher_env/bin/python -m tools.jyhf_daily_sync_v1.runner --mode daily

Mode daily = capture validated sources -> exact-main gate -> transactional DB apply and readback -> update cursor only after success. A stale or missing source returns an error, never a claimed success.

## Proposed unattended scheduling (not enabled)

An example macOS launchd agent runs at 16:45 local computer time on weekdays, using the merged main repo. It requires the JYHF App to be running and already displaying /subject/all. Weekdays that are exchange holidays will fail the quote-date gate rather than writing stale data. App closed, sleeping Mac, login expired, CDP unavailable, or locked UI will cause a BLOCKED state in launchd logs; no guarantee of zero-failure autonomy. Do not activate until merged-main verification and a successful real current trading-day E2E.

## Verification and unresolved risks

- Unit contract tests are supplementary only, not production acceptance.
- Real 2026-10-09 App session historical preview and 3-theme capture (75 real stock pairs): PASS.
- Saturday 2026-10-10 daily mode must block: PASS.
- Real current-trade-day transactional apply: NOT RUN (weekend and branch candidate).
- Per-branch leaf-level stock membership: NOT AVAILABLE from ordinary visible API; no guessing.
- Existing older subject stocks: incremental rolling sampling, not a daily full universe refresh.
- Parent/child relationships may contain local derived branch IDs; evidence provenance is mandatory.
