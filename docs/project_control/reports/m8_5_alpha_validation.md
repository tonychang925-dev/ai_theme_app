# M8.5 Alpha Validation Report

> 版本：v1.0
> 日期：2026-07-08
> 状态：In Progress — Alpha 验证阶段
> 关联：M8.5 分析师驾驶舱 MVP (P2.1–P2.5)

---

## 0. Alpha 验证目标

不是继续开发新引擎，而是用 **5–10 个真实交易日** 的工作流，回答四个核心问题：

| # | 问题 | 验证标准 |
|---|------|---------|
| 1 | 分析师是否愿意每天用这个页面 | 5+ 天连续使用，不退回旧流程 |
| 2 | AI 草稿哪些字段可用，哪些需要人工补 | 逐字段统计自动填充率 |
| 3 | OverrideLog 是否能准确记录修改 | 每次修改可追溯 to JSONL |
| 4 | 最终复盘素材是否明显优于旧版 | 分析师 A/B 对比评价 |

---

## 1. 验证范围

### 1.1 已验证的功能

| P2.x | 功能 | 状态 |
|------|------|------|
| P2.1 | Attention Radar — 自动评分的重点题材列表 | ✅ |
| P2.2 | Cognition Workspace — AI 草稿 + 11 字段认知卡 | ✅ |
| P2.4 | Playbook Builder — 交易剧本 + Review Panel | ✅ |
| P2.5 | Analyst Workspace — 三面板录入审核页 | ✅ |
| — | 观察方向 — 分析师自定义题材分组 | ✅ |
| — | 股票池 — 龙头/多头/空头池维护 | ✅ |
| — | OverrideLog — 所有修改写入 JSONL | ✅ |

### 1.2 未进入 Alpha 的功能

| 功能 | 原因 |
|------|------|
| P2.3 Narrative Builder | 应消费 Playbook + Cognition 后再做 |
| Causal Engine | 需要真实数据验证因果链模板 |
| Leader Evolution | 需要积累龙头交接事件 |
| 复盘报告一键生成 | 依赖 Alpha 反馈确定字段优先级 |

---

## 2. 核心指标体系

### 2.1 数据采集方式

每次保存工作台时，从 JSON 文件和 OverrideLog JSONL 中自动统计：

```
采集源：
  tmp/analyst_workspace/{trade_date}.json  → 题材数、字段填充状态
  tmp/analyst_overrides/{trade_date}_workspace_overrides.jsonl → Override 明细
```

### 2.2 核心指标

| # | 指标 | 计算方式 | 目标值 |
|---|------|---------|--------|
| K1 | AI 自动填充率 | 非空字段数 / 总字段数 per 题材 | ≥ 60% |
| K2 | 字段确认率 | 分析师直接确认的字段数 / 总字段 | ≥ 40% |
| K3 | 字段修改率 | 分析师修改的字段数 / 总字段 | ≤ 30% |
| K4 | 字段否定率 | 分析师否定的字段数 / 总字段 | ≤ 10% |
| K5 | 平均审核耗时 | 从打开到保存的时间差 | ≤ 15 分钟 |
| K6 | 每日题材数 | 工作台中主题数（CRITICAL+HIGH+手动） | 5–15 |
| K7 | 每日 Override 数 | override_log 行数 / 日 | 5–20 |
| K8 | 高频被修改字段 Top10 | 按字段名聚合 override 次数 | 识别系统性偏差 |

### 2.3 辅助指标

| # | 指标 | 说明 |
|---|------|------|
| A1 | 观察方向使用率 | 有 watch_groups 的天数 / 总天数 |
| A2 | 股票池填充率 | 有 leaders/bull/bear 的题材数 / 总题材数 |
| A3 | 手动新增题材率 | analyst_added 题材数 / 总题材数 |
| A4 | AI 推荐采纳率 | 保留的 AI 推荐题材数 / AI 推荐总数 |

---

## 3. Alpha 运行日志

### 模板

```
日期: YYYY-MM-DD
题材数: N  观察方向数: M  Override数: O
AI填充率: X%  确认率: Y%  修改率: Z%  否定率: W%
耗时: T 分钟

字段级统计:
  trading_style: [AI填充/确认/修改/否定]
  market_phase:  [AI填充/确认/修改/否定]
  event_stimuli: [AI填充/确认/修改/否定]
  current_leaders: [AI填充/确认/修改/否定]
  potential_leaders: [AI填充/确认/修改/否定]
  bull_pool:     [AI填充/确认/修改/否定]
  bear_pool:     [AI填充/确认/修改/否定]
  yesterday_view: [AI填充/确认/修改/否定]
  today_actual:  [AI填充/确认/修改/否定]
  tomorrow_view: [AI填充/确认/修改/否定]
  analyst_notes: [AI填充/确认/修改/否定]

高频修改字段: [Top 3]
分析师备注:
```

### Day 1 — 2026-07-08

```
日期: 2026-07-08
题材数: ___  观察方向数: ___  Override数: ___
AI填充率: ___%  确认率: ___%  修改率: ___%  否定率: ___%
耗时: ___ 分钟
分析师备注: ___
```

### Day 2–10

（逐日填写）

---

## 4. Alpha 结论

### 4.1 是否通过 Alpha

| 条件 | 阈值 | 实际 | 通过 |
|------|------|------|------|
| 连续使用天数 | ≥ 5 天 | — | — |
| AI 填充率 | ≥ 60% | — | — |
| 修改率 | ≤ 30% | — | — |
| OverrideLog 完整性 | 100% 修改可追溯 | — | — |
| 分析师主观评价 | 优于旧版复盘 | — | — |

### 4.2 发现与建议

（Alpha 结束后填写）

### 4.3 下一步优先级

基于 Alpha 数据决定：
1. 如果修改率 > 30% → 优先提升 AI 草稿质量
2. 如果否定率 > 10% → 某些字段应改为手动输入
3. 如果股票池填充率 < 30% → 接入 leader_score_snapshot 数据源
4. 如果审核耗时 > 20min → 简化字段或增加批量确认

---

## 5. Alpha 结束后路线图

```
Alpha 验证
    │
    ▼
高频修改字段分析 → 提升 AI 草稿质量
    │
    ▼
P2.3 Narrative Builder (基于真实数据)
    │
    ▼
Phase 1.5 Real World Modeling (Real DQ + Real Maturity)
    │
    ▼
Phase 2 White Paper (6–12 月历史回放)
```
