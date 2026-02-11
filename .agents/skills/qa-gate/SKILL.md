---
name: qa-gate
description: 当用户要求“质量门禁、单测策略、必跑命令、DoD与失败处理流程”时使用。
---

# QA Gate Flow

## Output (must)
- docs/project_control/QA_GATE.md

## Contents
1) Definition of Done (DoD)
2) Required checks
   - unit tests
   - lint
   - type check (if used)
   - formatting (if used)
3) Minimum test coverage policy (optional, if you have tooling)
4) Evidence format (commands + key outputs)
5) Failure workflow: triage -> fix -> re-run -> report

## Default Rules
- No milestone can be marked "Passed" unless all required checks are green.
- Every phase must produce a Phase Report in reports/phase-XX.md.
