# ai_theme_app 权威文档索引

> 本文件是 `docs/` 下策略与治理文档的唯一入口。实施会话开工前**必须先读本索引**，并以标为 AUTHORITY / APPROVED 的文档为准。
> 维护规则：新增、升级或作废一份权威文档，必须在同一个 PR 中更新本索引；地位变更只能由 Owner（Tony）决定。
> 最近更新：2026-10-08（D0 任务首次建立）

## 地位定义

| 地位 | 含义 |
|---|---|
| AUTHORITY | 当前生效的依据。实施必须遵守；冲突时以它为准 |
| APPROVED | Owner 已批准的计划，按批准的范围执行 |
| DRAFT_UNAUDITED | 草案，尚未审计，不得据此实施 |
| AUDIT / INVENTORY | 审计结论与清单，作为事实依据引用 |
| RECORD | 已完成任务的记录 |
| HISTORY | 已被取代的旧版本，仅供追溯 |
| UNREVIEWED | 未经审查的材料，不具任何权威 |

## 1. 策略模型

| 文档 | 地位 |
|---|---|
| `strategy_model/AI_THEME_APP_CANONICAL_INVESTMENT_STRATEGY_DEVELOPMENT_MODEL_v0.6.4_APPROVED_WORKING_BASELINE.md` | **AUTHORITY**：Owner 已批准的工作基线，**尚未冻结**；之后还会反复讨论、修订，最终冻结 |
| `strategy_model/history/…v0.6_DRAFT.md` ~ `…v0.6.3_DRAFT.md` | HISTORY |

## 2. 开发总计划

| 文档 | 地位 |
|---|---|
| `project_control/AI_THEME_APP_STRATEGY_ARCHITECTURE_DRIFT_CORRECTION_DEVELOPMENT_MASTER_PLAN_v0.2.md` | **APPROVED（只批准 P0-A）** |
| `project_control/…MASTER_PLAN_v0.3.md` | DRAFT_UNAUDITED（如 Owner 另有裁定，以裁定为准） |
| `project_control/…MASTER_PLAN_v0.1.md` | HISTORY |
| `project_control/DEVELOPMENT_MASTER_PLAN_v0.1_AUDIT.md`、`…v0.2_AUDIT.md` | AUDIT |

## 3. 审计与清单

| 文档 | 地位 |
|---|---|
| `project_control/AI_THEME_APP_ARCHITECTURE_STRATEGY_DRIFT_CORRECTION_AUDIT_R1_DETAILED.md` | AUDIT |
| `project_control/AI_THEME_APP_DRIFT_AUDIT_R1_INDEPENDENT_VERIFICATION.md` | AUDIT（含 “start” 的勘误） |
| `project_control/EXECUTABLE_RULE_AUTHORITY_INVENTORY.md` | INVENTORY（86 条规则） |
| `project_control/CANONICAL_AND_LEGACY_DECISION_PRODUCER_INVENTORY.md` | INVENTORY（P-01…P-23；EARLY 阻断项） |
| `project_control/AI_THEME_APP_PREIMPLEMENTATION_GAP_CLOSURE_P0A2.md` | AUDIT |
| `project_control/unreviewed/*` | UNREVIEWED |

## 4. 工作区治理（G0）

| 文档 | 地位 |
|---|---|
| `project_control/g0/G0_CLOSURE_RECORD.md` | RECORD：唯一工作区 = `/Users/admin/Desktop/ai_theme_app`，只有 main；旧历史存档在 `archive/*` |
| `project_control/g0/*`（其余文件） | RECORD |

## 5. 研究与参考（市场情绪、题材目录；均为 Mira 起草，未经 Owner 冻结）

| 文档 | 地位 |
|---|---|
| `strategy_research/MARKET_EMOTION_QUANT_AUDIT_AND_DESIGN_v0.1.md` | AUDIT + 设计提案（含补遗 v0.1.1） |
| `strategy_research/MARKET_EMOTION_VALIDATION_HAOGE_0624_0717.md` | RESEARCH（样本内 18 天） |
| `strategy_research/MARKET_EMOTION_VALIDATION_v2_OOS_0731_0929.md` | RESEARCH（样本外 42 天；V2 阈值已用到这批数据，因此**不再算样本外**） |
| `strategy_research/HAOGE_METRIC_REGISTRY_v0.1.md` | DRAFT：公式尚未全部闭合，**不授权实现** |
| `strategy_research/THEME_CATALOG_v0.1.md` | DRAFT：试点题材的成分股待补 |
| `strategy_model/history/AI_THEME_APP_STRATEGY_MODEL_AND_EXECUTABLE_CONTRACT_v0.5.0.md` | HISTORY：已被 v0.6.4 取代 |

## 6. 常设规则（Owner）

- 一个项目只有一个工作区：`/Users/admin/Desktop/ai_theme_app`。禁止任何副本、clone 和额外的 worktree。
- **Agent 不得创建任何分支。** 任务分支由 Tony 创建；一个任务一条分支，合并后当天删除。
- 每个实施 PR 都必须由**另一个会话**审查确切的 HEAD，并由 Tony 合并。
- 盘中不在工作区里切换分支（服务目前直接从工作区运行）。
- 禁止任何会打印进程环境变量或密钥的命令（例如 `ps eww`、`env`、`printenv`、`cat .env`）。
