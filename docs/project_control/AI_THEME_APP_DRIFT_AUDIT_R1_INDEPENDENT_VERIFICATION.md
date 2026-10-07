# AI Theme App — Drift Correction Audit R1：独立核验

> **核验对象**：`docs/project_control/AI_THEME_APP_ARCHITECTURE_STRATEGY_DRIFT_CORRECTION_AUDIT_R1_DETAILED.md`
> - SHA256 `108ea48e71a3e997bc3d36c58cbf1b4835a7768584fb1b8bf5bb3636ca046f64`，2143 行，已核对一致
> **代码基准**：`tonychang925-dev/ai_theme_app@ddc9442e88c5bf6f5248bfb141e74472c48eb25a`（本地 clone，HEAD 已核对）
> **策略基准**：v0.6.4 APPROVED WORKING BASELINE（SHA256 `f75dd662…1d2b`），**未冻结**
> **核验人**：Mira（Claude），2026-10-06
> **方式**：只读。逐条回到源码核对 R1 的结论，给出文件和行号。**没有修改任何代码、数据库或配置。**
> **定位**：R1 是总审计。本文只回答三个问题：R1 哪些说对了？哪些需要更正？漏了什么？本文不另起一套审计。

---

## 0. 结论

R1 的总体判断成立：旧链语义好、工程差；新链工程好、语义漂移；新旧两条链并行。纠偏优先、不重设计的方向也对。**我建议以 R1 作为纠偏总依据。**

但有 **3 处需要更正**，其中第 1 处会直接改变纠偏的顺序：

1. **L3 结构性缺口（R1 低估了）**：新链的周期状态**只对已确认的主线计算**，而且状态词汇里**没有 EARLY**。所以“候选主线 + 初期 → 1进2 试错”这个已批准的语义，在现在的架构里**根本表达不出来**。只改 1进2 的 confirmed_mainline 门槛（R1 DR-005 的“最小纠偏”）解决不了问题；交易许可层（L4）还会再挡一次。
2. **L1 的实际生产者认错了**：R1 把 `MarketEmotionEngine` 当作当前的混词生产者。实际上它**全仓库零引用**，是死代码。真正在线、给前端情绪页供数据的是 `NarrativeEngine`。R1 完全没提到它，而它正是用单一变量把大盘映射成周期词的那个模块。
3. **直连数据库的问题比 R1 说的更深**：R1 只说 Application 层越界，实际 **Domain 层也直接 `import asyncpg` 建连接池写 SQL**。

另外有 4 处小问题（§3）。

---

## 1. R1 结论逐条核验

