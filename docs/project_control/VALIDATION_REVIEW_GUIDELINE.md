# Market Thesis Validation Review Guideline

## 1. 目标与边界

本规范用于生成一致、可审计的 Market Thesis Ground Truth。Reviewer 只依据验证时点前已存在的市场事实裁决，不修改昨日 Thesis，不补写事后逻辑，不触发 Belief、Learning 或 Decision。

## 2. 标签标准

| Label | 判定标准 |
|---|---|
| `YES` | Thesis 的核心方向、对象和约定时点均被事实支持；不得填写 failure type。 |
| `NO` | 核心方向或核心对象被事实否定；必须选择一个一级 failure type。 |
| `PARTIAL` | 核心判断仅部分兑现，或方向正确但强度/范围明显不足；必须选择一个一级 failure type。 |
| `UNVERIFIABLE` | 截至验证时点缺少完成裁决所需的事实；failure type 固定为 `INSUFFICIENT_EVIDENCE`。 |

`PARTIAL` 不用于回避判断。能够明确判定方向错误时必须使用 `NO`。

## 3. Failure Type

一级分类固定为六种，不增加临时枚举：

- `WRONG_DIRECTION`
- `WRONG_TIMING`
- `WRONG_THEME`
- `INSUFFICIENT_EVIDENCE`
- `UNEXPECTED_EVENT`
- `MARKET_REGIME_SHIFT`

细节写入 `verification_reason`，不得通过新增枚举表达。

## 4. Reviewer 操作顺序

1. 冻结并核对昨日 `thesis_id`、`thesis_hash`、`as_of`。
2. 只加载 `reality_available_at` 之前可用的 Evidence。
3. 对照 Thesis 的对象、方向、验证窗口与失效条件。
4. 录入 Label、Failure Type、客观 Outcome、Reason 和 EvidenceRefs。
5. 复核无未来数据泄漏后提交 append-only Record。
6. 刷新并验证 Dataset Manifest。

## 5. 冲突处理

- 两位 Reviewer 一致：直接提交。
- 不一致：记录双方意见，由指定 Adjudicator 裁决。
- Adjudicator 不得覆盖已有 Record；未提交时形成单一最终裁决，已提交后发现问题则走更正 ADR/审计记录，不原地修改。
- 无法在证据范围内解决：标记 `UNVERIFIABLE`，不得多数投票猜测 Ground Truth。

## 6. Review Comment 最低要求

Comment 必须包含：争议点、采用证据、排除证据、最终理由、Reviewer/Adjudicator、验证时间。禁止使用“感觉较强”“基本符合”等无 EvidenceRef 的描述。

## 7. 质量抽检

- 每 5 个交易日抽检标签一致性与 EvidenceRef 完整性。
- 每 20 个交易日复核 Failure Type 分布、Reviewer 分歧率与 Calibration。
- Manifest Integrity 必须在每日写入结束后执行；失败时停止新增验证并先恢复数据完整性。
