# P3 D1 Baseline Record

- Phase: `P3`
- Task: `P3.phase0-T01`
- Date: `2026-04-23`
- Purpose: 冻结开发窗口、隔离运行产物、固化 P3 真源文档基线。

## 1. Mandatory Guard Command

```bash
.venv/bin/python scripts/p3_d1_workspace_guard.py --output tmp/p3_d1_workspace_guard_report.json
```

严格模式（存在高风险改动则返回非0）：

```bash
.venv/bin/python scripts/p3_d1_workspace_guard.py --strict --output tmp/p3_d1_workspace_guard_report.json
```

## 2. High-Risk Change Scope

以下路径默认视为高风险（应从功能提交中剥离）：
- `theme_data_complete/**`
- `tmp/**`
- `.claude-dev/**`

## 3. D1 Done Criteria

- 生成 `tmp/p3_d1_workspace_guard_report.json`
- `high_risk = 0`（或高风险变更已说明并单独处理）
- P3 真源文档已同步对齐：
  - `docs/project_control/PLAN_WBS.md`
  - `docs/project_control/FEATURE_SPEC_P3.md`
  - `tmp/feature_traceability_P3.json`

