# AI Theme App — 投资策略模型与可执行合同 v0.5.0

## Strategy Model & Executable Contract

> **Status**: DRAFT_FOR_OWNER_REVIEW
> **取代范围**: 取代 v0.4.2 的全部策略语义（第 6–7、12–15、25 节）与 `OWNER_FREEZE_CANDIDATE_v0.4.2`；工程合同（第 1–5、8–11、16–24 节）继承，并在本文件内修订。
> **Implementation Authorization**: SCHEMA / VALIDATOR / REPLAY INFRA / L1 测量计算 / 数据质量校验
> **Production Strategy Authority**: NO
> **Live Ordering**: NO
> **Date**: 2026-10-06
> **Author**: Mira（Claude），基于 v0.4.2 与 `~/Desktop/投资策略` 全部来源的逐条对照
> **重要**: 本文件中的任何策略规则都不会因为“写在这里”而被冻结；冻结只能来自第 XVI 部分的 Owner 显式批准。

---

# Part 0 — 读法、变更原因与规范组件

## 0.1 为什么要有 v0.5

v0.4.2 的工程合同很扎实，但作为“投资策略模型”有一个结构性缺陷：

```text
原始体系（CS-01 / CS-03）:
  高胜算交易 = 主线(35%) + 情绪(30%) + 龙头(20%) + 买点(15%)

v0.4.2 完整定义的模块:
  OneToTwo / WeakToStrong / Auction   → 全部属于“买点”层（15%）

v0.4.2 只有入口、没有定义的:
  主线判定（CONFIRMED_MAINLINE 如何得出）
  情绪周期（W2S-022、OF-03 引用的“退潮”无人判定）
  龙头识别（W2S-019 “必须是龙头”，但龙头无定义）
  市场环境 / 风格判断（原文“大环境保护”“择时重于择股”）
```

v0.5 的核心改动是**把模型从根部补齐**：L1 市场环境 → L2 主线 → L3 情绪周期 → L4 龙头定位 → L5 战法 → L6 确认 → L7 仓位风险 → L8 退出 → L9 复盘闭环，并修正 v0.4.2 规则注册表中对原文的偏离。

## 0.2 变更摘要（v0.4.2 → v0.5.0）

| # | 变更 | 位置 | 类型 |
|---|---|---|---|
| C-01 | 新增 L1 市场环境与风格层 | Part IV | 新增 |
| C-02 | 新增 L2 题材与主线判定（含 CONFIRMED_MAINLINE 的定义） | Part V | 新增 |
| C-03 | 新增 L3 题材情绪周期状态机与动作矩阵 | Part VI | 新增 |
| C-04 | 新增 L4 龙头定位（龙头/龙二/卡位/套利/补涨/跟风） | Part VII | 新增 |
| C-05 | 35/30/20/15 明确为“否决顺序与重要性”，禁止加权求和出买点 | §2.1 | 修正 |
| C-06 | OTO-001 删除“强热点”口径，与 OF-01 统一 | §8.3 | 修正（自相矛盾） |
| C-07 | 原文明确“不选”的条件恢复为 EXCLUSION，不再挂 OWNER_SEVERITY_UNFROZEN | §8.3 | 修正 |
| C-08 | 补齐原文已有、但注册表遗漏的排除规则（一年内连板大幅回落、高位首板、生死线、压力位） | §8.3 | 补漏 |
| C-09 | v0.4.2 OTO-012 与 OTO-003 重复，合并 | §8.3 | 去重 |
| C-10 | 退出规则类型修正（OTO-024/025 原标为信号），OTO-023 语义纠正 | §8.3 | 修正 |
| C-11 | W2S 补齐全部 EXIT 规则（原注册表为零） | §8.4 | 补漏 |
| C-12 | W2S 补齐环境门槛（大环境好时龙头分歧绝不能买 / 被动分歧） | §8.4 | 补漏 |
| C-13 | **T+1 约束与退出规则交叉校验**：当日买入当日触发的退出改为次日执行 | §3.5、Part X | 修正（交易逻辑 bug） |
| C-14 | Decision 与 Position State 分离：ENTERED 不再是决策 | §3.1 | 修正 |
| C-15 | 入场必须登记确定性止损（RISK-001），OF-03 改写 | §9.2、§10.3 | 修正 |
| C-16 | OF-03 删除“前一日分时低点被破=持仓终局卖点”（原文中它是买入前的护盘条件） | §10.3 | 修正（越界） |
| C-17 | 新增“止盈”退出类别（v0.4.2 无止盈） | §10.1 | 补漏 |
| C-18 | 新增阈值注册表，原文已有的数字作为带出处的种子值登记 | Part XIV | 新增 |
| C-19 | 新增来源冲突/歧义登记表 | Part XV | 新增 |
| C-20 | 规则状态拆为三维：source / empirical / owner；SOURCE_VERIFIED ≠ 有效 | §1.2 | 修正 |
| C-21 | 新增数据质量合同，登记 M8 抽取已知缺陷（loss_effect_ratio 缩放错误等） | Part XI | 新增 |
| C-22 | 数据可得性门槛：所需数据不可得的规则输出 UNKNOWN，而不是静默通过 | §11.2 | 新增 |
| C-23 | 新增复盘与学习闭环（自己的交易记录） | Part XIII | 新增 |
| C-24 | Owner 决策项由 3 个扩展为 11 个 | Part XVI | 扩展 |

## 0.3 规范组件

```text
本文件（Markdown）                               = 当前唯一规范来源
AI_THEME_APP_EXECUTABLE_STRATEGY_SCHEMA_v0.5.json   = NOT_YET_GENERATED
AI_THEME_APP_RULE_REGISTRY_v0.5.json                = NOT_YET_GENERATED
AI_THEME_APP_STATE_TRANSITIONS_v0.5.json            = NOT_YET_GENERATED
AI_THEME_APP_THRESHOLD_REGISTRY_v0.5.json           = NOT_YET_GENERATED
```

规则：JSON 组件由本文件生成，并通过“Markdown ↔ JSON 一致性校验”后才成为规范组件。v0.4.2 的三个 JSON 文件本次未提供审阅，**不得直接沿用**，必须按本文件重新生成。

---

# Part I — 来源与权威

## 1.1 来源注册表

所在目录：`/Users/admin/Desktop/投资策略`（SHA256 于 2026-10-06 计算）。

| ID | 文件 | SHA256 | 角色 | 权威等级 |
|---|---|---|---|---|
| CS-01 | 交易体系.key（三张流程图：短线交易系统 / 1进2操作流程 / 弱转强操作流程） | `1adfdbf19ee580ce1e54f01776d4b38c01741d5142f46201a9f3d3f77c64e407` | 体系总图 | NORMATIVE_OWNER_NOTE |
| CS-02 | 市场情绪周期.key | `6f3302777b3f75f0f14704fb150cc84172db74aca37d415426947db92397b791` | 情绪周期图 | NORMATIVE_OWNER_NOTE |
| CS-03 | 如何建立正确的交易体系.pdf（笔记14，8页） | `05d7108a557d91a9e45a7653af92cc2cf72236796962e6965420b29a40dc8676` | 体系正文 | NORMATIVE_OWNER_NOTE |
| CS-04 | 1进2买入法.pdf（笔记10，4页） | `4f8161aa514b48998e5037d7f5e074ecd6220d603a188f9c2b9a653be114f00a` | 战法 | NORMATIVE_OWNER_NOTE |
| CS-05 | 弱转强买入法.pdf（笔记17，5页） | `84f33649b1071f337e6c2f02fd2c4421fe59b772c153b0a2e12201226d6035b0` | 战法 | NORMATIVE_OWNER_NOTE |
| CS-06 | 投资学习笔记（16）_集合竞价.pdf（6页；`集合竞价.pdf` 为同一文件） | `89f0658b81b554c022fb000c9444723cd02c9acb5ec22a70f483a84c77c7ee80` | 确认工具 | NORMATIVE_OWNER_NOTE |
| CS-07 | 如何抓涨停股？.pdf（笔记11，3页） | `2186f1bb0735fc4214f615ec80b0089e683f728a1e3312f055525b5af038918c` | 龙头/涨停特征 | NORMATIVE_OWNER_NOTE |
| CS-08 | 如何找出牛股.pdf（笔记12，3页） | `7eb3f43221ff3ed521c8b5c7a5fafecc50fc9a56de868ccea811888b6d389dbf` | 强势股特征 | NORMATIVE_OWNER_NOTE |
| CS-09 | 股市见顶有哪4个强烈的见顶和离场讯号.docx | `9baf5de439ac9e38c774b3054816cbda5afa4f6d680e040ce6a8c77805258306` | 指数见顶（美股语境） | REFERENCE_ONLY |
| CS-10 | 缠中说禅：教你炒股票108课.pdf | `25625e82b7675ba35b1bb67dccce2f8420b080473742569461083f72c98a2e64` | 另一流派 | REFERENCE_ONLY（v0.5 不引用） |
| TH-01 | 2026年投资逻辑梳理（1）——国产算力.pdf | `bf70f258f804cd37163347b10c57231e3159b3ea256358cbff4c17a13adfa39f` | 题材研究（2025-12） | THEME_RESEARCH（有时效） |
| TH-02 | 2026年投资逻辑梳理（2）——商业航天.pdf | `f6c57595c91aa1f69a5d2a9cfc848fd37692d494b4025cff0953af9b697f696c` | 题材研究（2025-12） | THEME_RESEARCH（有时效） |
| TH-03 | 大科技（人工智能）逻辑.key | `35698fbaad19dbe6bb8a7cd3c21523dc3b9dd741cd7c792a272a9d6a691956af` | 产业链图谱 | THEME_RESEARCH（有时效） |
| TH-04 | A股题材&强势股跟踪.pdf（12/16，33页） | `b647f76744e1a597b0dff95d8496ba841a8c17407e6f2c671d13e233bfa91321` | 日跟踪模板 + 操作原则 | NORMATIVE_OWNER_NOTE（仅 p32–33 操作原则）/ 其余 THEME_RESEARCH |
| EXT-01 | 昊哥复盘 7/1、7/2、7/3(实为7/5发布)、7/6、7/7、7/8、7/9（md/pdf，含 DeepSeek 版） | 见附录 A | 外部信号与市场数据 | EXTERNAL_SIGNAL（非权威） |

**CS 编号说明**：CS-01、CS-03、CS-04、CS-05、CS-06 与 v0.4.2 的引用口径一致。CS-02、CS-07 及之后的编号由本文件分配，需与 Handbook v0.3.2 的编号核对（Handbook 本次未提供）。

**权威等级含义**：

```text
NORMATIVE_OWNER_NOTE : Owner 自己的方法论笔记，可作为规则来源
THEME_RESEARCH       : 题材与个股研究，只作为题材目录种子，带时效；其中“网传/未证实”内容按传闻处理
EXTERNAL_SIGNAL      : 外部作者观点与数据，可作为测量数据和假设来源，不能单独构成规则
REFERENCE_ONLY       : 参考，不产生规则，除非 Owner 另行批准
```

## 1.2 规则状态三维（修正 v0.4.2 的单维 Owner Status）

每条规则必须同时标注：

```text
source_status:
  SOURCE_VERIFIED     原文明确写了
  SOURCE_INFERRED     由原文推导（必须写推导理由）
  SOURCE_CONFLICT     原文之间互相矛盾（见 Part XV）
  PROPOSED_BY_AGENT   原文没有，由起草者提出

empirical_status:
  UNTESTED / IN_SAMPLE_ONLY / OOS_SUPPORTED / OOS_REJECTED

owner_status:
  FROZEN / UNFROZEN / PENDING_DECISION(OF-xx)
```

不变量：

```text
SOURCE_VERIFIED 只表示“忠实于笔记”，不表示“规则有效”。
任何规则进入生产决策的前提：owner_status = FROZEN 且 empirical_status = OOS_SUPPORTED。
当前全部规则 empirical_status = UNTESTED。
```

---

# Part II — 模型总览

## 2.1 核心公式的正确解读

```text
高胜算交易 = 主线(35%) + 情绪(30%) + 龙头(20%) + 买点(15%)        [CS-01 短线交易系统; CS-03]
交易心法：把握节奏 > 单纯选股；错过宁可空仓                       [CS-01]
择时重于择股，周期重于题材                                         [CS-03 p4]
```

规范解读：

```text
1. 百分比表示“重要性与否决顺序”，不是可加总的评分权重。
2. 上层否决，下层不得推翻：主线不成立 → 不看情绪；情绪不允许 → 不看龙头；以此类推。
3. 禁止：任何加权综合分（包括 Auction Score、Leader Score）直接生成 ENTRY_ELIGIBLE。
   （AUC-015 原只约束竞价分，v0.5 推广为全局不变量 INV-001）
4. 凡不满足原则者一律空仓观望，宁愿错过也绝不随便买入。          [CS-03 p7 结论]
```

## 2.2 分层管线

