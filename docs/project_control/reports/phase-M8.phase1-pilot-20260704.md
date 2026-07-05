# M8.phase1 真实交易日试运行报告 — 2026-07-04

## 1. 试运行边界

- 数据源：`stock_data_test.post_market_recap_snapshot`，只读。
- 交易日：2026-07-01、2026-07-02、2026-07-03。
- 执行范围：Phase 0 Replay、跨日 Validation Source 准入检查。
- 禁止项：不自动生成 Reviewer Verdict，不写 Ground Truth Record，不启动 Belief/Learning。

## 2. Replay 结果

| 交易日 | Replay | Decision unchanged | EvidenceRef | Unsupported claim | Thesis hash |
|---|---|---:|---:|---:|---|
| 2026-07-01 | ready | 是 | 100% | 0 | `e1009227f3b099795bf33cc32d0d4c2e8985e184a49b8540ed92fea3c9edaccf` |
| 2026-07-02 | ready | 是 | 100% | 0 | `5423f484bac38be69e16ad42f08d0118c1f78ffaec7a78ad54f8eea9bd6f07f7` |
| 2026-07-03 | ready | 是 | 100% | 0 | `0e686625fd7606e8a39f72b121a9c4e15a85da3256f4b5ca7d4d8ceec3a7cdbe` |

技术链路稳定，三日快照均可确定性进入 Cognition/Thesis，且未改变正式 Decision。

## 3. Validation Source 准入检查

2026-07-02 与 2026-07-03 的 Primary Thesis 均为：

> 当前不支持主动交易，核心任务是观察主线能否修复。当前主线观察聚焦磷化铟。

Scenario 为：

> 若短线情绪脱离冰点且主线获得资金确认，则重新评估交易权限，不提前假定修复成功。

当前不能直接生成正式 Validation Record，原因如下：

1. Primary Thesis 描述的是当日状态，不是带验证期限的未来命题。
2. Primary Thesis 的 `confidence=1.0` 当前来自 Evidence Quality，不能解释为预测成功概率。
3. Scenario 是条件分支，但没有独立概率；直接用于 Brier/ECE 会产生错误校准样本。
4. 在没有 Reviewer Verdict 的情况下自动填入 YES/NO/PARTIAL 会违反 Ground Truth Policy。

因此本次正式 Dataset 写入数为 `0`。这是准入阻断，不是 Dataset Writer 失败。

## 4. T03 最小准入裁决

T03 不验证 Narrative 文本，优先复用现有 `HypothesisState`：

- `statement`：待验证命题；
- `probability`：事前概率，也是 Calibration 的 confidence；
- `deadline`：验证期限；
- `expected_observations`：YES/PARTIAL 的判断依据；
- `falsifiers`：NO 的判断依据；
- `evidence_refs`：昨日证据；
- Reviewer Verdict：唯一 Ground Truth 输入。

不得使用 `MarketThesisSnapshot.primary_thesis.confidence` 计算 Brier/ECE，除非其语义以后明确升级为事前预测概率。

## 5. 下一步门禁

进入 T03 前必须先满足：

- 明确从昨日冻结 Cognition/Thesis 中提取 `HypothesisState`，禁止运行新版本代码后反向改写昨日命题；
- Reviewer 只录入 Verdict、Reason、Outcome 与 Today EvidenceRefs；
- 验证服务从 Hypothesis 复制 probability/deadline，不允许 Reviewer 事后修改 confidence；
- 六种 Failure Type 保持冻结；
- 首个 Record 经双人 Review 后才能写入正式 Dataset，并立即执行 Manifest Integrity。

## 6. 结论

T02 的存储、Replay 与完整性能力可用；真实数据试运行发现的是 Validation Source 语义缺口。修复该缺口前不进入批量 Ground Truth 写入，避免形成不可校准的数据资产。

## 7. T03 Eligibility Pilot 补充

实施 ADR-M8-009 的 Eligibility Gate 后，真实 2026-07-03 快照首次冻结时发现：

- 原 Hypothesis deadline 为 `2026-07-04`（周六）；
- 根因是 `FixedCognitionPolicy` 使用自然日 `trade_date + 1`；
- 同一快照已有 Trade Calendar Producer 生成的 `post_market_setup_plan.summary.watch_date=2026-07-06`。

最小修复后：

| 项目 | 结果 |
|---|---|
| Source trade date | 2026-07-03 |
| Frozen deadline | 2026-07-06 |
| Prediction probability | 0.35 |
| Calendar EvidenceRef | `post_market_setup_plan:summary.watch_date` |
| Source append | created |
| Source hash | `6635ae53c47580bbc58ebb947b6b93f62b59d968e030f2ed42e59c479cedeeb4` |

正式 Validation Record 仍为 `0`：截至本报告时间，2026-07-06 Reality 与 Reviewer Verdict 尚不存在。系统只冻结昨日 eligible Source，不提前生成 Ground Truth。
