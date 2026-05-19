# v2.4-FWD — Forward Auction Timeline Collection Plan

> 状态：ACTIVE
> 日期：2026-05-19
> 目标：每日对 D1 候选做 09:20–09:25 timeline 采集，积累 real_auction 样本

---

## 1. Why forward-only

- 历史竞价 timeline 无法回填（Tushare stk_auction 仅提供单点快照）
- 向前采集 20-30 个交易日后可达到最低验证样本量
- 管线已就绪（pre_market_auction_timeline_raw + pre_market_auction_feature）

## 2. Collection scope

**仅采集候选池股票，不做全市场：**

```
w2s_candidate_rebuild 当日 D1 候选
+
v2.0 previous_low 核心候选
```

预计每日 5–15 只股票。

## 3. Time points required

| Time | Mandatory | Why |
|------|-----------|-----|
| 09:20:00 | ✅ | 基准点，9:20后不可撤单的开始 |
| 09:21:00 | ✅ | 趋势检测 |
| 09:22:00 | ✅ | 趋势检测 |
| 09:23:00 | ✅ | 趋势检测 |
| 09:24:00 | ✅ | 最后一分钟起点 |
| 09:25:00 | ✅ | 竞价结束价，开盘价 |
| 09:24:30 | 可选 | 更细粒度尾段检测 |

## 4. Minimum fields

```
indicative_open_price
indicative_open_pct
matched_volume
matched_amount
snapshot_time
source_name
raw_payload
```

如果能拿到 L2 数据，补充：`bid_price, ask_price, bid_volume, ask_volume`

## 5. Daily workflow

```
09:25:30  → 采集 6 个时间点的快照数据
09:26:00  → 写入 pre_market_auction_timeline_raw
09:26:30  → 运行 AuctionTimelineFeatureBuilder.build()
09:27:00  → 写入 pre_market_auction_feature
09:27:30  → 输出 daily coverage report
```

## 6. Data source options

| Source | Timeline? | Status |
|--------|-----------|--------|
| Tushare stk_auction | ❌ single point only | 已接入 |
| Tushare Level-2 | ✅ 需要付费 | 待评估 |
| EastMoney API | ⚠️ 可能有分时 | 待调研 |
| 华泰/中信 L2 | ✅ 机构级 | 待评估 |

**当前推荐**：先用 Tushare stk_auction 单点数据保持 daily_open_proxy 覆盖，同时调研能提供 09:20-09:25 timeline 的数据源。

## 7. v2.4 unblock criteria

80%+ candidate coverage with:
- timeline_points_count >= 5
- 09:24 and 09:25 present
- data_status = real_auction_timeline
- 至少 20 个交易日

## 8. Daily collection script

见 `run_v2_4_fwd_daily_auction_collect.py`（生产环境用）

在 collection 环境配置好后：
```bash
python stock_processing_service/tests/contract/run_v2_4_fwd_daily_auction_collect.py
```

当前 v2.2c + v2.3 的管线会自动处理 feature 计算和 D2 scoring。