```text
L0  数据与数据质量            Part XI
L1  市场环境与风格            Part IV   —— “大环境保护”
L2  题材与主线                Part V    —— 35%
L3  题材情绪周期              Part VI   —— 30%
L4  龙头定位                  Part VII  —— 20%
L5  战法 Setup（OTO / W2S）    Part VIII —— 15%
L6  竞价与分时确认            §8.5–8.6
L7  仓位与风险                Part IX
L8  退出                      Part X
L9  复盘与学习闭环            Part XIII
```

不变量 INV-002（只收紧）：每一层输出“允许集合”，下层只能在上层的允许集合内进一步收紧，不能放宽。

## 2.3 确定性与认知判断的边界

| 类别 | 例子 | 实现方式 |
|---|---|---|
| DETERMINISTIC_MEASUREMENT | 涨停数、晋级率、换手率、封板时间、均线位置 | 纯计算，可重放 |
| DETERMINISTIC_INVARIANT | T+1、as-of、止损触发、去重、状态转移合法性 | 纯计算，validator 强制 |
| THRESHOLD_JUDGEMENT | 换手是否“充分”、情绪是否“冰点” | 测量值 + 版本化阈值策略 |
| COGNITIVE_JUDGEMENT | 题材新颖度、是否“最正宗”、逻辑影响广度 | 结构化输出：等级 + 证据引用 + 模型/提示词版本；必须可审计 |

规则：

```text
COGNITIVE_JUDGEMENT 只能输出“等级 + 证据”，不能直接输出 decision。
本边界需与 Julia_core ADR-032 / C-A5（禁止确定性适用性判断进入生产）对齐；
起草者只看到这两条 ADR 的摘要，具体对齐由 Owner 确认（OF-11 附带项）。
```

## 2.4 时间相位

| 相位 | 时间 | 计算内容 | as-of |
|---|---|---|---|
| EOD_REVIEW | T 日 15:00 之后 | L1–L4 全部状态、L5 Setup Plan | T 日收盘数据 |
| PRE_OPEN | T+1 09:15–09:25 | L6 竞价确认、AUC | 竞价路径 |
| INTRADAY | T+1 09:30–15:00 | L6 分时确认、L5 触发、L8 盘中退出信号 | 分钟级 |
| POST_CLOSE | T+1 15:00 后 | L8 日线退出、L9 复盘 | 收盘 |

不变量 INV-003：EOD_REVIEW 只能产生 Setup Plan（`WATCH`），不能产生 `ENTRY_ELIGIBLE`。（继承 OTO-014 / W2S-025 并推广）

---

# Part III — 通用约定

## 3.1 Decision 与 Position State 分离（修正 v0.4.2 §3）

**Decision 枚举**（引擎对某一时刻某一候选/持仓“应该怎么做”的判断）：

```text
INVALID          输入或状态转移非法
BLOCKED          缺证据/缺策略，无法判断
REJECTED         明确不符合
WATCH            观察，不行动
ENTRY_ELIGIBLE   满足入场条件（仍需执行层成交）
HOLD             已持仓，继续持有
ADD_ELIGIBLE     已持仓，满足加仓条件
REDUCE           已持仓，减仓
EXIT             已持仓，清仓
```

v0.4.2 的 `ENTERED` 移出 Decision 枚举。理由：是否已入场是成交事实，只能由成交证据（§12.3）产生，不能由决策引擎“决定”。

**Position State 枚举**（事实状态）：

```text
NONE
ORDER_PENDING
ENTERED              （需 FILL_PROVEN_* 证据）
PARTIALLY_REDUCED
EXIT_SCHEDULED       （退出已决定，受 T+1 或时段约束尚未可执行）
CLOSED
```

**Strategy State**（策略内部状态，如 `SETUP_CREATED`、`WATCH_THEME_ONLY`、`AWAITING_RECONSENSUS`）独立于以上两者。

Decision 输出结构：

```json
{
  "decision": "EXIT",
  "reason_code": "OTO_SECOND_BOARD_BROKEN_NOT_RESEALED",
  "all_reasons": ["..."],
  "earliest_executable_at": "2026-07-10T09:25:00+08:00",
  "rule_refs": ["OTO-X01"],
  "evidence_refs": ["..."],
  "policy_versions": {"threshold_policy": "...", "market_rule_policy": "..."}
}
```

## 3.2 Reason Code 命名空间

```text
DATA_*      数据缺失、质量问题（MISSING_EVIDENCE、AUCTION_PATH_INCOMPLETE、DATA_QUALITY_FAILED）
MKT_*       L1
THM_*       L2/L3
LDR_*       L4
OTO_* / W2S_* / AUC_* / INT_*   L5/L6
RISK_*      L7
EXIT_*      L8
INV_*       不变量违反（INVALID_STATE_TRANSITION、PEER_LOOKAHEAD、DUPLICATE_EVENT、T_PLUS_ONE_VIOLATION）
```

## 3.3 UNKNOWN 语义

```text
硬门槛（GATE / ELIGIBILITY / EXCLUSION）字段未知 → BLOCKED（DATA_MISSING_EVIDENCE）
证据（EVIDENCE）字段未知                         → 不得升级，最多 WATCH
任何情况下：未知 ≠ 通过；没有默认 PASS
退出侧：缺“策略元数据”绝不阻止已触发的确定性止损（§10.3）
```

## 3.4 时间、日历与 as-of（继承 v0.4.2 §4–5、§11，不变）

```text
market_timezone = Asia/Shanghai；时间戳一律带偏移的 RFC3339
trading_calendar_id 必填；拒绝 naive datetime、非交易日、跨日竞价证据、重复事件
data_as_of <= decision_time；peer 字段 event_time <= ranked_at（否则 INVALID / PEER_LOOKAHEAD）
事件身份：candidate_id、event_id 唯一；deduplication_key 不得重放
```

## 3.5 市场规则与 T+1（修正）

`market_rule_policy` 继承 v0.4.2 §19（交易所、板块、生效区间、涨跌幅限制、最小价位、T+1、时区）。涨跌幅比例必须从版本化策略读取，不得在领域逻辑里硬编码。

新增不变量：

```text
INV-T1-01  D 日买入的股份，最早 D+1 交易日可卖出。
INV-T1-02  validator 拒绝任何“同一 lot 同日买入、同日卖出”的回放路径（INVALID / T_PLUS_ONE_VIOLATION）。
INV-T1-03  入场当日触发的任何退出规则，输出 decision=EXIT 或 REDUCE，
           position_state=EXIT_SCHEDULED，earliest_executable_at = D+1 集合竞价。
INV-T1-04  回放的成交价按 earliest_executable_at 时点的可成交价格计算，不得使用触发时点价格。
```

这一条直接影响原文的“二板炸板午后不能回封必须减仓/清仓”（CS-04 p3）和“止损：当天炸板封不回立刻走”（CS-04 p4）：二板当天买入时，这些规则只能在次日执行。

## 3.6 测量与阈值分离（继承 v0.4.2 §10，并补充）

```text
测量值是确定性的；“强/弱/充分/冰点”等判断需要版本化阈值策略。
领域逻辑中不得出现阈值字面量。
补充：原文给出的数字必须作为“带出处的种子值”登记到阈值注册表（Part XIV），
      不允许以“不能硬编码”为由让阈值策略为空。
```

研究模式：

```text
policy_mode = RESEARCH_EXPLORATORY
  允许使用 owner_status=UNFROZEN 的种子阈值或预注册的参数变体
  所有结果的信任等级上限 = EXPLORATORY_IN_SAMPLE
policy_mode = OWNER_FROZEN
  只允许 FROZEN 阈值
```

---

# Part IV — L1 市场环境与风格层

## 4.1 目的与来源

```text
大环境保护：大盘如果是盛极而衰行情，坚决不能做龙头股；对行情的分析和性质判断是做龙头的前提。  [CS-03 p2]
大环境好：以突破买入为主；环境不好：以寻找阻力位置为核心，低吸为主。                          [CS-03 p2]
不要在熊市中轻易抢热点。                                                                          [CS-03 p2]
真正高胜算机会来临时要胆大，行情不好时要特别谨小慎微。                                            [CS-03 p2]
重点关注大盘以及板块情绪，如果盘前大盘情绪出现冰点，切忌操作。                                    [TH-04 p32]
```

## 4.2 市场测量值（MKT-M）

全部为 DETERMINISTIC_MEASUREMENT，按交易日计算。凡定义参照 EXT-01 的，均已用 EXT-01 数据反算校验，校验结果写在“校验”列。

| ID | 测量值 | 定义 | 校验 |
|---|---|---|---|
| MKT-M01 | limit_up_count | 收盘涨停家数（ST、北交所是否计入由 `universe_policy` 决定） | — |
| MKT-M02 | touched_limit_count | 盘中触及涨停家数 | — |
| MKT-M03 | broken_board_rate | 炸板率 = (触及 − 收盘封住) / 触及 | EXT-01 7/1 为 33.04%（定义待对齐） |
| MKT-M04 | chain_board_count | 连板（≥2 板）家数 | — |
| MKT-M05 | max_board_height / stock | 最高连板高度及个股 | — |
| MKT-M06 | down_5pct_count | 跌幅 ≥5% 家数 | — |
| MKT-M07 | loss_effect_ratio | **down_5pct_count / limit_up_count** | SOURCE_INFERRED：EXT-01 6/26、7/1、7/2、7/6 四个点（929/60=15.48，194/151=1.28，526/93=5.66，637/64=9.95）全部吻合 |
| MKT-M08 | advance_ratio | 上涨家数 / (上涨 + 下跌) | EXT-01 “大盘上涨比”口径未知，**不得混用** |
| MKT-M09 | first_board_seal_rate | 首板封板率 = 首板收盘封住 / 首板触及 | EXT-01 7/1：128/204=63% 吻合 |
| MKT-M10 | promotion_rate_k | k→k+1 晋级率 = 今日 (k+1) 板数 / 昨日 k 板数 | EXT-01 7/1 一进二 20/120 吻合 |
| MKT-M11 | prev_first_board_red_ratio | 昨日首板今日收红比例 | — |
| MKT-M12 | prev_first_board_big_loss_ratio | 昨日首板今日“大面”比例（大面阈值见 TH-025） | — |
| MKT-M13 | prev_chain_red_ratio / prev_chain_not_limit_green_ratio | 昨日连板今日收红比例；昨日连板今日未涨停且收绿比例 | — |
| MKT-M14 | active_capital | 今日所有涨停及触及涨停个股的成交额之和（亿元） | 口径来自 EXT-01 |
| MKT-M15 | auction_avg_return | 全市场/涨停池总竞价涨幅 | EXT-01 “总竞价涨幅” |
| MKT-M16 | index_state_inputs | 上证、深成指、创业板：收盘相对 5/10/20/60 日线、连续阴线数、单日波幅 | — |
| MKT-M17 | breadth_above_ma | 站上 50/200 日线的成分股比例（CS-09 方法） | — |
| MKT-M18 | external_anchor | KOSPI 等外部指数：日涨跌、距高点回撤 | 来源 EXT-01 7/2、7/8 |

不得在系统内复刻 EXT-01 的“指数势能”“情绪动能综合值”“周期”这三个指标（计算方法未公开）。它们只能作为外部对照数据存储，字段名加 `ext_` 前缀。

## 4.3 市场状态

### 4.3.1 MARKET_EMOTION_STATE

```text
ICE_POINT     冰点
REPAIR        修复
EXPANSION     扩散/赚钱效应
CLIMAX        高潮
DIVERGENCE    分歧
RETREAT       退潮
UNCLASSIFIED  阈值未冻结或数据不足
```

分类阈值：**CALIBRATION_REQUIRED（TH-026）**。原文没有给出市场层面的数字阈值。

建议的校准方法（PROPOSED_BY_AGENT，需 OF-11 批准）：

```text
1. 对 MKT-M01/M04/M06/M07/M09/M10/M14 计算滚动 N 日（建议 120 交易日）分位数；
2. 以分位数区间定义状态，状态带滞后（进入/退出阈值不同），避免日间抖动；
3. 在 EXPLORATORY 回放中，用 EXT-01 7/1–7/9 作为人工标注对照（7/7 作者明确判断为“情绪冰点”）；
4. 冻结前必须在样本外窗口验证。
```

在冻结前，正式模式下 `MARKET_EMOTION_STATE = UNCLASSIFIED`，下游按 UNKNOWN 处理。

### 4.3.2 INDEX_TREND_STATE

```text
UPTREND / RANGE / DOWNTREND / TOP_RISK / UNCLASSIFIED
```

`TOP_RISK` 由 §4.5 的见顶模块触发。EXT-01 所说的“量化风险提示线顶，12–24 天调整窗口”是外部未公开方法，只记录为 `ext_index_risk_window`，不作为规则输入。

### 4.3.3 EXTERNAL_RISK_STATE

```text
NORMAL / ELEVATED / SYSTEMIC / UNCLASSIFIED
```

