# P3-M1 Layer A 主线身份算法迁移实施清单

> 状态：In Progress  
> 更新时间：2026-04-24  
> 目标：将旧链主线身份核心算法迁移至新链 `stock_processing_service`，保持架构解耦与可回放。

## 1. 范围与边界

### In Scope

1. 规则评分：`logic_score/market_score/composite_score`
2. 一日游与 K 线连续性门禁
3. `review_pending` 升级漏斗与受控复核接口
4. 身份决策输出：`observed/review_pending/confirmed/inactive`

### Out of Scope

1. 数据库写入策略变更
2. Layer B/C/D 规则调整
3. 前端展示逻辑改造

## 2. 任务拆解

### T1 规则模型迁移（Domain）

1. 新增 `identity_rule_engine.py`
2. 将旧链评分公式迁移为纯函数
3. 输出结构体含 `score_flags/reasons/evidence_refs`

验收：
1. 单测覆盖公式关键分支
2. 输入缺失时有确定性降级

### T2 一日游与 K 线门禁迁移（Domain）

1. 扩展 `one_day_tour_detector.py`，支持旧链核心判定字段
2. 统一门禁输出：`one_day_tour_flag/kline_support_hold/platform_breakout_flag`

验收：
1. 单测覆盖 spike + retrace + 均线失守场景
2. 反例不误杀（稳定上涨非一日游）

### T3 受控复核与升级漏斗（Domain + Application）

1. `identity_llm_review_service` 改为“受控输入+结构化输出”接口
2. `IdentityDecider` 增加 `review_pending` 漏斗约束
3. `BuildIdentityJob` 输出审计字段（来源、门禁命中、漏斗阶段）

验收：
1. `upgrade_trigger` 不得直通 `confirmed`
2. `review_pending` 样本可追踪原因链路

### T4 A/B 对账脚本（Tools）

1. 新增 `scripts/compare_identity_old_new.py`
2. 按交易日输出差异：
   - 状态差异
   - 分数差异
   - 门禁差异

验收：
1. 支持指定样本日（4/7、4/15）
2. 产出 CSV + summary

## 3. 回归样本

1. 神剑股份（002361.SZ）- 2026-04-07
2. 联德股份（605060.SH）- 2026-04-15
3. 一日游反例样本（高冲高回落）
4. 非主线但强势样本（两连板旁路）

## 4. DoD

1. Domain 层无 SQL / 无 asyncpg 依赖
2. 所有读写经 Ports + Gateway Adapter
3. 核心规则单测通过
4. 回放样本可复现，对账结果可审计

## 5. 当前推进顺序

1. 先 T1 + T2（算法等价）
2. 再 T3（漏斗与复核）
3. 最后 T4（对账闭环）
