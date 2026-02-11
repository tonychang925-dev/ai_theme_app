---
name: dev-orchestrator
description: 当用户要求“按阶段自动制定计划->实施->单测验证->输出报告->等待验收->进入下一阶段”时使用。
---

# Development Orchestration Flow

## Hard Constraints
- Always work on a feature branch: codex/<phase>/<topic>
- Small diffs, incremental commits
- No destructive commands without explicit user approval
- End of each phase MUST:
  1) run required commands
  2) generate reports/phase-XX.md
  3) propose review checklist
  4) stop and wait for user acceptance

## Inputs expected from user each phase
- Milestone name / Phase number
- Acceptance targets (checklist)
- Required commands to run (tests/lint/etc)

## Phase Execution Steps (must follow)
1) Planning
   - Read relevant docs + code
   - Produce WBS (tasks) + risk list
   - Produce change plan: files to touch + diff summary (no code yet)
   - Ask user to confirm plan (if uncertain)
2) Implementation
   - Apply changes stepwise
   - Keep system runnable after each step
3) Verification
   - Run user-specified commands
   - If failures: fix and re-run
4) Reporting
   - Write reports/phase-XX.md using the standard template
   - Summarize: what changed, how verified, remaining risks
5) Gate
   - Provide a checklist for review
   - STOP and wait for user acceptance decision

## Standard Review Checklist (output every phase)
- [ ] Acceptance targets all met
- [ ] Unit tests pass
- [ ] Lint/format checks pass
- [ ] No unintended API/schema breaking changes
- [ ] Docs updated (if needed)
- [ ] Rollback strategy noted (if needed)