来源：EXT-01 7/2（韩国大跌、高杠杆踩踏可能传导到全球科技 AI 硬件抱团）、7/8（“韩国指数权重甚至超过我们自己指数”）。整层为 EXTERNAL_SIGNAL，source_status=PROPOSED_BY_AGENT，是否采用见 OF-04。

### 4.3.4 STYLE_REGIME（风格）

```text
INSTITUTIONAL_TREND    指数强；机构/基民增量主导；业绩确定性科技大票   [EXT-01 7/1、7/3]
SPECULATIVE_RELAY      指数弱或调整；游资情绪连板                      [EXT-01 7/2、7/6、7/7]
DEFENSIVE_ROTATION     医药/消费等防守抱团                             [EXT-01 7/6]
NO_EDGE                冰点或系统性风险                                [EXT-01 7/2；TH-04 p32]
UNCLASSIFIED
```

说明：Owner 笔记（CS-03 p3）写的是“龙头基本不看财务基本面”，属于纯游资框架；2026 年的 EXT-01 显示“业绩预告主导”的机构风格。两者并存是事实，但当前 v0.5 **只为 SPECULATIVE_RELAY 风格建模了战法**（OTO、W2S）。INSTITUTIONAL_TREND 风格下的业绩趋势战法为 NOT_MODELED（§8.1）。这一层是否采用见 OF-04。

## 4.4 L1 规则

| ID | 类型 | 规则 | 来源 | UNKNOWN | 状态 |
|---|---|---|---|---|---|
| MKT-001 | GATE | 市场处于 CLIMAX→DIVERGENCE/RETREAT（盛极而衰）时，禁止龙头接力类新开仓（OTO、W2S） | CS-03 p2 | BLOCKED | SOURCE_VERIFIED / UNFROZEN |
| MKT-002 | PERMISSION | 环境好：允许突破买入；环境不好：只允许阻力位/低吸型买点（v0.5 未建模低吸 → 环境不好时 OTO 不开放） | CS-03 p2 | BLOCKED | SOURCE_VERIFIED / UNFROZEN |
| MKT-003 | GATE | 市场 RETREAT（及熊市）时不抢热点：OTO、W2S 新开仓 BLOCKED | CS-03 p2；CS-04 p2；CS-05 p5 | BLOCKED | SOURCE_VERIFIED |
| MKT-004 | GATE | 盘前市场情绪为 ICE_POINT 时，当日禁止新开仓 | TH-04 p32 | BLOCKED | SOURCE_VERIFIED；与 EXT-01、CS-07 冲突（SC-06 / OF-05） |
| MKT-005 | EVIDENCE | 好行情多参与早盘热点；早盘热点与晚盘热点相同时可提高仓位等级 | CS-03 p2 | WATCH | SOURCE_VERIFIED |
| MKT-006 | GATE | EXTERNAL_RISK_STATE=SYSTEMIC 时禁止新开仓 | EXT-01 7/2 | BLOCKED | PROPOSED_BY_AGENT / OF-04 |
| MKT-007 | PERMISSION | INDEX_TREND_STATE ∈ {DOWNTREND, TOP_RISK} 时，INSTITUTIONAL_TREND 风格不开放；SPECULATIVE_RELAY 是否开放取决于 L3 | EXT-01 7/6 | BLOCKED | PROPOSED_BY_AGENT / OF-04 |
| MKT-008 | INPUT_CONTRACT | 盘前必备输入：涨跌停家数、各板块指数涨幅（含昨日涨停股的盘前涨幅）、各板块成交量、昨日热点题材延续性、题材与个股关联度；缺任何一项 → 当日 L5 BLOCKED | CS-03 p4 | BLOCKED | SOURCE_VERIFIED |

## 4.5 指数见顶模块（REFERENCE，需 Owner 启用）

来源 CS-09（欧奈尔体系，美股语境）。在 A 股使用前必须本地化：

| 信号 | 原文定义 | A 股本地化要求 |
|---|---|---|
| 出货日 | 下跌日（或微涨/冲高回落日）成交量高于前一日，且高于 50 日均量 | 50 日均量窗口待定；排除股指期货交割日（A 股为每月第三个周五，不是按季度） |
| 出货日聚集 | 2–4 周内 ≥4 个出货日 | 阈值需在 A 股重新校准 |
| 突兀走势 | 大阴线或跳空低开、波幅约 ≥3%、全天走低 | 3% 是美股指数口径，A 股需重新校准 |
| 广度背离 | 站上 50/200 日线的成分股比例下降，而指数上涨 | 指数成分股口径（沪深 300 / 中证 1000 等）待定 |
| 急涨后最大单日跌幅 | 延伸性涨势之后的急涨，出现一段时期内最大的单日跌幅 | 斜率分段方法待定 |

输出：`INDEX_TREND_STATE=TOP_RISK` 与组合层 REDUCE 建议（§10.6）。状态：REFERENCE_ONLY，是否启用见 OF-11。

---

# Part V — L2 题材与主线层

## 5.1 题材对象

```json
{
  "theme_id": "...",
  "name": "商业航天",
  "catalysts": [
    {"event_id": "...", "type": "POLICY|TECH|EVENT|INDUSTRY_CYCLE|RESTRUCTURING",
     "published_at": "...", "source_ref": "...",
     "claim_status": "OFFICIAL|MEDIA_REPORTED|UNVERIFIED_RUMOR|DENIED"}
  ],
  "members": [{"stock_code": "...", "linkage": "CORE|RELATED|EDGE", "linkage_evidence": ["..."]}],
  "research_as_of": "2025-12-30",
  "staleness_status": "FRESH|STALE"
}
```

来源：

```text
题材来源五类：政策（第一沃土）、技术创新、重大事件、行业周期、资产重组。      [CS-03 p1]
TH-01/02/03 中大量条目标注“网传/未证实”  → claim_status = UNVERIFIED_RUMOR
TH 系列写于 2025-12，到 2026-10 已超过 9 个月 → 默认 staleness_status = STALE，需刷新后才能作为 L2 证据
```

## 5.2 逻辑评估（COGNITIVE_JUDGEMENT）

```text
novelty   新颖度：越新越有炒作机会                          [CS-03 p1]
timing    时机：出现在市场低潮混沌期，成为主线的可能性越大   [CS-03 p1]
breadth   影响广度：影响越深远、人群越多，级别越大          [CS-03 p1]
scale     题材级别：BIG / SMALL —— 大热点大干，小热点不干    [CS-03 p1]
```

每项输出 `LOW|MID|HIGH|UNKNOWN` 与证据引用；不得输出决策。

## 5.3 市场认可测量（DETERMINISTIC_MEASUREMENT）

| ID | 测量值 | 定义 |
|---|---|---|
| THM-M01 | theme_limit_up_count | 题材内当日涨停家数 |
| THM-M02 | theme_lead_count_w | 窗口 W 内题材“领涨”次数（领涨 = 题材按涨停家数或板块涨幅排名第 1；W 见 TH-031） |
| THM-M03 | theme_max_board | 题材内最高连板高度 |
| THM-M04 | theme_first_3plus_leader | 是否已出现首个 ≥3 连板龙头 |
| THM-M05 | theme_amount_trend | 题材成交额相对 N 日均值 |
| THM-M06 | theme_lhb_count | 题材个股上龙虎榜次数 |
| THM-M07 | theme_limit_down_count | 题材内跌停家数 |
| THM-M08 | theme_rank_open / theme_rank_close | 早盘 / 收盘热点排名（用于“早盘热点=晚盘热点”） |

## 5.4 主线状态机

```text
UNKNOWN
MAINLINE_CANDIDATE
CONFIRMED_MAINLINE
STRONG_HOTSPOT        市场认可强，但逻辑级别 SMALL 或持续性不足
DEGRADED_MAINLINE     主线出现平级或降级行情
EXPIRED               退潮结束或市场不认可
NON_MAINLINE
```

| ID | 类型 | 规则 | 来源 | 状态 |
|---|---|---|---|---|
| THM-001 | DEFINITION | 主线 = 逻辑（新、时、广）+ 市场（持续被更多资金买入认可）；两个维度缺一不算主线 | CS-03 p1；CS-01 | SOURCE_VERIFIED |
| THM-002 | DEFINITION | 逻辑成立但市场不相信、没有持续性 → 果断放弃（NON_MAINLINE 或 EXPIRED） | CS-03 p1 | SOURCE_VERIFIED |
| THM-003 | TRANSITION | UNKNOWN → MAINLINE_CANDIDATE：出现催化，且题材当日涨停 1–3 只、板块异动排名靠前（即情绪“初期”特征） | CS-03 p2 | SOURCE_VERIFIED |
| THM-004 | TRANSITION | → CONFIRMED_MAINLINE：逻辑 scale=BIG，且窗口 W 内主线题材出现 **2 次领涨**，且**板块内出现首个 ≥3 连板龙头、资金开始抱团** | CS-03 p2–3（“发酵-进场”） | SOURCE_VERIFIED 的两个特征 + PROPOSED 的“同时满足”组合（OF-01） |
| THM-005 | TRANSITION | 满足 THM-004 的市场条件，但 scale=SMALL → STRONG_HOTSPOT | CS-03 p1（小热点不干） | SOURCE_INFERRED |
| THM-006 | TRANSITION | CONFIRMED → DEGRADED：主线出现平级或降级行情（龙头/次龙头首阴分歧） | CS-03 p3 | SOURCE_VERIFIED |
| THM-007 | TRANSITION | → EXPIRED：题材进入 RETREAT（大面积跌停、龙头连续下跌），或“题材不被市场认可，直接结束周期” | CS-03 p3；CS-02 | SOURCE_VERIFIED |
| THM-008 | GATE | 原则上只参与主线题材关联股票；避免杂毛股、小热点 | CS-03 p1；CS-01 | SOURCE_VERIFIED |
| THM-009 | EVIDENCE | 真正的炒作是炒刚被挖掘的热点，最好在大家还怀疑犹豫时介入 | CS-03 p1 | SOURCE_VERIFIED（仅作证据，不单独构成入场） |

战法准入（OF-01 修订版，见 §16）：

```text
OTO 与 W2S：只有 CONFIRMED_MAINLINE 可以创建 SETUP_CREATED
MAINLINE_CANDIDATE → WATCH_THEME_ONLY（除非 OF-01 批准“初期试错”例外）
STRONG_HOTSPOT     → WATCH_THEME_ONLY
DEGRADED_MAINLINE  → 只允许 W2S（因为“分歧→弱转强”正是该阶段的战法）
NON_MAINLINE / EXPIRED → REJECTED
UNKNOWN            → BLOCKED
```

---

# Part VI — L3 题材情绪周期状态机

## 6.1 状态

来源：CS-02（市场情绪周期.key）、CS-03 p2–3、CS-01 短线交易系统图。

| 状态 | 中文 | 识别特征（原文） | 可测映射 |
|---|---|---|---|
| CHAOS | 混沌期 | 市场处于混沌期，直到新的题材出现 | 无主线；L2 无 CONFIRMED |
| INITIAL | 初期 | 1–3 只股票涨停，板块异动排名靠前，消息集中爆发；情绪犹豫、观望 | THM-M01 ∈ [1,3]、THM-M08 靠前、有新催化 |
| FERMENT | 发酵 | 板块内出现首个 3 连板以上龙头，资金开始抱团，主升浪开启；主线题材出现 2 次领涨 | THM-M04=true；THM-M02 ≥ 2 |
| ACCELERATE | 加速 | 受持续利好刺激，股价连续上涨，兴奋 | 龙头连板递增、THM-M01 上升 |
| CLIMAX | 高潮 | 板块上龙虎榜次数多、涨停家数连续 3 天超 10 家、题材日均成交量大幅上升 | THM-M06 高；THM-M01 >10 连续 3 日；THM-M05 大幅上升 |
| DIVERGENCE | 分歧 | 龙头或次龙头出现首阴分歧；买盘不足，较多观望 | 龙头/次龙头首个非涨停阴线 |
| RE_STRENGTHEN | 弱转强 | 首阴分歧后第二天反包，最好再次打板 | 分歧次日反包 |
| SECOND_CLIMAX | 再次高潮 | 龙头开始分歧，连板次数大面积降级，打板数量逐日下降 | 连板降级 + THM-M01 逐日下降 |
| CATCH_UP | 分歧-补涨 | 高标龙头再次分歧，后排出现补涨 | 龙头再分歧 + 后排首板增加 |
| RETREAT | 退潮 | 板块大面积跌停，龙头连续下跌；恐惧 | THM-M07 高；龙头连续下跌 |

所有数字阈值（“连续 3 天超 10 家”除外）见 Part XIV；“大面积”“大幅”为 UNDEFINED，必须冻结。

## 6.2 合法转移

