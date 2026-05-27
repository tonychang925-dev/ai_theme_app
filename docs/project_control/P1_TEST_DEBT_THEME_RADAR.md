# P1-test-debt: theme-radar stage mapping

## Scope

This is a test debt record only. It is intentionally separated from Runtime Profile P0 so runtime/router fixes do not expand into theme-radar behavior changes.

## Current Failing Tests

Command:

```bash
.venv/bin/python -m pytest -q web_app_service/tests/test_p4_phase0_contracts.py
```

Known failures:

- `test_workspace_theme_radar_stage_mapping`
- `test_workspace_theme_radar_stage_enriched_from_strong_watch`
- `test_workspace_theme_radar_stage_enriched_from_theme_name`
- `test_workspace_theme_radar_stage_enriched_from_recap_snapshot`

Observed mismatch:

- Expected: `stage == "CONFIRMED"`
- Actual: `stage == "UNKNOWN"`

## Follow-up

Fix the theme-radar stage enrichment path in a dedicated P1 task. Do not couple this with Runtime Profile, realtime routing, or JYHF DOM collector work.