| R1 编号 | R1 的结论 | 核验 | 证据（main@ddc9442） |
|---|---|---|---|
| DR-001 | 盘后复盘任务里新旧两条决策链并存 | **成立** | `application/jobs/build_post_market_recap_job.py`：L27 引入旧 `PostMarketDecisionEngine`，L129 实例化，L828–834 执行后 `recap_doc.update(decision_payload)` 并入复盘文档；L1768–1790 同时跑 `PostMarketDecisionEngineV2` |
| DR-002 | 大盘层使用周期词，作用域混用 | **成立，但生产者认错了**，见 §2.2 | `MarketEmotionEngine`（`market_cognition/emotion_engine.py` L54）全仓库**没有任何引用**（.py / .ts / .tsx 都查过）；`cycle_fsm_v1.yaml` 只被 3 个脚本引用。在线的混词路径是 `NarrativeEngine` → `/api/v1/emotion` |
| DR-003 | 题材周期由“加权分 → 状态”直接决定 | **成立** | `domain/services/subject_cycle_judgement_service.py` L30–38：阈值 60/60/60/65/75/60；L103–127：按优先级逐级判断（fade_confirmed → repair → divergence → acceleration → fermentation） |
| DR-004 | 估算值、缺失值进入正式判断 | **成立** | `market_metrics/service.py` L731 `chain_red` 由反馈分反推；L732 `chain_loss = 首板大面 × 0.8`；L733 `yest_red = 0.5`；L735–742 无数据时用涨跌家数估算；L705 活跃资金 × 2.04。W2S 部分见 DR-006 |
| DR-005 | 1进2 要求 confirmed_mainline 才能 focus | **成立，但只修这一处不够**，见 §2.1 | `domain/services/one_to_two_rule_engine.py` L125–127：非 confirmed_mainline → `pending_review_only`，提示“不得 focus”。L38 允许强热点进入候选，这一点是对的 |
| DR-006 | W2S 资格放宽、缺数据也能通过 | **成立** | `domain/services/w2s_candidate_service.py`：L222–230 缺周线数据 → `passed: True`（`weekly_data_insufficient_bypass`）；L506 `strong_background = 龙头 OR 涨停 OR 近期涨停≥2 OR 排名≤3`；L512–519 前一状态未知时默认软通过（环境变量默认 `"1"`） |
| DR-007 | 35/30/20/15 被当成加权分 | **成立，而且还多一层错** | `domain/services/post_market_decision/theme_decision_engine.py` L195–198。另外，这里的 30% 用的是 `market_environment_score`，但按 v0.6.4（M-11），原文里 30% 的“情绪”指的是**主线周期**，不是大盘环境 |
| DR-008 | Application 层直连数据库 | **成立，范围更大**，见 §2.3 | 粗略统计：Application 33 个文件、Domain 11 个文件出现 `asyncpg` / `._pool` / `._db` / `._client` / `execute_query` / `SELECT…FROM`。其中含误报（例如 HTTP client），需要逐个分类 |
| DR-009 | 仓位等阈值未经授权写死 | **成立** | `domain/services/market_regime/trading_permission_engine.py` L67/76/84/91：仓位上限 0.2 / 0.15 / 0.3 / 0.5（OP-16 未冻结）。`one_to_two_rule_config.py` L25–26、L58–66：换手 8%，否决线 5% / 3%（OP-10 未冻结） |
| DR-010 | 同一能力有多个生产者 | **成立** | 大盘层至少有：NarrativeEngine（在线）、MarketRegime 系列（新链）、旧 MarketEnvironmentEngine、MarketEmotionEngine（死代码）、CycleFSM（脚本） |
| DR-011 ~ 014 | L8 预期、L12 学习、两板绕过、可追溯性 | 未逐行核验 | 方向与 v0.6.4 一致，无异议 |

---

## 2. 需要更正的三处

### 2.1 L3 结构性缺口：初期主线在新链里无法表达（P0，影响纠偏顺序）

**证据：**
- `application/services/mainline_lifecycle/mainline_lifecycle_fact_context_builder.py` L3、L22、L41–46：周期事实只从 `get_active_confirmed_mainlines` 读取。**候选主线不计算周期。**
- 新链周期词汇（domain 中出现的状态字面量）：`fermentation / acceleration / climax / divergence / repair / fade_watch / fade_confirmed / dead`。
  - **没有** `early`、`catch_up`、`ended`；
  - 多出了 v0.6.4 没有的 `fade_watch`、`fade_confirmed`、`dead`。
- `domain/services/market_regime/trading_permission_engine.py` L31–34：主线环境为 `no_confirmed_mainline` 时，`position_limit = 0.0`，理由是“无人工确认主线”。**这里是在许可层整体关闭交易。**

**后果**：v0.6.4 已批准的两条语义，在现有架构里是**结构性不可达**：
- OP-11：EARLY_PROBE，初期轻仓试错；
- §5.5：1进2 在“候选主线 + EARLY”窗口内有资格。

阻断发生在三个地方，按顺序是：

```text
① L3 不对候选主线计算周期，而且词汇里没有 EARLY
② L4 许可层在“无确认主线”时把仓位上限设为 0
③ 1进2 规则引擎要求 confirmed_mainline 才能 focus
```

R1 只指出了 ③。只修 ③，①② 仍然会把它挡住。