```text
CHAOS → INITIAL
INITIAL → FERMENT | CHAOS（题材不被认可，直接结束周期）
FERMENT → ACCELERATE | DIVERGENCE
ACCELERATE → CLIMAX | DIVERGENCE
CLIMAX → DIVERGENCE
DIVERGENCE → RE_STRENGTHEN | RETREAT | CATCH_UP
RE_STRENGTHEN → SECOND_CLIMAX | DIVERGENCE
SECOND_CLIMAX → CATCH_UP | DIVERGENCE | RETREAT
CATCH_UP → RETREAT
RETREAT → CHAOS
```

其余转移 → `INVALID / INVALID_STATE_TRANSITION`。状态由 EOD_REVIEW 相位计算，盘中只能产生“候选转移”，收盘后确认。

## 6.3 动作矩阵

| 状态 | 原文操作 | v0.5 允许 | 来源 |
|---|---|---|---|
| CHAOS | 休息/调整策略 | 无新开仓 | CS-01 |
| INITIAL | 关注第一个换手板龙头，轻仓试探打板或低吸前排人气股；环境不好要果断收手，等待发酵 | 默认无新开仓（OF-01 可开放轻仓试错） | CS-03 p2 |
| FERMENT | 进场买入；加仓龙头（换手高标）；围绕分歧转一致参与前排高辨识度个股 | OTO；龙头 ADD | CS-03 p3；CS-02 |
| ACCELERATE | 市场加速要警惕，关注龙头高度变化 | HOLD；不追跟风 | CS-02 |
| CLIMAX | 高度警惕，必要时止盈离场 | 无新开仓；止盈 REDUCE 候选 | CS-03 p3 |
| DIVERGENCE | 密切关注龙头次日是否反包；下跌当天尽量不要低吸 | 无新开仓（SC-07 / OF-07）；建立 W2S Setup | CS-03 p3 |
| RE_STRENGTHEN | 围绕分歧转一致节点参与龙头或次龙头 | W2S | CS-03 p3 |
| SECOND_CLIMAX | 止盈离场 | EXIT | CS-03 p3 |
| CATCH_UP | 不参与跟风股的二次分歧，尽量少参与补涨 | 无新开仓 | CS-03 p3 |
| RETREAT | 观望 | EXIT；无新开仓 | CS-03 p3 |

## 6.4 二波潜力（EVIDENCE）

```text
龙头容易出现二波：大级别题材（级别越大越容易有第二春）；A 浪未被过分透支；大盘配合且消息连续刺激。  [CS-03 p3]
```

输出 `second_wave_potential: LOW|MID|HIGH`，只作为 W2S 的证据，不作为入场条件。

---

# Part VII — L4 龙头定位层

## 7.1 角色

| 角色 | 含义 | 来源 |
|---|---|---|
| LEADER | 龙头：题材发动机和旗杆 | CS-03 p3 |
| SECOND | 龙二 / 次龙头 | CS-03 p3–4 |
| BLOCKER | 卡位龙 | CS-06 p6 |
| ARBITRAGE_20CM | 套利：创业板 20cm 核心（“一字板定方向”） | CS-03 p4 |
| CATCH_UP | 补涨 | CS-03 p3–4 |
| FOLLOWER | 跟风 / 杂毛 | CS-03 p3 |
| UNRANKED | 证据不足 | — |

角色是**题材内的相对排名**，必须基于同一 as-of 快照计算（继承 v0.4.2 §11 的 AUCTION / OPEN / TRIGGER 快照与 PEER_LOOKAHEAD 不变量）。

## 7.2 龙头识别规则

| ID | 类型 | 规则 | 来源 | 实现类别 |
|---|---|---|---|---|
| LDR-001 | CRITERION | 硬逻辑：关联题材最正宗；多题材、热点汇集（复合题材优先） | CS-03 p3 | COGNITIVE |
| LDR-002 | CRITERION | 高辨识度：最快封板，资金最狠最夸张；看封板金额、封板时间、形态 | CS-03 p3 | MEASUREMENT（题材内封板时间排名、封单金额排名） |
| LDR-003 | CRITERION | 多个首板时，次日率先走出二板者为龙头雏形；龙头的二板比同题材二板更快、更强、更稳 | CS-07 p3 | MEASUREMENT |
| LDR-004 | CRITERION | 抗跌：大盘和板块走弱时依然强势涨停 | CS-03 p3 | MEASUREMENT |
| LDR-005 | ATTRIBUTE | 人气最旺、游资为主、涨幅最高、首板换手率 >8%、量比 >2.5、持续放量、次新居多、地域独特、低价+低位置+低市值 | CS-03 p3 | MEASUREMENT（属性证据，不是硬门槛） |
| LDR-006 | ATTRIBUTE | 龙虎榜出现强势游资席位 | CS-07 p3 | MEASUREMENT（需要龙虎榜数据） |
| LDR-007 | CRITERION | 龙头的盘口波动通常是当天全市场最受关注的 | CS-07 p3 | COGNITIVE / 代理测量 |
| LDR-008 | ROLE_RULE | 角色判定在股票所处板块中的地位是第一位的；跟风股分歧不能买；补涨股要特别小心 | CS-03 p3 | — |

角色分配算法（PROPOSED_BY_AGENT，OF-11 附带项）：

```text
1. 候选池 = 题材内当日涨停/连板股；
2. 以 LDR-003（谁先晋级）> LDR-002（封板时间/封单）> LDR-004（抗跌）的字典序排名；
3. LDR-001 认知判断为 LOW 的个股，不能成为 LEADER；
4. 排名第 1 = LEADER，第 2 = SECOND；其余按特征归入 BLOCKER / CATCH_UP / FOLLOWER；
5. 并列或证据不足 → UNRANKED（不得猜）。
```

## 7.3 角色权限

| 角色 | 允许的战法 | 来源 |
|---|---|---|
| LEADER | OTO（首板阶段为“龙头候选”）、W2S、ADD | CS-03 p3；CS-05 p4 |
| SECOND | OTO、W2S（仓位更轻） | CS-03 p4“买不到龙头就买龙二”；CS-05 p4 |
| BLOCKER | 观察，NOT_MODELED | CS-06 p6 |
| ARBITRAGE_20CM | NOT_MODELED | CS-03 p4 |
| CATCH_UP | REJECTED（尽量少参与补涨） | CS-03 p3 |
| FOLLOWER | REJECTED（宁愿涨停板上追龙头，也不在低位买跟风股） | CS-03 p3 |
| UNRANKED | BLOCKED | — |

持有风格冲突：原文“要捂得住，不要失去位置；不要在龙头股上做短线”（CS-03 p3）与“龙头战法的核心就是快进快出”（CS-04 p3）矛盾，见 SC-08 / OF-08。

---

# Part VIII — L5 战法、L6 确认

## 8.1 战法注册表

| strategy_id | 状态 | 来源 |
|---|---|---|
| ONE_TO_TWO（OTO） | MODELED | CS-04；CS-01 |
| WEAK_TO_STRONG（W2S） | MODELED | CS-05；CS-01 |
| INITIAL_PROBE（初期轻仓试错） | NOT_MODELED（OF-01） | CS-03 p2 |
| LEADER_ADD（发酵期加仓龙头） | 作为 OTO/W2S 持仓的 ADD 规则，不单独建模 | CS-03 p3 |
| PASSIVE_DIVERGENCE_BUY（被动分歧当日买） | NOT_MODELED（OF-07） | CS-03 p3 |
| ARBITRAGE_20CM | NOT_MODELED | CS-03 p4 |
| CATCH_UP | NOT_MODELED（原文不鼓励） | CS-03 p3 |
| LOW_ABSORB（低吸前排 / 阻力位低吸） | NOT_MODELED | CS-03 p2 |
| INSTITUTIONAL_EARNINGS_TREND（业绩科技、做 T） | NOT_MODELED | EXT-01 |
| BULL_STOCK_PATTERNS（牛股三绝等） | NOT_MODELED（可作为特征） | CS-08 |

任何候选的 strategy_id 为 NOT_MODELED → `REJECTED / STRATEGY_NOT_MODELED`。

## 8.2 上下文准入矩阵

| 条件 | OTO | W2S |
|---|---|---|
| L1 MARKET_EMOTION_STATE | ∉ {ICE_POINT（OF-05）, RETREAT, CLIMAX→DIVERGENCE 的盛极而衰} | ∉ {RETREAT}；且见 W2S-008 环境门槛 |
| L1 环境好/坏（MKT-002） | 仅环境好（突破买入） | 不限（但 W2S-008 规定方向） |
| L2 主线 | CONFIRMED_MAINLINE | CONFIRMED_MAINLINE 或 DEGRADED_MAINLINE |
| L3 题材状态 | FERMENT（INITIAL 需 OF-01） | DIVERGENCE → RE_STRENGTHEN |
| L4 角色 | 首板阶段的龙头候选 / SECOND | LEADER / SECOND / 核心高标 |

任何一项为 UNKNOWN → BLOCKED。

## 8.3 OneToTwo（OTO）规则注册表

日期约定：`T` = 首板日；`D = T+1` = 二板日（入场日）；`D+1`、`D+2` 依次类推。

公式：`OTO = 主线正宗龙头候选 + 高质量首板 + 次日竞价/分时强 + 二板确认触发`。核心思想：**题材够新、筹码够干净、走势够强**（CS-01）。

### 8.3.1 资格与排除（EOD_REVIEW，T 日）

| ID | 类型 | 规则 | 来源 | 阈值 | UNKNOWN | 状态 | v0.4.2 对应 |
|---|---|---|---|---|---|---|---|
| OTO-001 | ELIGIBILITY | 题材必须为 CONFIRMED_MAINLINE | CS-01 1进2流程；CS-03 p1；CS-04 p3（SOP 第一步） | — | BLOCKED | SOURCE_VERIFIED / OF-01 | OTO-001（删除“强热点”） |
| OTO-002 | ELIGIBILITY | 题材最正宗、辨识度最高；不是边角股或补涨股 | CS-04 p1、p3 | — | WATCH | SOURCE_VERIFIED | OTO-002 |
| OTO-003 | ELIGIBILITY | 板块效应：同题材当日至少 2–3 只助攻股涨停，形成合力；无板块效应不选 | CS-04 p2、p3；CS-07 p3 | TH-003 | BLOCKED | SOURCE_VERIFIED | OTO-003 + OTO-012（合并去重） |
| OTO-004 | ELIGIBILITY | T 日为真实首板（近 N 日无涨停） | CS-04 p1–2 | TH-022 | BLOCKED | SOURCE_INFERRED（N 未定义） | OTO-004 |
| OTO-005 | EXCLUSION | 首板位置相对较高的不考虑 | CS-04 p2 | TH-032 | BLOCKED | SOURCE_VERIFIED | OTO-005（原为信号） |
| OTO-006 | EXCLUSION | 一字板、跳空秒板不选；低换手板宁可错过 | CS-04 p2、p3 | — | BLOCKED | SOURCE_VERIFIED（无需 Owner 定严重度） | OTO-009 |
| OTO-007 | GATE | 首板充分换手 | CS-04 p1（>8% 更佳）、p3（不低于 15%）；CS-07 p2（>15%） | TH-001（冲突 SC-01） | BLOCKED | SOURCE_CONFLICT / OF-06 | OTO-006 |
| OTO-008 | GATE | 首板成交额 ≥ 10 亿 | CS-04 p3 | TH-002 | BLOCKED | SOURCE_VERIFIED | 新增 |
| OTO-009 | EXCLUSION | 封板不坚决、尾盘才偷封的不选 | CS-04 p1、p3 | TH-023 | BLOCKED | SOURCE_VERIFIED（时点未定义） | OTO-008 |
| OTO-010 | EVIDENCE | 近期无异动放量，涨停时倍量最佳 | CS-04 p1 | TH-021 | WATCH | SOURCE_VERIFIED | OTO-007 |
| OTO-011 | EXCLUSION | 处于下降趋势的不选 | CS-04 p2 | TH-033 | BLOCKED | SOURCE_VERIFIED | OTO-010 |
| OTO-012 | EXCLUSION | 涨停没有突破“生死线”压制的不选 | CS-04 p2 | TH-024（未定义） | BLOCKED | SOURCE_VERIFIED / SA-02 | OTO-011（拆分） |
| OTO-013 | EXCLUSION | 涨停后价位正好处在重要压力位的不选 | CS-04 p2 | TH-034 | BLOCKED | SOURCE_VERIFIED | OTO-011（拆分） |
| OTO-014 | EXCLUSION | 一年内出现大幅连板回落的不选 | CS-04 p2 | TH-035 | BLOCKED | SOURCE_VERIFIED | **新增（v0.4.2 有字段无规则）** |
| OTO-015 | EXCLUSION | 流通市值 > 200 亿不选 | CS-04 p2 | TH-004 = 200 亿 | BLOCKED | SOURCE_VERIFIED | OTO-013 |
| OTO-016 | EVIDENCE | 优选：市值 20–100 亿、股价 20 元以下、未开通沪股通和融券 | CS-04 p2 | TH-005 | WATCH | SOURCE_VERIFIED / SC-02 | 新增（偏好，非门槛） |
| OTO-017 | EVIDENCE | 优选：低位、超跌首板、趋势首板；次新叠加热点；均线“金蜘蛛”形态；近日涨停后回踩不破启动位 | CS-04 p1 | — | WATCH | SOURCE_VERIFIED | OTO-005（拆分） |
| OTO-018 | BOUNDARY | T 日只能形成 Setup Plan，不能 ENTRY | CS-04 p3–4；CS-01 | — | — | SOURCE_VERIFIED | OTO-014 |

