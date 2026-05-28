# v3.0-A W2SSignal 回归验收报告

> 验收日期: 2026-05-28
> 验收人: Claude Code
> 版本: v3.0-A (implemented → regression)

## 验收结论: ✅ PASS (4/4)

---

## 验收用例 1: W2SSignal 字段完整性

**方法**: 构造 20 条多样化 UnifiedW2SAlert，通过 `w2s_signal_from_unified_alert()` 转换并逐字段检查。

| 字段 | 通过率 | 状态 |
|------|--------|------|
| signal_id | 20/20 | ✅ |
| stage | 20/20 | ✅ |
| scorer_version | 20/20 | ✅ |
| stock_code | 20/20 | ✅ |
| stock_name | 20/20 | ✅ |
| scores | 20/20 | ✅ |
| evidence | 20/20 | ✅ |
| risk_flags | 20/20 | ✅ |
| alert_level | 20/20 | ✅ |
| trace_id | 20/20 | ✅ |
| run_id | 20/20 | ✅ |
| biz_date | 20/20 | ✅ |
| event_time | 20/20 | ✅ |
| source_chain | 20/20 | ✅ |
| factor_snapshot | 20/20 | ✅ |
| **总计** | **300/300** | **✅** |

**额外检查**:
- ✅ signal_id 唯一性: 20/20 无重复
- ✅ source_chain 值: `{'realtime'}`
- ✅ alert_level 分布: alert=3, watch=17
- ✅ factor_snapshot keys: 15 个字段（含 d2/intraday/support 全阶段）

**样例 signal**:
```
signal_id: 2026-05-15:300001.SZ:intraday:v2.2:realtime
stage: intraday
scorer_version: v2.2
stock_code: 300001.SZ
stock_name: 测试股票1
alert_level: alert
trace_id: trace_20260528172414_17372d2b
biz_date: 2026-05-15
source_chain: realtime
scores: {"final": 70, "auction": 85, "intraday": 70}
evidence count: 2
factor_snapshot: 15 keys (d2_level, d2_score, auction_open_pct, carry_ratio, capital_flow, capital_imbalance, intraday_level, intraday_score, relative_strength_cross_zero, above_vwap, support_state, chase_risk_penalty, break_platform_30m, amount_acceleration, unified_level)
```

---

## 验收用例 2: Redis Pusher 双格式兼容

| 检查项 | 状态 |
|--------|------|
| `push_unified_alerts()` (旧格式) 保留 | ✅ |
| `push_w2s_signals()` (新方法) 存在 | ✅ |
| `w2s_signal_from_unified_alert()` 独立 adapter | ✅ |
| 旧 `UnifiedW2SAlert` dataclass 未修改 | ✅ |
| 新 `W2SSignal` dataclass 独立存在 | ✅ |
| adapter 通过 `getattr` 访问旧对象字段（不耦合） | ✅ |

**关键设计决策验证**:
- ✅ adapter 是独立函数，不修改旧 dataclass
- ✅ 旧对象保持原样，linter 无冲突
- ✅ 通过 `isinstance(s, W2SSignal)` 判断格式，通过 `w2s_signal_from_unified_alert(s)` 转换

---

## 验收用例 3: Shadow Report 兼容

| 检查项 | 状态 |
|--------|------|
| `w2s_field()` helper 存在 | ✅ |
| 优先从 `payload` JSONB 读取 W2SSignal 兼容字段 | ✅ |
| 字段映射: current, vwap, relative_strength_cross_zero 等 9 字段 | ✅ |
| `factor_snapshot` 嵌套路径回退 | ✅ |
| 缺字段时回退到旧 log 表列 | ✅ |

**字段映射表**:
```
current → current
vwap → vwap
relative_strength_vs_index → relative_strength
relative_strength_cross_zero → relative_strength_cross_zero
above_vwap_cross_up → above_vwap
amount_acceleration → amount_acceleration
break_platform_30m → break_platform_30m
support_state → support_state
alert_level → alert_level
```

---

## 验收用例 4: 旧前端不受影响

| 检查项 | 状态 |
|--------|------|
| 旧 `UnifiedW2SAlert` 仍可推送 | ✅ `push_unified_alerts()` 未修改 |
| 旧 SSE 前端仍可消费 `stream:w2s:alerts` | ✅ Stream 名称未变 |
| 旧 Redis 消息格式未变 | ✅ 旧 `push_*` 方法均保留 |
| 新 `push_w2s_signals()` 可独立使用 | ✅ 渐进迁移 |

---

## 未做事项（确认不涉及）

| 事项 | 状态 |
|------|------|
| 接 `signal_decision` 表 | ❌ 未接（符合设计） |
| 切 `stream:alert.decision` | ❌ 未切（符合设计） |
| 废弃旧 `UnifiedW2SAlert` | ❌ 未废弃（符合设计） |
| 废弃 `strategy_signal_daily` 等旧表 | ❌ 未废弃（符合设计） |
| 修改 scorer 评分逻辑 | ❌ 未修改（符合设计） |

---

## 版本标记

```
v3.0-A: REGRESSION PASSED → FROZEN
```

下一步: v3.0-A+ W2S Intraday Fusion shadow run（前置条件: v3.0-A 验收通过 ✅）