**对 R1 纠偏顺序的建议**：R1 Phase B3（L3 语义恢复）里要明确加上两项：
- 周期计算覆盖 CANDIDATE 主线；
- 周期词汇对齐 v0.6.4，补上 EARLY、CATCH_UP、ENDED；`fade_watch`、`fade_confirmed`、`dead` 怎么映射，要单独列成待决项，不能自行合并。

Phase C1 的许可层要能区分“无确认主线”和“有候选主线、处于初期”。Phase D1 改 1进2 必须排在这两项之后。

### 2.2 L1 的在线生产者是 NarrativeEngine，不是 MarketEmotionEngine（P0）

**证据：**
- `application/services/market_metrics/narrative_engine.py` L393–409 `_phase_label`：除了“恐慌 / 冰点”的几条升级规则以外，**市场阶段只由 `feedback_score` 一个变量分段决定**：`<-40` 为退潮，`<-10` 为分歧，`<20` 为混沌，`<50` 为修复，否则为强势。
- `api_app.py` L8034 `/api/v1/emotion/{trade_date}`，L8057–8061：把上面的阶段映射成 `ICE_POINT / FADE / DIVERGENCE / REPAIR / CHAOS / CLIMAX` 返回给前端。
- `MarketEmotionEngine` 全仓库没有引用。

**后果**：前端情绪页展示的“大盘处于分歧 / 修复 / 退潮”，正是 v0.6.4 §4.3 要消除的作用域混用：用题材周期的词描述大盘，而且只看一个变量、没有前一状态的记忆。这和我在 `MARKET_EMOTION_QUANT_AUDIT_AND_DESIGN_v0.1` 中查到的“62 天里 36 天是 CHAOS、从未出现 CLIMAX”是同一个根源。

**对 R1 的建议**：
- DR-002 的对象改为 **NarrativeEngine + `/api/v1/emotion` 映射**；
- MarketEmotionEngine 和 CycleFSM 归入“死代码 / 脚本”，在 Phase E 统一清理，不必作为 P0。

### 2.3 Domain 层也直连数据库（P0）

**证据**：`domain/services/w2s_intraday_alert_service.py` L24 `import asyncpg`；L96–101 自建连接池；L183、L188 直接写 SQL 读 `stock_position_judgement`、`stock_pattern_judgement`。

**后果**：违反了 `stock_processing_service` 架构设计中“Domain 只做业务算法”的冻结边界。R1 §5.1 只写了 Application 层。

**对 R1 的建议**：
- DR-008 的范围扩大到 Domain 层；
- P0A 盘点时，Domain 层的命中要单独列出。Domain 层的优先级应高于 Application 层，因为它直接破坏“领域层纯净”这条最基本的边界。

---

## 3. 小问题

| # | 位置 | 问题 | 建议 |
|---|---|---|---|
| m-1 | R1 §1.1 | 把 CS-01…CS-12 一并列为最高策略权威 | 按 v0.6.4 §0.2：CS-10–12 是 tier C，**没有交易规则权威**，只在题材研究方法上有限定权威；CS-09 是 tier B，交易规则权威只限 p32–33 |
| m-2 | R1 §5.1 vs 附录 B | §5.1 写“R0 and source inspection show…”，附录 B 又说 R0 没找到、没有使用 | §5.1 删掉对 R0 的引用。该结论本身已由本文 §2.3 独立证实 |
| m-3 | R1 §5.5 | 没有列出 `first_red = relay.continue_ratio`（`market_metrics/service.py` L726） | 这是**口径错误**，不是估算：“昨日首板今日红盘比”被算成了“昨日涨停今日继续涨停率”。应列为 WRONG_DATA |
| m-4 | R1 §5.8 | 没有提到 W2S 评分把 `fade_watch`（75）排在 `divergence`（55）之上（`w2s_candidate_service.py` L194–205），以及 `strong_grade` 缺失时默认取 `"B"`（L379） | 前者把“接近退潮”的题材排在“分歧”之前，与 OP-20“题材 FADE → 弱转强不成立”方向相反；后者是缺失值被赋予默认等级。都应列入 DR-006 |

---