歧义 SA-01：CS-04 p2 写“首板之后第 2 天最好是一个温和放量的中小阳线，代表多头趋势没有断；K 线在 5 日均线之上”。这与“次日二板”的连续 1 进 2 不一致，可能是另一种“首板—整理—二板”的变体。v0.5 的 OTO 只建模**连续**的 1 进 2（与 CS-04 SOP 第三步“二板实时盯盘”一致），该变体记为 NOT_MODELED，待 Owner 澄清。

### 8.3.2 次日确认（PRE_OPEN / INTRADAY，D 日）

| ID | 类型 | 规则 | 来源 | 阈值 | UNKNOWN | v0.4.2 对应 |
|---|---|---|---|---|---|---|
| OTO-019 | EVIDENCE | 竞价强：高开 3–5%、量能活跃 | CS-04 p2；CS-06 p6 | TH-006 | WATCH | OTO-015 |
| OTO-020 | EVIDENCE | 9:24 之后，竞价大买单超过昨日涨停放量的，重点观察 | CS-04 p2 | TH-036 | WATCH | OTO-016 |
| OTO-021 | CONFIRMATION | 分时强：竞价后快速直线拉升、封板果断；开板能迅速回封，盘口有承接 | CS-04 p2、p3 | — | WATCH | OTO-017 |
| OTO-022 | ELIGIBILITY | 多个竞争票时，资金只保留最强；看题材内谁先涨停/谁先走出二板，跟错就是大坑 | CS-04 p2；CS-07 p3 | — | BLOCKED | OTO-018 + OTO-019 |
| OTO-023 | CONFIRMATION | 当天市场情绪偏强，不是普跌环境 | CS-04 p3 | 由 L1 给出 | BLOCKED | 新增 |
| OTO-024 | VETO | 结合分时量价与成交明细，防诱多（见 INT-004） | CS-04 p3 | — | WATCH | 新增 |

### 8.3.3 触发、仓位与止损

| ID | 类型 | 规则 | 来源 | 阈值 | v0.4.2 对应 |
|---|---|---|---|---|---|
| OTO-025 | TRIGGER | 二板封死后前 5 分钟内、封单稳定时入场；封单金额大、封板速度快 | CS-04 p3 | TH-008 | OTO-020 |
| OTO-026 | VETO | 不追高；不打反复炸板股；炸板后长时间不能回封则放弃 | CS-04 p3–4 | TH-037 | 新增 |
| OTO-027 | POSITION | 初始仓位 1–2 成；严禁满仓；“1 进 2 是最容易亏损的位置” | CS-04 p2、p4 | TH-014 | OTO-021 |
| OTO-028 | STOP | 入场时登记止损：跌破二板均价 | CS-04 p4 | — | **新增（RISK-001 的 OTO 实例）** |

### 8.3.4 退出与加仓（全部经过 T+1 校验）

| ID | 类型 | 规则 | 来源 | T+1 处理 | v0.4.2 对应 |
|---|---|---|---|---|---|
| OTO-X01 | EXIT | 二板封板被砸开，午后不能回封 → 减仓/清仓 | CS-04 p3（心态 2）、p4（SOP 止损） | D 日触发 → EXIT_SCHEDULED，D+1 竞价执行 | OTO-022（修正：原文的“当天走”不可执行） |
| OTO-X02 | EXIT | 二板封板失败 → D+1 早盘观察竞价是否弱转强，没有则坚决离场 | CS-04 p3（离场 4） | D+1 竞价判断、开盘执行 | 新增 |
| OTO-X03 | EXIT | 二板封板失败，D+1 走强但 10:30 前一直不封板 → 坚决离场 | CS-04 p3（离场 5） | D+1 10:30 判断 | 新增 |
| OTO-X04 | EXIT | 二板后，D+1 小高开 7–8% 后回落 → 离场 | CS-04 p3（离场 2） | D+1 盘中 | OTO-024（类型修正） |
| OTO-X05 | EXIT | 二板后，D+1 低开 → 在冲高回落时离场（不是“反弹失败再走”） | CS-04 p3（离场 3） | D+1 盘中 | OTO-023（语义修正） |
| OTO-X06 | EXIT | 三板炸板 → 离场；三板走弱第一时间兑现，不恋战 | CS-04 p3（离场 1）、p4 | D+1 盘中 | OTO-025（类型修正） |
| OTO-X07 | STOP | 跌破二板均价（OTO-028） | CS-04 p4 | D 日触发 → D+1 执行 | 新增 |
| OTO-A01 | ADD | 三板继续强势，可加仓，但需设好保护线 | CS-04 p4 | D+1 | 新增 / OF-08 |

## 8.4 WeakToStrong（W2S）规则注册表

公式（继承 v0.4.2 W2S-024）：`W2S = 核心强势股 + 分歧 + 结构存活 + 再一致`。核心思想：**该弱不弱则为强**（CS-05 p2；CS-01）。

日期约定：`S` = 分歧日；`S+1` = 转强观察/入场日。

### 8.4.1 资格与环境

| ID | 类型 | 规则 | 来源 | UNKNOWN | 状态 | v0.4.2 对应 |
|---|---|---|---|---|---|---|
| W2S-001 | ELIGIBILITY | 标的必须是龙头、次龙头或核心高标；跟风杂毛不配弱转强 | CS-05 p4；CS-01 弱转强流程 | BLOCKED | SOURCE_VERIFIED（原文明确，不需 Owner 定严重度） | W2S-019 |
| W2S-002 | ELIGIBILITY | 题材为 CONFIRMED_MAINLINE 或 DEGRADED_MAINLINE；题材 L3 状态为 DIVERGENCE | CS-03 p3 | BLOCKED | SOURCE_INFERRED | 新增 |
| W2S-003 | GATE | 大盘极度退潮时成功率极低：市场 RETREAT → BLOCKED；适用于“分歧—修复”而非“全面退潮” | CS-05 p5；CS-01 | BLOCKED | SOURCE_VERIFIED | W2S-022 |
| W2S-004 | GATE | 板块情绪没有全面退潮，仍有资金支撑；板块内其他个股有异动，尤其是补涨助攻 | CS-05 p1–2 | BLOCKED | SOURCE_VERIFIED | W2S-006 |
| W2S-005 | GATE | **环境方向门槛**：大盘环境好、指数上涨、板块也在上涨时，龙头出现的分歧**绝不能买** | CS-03 p3 | BLOCKED | SOURCE_VERIFIED | **新增** |
| W2S-006 | NOTE | 大盘环境不好时出现的被动分歧，若盘口承接好、收盘守住关键点位、换手 <50%（20% 以内最好），分歧当日可买 | CS-03 p3 | — | SOURCE_VERIFIED；v0.5 NOT_MODELED（OF-07） | 新增 |
| W2S-007 | TIMING | 分歧（下跌）当天尽量不要低吸 | CS-03 p3 | — | SOURCE_VERIFIED；与 W2S-006 冲突（SC-07） | 新增 |

### 8.4.2 分歧与结构存活（S 日，EOD_REVIEW）

| ID | 类型 | 规则 | 来源 | 阈值 | v0.4.2 对应 |
|---|---|---|---|---|---|
| W2S-010 | SETUP | 连板过程中 S 日出现分歧，类型：`BIG_BEARISH`（中到大阴线）/ `LONG_UPPER_SHADOW`（冲高回落上影）/ `BROKEN_BOARD`（烂板、涨停被砸开） | CS-05 p1 | — | W2S-001、W2S-002 |
| W2S-011 | DEFINITION | “弱”指分歧，不是固定跌幅 | CS-05 p1–5 | — | W2S-023 |
| W2S-012 | STRUCTURE | S 日收盘仍有资金护盘，价格守住关键支撑（5 日/10 日均线、前一日涨停价附近） | CS-05 p1 | TH-012 | W2S-003 |
| W2S-013 | STRUCTURE | 烂板“烂而不弱”五要素：① 涨停位置在箱体突破或前期高点；② 放量释放套牢盘；③ 有炸板；④ 破板后不大跌，在均线之上震荡，回撤 ≤3%；⑤ 烂板封单量少于正常，下跌过程缩量 | CS-05 p2 | TH-011 | W2S-007（补回 3%） |
| W2S-014 | EVIDENCE | 底部首板烂板如不暴量，筹码更干净、更强；关键位置暴量大概率走妖 | CS-05 p2 | — | 新增 |

结构存活组件（继承 v0.4.2 §12，每项 PASS/FAIL/UNKNOWN + 证据引用，overall 由 validator 推导）：

```text
prior_intraday_low      S+1 日不破 S 日分时低点        [CS-05 p4]
ma5_support / ma10_support                             [CS-05 p1、p4]
prior_limitup_support   前一日涨停价附近               [CS-05 p1]
close_control           S 日收盘位置
drawdown_control        烂板回撤 ≤3%                   [CS-05 p2]
volume_continuity       成交量不明显萎缩                [CS-05 p4]
overall
```

### 8.4.3 转强确认与触发（S+1）

| ID | 类型 | 规则 | 来源 | 阈值 | v0.4.2 对应 |
|---|---|---|---|---|---|
| W2S-020 | CONFIRMATION | 竞价弱转强：高开或抢筹 | CS-05 p2；CS-06 p6 | — | W2S-009 |
| W2S-021 | CONFIRMATION | 早盘分时弱转强：开盘后不单边下跌，放量拉升，大部分时间在分时均线上；跌破均价线也能被快速拉回 | CS-05 p3 | — | W2S-010 |
| W2S-022 | CONFIRMATION | 盘中弱转强：由弱于上证到强于上证；由分时均线下到线上；突破 ≥30 分钟分时平台 | CS-05 p3 | TH-013 | W2S-011–013 |
| W2S-023 | STRUCTURE | 前一日分时低点不破；关键均线支撑有效；成交量不明显萎缩（否则为假反抽） | CS-05 p4 | — | W2S-014–016 |
| W2S-024 | DISCRIMINATOR | 真：放量换手、封单坚决、次日承接良好；假：缩量拉升、封单虚弱、次日冲高回落 | CS-05 p4 | — | W2S-020、021 |
| W2S-025 | TRIGGER | 买点任一：回踩承接确认后打板或半路；低开→震荡→直线拉升封板；反包前高；回踩 5/10 日线后放量突破；分时均线支撑处放量上攻；反包涨停瞬间 | CS-05 p4 | — | W2S-017、018 |
| W2S-026 | WINDOW | 再一致窗口：分歧后“第二天（或随后极短时间内）”；超过窗口 → 终局失效 | CS-05 p1 | TH-028 | v0.4.2 §13 |
| W2S-027 | PRINCIPLE | 不贪图最低点，抓确认信号更安全 | CS-05 p5；CS-01 | — | 新增 |
| W2S-028 | BOUNDARY | Setup 不等于买入，必须有 S+1 确认 | CS-05 p4 | — | W2S-025 |

### 8.4.4 仓位、止损、退出

| ID | 类型 | 规则 | 来源 | T+1 处理 | v0.4.2 对应 |
|---|---|---|---|---|---|
| W2S-030 | POSITION | 首次尝试 1–2 成；主线+绝对龙头可到 5–8 成；龙二/次龙头 2–4 成；信号确认后可加到中等；禁止满仓 | CS-05 p4 | — | 新增 / SC-09 / OF-09 |
| W2S-031 | STOP | 入场时登记止损：前高或前板封单价（当天能否站回）；日线 10 日线或前低 | CS-05 p4 | — | 新增 |
| W2S-X01 | EXIT | 反包失败：当天不能重新站上关键价位（前高/前板封单价）→ 减仓或止损 | CS-05 p4 | S+1 触发 → S+2 竞价执行 | **新增** |
| W2S-X02 | EXIT | 日线跌破支撑（10 日线/前低）→ 立刻减仓或清仓 | CS-05 p4 | 收盘确认，次日执行 | **新增** |
| W2S-X03 | HOLD | 成功反包后持股待涨，等待二波或高度加速；之后的退出由 L3 状态（SECOND_CLIMAX/RETREAT）决定 | CS-05 p4；CS-03 p3 | — | 新增 |
| W2S-X04 | EXIT | 识别为诱多 / 假弱转强（W2S-024“假”）→ 快速反应 | CS-01 弱转强流程；CS-05 p5 | 按 T+1 | 新增 |
| W2S-X05 | EXIT | 再一致窗口过期（W2S-026） | CS-05 p1 | — | v0.4.2 §13 |

