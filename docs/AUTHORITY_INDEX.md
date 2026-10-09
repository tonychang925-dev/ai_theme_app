# ai_theme_app 权威文档索引

> 本文件是 `docs/` 下策略与治理文档的唯一入口。实施会话开工前**必须先读本索引**，并以标为 AUTHORITY / APPROVED 的文档为准。
> 维护规则：新增、升级或作废一份权威文档，必须在同一个 PR 中更新本索引；地位变更只能由 Owner（Tony）决定。
> 最近更新：2026-10-09（D0 第二版：按 PR #450 审查意见修订，见 §7）
> 逐文件哈希：`docs/AUTHORITY_MANIFEST.tsv`（本版实际文件）；原始文档包清单：`docs/project_control/d0/BUNDLE_MANIFEST.tsv`

## 地位定义

| 地位 | 含义 |
|---|---|
| AUTHORITY | 当前生效的依据。实施必须遵守；冲突时以它为准 |
| APPROVED | Owner 已批准的计划，按批准的范围执行 |
| DRAFT_UNAUDITED | 草案，尚未审计，不得据此实施 |
| AUDIT / INVENTORY | 审计结论与清单，作为事实依据引用 |
| RECORD | 已完成任务的记录 |
| RECORD_PARTIAL | 任务记录，但记录中的部分步骤尚未完成；未完成部分不具执行效力 |
| PLAN_PENDING_APPROVAL | 待 Owner 批准的方案或任务卡；未经批准不得执行 |
| RESEARCH | 研究材料，可引用其数据，结论不具执行效力 |
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
| `project_control/AI_THEME_APP_STRATEGY_ARCHITECTURE_DRIFT_CORRECTION_DEVELOPMENT_MASTER_PLAN_v0.2.md` | **APPROVED（只批准 P0-A）**。Gate O-01 同时记录的运行决定：`SPS_ENABLE_W2S_ALERT_LOOP = DISABLE_UNTIL_P0B04_VERIFIED`（Owner 2026-10-09 裁定）。理由：该循环已知会复用陈旧候选，并可能在资金流证据缺失时给出 `high_confidence`。执行方式：收盘后由 Owner 安排运维操作关闭，P0-B04 修复并验证通过后再由 Owner 决定重新开启；在关闭生效前，其输出只作提示，不作出手依据 |
| `project_control/…MASTER_PLAN_v0.3.md` | DRAFT_UNAUDITED（如 Owner 另有裁定，以裁定为准） |
| `project_control/…MASTER_PLAN_v0.1.md` | HISTORY |
| `project_control/DEVELOPMENT_MASTER_PLAN_v0.1_AUDIT.md`、`…v0.2_AUDIT.md` | AUDIT |

## 3. 审计与清单

| 文档 | 地位 |
|---|---|
| `project_control/AI_THEME_APP_ARCHITECTURE_STRATEGY_DRIFT_CORRECTION_AUDIT_R1_DETAILED.md` | AUDIT |
| `project_control/AI_THEME_APP_DRIFT_AUDIT_R1_INDEPENDENT_VERIFICATION.md` | AUDIT（含 “start” 的勘误） |
| `project_control/EXECUTABLE_RULE_AUTHORITY_INVENTORY.md` | INVENTORY（86 条规则） |
| `project_control/CANONICAL_AND_LEGACY_DECISION_PRODUCER_INVENTORY.md` | INVENTORY（P-01…P-23；EARLY 阻断项；P-19 / P-20 已按 P0A2 更正清单 2 修订） |
| `project_control/AI_THEME_APP_PREIMPLEMENTATION_GAP_CLOSURE_P0A2.md` | AUDIT（其更正清单已回写到两份清单） |
| `project_control/unreviewed/*` | UNREVIEWED |

## 4. 工作区治理（G0）

| 文档 | 地位 |
|---|---|
| `project_control/g0/G0_CLOSURE_RECORD.md` | RECORD：唯一工作区 = `/Users/admin/Desktop/ai_theme_app`，只有 main；旧历史存档在 `archive/*` |
| `project_control/g0/G0_TASK_CARD_AI_THEME_APP_SINGLE_WORKSPACE_v2.md` | RECORD：已执行的任务卡（G0 v2.1） |
| `project_control/g0/G0_PREP_JYHF_MIGRATION_PLAN.md` | PLAN_PENDING_APPROVAL：标题注明“待 Tony 批准”；文件内未记录批准，不得据此执行 |
| `project_control/g0/G0_POST_RELOCATION_RECOVERY_CARD.md` | PLAN_PENDING_APPROVAL：标题注明“待 Tony 批准”；文件内未记录批准，不得据此执行 |
| `project_control/g0/JULIA_BRANCH_CLOSEOUT_STEP0_2_3_REPORT.md` | RECORD_PARTIAL：第 0 步未完成；未完成部分不具执行效力 |
| `project_control/g0/JULIA_BRANCH_VS_JULIA_CORE_OVERLAP_AUDIT.md` | AUDIT |
| `project_control/g0/julia_branch_file_classification.tsv` | AUDIT（上一行审计的附件数据） |
| `project_control/d0/BUNDLE_MANIFEST.tsv`、`BUNDLE_MANIFEST.sha256` | RECORD：D0 原始文档包的逐文件 SHA256 清单（v1 的 31 个文件） |
| `AUTHORITY_MANIFEST.tsv` | RECORD：本版文档集的逐文件 SHA256；`changed_from_bundle` 列标出相对原始文档包新增或修改的文件 |

## 5. 研究与参考（市场情绪、题材目录；均为 Mira 起草，未经 Owner 冻结）

| 文档 | 地位 |
|---|---|
| `strategy_research/MARKET_EMOTION_QUANT_AUDIT_AND_DESIGN_v0.1.md` | AUDIT + 设计提案（含补遗 v0.1.1） |
| `strategy_research/MARKET_EMOTION_VALIDATION_HAOGE_0624_0717.md` | RESEARCH（样本内 18 天）；转录数据与复现脚本：`strategy_research/haoge_data/` |
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

## 7. 修订记录

| 日期 | 版本 | 内容 |
|---|---|---|
| 2026-10-08 | D0 v1 | 首次建立，31 个文件原样来自文档包（`BUNDLE_MANIFEST.tsv`，清单 SHA256 `51f6cc2d…c8`） |
| 2026-10-09 | D0 v2 | 按 PR #450 审查修订：① 记录 Gate O-01 的 W2S 预警运行决定（Owner 裁定 DISABLE_UNTIL_P0B04_VERIFIED）；② 生产者清单 P-19 / P-20 按 P0A2 更正清单 2 改为在线；③ G0 文件逐个标注地位，区分已完成记录、未批准方案和未完成记录；④ 提交原始文档包清单和本版逐文件哈希；⑤ 规则清单 §1 七条规则补上稳定 ID（M-01…M-07）；⑥ 提交昊哥情绪验证的转录数据和复现脚本。被修改文件的新哈希见 `AUTHORITY_MANIFEST.tsv` 的 `changed_from_bundle` 列 |