## 4. 关于 R1 第 18 节的第一批任务（P0A）

R1 自己写明“文档本身不构成实施授权”。我同意。需要提醒的是，P0A 的 6 项交付物性质不同：

| P0A 交付物 | 性质 | 当前授权（Tony，2026-10-06：只读审计） |
|---|---|---|
| 1. 可执行阈值 / 门槛的权威分类清单 | 只读盘点 | **已授权** |
| 5. 新旧并行决策生产者清单 | 只读盘点 | **已授权** |
| 2. 禁止新增直连数据库的契约测试 | **写代码**（测试） | 未授权 |
| 3. 禁止“缺失 → 通过”的契约测试 | **写代码**（测试） | 未授权 |
| 4. 估算值进入正式门槛时输出诊断 | **改业务代码** | 未授权 |
| 6. 不切换生产 | — | — |

所以在 Tony 明确开始实施之前，我能做的只有第 1、5 两项。第 2、3、4 项要等 Tony 授权实施后才能动。

---

## 5. 关于 R0

R1 附录 B 提到，`docs/project_control/ARCHITECTURE_CODE_SEMANTIC_AUDIT_R0_DETAILED.md` 是“之前 Claude 声称生成的”。

- **我在本会话中没有生成、也没有声称生成过这个文件。** 本会话之前给出的审计结论都在项目文档 `MARKET_EMOTION_QUANT_AUDIT_AND_DESIGN_v0.1.md` 里。
- 我也在两个本地目录（`Desktop/ai_theme_app`、`glm-workspace/ai_theme_app`）里搜索了这个文件名，确实不存在。
- 如果它来自另一个 Claude 会话，那份声明需要 Tony 去那个会话核实。R1 不把它当作依据，这个处理是对的。

---

## 6. 核验过程中的一个操作事故（已处理）

核验开始时，我在 `glm-workspace/ai_theme_app` 里运行了一次 `git status`，想确认工作区干净。

- 这个命令会尝试刷新 git 索引。它在只读挂载上留下了一个**空的 `.git/index.lock`**，这个文件会挡住 Tony 后续的 git 操作。
- 我已经申请删除权限，只删除了这一个空文件，确认它已不存在。
- 此后所有命令只用 `grep` / `sed` / `ls` 这类纯读取命令。
- 仓库的代码、分支、提交都没有被改动。

---

## 7. 状态

```text
R1                                 = 总体成立，建议作为纠偏总依据
R1 需更正                           = 3 处（§2.1 L3 结构性缺口 / §2.2 NarrativeEngine / §2.3 Domain 直连数据库）
R1 小问题                           = 4 处（§3）
策略基线                            = v0.6.4 APPROVED WORKING BASELINE（未冻结）
本次核验                            = 只读；无代码、数据库、配置改动
可立即做（已授权、只读）              = P0A 第 1 项（阈值权威清单）、第 5 项（并行生产者清单）
需 Tony 另行授权                     = P0A 第 2–4 项，以及之后所有实施
```

---

## 勘误（2026-10-07，盘点清单时发现）

§0 第 1 点和 §2.1 写的“新链周期词汇里**没有 EARLY**”**不准确**。

- Layer B 的 `SubjectCycleJudgementService` 会输出 `start`（`subject_cycle_judgement_service.py:128–130`）；适配器里还有 `seed` / `start`；许可层把 `start` 当成可交易。
- 准确的说法是：`start` 是**残差默认值**，所有没达到阈值的题材都会落到这里，所以它在语义上**不等于** EARLY。

阻断主因仍然成立，而且比原来写的多一处。完整的阻断链是：

- **B0**：1进2 的主线上下文只取已确认主线；
- **B1**：周期复核只覆盖已确认主线；
- **B1'**：`start` 是残差，不是 EARLY；
- **B2**：许可层没有已确认主线时，仓位为 0；
- **B3**：1进2 要求已确认主线才能 focus。

详见 `CANONICAL_AND_LEGACY_DECISION_PRODUCER_INVENTORY.md` §3、§5。