## 8.5 集合竞价确认（AUC）

继承 v0.4.2 §8–9 的连续路径合同与覆盖率公式（Part XII 摘录）。规则表：

| ID | 类型 | 规则 | 来源 | UNKNOWN | 修订 |
|---|---|---|---|---|---|
| AUC-000 | DATA_GATE | 若 L0 不具备 09:20–09:25 连续竞价路径数据，所有依赖 AUC 的确认为 UNKNOWN；相关战法最高 WATCH | — | — | **新增** |
| AUC-001 | EVIDENCE | 真实竞价重点观察 09:20–09:25 | CS-06 p1 | BLOCKED | 不变 |
| AUC-002 | EXCLUSION | 竞价分时要稳定：不能大起大落，不能临近结束才小幅波动，不能有急跌 | CS-06 p1 | BLOCKED | 补全原文三种情况 |
| AUC-003 | EVIDENCE | 优秀形态：倒 L+上坡、红盘阶梯、红盘锥形+U 形、红盘上翘一字、倒 L+U 形、一字上翘+阶梯向上 | CS-06 p2–4 | WATCH | 不变 |
| AUC-004 | EVIDENCE | 红盘阶梯必须在 0 轴之上且量能逐步放大 | CS-06 p3 | WATCH | 不变 |
| AUC-005 | EVIDENCE | 09:24–09:25 最后一分钟是否出现竞价单明显放大的抢筹 | CS-06 p5 | WATCH | 不变 |
| AUC-006 | EVIDENCE | 龙头正常符合预期开盘时（一字无买入机会），观察板块内龙二、龙三是否有溢价 | CS-06 p6 | WATCH | 不变 |
| AUC-007 | EXCLUSION | 龙头不符合预期开盘 → 情绪走弱，规避相关板块个股 | CS-06 p6 | BLOCKED | 不变 |
| AUC-008 | EVIDENCE | 观察板块内是否出现卡位龙 | CS-06 p6 | WATCH | 联动 L4 BLOCKER |
| AUC-009 | EVIDENCE | 关注量价抬升、资金积极抢筹的个股 | CS-06 p6 | WATCH | 不变 |
| AUC-010 | CONFIRMATION | 昨日烂板或炸板个股，横向比较是否出现弱转强 | CS-06 p6 | WATCH | 联动 W2S-020 |
| AUC-011 | CONFIRMATION | 09:25 竞价成交量 ≥ 上一交易日盘中单分钟最大成交量的 1/2（多为瞬间上板那一分钟）→ 买盘力量强 | CS-06 p6 | WATCH | 定义精确化 |
| AUC-012 | EVIDENCE | 在满足 AUC-011 时，高开 3–5% 当日继续涨停概率高 | CS-06 p6 | WATCH | 不变 |
| AUC-013 | BOUNDARY | 竞价的本质是确认承接，不是在全市场发现候选 | CS-06 p1–6 | BLOCKED | 不变 |
| AUC-014 | ELIGIBILITY | 竞价判断必须读取龙头开盘情况和板块环境 | CS-06 p6；CS-05 p2 | BLOCKED | 不变 |
| AUC-015 | INVARIANT | 单一 Auction Score 不得直接生成 ENTRY_ELIGIBLE（已推广为 INV-001） | — | — | 推广 |

## 8.6 分时买点与否决（INT）

| ID | 类型 | 规则 | 来源 |
|---|---|---|---|
| INT-001 | GATE | 即时价格线不跌破分时均线 = 当天走势强；但必须放量才可买，买点在放量的几分钟内 | CS-03 p4 |
| INT-002 | VETO | 即时价格线跌破分时均线 = 弱势，坚决不买 | CS-03 p4 |
| INT-003 | VETO | 不放量不买（全局） | CS-03 p4；CS-01 |
| INT-004 | VETO | 价格线快速远离分时均线，同时分时成交量萎缩且 MACD 顶背离或红柱缩头死叉 → 缩量拉升诱多，观望 | CS-03 p6 |
| INT-010 | TRIGGER | 分时买点 1：放量突破瞬间 | CS-03 p4 |
| INT-011 | TRIGGER | 分时买点 2：放量突破均价线 | CS-03 p5 |
| INT-012 | TRIGGER | 分时买点 3：分时攻击波回踩 | CS-03 p5 |
| INT-013 | TRIGGER | 分时买点 4：虎踞龙盘走势，MACD 背离且过零轴 | CS-03 p6 |
| INT-020 | PRINCIPLE | 交易你所见，而非你所想；变化修正计划，交易服从变化；买前宜慢，卖时宜快 | CS-03 p4 |

“放量”的定义（相对前 N 分钟均量的倍数）为 TH-030，未定义，必须冻结。INT 依赖分钟级数据，数据不可得时按 AUC-000 同理处理。

---

# Part IX — L7 仓位与风险

## 9.1 仓位矩阵（种子值，全部 UNFROZEN）

| 场景 | 仓位 | 来源 |
|---|---|---|
| OTO 初始 | 1–2 成 | CS-04 p2、p4 |
| OTO 三板继续强势加仓 | 未给数值 | CS-04 p4 |
| W2S 首次 | 1–2 成 | CS-05 p4 |
| W2S 主线+绝对龙头 | 5–8 成 | CS-05 p4（SC-09） |
| W2S 龙二/次龙头 | 2–4 成 | CS-05 p4 |
| 初期试错 | “轻仓”，未给数值 | CS-03 p2 |
| 全局 | 严禁满仓梭哈 | CS-04 p2；CS-05 p4 |
| 环境调节 | 高胜算时胆大，行情不好时谨小慎微 | CS-03 p2 |

## 9.2 风险不变量

```text
RISK-001  入场必须登记止损：ENTRY_ELIGIBLE 要求 stop_spec 已登记
          stop_spec = {type: PRICE|MA|PRIOR_LOW|SESSION_CONDITION, level, evaluation_basis: INTRADAY|CLOSE, source_rule}
          缺失 → BLOCKED / RISK_MISSING_STOP_SPEC
RISK-002  任何单一候选不得满仓（单票仓位上限 < 10 成；具体上限 OF-10）
RISK-003  仓位必须由 (strategy, role, market_state) 查表得出，不得由评分连续映射
RISK-004  T+1 不变量（§3.5）
```

## 9.3 组合层限制（原文没有，全部需要 Owner 决定：OF-10）

```text
max_gross_exposure          总仓位上限（可按 MARKET_EMOTION_STATE 分级）
max_per_theme_exposure      单题材上限
max_concurrent_positions    同时持仓数
daily_loss_stop             单日亏损停手线
consecutive_loss_cooldown   连续止损后冷却天数
```

冻结前，回放按“每个候选独立核算”，不模拟组合交互，并在报告中注明 `PORTFOLIO_POLICY_UNFROZEN`。

---

# Part X — L8 退出统一框架

## 10.1 退出原因分类（v0.4.2 基础上新增止盈）

```text
1. STRATEGY_LOGIC_INVALIDATION       战法前提失效（如再一致窗口过期、假弱转强）
2. MARKET_OR_THEME_TERMINAL_RETREAT  市场或题材进入 RETREAT
3. STRUCTURAL_BREAK                  登记止损触发、关键支撑跌破
4. EXECUTION_FAILURE                 二板炸板封不回、10:30 前不封板等执行层失败
5. EXPECTATION_DRIFT                 高开回落、低开冲高回落等预期偏离
6. PROFIT_TAKING_STAGE               题材 CLIMAX（必要时止盈）、SECOND_CLIMAX（止盈离场）   ← 新增
```

v0.4.2 没有止盈类别；而原文对高潮期、再次高潮期的止盈写得很明确（CS-03 p3；CS-02）。

## 10.2 主原因报告顺序（OF-02）

上表 1→6 的顺序**只用于**确定性地选出 `primary_exit_reason` 以便报告；全部并发原因保留在 `all_exit_reasons[]`。它**不**决定 REDUCE 还是 EXIT。REDUCE/EXIT 由各条规则自己的 decision 决定；多条规则冲突时取更强的动作（EXIT > REDUCE > HOLD）。

## 10.3 止损与终局失效的强制执行（OF-03 修订版）

```text
主机制（确定性，不依赖上层判断）:
  已入场仓位的 stop_spec（RISK-001）一旦被价格数据证实触发
  → decision = EXIT（或规则规定的 REDUCE）
  → 任何“策略元数据缺失 / 策略未冻结”都不得把它变成 BLOCKED

补充机制:
  VERIFIED 的 MARKET_TERMINAL_RETREAT / THEME_TERMINAL_RETREAT / STRATEGY_LOGIC_INVALIDATION
  → decision = EXIT
  （前提是 L1/L3 已冻结并能给出 VERIFIED；否则补充机制不可用，只有主机制）

数据缺失时:
  无法确认止损是否触发（价格数据缺失）→ decision = BLOCKED / DATA_MISSING_EVIDENCE
  同时 alert_severity = CRITICAL，并要求人工处理；不得静默

删除:
  v0.4.2 OF-03 中“前一日分时低点被跌破 = 已入场仓位的终局结构破坏”。
  原文里这是买入前的护盘条件（CS-05 p4），持仓的退出依据是“日线跌破 10 日线/前低”与“反包失败”（W2S-X01/X02）。
```

## 10.4 T+1 执行

所有退出 decision 必须携带 `earliest_executable_at`（§3.5 INV-T1-03）。回放按该时点的可成交价计算（INV-T1-04）。

## 10.5 阶段型退出（来自 L3）

| L3 状态 | 对已持仓的动作 | 来源 |
|---|---|---|
| ACCELERATE | HOLD，关注龙头高度变化 | CS-02 |
| CLIMAX | REDUCE 候选（必要时止盈） | CS-03 p3 |
| SECOND_CLIMAX | EXIT（止盈离场） | CS-03 p3 |
| RETREAT | EXIT | CS-03 p3 |

## 10.6 组合层（REFERENCE）

若 §4.5 见顶模块启用并给出 INDEX_TREND_STATE=TOP_RISK：组合层 REDUCE 建议。状态 REFERENCE_ONLY（OF-11）。

---

# Part XI — L0 数据合同与数据质量

## 11.1 主要数据源

```text
ai_theme_app market_public: market.analysis.read / market.state.read / market.stock.quote.read 等（已在 main，bc34e97）
分钟级行情（INT、W2S 分时确认）
09:20–09:25 竞价路径（AUC）
封单金额时间序列（LDR-002、OTO-025）
龙虎榜（LDR-006、THM-M06）
题材成分与关联度（L2）
EXT-01 外部复盘（只作对照与人工标注）
```

## 11.2 数据可得性门槛（新增）

每条规则在注册表中声明 `required_datasets[]`。数据集在某交易日不可得 → 该规则 UNKNOWN（硬门槛 → BLOCKED）。必须先完成以下核查，否则 L6 的大部分规则在回放中会全部 UNKNOWN：

| 数据集 | 用于 | 当前可得性 |
|---|---|---|
| 竞价连续路径 09:20–09:25 | AUC 全部、OTO-019/020、W2S-020 | ❓ 待核查 |
| 分钟线 | INT 全部、W2S-021/022、OTO-021/025 | ❓ 待核查 |
| 封单金额时序 | LDR-002、OTO-025 | ❓ 待核查 |
| 龙虎榜 | LDR-006、THM-M06、CLIMAX 识别 | ❓ 待核查 |
| 日线与涨停池 | L1、L2、OTO 资格 | ✅ market_public 已有（具体字段待核对） |

## 11.3 已知数据缺陷（来自本次审计，必须先修）

| ID | 缺陷 | 证据 | 处理 |
|---|---|---|---|
| DQ-D01 | M8 抽取的 `loss_effect_ratio` 被除以 100 | 原表 7/1=1.28、7/2=5.66、7/6=9.95；JSON 为 0.0128、0.0566、0.0995 | 修复抽取；用 MKT-M07 恒等式校验 |
| DQ-D02 | 同一文件自相矛盾 | `7月9日复盘_DeepSeek完整结构版.md` 第 4 节为 1.17，第 17 节为 0.0117 | 同上 |
| DQ-D03 | 字段名误导 | `first_board_success_rate` 实为首板封板率 | 改名为 `first_board_seal_rate` |
| DQ-D04 | 数值不一致 | 7/6 正文“主板周期 -14”，JSON `cycle_score=-8` | 抽取需保留原始值与来源位置 |
| DQ-D05 | 推断标签混入事实 | `phase`（7/1 ACCELERATION、7/3 FADE 等）为模型推断，非作者原话；7/1 作者实际在提示高抛科技股 | 拆为 `ext_author_view`（原文）与 `inferred_phase`（带 provenance=MODEL_INFERRED） |
| DQ-D06 | 无来源的断言 | DeepSeek 7/9 文件写“7/7 PANIC → 7/8 REPAIR_WATCH”，但 7/7、7/8 没有对应的 M8 抽取 | 删除，或补抽取后再引用 |
| DQ-D07 | 发布日 ≠ 行情日 | `7月3日复盘.md` 实为 7/5 发布、讨论 7/3 行情 | 区分 `publish_date` 与 `market_date` |
| DQ-D08 | 观测时间不可证明 | `market.analysis.read` 的 `observed_at` 固定为 T 15:30 | 回放信任等级标注 `HINDSIGHT_NOT_PROVEN` |

## 11.4 数据质量规则

```text
DQ-001  每个抽取数值保留：raw_value、unit、source_ref（文件+位置）、extraction_method、extractor_version
DQ-002  推断字段与事实字段分开存储；推断字段必须带 provenance
DQ-003  恒等式校验：loss_effect_ratio == down_5pct_count / limit_up_count（容差 0.01）；
        promotion_rate == 分子/分母；违反 → DATA_QUALITY_FAILED
DQ-004  publish_date 与 market_date 分离
DQ-005  传闻类题材催化 claim_status=UNVERIFIED_RUMOR，不能单独构成 L2 逻辑证据
DQ-006  THEME_RESEARCH 超过 staleness 窗口 → STALE，L2 不得引用
```

---

# Part XII — 执行与回放基础设施（继承 v0.4.2，摘录）

以下各节语义与 v0.4.2 相同，只做编号迁移；实现以 v0.4.2 原文为准，本节为摘要。

## 12.1 机器 Schema（v0.4.2 §1）

```text
序列化：JSON；校验：JSON Schema Draft 2020-12；不符合 → INVALID_SCHEMA，不得进入回放或决策
```

## 12.2 竞价连续路径与覆盖率（v0.4.2 §8–9）

```text
窗口 09:20:00–09:25:00，W = 300 秒，按秒划分
采样模式 ON_FEED_UPDATE | FIXED_INTERVAL；必须持久化 sampling_policy_id、interval_seconds、
  max_allowed_gap_seconds、missing_window_rule、duplicate_timestamp_rule、carry_forward_rule
coverage_ratio = covered_seconds / 300；不对 09:24–09:25 额外加权
尾段行为另由 late_scramble_strength、last_60s_return_pct 测量
coverage_ratio < policy.min_coverage_ratio → BLOCKED / AUCTION_PATH_INCOMPLETE（TH-027）
测量值：max_drawdown_pct、largest_negative_step_pct、last_60s_return_pct、linear_slope、
  reversal_count、late_scramble_strength、coverage_ratio
```

## 12.3 成交证据（v0.4.2 §16–18）

```text
强度排序：FILL_PROVEN_ORDER_LEVEL > FILL_PROVEN_TRADE_THROUGH > FILL_PROVEN_QUEUE_MODEL
  > PARTIAL_PROVEN > UNPROVEN_FILL > UNFILLED > REJECTED > CANCELLED
真实委托/成交回报 > 市场穿价证据 > 排队模型；排队模型不得推翻真实证据
部分成交：proof_source 与 fill_completion 分两维记录
去重键：broker_order_id + exchange_execution_id；回退键：order_intent_id + execution_timestamp + price + quantity + side
重复 → INVALID / DUPLICATE_EVENT；未解决冲突 → 绩效归因 BLOCKED
Position State = ENTERED 只能由 FILL_PROVEN_* 产生（§3.1）
涨停板排队：打板入场的回放成交至少需要 FILL_PROVEN_TRADE_THROUGH（涨停价有成交且开板/换手证据），
  否则为 UNPROVEN_FILL，不进入绩效分母（新增说明）
```

## 12.4 费用与市场规则（v0.4.2 §19）

```text
fee_policy、market_rule_policy 均带 effective_from / effective_to；禁止全局单一 10% 涨跌幅规则
```

## 12.5 指标口径与信任门槛（v0.4.2 §20–24）

```text
已实现盈亏分母：只含已证实入场且有规范退出的交易
WATCH / BLOCKED / REJECTED / INVALID / 未成交 / UNPROVEN_FILL：只出现在漏斗指标
信任等级：EXPLORATORY_IN_SAMPLE | VALIDATION | OUT_OF_SAMPLE | WALK_FORWARD | PRODUCTION_SHADOW
未声明信任等级的结果 → NOT_ACCEPTABLE_AS_STRATEGY_EVIDENCE
最小样本策略接口（数值待冻结）；重复与重叠单独报告；数据修订后旧回放不可变
```

## 12.6 规则级归因（新增）

每笔候选记录被哪些规则 PASS / FAIL / UNKNOWN，以便统计“每条规则的过滤贡献与事后收益差”。这是把 empirical_status 从 UNTESTED 推进的唯一途径。

---

# Part XIII — L9 复盘与学习闭环

来源：

```text
学习投资就是向自己的交易历史中学习，总结交易得失……建立一个盈多亏少的交易系统。   [CS-03 p1]
接受试错：即使错了，也要把它当作学费，记录下失败的原因。                       [CS-04 p3]
每次交易前认真做好复盘和盘前推演。                                             [CS-03 p4]
```

现状：`投资策略` 文件夹中没有 Owner 自己的交易记录。这是整个模型最大的反馈缺口。

## 13.1 交易日志（新增数据对象）

```json
{
  "journal_id": "...",
  "candidate_id": "...",
  "plan": {"strategy_id": "...", "setup_rules_passed": ["..."], "planned_entry": "...", "stop_spec": {}},
  "actual": {"entered_at": "...", "fill_proof": "...", "exited_at": "...", "exit_reason": "..."},
  "plan_adherence": "FOLLOWED|DEVIATED",
  "deviation_note": "...",
  "outcome_pct": 0.0,
  "failure_taxonomy": ["WRONG_THEME|WRONG_ROLE|WRONG_STAGE|BAD_TIMING|EXECUTION|RULE_GAP|MARKET_SHOCK"],
  "lesson_candidate": "..."
}
```

`lesson_candidate` 对接已冻结的 `JuliaReviewOverlay.v1`（#420），不在本文件重新定义。

## 13.2 每日复盘输出（对应 TH-04 模板）

```text
L1 市场状态 + 测量值
L2 题材清单：主线状态、催化事件
L3 每个主线的情绪状态
L4 强势股跟踪：角色、涨停类型、资金性质、流通性质、封单、技术形态、是否次新
L5 次日交易计划：标的、战法、观察条件（例如“是否突破 8.45、是否出现弱转强”）
当前操作原则（例如 TH-04 p32：“盘前大盘情绪冰点切忌操作”）
```

---

# Part XIV — 阈值注册表

状态：`SOURCE_SEED`（原文给出）/ `RANGE`（原文给区间）/ `CONFLICT` / `UNDEFINED`（原文用词无数值）/ `CALIBRATION_REQUIRED` / `REFERENCE`。全部 owner_status = UNFROZEN。

| ID | 用于 | 测量 | 种子值 | 来源 | 状态 |
|---|---|---|---|---|---|
| TH-001 | OTO-007、LDR-005 | 首板换手率下限 | 8% 或 15% | CS-03 p3、CS-04 p1：>8%；CS-04 p3、CS-07 p2：≥15% / >15% | CONFLICT（SC-01） |
| TH-002 | OTO-008 | 首板成交额下限 | 10 亿 | CS-04 p3 | SOURCE_SEED |
| TH-003 | OTO-003 | 题材助攻涨停数 | 2–3 只 | CS-04 p3；CS-07 p3 | RANGE |
| TH-004 | OTO-015 | 流通市值上限 | 200 亿 | CS-04 p2 | SOURCE_SEED |
| TH-005 | OTO-016 | 优选市值 / 股价 | 20–100 亿 / <20 元 | CS-04 p2 | SOURCE_SEED（偏好） |
| TH-006 | OTO-019、AUC-012 | 竞价高开 | 3%–5% | CS-04 p2；CS-06 p6 | RANGE |
| TH-007 | AUC-011 | 09:25 竞价量 / 昨日最大分钟量 | ≥ 0.5 | CS-06 p6 | SOURCE_SEED |
| TH-008 | OTO-025 | 二板封死后入场时窗 | 5 分钟 | CS-04 p3 | SOURCE_SEED |
| TH-009 | OTO-X04 | D+1 高开回落离场 | 7%–8% | CS-04 p3 | RANGE |
| TH-010 | OTO-X03 | D+1 不封板离场时点 | 10:30 | CS-04 p3 | SOURCE_SEED |
| TH-011 | W2S-013 | 烂板回撤上限 | 3% | CS-05 p2 | SOURCE_SEED |
| TH-012 | W2S-012/023/031 | 支撑均线 | 5 日、10 日 | CS-05 p1、p4 | SOURCE_SEED |
| TH-013 | W2S-022 | 分时平台最短时长 | 30 分钟 | CS-05 p3 | SOURCE_SEED |
| TH-014 | OTO-027、W2S-030 | 仓位 | OTO 1–2 成；W2S 1–2 / 5–8 / 2–4 成 | CS-04 p2；CS-05 p4 | SOURCE_SEED（SC-09） |
| TH-015 | LDR-005 | 量比 | > 2.5 | CS-03 p3 | SOURCE_SEED |
| TH-016 | W2S-006 | 被动分歧换手 | < 50%（≤20% 最佳） | CS-03 p3 | SOURCE_SEED |
| TH-017 | L3 CLIMAX | 题材涨停家数 | 连续 3 天 > 10 家 | CS-03 p3 | SOURCE_SEED |
| TH-018 | THM-004 | 主线确认 | 2 次领涨；首个 ≥3 连板龙头 | CS-03 p2–3 | SOURCE_SEED |
| TH-019 | THM-003、L3 INITIAL | 题材初期涨停数 | 1–3 只 | CS-03 p2 | RANGE |
| TH-020 | 涨停基因 | 回看窗口 | 6 天 | CS-08 p2 | SOURCE_SEED（NOT_MODELED 特征） |
| TH-021 | OTO-010 | 涨停日放量 | > 60 日均量或倍量 | CS-07 p2 | SOURCE_SEED |
| TH-022 | OTO-004 | 首板判定回看天数 N | — | — | UNDEFINED |
| TH-023 | OTO-009 | “尾盘偷封”时点 | — | CS-04 | UNDEFINED |
| TH-024 | OTO-012 | “生死线”均线 | — | CS-04 p2 | UNDEFINED（SA-02） |
| TH-025 | MKT-M12 | “大面”跌幅 | — | EXT-01 | UNDEFINED |
| TH-026 | L1 状态 | 市场情绪分档 | — | — | CALIBRATION_REQUIRED |
| TH-027 | AUC | min_coverage_ratio | — | v0.4.2 | UNDEFINED |
| TH-028 | W2S-026 | 再一致窗口 | 1 个交易日（“第二天”），上限待定 | CS-05 p1 | SOURCE_SEED + UNDEFINED |
| TH-029 | §4.5 | 出货日聚集 / 突兀波幅 | 2–4 周内 ≥4 个 / ≈3%（美股） | CS-09 | REFERENCE |
| TH-030 | INT | 分时“放量”倍数 | — | CS-03 | UNDEFINED |
| TH-031 | THM-M02 | 领涨计数窗口 W | — | — | UNDEFINED |
| TH-032 | OTO-005 | “位置相对较高”的度量 | — | CS-04 p2 | UNDEFINED |
| TH-033 | OTO-011 | “下降趋势”的判定 | — | CS-04 p2 | UNDEFINED |
| TH-034 | OTO-013 | “重要压力位”的判定 | — | CS-04 p2 | UNDEFINED |
| TH-035 | OTO-014 | “一年内大幅连板回落”的度量 | — | CS-04 p2 | UNDEFINED |
| TH-036 | OTO-020 | 竞价大单 vs 昨日涨停放量 | “超过” | CS-04 p2 | SOURCE_SEED（比较方式待定） |
| TH-037 | OTO-026 | “长时间不能回封” | — | CS-04 p4 | UNDEFINED |

UNDEFINED 阈值的处理：研究模式下以**预注册的参数网格**回放（例如 TH-001 同时跑 8% 与 15%），冻结前不得选择“回放最好看”的值，选择规则必须在回放前写定。

---

# Part XV — 来源冲突与歧义登记

| ID | 冲突/歧义 | A | B | v0.5 默认 | 决策项 |
|---|---|---|---|---|---|
| SC-01 | 首板换手下限 | >8%（CS-03 p3；CS-04 p1） | ≥15%（CS-04 p3 SOP；CS-07 p2） | 预注册双变体回放 | OF-06 |
| SC-02 | 价格与市值偏好 | 低价+低位+低市值；股价 <20 元（CS-03 p3；CS-04 p2） | 龙头往往价格不便宜，强者恒强（CS-07 p3） | 仅作偏好证据，不作门槛 | — |
| SC-03 | 基本面 | 龙头基本不看财务基本面（CS-03 p3） | 2026 年业绩预告主导（EXT-01） | 通过 STYLE_REGIME 区分；业绩战法 NOT_MODELED | OF-04 |
| SC-04 | 1 进 2 准入 | 主线/强热点（v0.4.2 OTO-001） | 只做主线（CS-01；CS-03 p1；v0.4.2 OF-01） | 只做 CONFIRMED_MAINLINE | OF-01 |
| SC-05 | 主线确认前能否出手 | 初期轻仓试探打板（CS-03 p2） | 题材是否主线，否则放弃（CS-01） | 不出手 | OF-01 |
| SC-06 | 冰点能否操作 | 盘前大盘冰点切忌操作（TH-04 p32） | 冰点后新题材如有必干（EXT-01 7/7）；龙头往往诞生在冰点后第一波反弹（CS-07 p3） | 冰点当日不开仓；冰点后首日待定 | OF-05 |
| SC-07 | 分歧当日能否买 | 下跌当天尽量不要低吸（CS-03 p3） | 大环境不好的被动分歧，满足条件可买（CS-03 p3） | 不建模分歧当日买入 | OF-07 |
| SC-08 | 龙头持有方式 | 要捂得住，不要在龙头股上做短线（CS-03 p3） | 龙头战法的核心是快进快出（CS-04 p3） | OTO 持仓按 OTO 退出；角色升为 LEADER 后是否切换到阶段型退出待定 | OF-08 |
| SC-09 | W2S 初始仓位 | 首次尝试 1–2 成（CS-05 p4） | 主线+绝对龙头 5–8 成（CS-05 p4） | 首次 1–2 成，确认后按角色上限加仓 | OF-09 |
| SA-01 | 1 进 2 是否必须连续 | SOP：二板实时盯盘（CS-04 p3） | “首板之后第 2 天最好是温和放量中小阳线”（CS-04 p2） | 只建模连续 1 进 2 | Owner 澄清 |
| SA-02 | “生死线”定义 | 原文未定义（CS-04 p2） | — | UNDEFINED | Owner 澄清 |

---

# Part XVI — Owner 决策项

本文件不推断任何批准。在 Owner 显式填写之前：

```text
OWNER POLICY STATUS = UNFROZEN
LIVE ORDERING = NO
```

| ID | 决策 | 起草者建议 | 理由 |
|---|---|---|---|
| OF-01 | 主线准入：只允许 CONFIRMED_MAINLINE 创建 OTO/W2S Setup；CONFIRMED 的定义采用 THM-004（BIG 逻辑 + 2 次领涨 + 首个 ≥3 连板龙头同时满足） | **APPROVE**，初期试错暂不建模 | 原文主线为第一否决；严格版放弃初期试错，没有回测时保守合理。代价：会错过部分主线最早的一段 |
| OF-02 | 退出原因顺序只用于报告 | **APPROVE_AS_REPORTING_PRIORITY_ONLY** | 防止工程排序悄悄变成交易严重度 |
| OF-03 | 入场强制登记止损（RISK-001）为主机制；VERIFIED 终局失效为补充；删除“分时前低=持仓终局” | **APPROVE** | 确定性、可重放，不依赖尚未冻结的 L1/L3 |
| OF-04 | 采用 L1 的 EXTERNAL_RISK_STATE 与 STYLE_REGIME（来源为 EXT-01） | **APPROVE_RESEARCH_ONLY** | 2026 年真实存在双风格，但目前只有外部作者观点支撑，需回放验证 |
| OF-05 | 冰点政策（SC-06） | 冰点当日 BLOCKED；冰点后首日的新题材首板 → WATCH，并做专项回放 | 三个来源结论不同，需要数据裁决 |
| OF-06 | 首板换手下限（SC-01） | 预注册 8% 与 15% 双变体，按样本外结果冻结 | 原文自相矛盾，不应由起草者选择 |
| OF-07 | 被动分歧当日买入（SC-07） | **NOT_MODELED（v1）** | 与“分歧当天不低吸”冲突，且需要更细的承接测量 |
| OF-08 | OTO 持仓升级为 LEADER 后的持有方式；OTO-A01 加仓 | 暂按 OTO 退出规则执行；加仓 NOT_MODELED | 原文冲突（SC-08），先保守 |
| OF-09 | W2S 仓位（SC-09） | 首次 1–2 成；确认后按角色上限（龙头 ≤5–8 成、龙二 ≤2–4 成）加仓 | 兼容原文两句话 |
| OF-10 | 组合层风险限额 | 需要 Owner 给出数值 | 原文没有任何组合层规则 |
| OF-11 | L1 市场状态校准方法（分位数+滞后）、见顶模块（§4.5）是否启用、龙头排名算法（§7.2）、与 ADR-032/C-A5 的边界 | 校准方法 APPROVE_RESEARCH_ONLY；见顶模块暂不启用 | 均为起草者提案，无原文数值 |

```text
OF-01 =
OF-02 =
OF-03 =
OF-04 =
OF-05 =
OF-06 =
OF-07 =
OF-08 =
OF-09 =
OF-10 =
OF-11 =
SA-01 澄清 =
SA-02 澄清 =
```

---

# Part XVII — 实现边界与构建顺序

## 17.1 现在允许

```text
v0.4.2 已允许的：schema / validator / 状态转移校验 / 去重 / as-of / authority-hash / 回放基础设施 / 非交易证据采集
新增允许：
  L0 数据质量 validator（DQ-001–006）与 M8 抽取缺陷修复（DQ-D01–D08）
  L1 测量值计算（MKT-M01–M18，纯测量，不出状态）
  L2 题材目录导入（TH 系列，标注 claim_status 与 staleness）
  数据可得性核查（§11.2）
  由本文件生成 v0.5 JSON 组件，并做 Markdown ↔ JSON 一致性校验
```

## 17.2 仍然禁止

```text
生产策略切换；实盘下单；资金部署
静默阈值选择；静默 Owner 政策选择
任何加权评分直接生成 ENTRY_ELIGIBLE
在 OF-01/OF-03 冻结前，回放结果以“策略有效”的口径对外报告
```

## 17.3 构建顺序

| 阶段 | 内容 | 前置 | 产出 |
|---|---|---|---|
| P0 | 数据缺陷修复 + 数据可得性核查 | — | DQ 报告；可用数据集清单 |
| P1 | L1 测量值 + 回放 2026-06-17 至 07-09（与 EXT-01 对照） | P0 | 测量值时间序列；与 EXT-01 的差异报告 |
| P2 | L2 主线 + L3 情绪周期（研究模式） | P1、OF-01、OF-11 | 每日主线/阶段标注 + 人工抽检 |
| P3 | L4 龙头定位 | P2 | 每日角色表（对照 TH-04 模板） |
| P4 | OTO / W2S 重建注册表与 JSON | P3 | Rule Registry v0.5 |
| P5 | L7 / L8（止损、T+1、阶段退出） | P4、OF-03 | 端到端回放 |
| P6 | 预注册参数网格 + 样本外 / walk-forward | P5、最小样本策略 | 规则级归因报告；empirical_status 更新 |

## 17.4 代码审计清单（下一步用本文件审计代码）

```text
A-01  是否存在“加权综合分 → 买入/BUY_ELIGIBLE”的路径（违反 INV-001）
A-02  领域逻辑中是否有阈值字面量（违反 §3.6）
A-03  OTO/W2S 是否在没有 L1–L4 门槛的情况下直接计算（违反 INV-002）
A-04  是否存在同日买卖路径或退出未带 earliest_executable_at（违反 INV-T1）
A-05  ENTERED 是否由决策产生而不是成交证据（违反 §3.1）
A-06  UNKNOWN 是否被默认当作通过（违反 §3.3）
A-07  M8 / 外部抽取数据是否原样进入决策（违反 DQ-002、EXTERNAL_SIGNAL 权威等级）
A-08  确定性适用性判断是否进入 Julia 生产路径（ADR-032 / C-A5）
A-09  as-of 与 peer 快照是否存在前视
A-10  规则 ID 是否可追溯到本文件；无出处的规则一律标注 PROPOSED 或删除
```

---

# Part XVIII — v0.4.2 → v0.5 规则映射

## 18.1 OneToTwo

| v0.4.2 | v0.5 | 变化 |
|---|---|---|
| OTO-001 | OTO-001 | 删除“强热点” |
| OTO-002 | OTO-002 | — |
| OTO-003 | OTO-003 | 合并 v0.4.2 OTO-012 |
| OTO-004 | OTO-004 | N 标为 UNDEFINED |
| OTO-005 | OTO-005 + OTO-017 | 拆为排除与偏好 |
| OTO-006 | OTO-007 | 阈值冲突登记 |
| OTO-007 | OTO-010 | — |
| OTO-008 | OTO-009 | 改为 EXCLUSION |
| OTO-009 | OTO-006 | 改为 EXCLUSION，去掉 SEVERITY_UNFROZEN |
| OTO-010 | OTO-011 | — |
| OTO-011 | OTO-012 + OTO-013 | 拆分 |
| OTO-012 | （并入 OTO-003） | 重复 |
| OTO-013 | OTO-015 | 改为 EXCLUSION，200 亿为原文数值 |
| OTO-014 | OTO-018 | — |
| OTO-015 | OTO-019 | — |
| OTO-016 | OTO-020 | — |
| OTO-017 | OTO-021 | — |
| OTO-018、OTO-019 | OTO-022 | 合并 |
| OTO-020 | OTO-025 | 补 5 分钟时窗 |
| OTO-021 | OTO-027 | — |
| OTO-022 | OTO-X01 | T+1 修正 |
| OTO-023 | OTO-X05 | 语义修正 |
| OTO-024 | OTO-X04 | 类型改为 EXIT |
| OTO-025 | OTO-X06 | 类型改为 EXIT |
| — | OTO-008、014、016、023、024、026、028、X02、X03、X07、A01 | 新增 |

## 18.2 WeakToStrong

| v0.4.2 | v0.5 | 变化 |
|---|---|---|
| W2S-001、002 | W2S-010 | 合并 |
| W2S-003 | W2S-012 | — |
| W2S-004、009、010 | W2S-020、021 | — |
| W2S-005、020、021 | W2S-024 | 合并 |
| W2S-006 | W2S-004 | — |
| W2S-007 | W2S-013 | 补回 3% 与五要素 |
| W2S-008 | W2S-011 + 核心思想 | — |
| W2S-011–013 | W2S-022 | 合并 |
| W2S-014–016 | W2S-023 | 合并 |
| W2S-017、018 | W2S-025 | 合并 |
| W2S-019 | W2S-001 | 去掉 SEVERITY_UNFROZEN |
| W2S-022 | W2S-003 | — |
| W2S-023 | W2S-011 | — |
| W2S-024 | §8.4 公式 | — |
| W2S-025 | W2S-028 | — |
| — | W2S-002、005、006、007、014、026、027、030、031、X01–X05 | 新增 |

## 18.3 Auction

AUC-001 至 AUC-015 编号保留；新增 AUC-000；AUC-002、AUC-011 定义补全；AUC-015 推广为 INV-001。

---

# 附录 A — EXT-01 文件哈希

| 文件 | SHA256 |
|---|---|
| 7月1日复盘.md | `228bf4bafbffd08998c407b8a4530fc564d76f386181b77205ed9457d741a85c` |
| 7月2日复盘.md | `47f36388e3e104d4d222b33bb78dfe5e9346a411c514cd70cdf5c84bb2f4abed` |
| 7月3日复盘.md（7/5 发布） | `83be4040d63c2f901b58366b5ed0ea4883d361f53ae8b99f2ed02286e3a58a3c` |
| 7月6日复盘.md | `dfeb70bab3552603c4af5fb985d048bfc5e83e32e05ec203d137b0a9344bcc0c` |
| 7:7日复盘.pdf | `6c063d4d382373cad0f37d0daaf666ed89b6bfe1614446c415eeaa85c864bcb8` |
| 7:8日复盘.pdf | `ea8c9539dcb13e73565b882afe35663673d3c5d70171e02c881c9ddf36de4459` |
| 7:9日复盘.pdf | `9e3c7c62769e97a76ce4c203edaa61d410775fe068f87bc205c5b017ff850293` |
| 7月9日复盘.md | `19ace3dd240e57dae5c6e6c0dbca5c5bf6c34684e7fa5f10666a7cdc14eae1a6` |
| 7月9日复盘_DeepSeek完整结构版.md | `411f24993bb15307a5e07fe23307d37390d04d50aa8387bd792453023a409dc3` |

# 附录 B — 页码约定

CS-03、CS-04、CS-05、CS-06、CS-07、CS-08 的页码按 PDF 页脚编号；Keynote（CS-01、CS-02、TH-03）按流程图标题引用（“短线交易系统”“1进2打板操作流程”“弱转强操作流程”“市场情绪周期”）。页码由 2026-10-06 的文本抽取确定，若与 Handbook v0.3.2 的引用口径不一致，以原文件为准重新核对。
