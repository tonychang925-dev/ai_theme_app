# 弱转强系统扩展设计方案（含强势股持续跟踪观察池）

**版本**：v1.0  
**定位**：在现有“主线周期判断 + 盘后弱转强候选池 + 盘前竞价确认”基础上，新增“强势股持续跟踪观察池”层，形成更贴近实战的三层系统。  
**适用场景**：A 股短线主线题材、龙头/龙二/卡位股的分歧—修复—转强机会识别。  

---

## 1. 背景与核心问题

当前系统已经逐步形成两层能力：

1. **主线周期层**：判断题材是否仍活着，是否处于分歧、修复或退潮阶段。  
2. **弱转强候选层**：从个股层面筛出可能在次日发生弱转强的候选股。  

但实战中还存在一个关键缺口：

> 很多真正值得做的弱转强机会，不是当天临时扫出来的，而是前几天就已经进入视野、需要持续盯住的强势股。

也就是说，仅靠“当天静态筛选”不够，还需要一层“带记忆的观察池”，去持续跟踪过去 1 周内的：

- 2 连板
- 3 天 2 板
- 3/4 连板
- 龙头、龙二、卡位股
- 强趋势异动股
- 盘后复盘识别出的强势股/异动股

这一层的价值在于：

- 当主线判断尚不清晰时，可以通过龙头状态获得更直接的硬证据；
- 当题材板块分化剧烈时，可以避免把所有票一刀切为“退潮”；
- 当龙头不倒但跟风已死时，可以明确“只做龙头，不做杂毛”的策略；
- 当龙二或卡位股出现结构修复时，可以更早纳入弱转强跟踪；
- 当个股跌到关键支撑位时，可以更及时地从观察池提升到正式候选。

---

## 2. 设计目标

新增“强势股持续跟踪观察池”后，系统应形成以下三层结构：

### Layer 1：主线周期层
负责判断：
- 主线是否仍活着；
- 周期状态属于 start / fermentation / acceleration / divergence / repair / fade_watch / fade_confirmed 哪一类；
- 是否允许弱转强继续观察。

### Layer 2：强势股持续跟踪观察池
负责：
- 把过去 5~7 个交易日内有辨识度的强势股留在视野中；
- 每日更新标签、评分、状态；
- 决定保留、降级、剔除、或升级到正式弱转强候选池。

### Layer 3：弱转强触发层
负责：
- 对观察池及当日静态扫描的结果做正式候选判断；
- 在盘前竞价中完成最终确认；
- 输出 A/B/C/X 级信号。

---

## 3. 核心设计原则

### 3.1 不再只依赖“主线唯一判断”
主线判断非常重要，但不是唯一入口。  
当主线不明朗时，应允许从“龙头状态、梯队结构、个股技术位置”获得额外证据。

### 3.2 只跟踪“值得盯”的股票，而不是全市场
观察池只保留：
- 强势股
- 龙头/龙二/卡位股
- 异动趋势股
- 盘后复盘识别出的重点股

这样可以把弱转强判断建立在“高质量对象池”上，而不是在全市场平面扫描。

### 3.3 主线不清晰时，更要看龙头，而不是看杂毛
如果某天只有龙头还在连板，而板块跟风都不行：

- **不能直接判断主线已死**
- 更合理的做法是：
  - 盯紧龙头
  - 放弃跟风和杂毛
  - 如要参与，只做龙头或龙二/卡位股

### 3.4 观察池是“持续跟踪层”，不是“买入信号层”
进入观察池，不代表当天要买。  
观察池的意义是：
- 挂着盯
- 看是否跌到位
- 看是否还有主力
- 看是否出现回流和抢筹
- 等待真正的弱转强触发

---

## 4. 系统总架构

```text
盘后复盘结果
   ├─ 强势股
   ├─ 异动股
   ├─ 连板股 / 3天2板 / 龙头 / 龙二 / 卡位股
   ↓
强势股持续跟踪观察池（Layer 2）
   ↓ 每日更新标签/评分/状态
弱转强候选池（formal / observe_only）
   ↓
盘前竞价确认
   ↓
正式信号输出（A/B/C/X）
```

---

## 5. 观察池的入池来源

观察池不是单一来源，而应由多来源合并生成。

### 5.1 来源 A：盘后复盘功能
从每日“盘后复盘”模块中提取：

- 强势股
- 异动股
- 资金活跃股
- 结构完整股
- 有消息刺激的题材核心股

### 5.2 来源 B：板型触发
自动纳入：

- 2 连板
- 3 天 2 板
- 连续 3 板
- 连续 4 板

### 5.3 来源 C：梯队角色触发
自动纳入：

- 龙头
- 龙二
- 前排核心股
- 卡位候选股

### 5.4 来源 D：趋势异动触发
自动纳入：

- 近 5 日涨幅显著
- 最近 5 日出现涨停或强突破
- 换手率、量价结构、辨识度较高的强趋势股

---

## 6. 观察池核心标签体系

观察池的关键不是“存股票列表”，而是给股票持续打标签。

### 6.1 角色标签
- `is_dragon_head`
- `is_sub_dragon`
- `is_card_position_candidate`
- `is_front_row_core`
- `relay_role`：dragon / sub_dragon / follow_up / card_position_candidate / unknown

### 6.2 主线标签
- `is_main_theme_core`
- `theme_alive_level`
- `cycle_state`
- `fade_watch`
- `fade_confirmed`

### 6.3 强势背景标签
- `has_recent_limit_up`
- `limit_up_pattern`
- `recent_limit_up_count`
- `max_consecutive_limit_up_days`

### 6.4 技术结构标签
- `is_gap_support_candidate`
- `is_ma_support_candidate`
- `is_break_recover_candidate`
- `is_upper_shadow_repair_candidate`
- `is_bad_limit_repair_candidate`
- `is_strong_trend_repair`

### 6.5 资金与量价标签
- `turnover_state`
- `capital_flow_state`
- `volume_price_state`
- `main_force_still_inside`

### 6.6 观察标签
- `watch_window_days`
- `watch_status`
- `watch_priority`
- `watch_reason`

---

## 7. 数据库表设计

### 7.1 `strong_stock_watch_pool`
当前活跃观察池。

```sql
CREATE TABLE strong_stock_watch_pool (
    id BIGSERIAL PRIMARY KEY,
    trade_date DATE NOT NULL,
    stock_id VARCHAR(16) NOT NULL,
    stock_name VARCHAR(64) NOT NULL,
    subject_key VARCHAR(64),
    theme_name VARCHAR(128),

    watch_start_date DATE NOT NULL,
    watch_window_days INT NOT NULL DEFAULT 1,

    source_tag VARCHAR(32) NOT NULL,
    relay_role VARCHAR(32) DEFAULT 'unknown',
    watch_status VARCHAR(32) NOT NULL DEFAULT 'active',
    watch_priority NUMERIC(6,2) NOT NULL DEFAULT 0,
    watch_score NUMERIC(6,2) NOT NULL DEFAULT 0,

    pool_entry_type VARCHAR(16) DEFAULT 'observe_only',
    candidate_promoted BOOLEAN NOT NULL DEFAULT FALSE,

    labels_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    evidence_json JSONB NOT NULL DEFAULT '{}'::jsonb,

    created_at TIMESTAMP NOT NULL DEFAULT now(),
    updated_at TIMESTAMP NOT NULL DEFAULT now(),

    UNIQUE (trade_date, stock_id)
);
```

### 7.2 `strong_stock_watch_history`
历史跟踪轨迹表。

```sql
CREATE TABLE strong_stock_watch_history (
    id BIGSERIAL PRIMARY KEY,
    trade_date DATE NOT NULL,
    stock_id VARCHAR(16) NOT NULL,
    stock_name VARCHAR(64) NOT NULL,
    subject_key VARCHAR(64),
    theme_name VARCHAR(128),

    watch_status VARCHAR(32) NOT NULL,
    watch_score NUMERIC(6,2) NOT NULL DEFAULT 0,
    watch_priority NUMERIC(6,2) NOT NULL DEFAULT 0,

    relay_role VARCHAR(32) DEFAULT 'unknown',
    cycle_state VARCHAR(32),
    mainline_strength_score NUMERIC(6,2) DEFAULT 0,
    fade_watch BOOLEAN DEFAULT FALSE,
    fade_confirmed BOOLEAN DEFAULT FALSE,

    promoted_to_candidate BOOLEAN NOT NULL DEFAULT FALSE,
    removed_reason VARCHAR(128),

    labels_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    evidence_json JSONB NOT NULL DEFAULT '{}'::jsonb,

    created_at TIMESTAMP NOT NULL DEFAULT now()
);
```

---

## 8. StrongStockTrackingService 设计

新增服务：

`StrongStockTrackingService`

### 8.1 核心职责
- 从盘后复盘和板型筛选生成观察池初始对象
- 每日更新观察池股票的标签和状态
- 评估是否保留 / 升级 / 剔除
- 将符合条件的股票升级到弱转强候选池

### 8.2 核心方法

#### `seed_watch_pool(trade_date)`
作用：
- 从盘后复盘、2 连板、3 天 2 板、龙头/龙二、异动股中生成首批观察池

#### `refresh_watch_pool(trade_date)`
作用：
- 更新观察池股票：
  - 主线标签
  - 龙头角色
  - 支撑状态
  - K 线形态
  - 量价/换手/资金状态
- 更新 `watch_score / watch_priority / watch_status`

#### `promote_watch_candidates(trade_date)`
作用：
- 将观察池中满足条件的股票送入：
  - `weak_to_strong_candidate_pool.formal`
  - 或 `weak_to_strong_candidate_pool.observe_only`

#### `prune_watch_pool(trade_date)`
作用：
- 删除明显失效的观察池对象：
  - `fade_confirmed`
  - 龙头彻底死亡
  - 跌破关键支撑且无承接
  - 长时间未强化

---

## 9. 观察池评分模型（watch_score）

建议先做一个 100 分制跟踪分数。

### 9.1 强势背景分（25）
- 连板高度
- 3 天 2 板
- 龙头/龙二/前排地位
- 辨识度

### 9.2 主线存活分（20）
- `mainline_strength_score`
- 事件连续性
- 是否仍有持续催化

### 9.3 龙头关系分（20）
- 龙头未死
- 龙头仍在连板或高位承接
- 龙二是否跟随
- 是否有卡位机会

### 9.4 结构位置分（20）
- 是否靠近缺口 / 前低 / 均线 / 启动枢轴
- 是否属于“跌到位”
- K 线是否仍健康

### 9.5 量价资金分（15）
- 换手率
- 承接/缩量/放量结构
- 资金流向
- 主力是否仍在

---

## 10. 保留 / 升级 / 剔除逻辑

### 10.1 保留
满足：
- `watch_score >= 55`
- 且未出现硬性死亡信号

### 10.2 升级为正式弱转强候选
满足：
- `watch_score >= 70`
- `mainline_alive = true`
- `fade_confirmed = false`
- `support_score >= 阈值`
- 个股处于分歧 / 修复窗口
- 龙头未死或具备卡位机会

### 10.3 剔除
满足任一：
- `fade_confirmed = true`
- 龙头彻底死亡，且无接力
- 个股跌破关键支撑且无承接
- 资金连续流出
- 观察窗口超时且未再强化

---

## 11. “只做龙头，不做杂毛”如何程序化

这一点非常重要。

程序上必须把“角色关系”写出来，而不是只看题材或涨跌幅。

### 11.1 角色定义
- `dragon`：当前主线最核心、最有辨识度的龙头
- `sub_dragon`：最强龙二
- `follow_up`：普通跟风
- `card_position_candidate`：潜在卡位者
- `unknown`

### 11.2 实战逻辑映射
如果出现：

- 板块内只有龙头还在连板
- 跟风股都不行
- 板块主线状态不够明朗

则程序不应直接判“主线已死”。  
正确动作是：

- 降低跟风/杂毛权重
- 继续保留龙头为 `active`
- 若龙二结构尚可，也可保留 `observe_only`
- 严格限制普通跟风股进入 formal candidate

---

## 12. 与现有弱转强候选池的衔接

观察池不是替代 CandidateBuilder，而是作为其上游之一。

### 候选来源 = 两部分合并

#### 来源 1：当日静态扫描
继续使用现有 CandidateBuilder 的静态扫描逻辑。

#### 来源 2：观察池升级
从 `strong_stock_watch_pool` 中筛选：

- `watch_status = active`
- `watch_score >= 阈值`
- `fade_confirmed = false`
- `support_score` 达标
- 龙头未死 / 卡位机会存在

将其送入：
- `formal`
- 或 `observe_only`

这样弱转强候选池就不再只依赖“当天新扫出的股票”，而是会继承过去 1 周持续跟踪的高质量强势股。

---

## 13. 与盘后复盘功能的衔接

这是本次扩展里最值得立即落地的部分。

### 13.1 盘后复盘结果作为观察池输入
将盘后复盘模块产出的：
- 强势股
- 异动股
- 龙头股
- 主线核心股
- 有事件刺激股

直接写入 `strong_stock_watch_pool`。

### 13.2 形成“复盘 → 跟踪 → 候选 → 确认”闭环
```text
盘后复盘
  ↓
强势股/异动股观察池
  ↓
每日刷新标签与 watch_score
  ↓
满足条件时升级为弱转强候选
  ↓
盘前竞价确认
  ↓
正式信号
```

---

## 14. 最小实施路径

### P1.5：新增观察池层
#### 表
- `strong_stock_watch_pool`
- `strong_stock_watch_history`

#### 服务
- `StrongStockTrackingService`

#### 方法
- `seed_watch_pool()`
- `refresh_watch_pool()`
- `promote_watch_candidates()`
- `prune_watch_pool()`

---

## 15. 推荐实施顺序

### 第一步
先建表，并让“盘后复盘”结果能入观察池。

### 第二步
实现标签和 watch_score 计算，先不接盘前竞价。

### 第三步
实现升级逻辑，把观察池合并进现有 CandidateBuilder。

### 第四步
再做盘前确认层的联动过滤：
- `formal` 才允许出正式 A/B
- `observe_only` 只跟踪，不出正式 A/B

---

## 16. 一句话总结

现有系统已经有：

- 主线周期判断
- 弱转强候选池
- 盘前竞价确认

但还缺少一层关键能力：

> **历史强势股持续跟踪观察池**

这层的本质不是“多加一个表”，而是让系统具备记忆能力。  
它能把盘后复盘发现的强势股、异动股、龙头/龙二/卡位股持续挂在视野中，结合：

- 主线是否仍有消息刺激
- 龙头是否倒下
- 板块是否还有接力
- 个股资金/换手/结构是否健康
- 是否跌到关键支撑位

从而更早、更稳地捕捉弱转强机会。

---


---

## 附录 A：观察池建表 SQL

```sql
-- 强势股持续跟踪观察池 - 建表 SQL
-- 版本: v1.0

CREATE TABLE IF NOT EXISTS strong_stock_watch_pool (
    id BIGSERIAL PRIMARY KEY,
    trade_date DATE NOT NULL,
    stock_id VARCHAR(16) NOT NULL,
    stock_name VARCHAR(64) NOT NULL,
    subject_key VARCHAR(64),
    theme_name VARCHAR(128),

    watch_start_date DATE NOT NULL,
    watch_window_days INT NOT NULL DEFAULT 1,

    source_tag VARCHAR(32) NOT NULL,
    relay_role VARCHAR(32) NOT NULL DEFAULT 'unknown',
    watch_status VARCHAR(32) NOT NULL DEFAULT 'active',
    watch_priority NUMERIC(6,2) NOT NULL DEFAULT 0,
    watch_score NUMERIC(6,2) NOT NULL DEFAULT 0,

    pool_entry_type VARCHAR(16) NOT NULL DEFAULT 'observe_only',
    candidate_promoted BOOLEAN NOT NULL DEFAULT FALSE,

    cycle_state VARCHAR(32),
    mainline_strength_score NUMERIC(6,2) DEFAULT 0,
    fade_watch BOOLEAN DEFAULT FALSE,
    fade_confirmed BOOLEAN DEFAULT FALSE,

    support_type VARCHAR(32),
    support_level NUMERIC(12,3),
    support_score NUMERIC(6,2) DEFAULT 0,

    labels_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    evidence_json JSONB NOT NULL DEFAULT '{}'::jsonb,

    created_at TIMESTAMP NOT NULL DEFAULT now(),
    updated_at TIMESTAMP NOT NULL DEFAULT now(),

    UNIQUE (trade_date, stock_id)
);

CREATE INDEX IF NOT EXISTS idx_strong_stock_watch_pool_trade_date
    ON strong_stock_watch_pool (trade_date);

CREATE INDEX IF NOT EXISTS idx_strong_stock_watch_pool_status
    ON strong_stock_watch_pool (trade_date, watch_status);

CREATE INDEX IF NOT EXISTS idx_strong_stock_watch_pool_score
    ON strong_stock_watch_pool (trade_date, watch_score DESC);

CREATE INDEX IF NOT EXISTS idx_strong_stock_watch_pool_theme
    ON strong_stock_watch_pool (trade_date, subject_key);

CREATE INDEX IF NOT EXISTS idx_strong_stock_watch_pool_promoted
    ON strong_stock_watch_pool (trade_date, candidate_promoted);


CREATE TABLE IF NOT EXISTS strong_stock_watch_history (
    id BIGSERIAL PRIMARY KEY,
    trade_date DATE NOT NULL,
    stock_id VARCHAR(16) NOT NULL,
    stock_name VARCHAR(64) NOT NULL,
    subject_key VARCHAR(64),
    theme_name VARCHAR(128),

    watch_status VARCHAR(32) NOT NULL,
    watch_score NUMERIC(6,2) NOT NULL DEFAULT 0,
    watch_priority NUMERIC(6,2) NOT NULL DEFAULT 0,

    relay_role VARCHAR(32) NOT NULL DEFAULT 'unknown',
    cycle_state VARCHAR(32),
    mainline_strength_score NUMERIC(6,2) DEFAULT 0,
    fade_watch BOOLEAN DEFAULT FALSE,
    fade_confirmed BOOLEAN DEFAULT FALSE,

    pool_entry_type VARCHAR(16) DEFAULT 'observe_only',
    promoted_to_candidate BOOLEAN NOT NULL DEFAULT FALSE,
    removed_reason VARCHAR(128),

    support_type VARCHAR(32),
    support_level NUMERIC(12,3),
    support_score NUMERIC(6,2) DEFAULT 0,

    labels_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    evidence_json JSONB NOT NULL DEFAULT '{}'::jsonb,

    created_at TIMESTAMP NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_strong_stock_watch_history_trade_date
    ON strong_stock_watch_history (trade_date);

CREATE INDEX IF NOT EXISTS idx_strong_stock_watch_history_stock
    ON strong_stock_watch_history (stock_id, trade_date DESC);

CREATE INDEX IF NOT EXISTS idx_strong_stock_watch_history_theme
    ON strong_stock_watch_history (subject_key, trade_date DESC);


-- 可选：观察池状态枚举约束（根据现有数据库规范酌情开启）
-- ALTER TABLE strong_stock_watch_pool
--     ADD CONSTRAINT chk_watch_status
--     CHECK (watch_status IN ('active', 'weakening', 'removed', 'promoted_to_candidate'));
--
-- ALTER TABLE strong_stock_watch_pool
--     ADD CONSTRAINT chk_pool_entry_type
--     CHECK (pool_entry_type IN ('formal', 'observe_only', 'reject'));

```

---

## 附录 B：StrongStockTrackingService Python 骨架

```python
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date
from typing import Any, Dict, List, Optional

import asyncpg

from stock_service.config import StockServiceConfig


@dataclass
class WatchSeedRow:
    stock_id: str
    stock_name: str
    subject_key: str
    theme_name: str
    source_tag: str
    relay_role: str
    labels: Dict[str, Any]
    evidence: Dict[str, Any]


@dataclass
class WatchScoreResult:
    watch_score: float
    watch_priority: float
    watch_status: str
    pool_entry_type: str
    cycle_state: str
    mainline_strength_score: float
    fade_watch: bool
    fade_confirmed: bool
    support_type: Optional[str]
    support_level: Optional[float]
    support_score: float
    labels: Dict[str, Any]
    evidence: Dict[str, Any]


class StrongStockTrackingService:
    """
    强势股持续跟踪观察池服务。

    职责：
    1. 从盘后复盘 / 连板结构 / 强势异动中生成观察池
    2. 每日更新标签、watch_score、watch_status
    3. 将符合条件的对象升级到弱转强候选池
    4. 维护观察池历史轨迹
    """

    RULE_VERSION = "strong_stock_watch.v1"

    def __init__(self, config: Optional[StockServiceConfig] = None):
        self.config = config or StockServiceConfig()
        self.pool: Optional[asyncpg.Pool] = None

    async def _ensure_pool(self) -> asyncpg.Pool:
        if self.pool is None:
            self.pool = await asyncpg.create_pool(
                host=self.config.postgres_host,
                port=self.config.postgres_port,
                database=self.config.postgres_database,
                user=self.config.postgres_user,
                password=self.config.postgres_password,
                min_size=1,
                max_size=4,
            )
        return self.pool

    async def close(self) -> None:
        if self.pool is not None:
            await self.pool.close()
            self.pool = None

    async def seed_watch_pool(self, trade_date: date) -> int:
        """
        生成观察池初始对象。

        当前建议来源：
        - 盘后复盘强势股/异动股
        - 2连板 / 3天2板 / 3-4连板
        - 龙头 / 龙二 / 前排核心
        """
        pool = await self._ensure_pool()
        rows = await self._fetch_seed_rows(trade_date)
        inserted = 0

        async with pool.acquire() as conn:
            async with conn.transaction():
                for row in rows:
                    inserted += await self._upsert_watch_pool_seed(conn, trade_date, row)
                    await self._append_watch_history(conn, trade_date, row, None)
        return inserted

    async def refresh_watch_pool(self, trade_date: date) -> int:
        """
        更新观察池中全部 active/weakening 对象的标签与评分。
        """
        pool = await self._ensure_pool()
        current_rows = await self._fetch_active_watch_pool(trade_date)
        updated = 0

        async with pool.acquire() as conn:
            async with conn.transaction():
                for row in current_rows:
                    result = await self._score_watch_row(conn, trade_date, row)
                    await self._update_watch_pool_row(conn, trade_date, row, result)
                    await self._append_watch_history(conn, trade_date, row, result)
                    updated += 1
        return updated

    async def promote_watch_candidates(self, trade_date: date) -> int:
        """
        从观察池中筛选符合条件的对象，升级进入弱转强候选池。

        这里建议后续与 WeakToStrongCandidateBuilder 做合流，当前骨架只返回数量。
        """
        pool = await self._ensure_pool()
        sql = """
        SELECT *
        FROM strong_stock_watch_pool
        WHERE trade_date = $1::date
          AND watch_status = 'active'
          AND pool_entry_type IN ('formal', 'observe_only')
          AND fade_confirmed = FALSE
          AND candidate_promoted = FALSE
        ORDER BY watch_score DESC, watch_priority DESC
        """
        async with pool.acquire() as conn:
            rows = await conn.fetch(sql, trade_date)
            # TODO: 在这里与弱转强候选池合流，升级到 formal/observe_only candidate
            # 当前先打标
            for row in rows:
                await conn.execute(
                    """
                    UPDATE strong_stock_watch_pool
                    SET candidate_promoted = TRUE,
                        updated_at = now()
                    WHERE trade_date = $1::date AND stock_id = $2
                    """,
                    trade_date,
                    row["stock_id"],
                )
        return len(rows)

    async def prune_watch_pool(self, trade_date: date) -> int:
        """
        剔除明显失效对象。
        """
        pool = await self._ensure_pool()
        sql = """
        UPDATE strong_stock_watch_pool
        SET watch_status = 'removed',
            updated_at = now()
        WHERE trade_date = $1::date
          AND (
                fade_confirmed = TRUE
                OR watch_score < 35
              )
        """
        async with pool.acquire() as conn:
            result = await conn.execute(sql, trade_date)
        return int(result.split()[-1])

    async def _fetch_seed_rows(self, trade_date: date) -> List[WatchSeedRow]:
        """
        最小版本：从 subject_stock_daily_snapshot 中拉种子。
        后续可并入“盘后复盘”结果表。
        """
        pool = await self._ensure_pool()
        sql = """
        WITH limit_up_stats AS (
            SELECT
                stock_id,
                stock_name,
                subject_key,
                COALESCE(theme_name, subject_key) AS theme_name,
                COUNT(*) FILTER (WHERE COALESCE(limit_up, FALSE)) AS recent_limit_up_count,
                MAX(CASE WHEN COALESCE(is_leader, FALSE) THEN 1 ELSE 0 END) AS is_leader_flag,
                MIN(COALESCE(rank_order, 999)) AS best_rank
            FROM subject_stock_daily_snapshot
            WHERE trade_date <= $1::date
              AND trade_date >= ($1::date - INTERVAL '7 days')
            GROUP BY stock_id, stock_name, subject_key, COALESCE(theme_name, subject_key)
        )
        SELECT *
        FROM limit_up_stats
        WHERE recent_limit_up_count >= 2
           OR is_leader_flag = 1
           OR best_rank <= 3
        ORDER BY recent_limit_up_count DESC, is_leader_flag DESC, best_rank ASC
        """
        async with pool.acquire() as conn:
            rows = await conn.fetch(sql, trade_date)

        result: List[WatchSeedRow] = []
        for row in rows:
            recent_limit_up_count = int(row["recent_limit_up_count"] or 0)
            is_leader = bool(row["is_leader_flag"] or 0)
            best_rank = int(row["best_rank"] or 999)

            if recent_limit_up_count >= 4:
                source_tag = "4_limit_up"
            elif recent_limit_up_count >= 3:
                source_tag = "3_limit_up"
            elif recent_limit_up_count >= 2:
                source_tag = "2_limit_up"
            else:
                source_tag = "review_strong_stock"

            if is_leader:
                relay_role = "dragon"
            elif best_rank <= 3:
                relay_role = "sub_dragon"
            else:
                relay_role = "unknown"

            labels = {
                "has_recent_limit_up": recent_limit_up_count > 0,
                "recent_limit_up_count": recent_limit_up_count,
                "is_dragon_head": is_leader,
                "is_front_row_core": best_rank <= 3,
                "watch_window_days": 7,
            }
            evidence = {
                "schema_version": "watch_evidence.v1",
                "seed_reason": {
                    "recent_limit_up_count": recent_limit_up_count,
                    "is_leader": is_leader,
                    "best_rank": best_rank,
                },
            }
            result.append(
                WatchSeedRow(
                    stock_id=row["stock_id"],
                    stock_name=row["stock_name"],
                    subject_key=row["subject_key"],
                    theme_name=row["theme_name"],
                    source_tag=source_tag,
                    relay_role=relay_role,
                    labels=labels,
                    evidence=evidence,
                )
            )
        return result

    async def _fetch_active_watch_pool(self, trade_date: date) -> List[asyncpg.Record]:
        pool = await self._ensure_pool()
        sql = """
        SELECT *
        FROM strong_stock_watch_pool
        WHERE trade_date = $1::date
          AND watch_status IN ('active', 'weakening')
        ORDER BY watch_score DESC, watch_priority DESC
        """
        async with pool.acquire() as conn:
            return await conn.fetch(sql, trade_date)

    async def _score_watch_row(
        self,
        conn: asyncpg.Connection,
        trade_date: date,
        row: asyncpg.Record,
    ) -> WatchScoreResult:
        """
        观察池评分骨架：
        - 强势背景分 25
        - 主线存活分 20
        - 龙头关系分 20
        - 结构位置分 20
        - 量价资金分 15
        """
        stock_id = row["stock_id"]
        subject_key = row["subject_key"]

        cycle = await conn.fetchrow(
            """
            SELECT final_cycle_state, final_mainline_alive, fade_watch, fade_confirmed,
                   mainline_strength_score
            FROM theme_cycle_judgement_v2
            WHERE trade_date = $1::date AND subject_key = $2
            """,
            trade_date,
            subject_key,
        )

        strong_background_score = 0.0
        labels = dict(row["labels_json"] or {})
        recent_limit_up_count = int(labels.get("recent_limit_up_count", 0) or 0)
        if recent_limit_up_count >= 4:
            strong_background_score += 25
        elif recent_limit_up_count >= 3:
            strong_background_score += 20
        elif recent_limit_up_count >= 2:
            strong_background_score += 15
        if labels.get("is_dragon_head"):
            strong_background_score = max(strong_background_score, 22)
        elif labels.get("is_front_row_core"):
            strong_background_score = max(strong_background_score, 16)

        mainline_strength_score = float(cycle["mainline_strength_score"] or 0.0) if cycle else 0.0
        theme_alive_score = min(mainline_strength_score * 0.20, 20.0)

        relay_role = row["relay_role"]
        relay_score = 0.0
        if relay_role == "dragon":
            relay_score = 20.0
        elif relay_role == "sub_dragon":
            relay_score = 15.0
        elif relay_role == "card_position_candidate":
            relay_score = 12.0

        # 结构位置分：当前先占位，后续接 support scorer / kline scorer
        structure_score = 12.0

        # 量价资金分：当前先占位，后续接 turnover/capital flow 模块
        money_flow_score = 8.0

        watch_score = round(
            strong_background_score + theme_alive_score + relay_score + structure_score + money_flow_score,
            2,
        )
        watch_priority = round(watch_score + (5 if relay_role == "dragon" else 0), 2)

        fade_watch = bool(cycle["fade_watch"] or False) if cycle else False
        fade_confirmed = bool(cycle["fade_confirmed"] or False) if cycle else False
        cycle_state = str(cycle["final_cycle_state"] or "") if cycle else ""

        if fade_confirmed:
            watch_status = "removed"
        elif watch_score >= 55:
            watch_status = "active"
        else:
            watch_status = "weakening"

        if fade_confirmed:
            pool_entry_type = "reject"
        elif watch_score >= 70 and mainline_strength_score >= 60:
            pool_entry_type = "formal"
        elif watch_score >= 55:
            pool_entry_type = "observe_only"
        else:
            pool_entry_type = "reject"

        evidence = {
            "schema_version": "watch_evidence.v1",
            "watch_score_breakdown": {
                "strong_background_score": strong_background_score,
                "theme_alive_score": theme_alive_score,
                "relay_score": relay_score,
                "structure_score": structure_score,
                "money_flow_score": money_flow_score,
            },
            "cycle_state": cycle_state,
            "mainline_strength_score": mainline_strength_score,
        }

        labels.update(
            {
                "cycle_state": cycle_state,
                "fade_watch": fade_watch,
                "fade_confirmed": fade_confirmed,
            }
        )

        return WatchScoreResult(
            watch_score=watch_score,
            watch_priority=watch_priority,
            watch_status=watch_status,
            pool_entry_type=pool_entry_type,
            cycle_state=cycle_state,
            mainline_strength_score=mainline_strength_score,
            fade_watch=fade_watch,
            fade_confirmed=fade_confirmed,
            support_type=None,
            support_level=None,
            support_score=0.0,
            labels=labels,
            evidence=evidence,
        )

    async def _upsert_watch_pool_seed(
        self,
        conn: asyncpg.Connection,
        trade_date: date,
        row: WatchSeedRow,
    ) -> int:
        sql = """
        INSERT INTO strong_stock_watch_pool (
            trade_date, stock_id, stock_name, subject_key, theme_name,
            watch_start_date, watch_window_days,
            source_tag, relay_role, watch_status,
            watch_priority, watch_score,
            pool_entry_type, candidate_promoted,
            labels_json, evidence_json,
            created_at, updated_at
        ) VALUES (
            $1, $2, $3, $4, $5,
            $6, $7,
            $8, $9, 'active',
            0, 0,
            'observe_only', FALSE,
            $10::jsonb, $11::jsonb,
            now(), now()
        )
        ON CONFLICT (trade_date, stock_id) DO UPDATE SET
            stock_name = EXCLUDED.stock_name,
            subject_key = EXCLUDED.subject_key,
            theme_name = EXCLUDED.theme_name,
            source_tag = EXCLUDED.source_tag,
            relay_role = EXCLUDED.relay_role,
            labels_json = EXCLUDED.labels_json,
            evidence_json = EXCLUDED.evidence_json,
            updated_at = now()
        """
        await conn.execute(
            sql,
            trade_date,
            row.stock_id,
            row.stock_name,
            row.subject_key,
            row.theme_name,
            trade_date,
            int(row.labels.get("watch_window_days", 7)),
            row.source_tag,
            row.relay_role,
            json.dumps(row.labels, ensure_ascii=False),
            json.dumps(row.evidence, ensure_ascii=False),
        )
        return 1

    async def _update_watch_pool_row(
        self,
        conn: asyncpg.Connection,
        trade_date: date,
        row: asyncpg.Record,
        result: WatchScoreResult,
    ) -> None:
        sql = """
        UPDATE strong_stock_watch_pool
        SET watch_window_days = GREATEST(watch_window_days, (trade_date - watch_start_date) + 1),
            watch_status = $3,
            watch_priority = $4,
            watch_score = $5,
            pool_entry_type = $6,
            cycle_state = $7,
            mainline_strength_score = $8,
            fade_watch = $9,
            fade_confirmed = $10,
            support_type = $11,
            support_level = $12,
            support_score = $13,
            labels_json = $14::jsonb,
            evidence_json = $15::jsonb,
            updated_at = now()
        WHERE trade_date = $1::date
          AND stock_id = $2
        """
        await conn.execute(
            sql,
            trade_date,
            row["stock_id"],
            result.watch_status,
            result.watch_priority,
            result.watch_score,
            result.pool_entry_type,
            result.cycle_state,
            result.mainline_strength_score,
            result.fade_watch,
            result.fade_confirmed,
            result.support_type,
            result.support_level,
            result.support_score,
            json.dumps(result.labels, ensure_ascii=False),
            json.dumps(result.evidence, ensure_ascii=False),
        )

    async def _append_watch_history(
        self,
        conn: asyncpg.Connection,
        trade_date: date,
        row: Any,
        result: Optional[WatchScoreResult],
    ) -> None:
        if isinstance(row, WatchSeedRow):
            stock_id = row.stock_id
            stock_name = row.stock_name
            subject_key = row.subject_key
            theme_name = row.theme_name
            relay_role = row.relay_role
            labels = row.labels
            evidence = row.evidence
            watch_status = "active"
            watch_score = 0.0
            watch_priority = 0.0
            pool_entry_type = "observe_only"
            cycle_state = ""
            mainline_strength_score = 0.0
            fade_watch = False
            fade_confirmed = False
            support_type = None
            support_level = None
            support_score = 0.0
            promoted_to_candidate = False
            removed_reason = None
        else:
            stock_id = row["stock_id"]
            stock_name = row["stock_name"]
            subject_key = row["subject_key"]
            theme_name = row["theme_name"]
            relay_role = row["relay_role"]
            labels = result.labels if result else dict(row["labels_json"] or {})
            evidence = result.evidence if result else dict(row["evidence_json"] or {})
            watch_status = result.watch_status if result else row["watch_status"]
            watch_score = result.watch_score if result else float(row["watch_score"] or 0.0)
            watch_priority = result.watch_priority if result else float(row["watch_priority"] or 0.0)
            pool_entry_type = result.pool_entry_type if result else row["pool_entry_type"]
            cycle_state = result.cycle_state if result else (row["cycle_state"] or "")
            mainline_strength_score = result.mainline_strength_score if result else float(row.get("mainline_strength_score") or 0.0)
            fade_watch = result.fade_watch if result else bool(row.get("fade_watch") or False)
            fade_confirmed = result.fade_confirmed if result else bool(row.get("fade_confirmed") or False)
            support_type = result.support_type if result else row.get("support_type")
            support_level = result.support_level if result else row.get("support_level")
            support_score = result.support_score if result else float(row.get("support_score") or 0.0)
            promoted_to_candidate = bool(row.get("candidate_promoted") or False)
            removed_reason = "fade_confirmed" if fade_confirmed else None

        sql = """
        INSERT INTO strong_stock_watch_history (
            trade_date, stock_id, stock_name, subject_key, theme_name,
            watch_status, watch_score, watch_priority,
            relay_role, cycle_state, mainline_strength_score, fade_watch, fade_confirmed,
            pool_entry_type, promoted_to_candidate, removed_reason,
            support_type, support_level, support_score,
            labels_json, evidence_json,
            created_at
        ) VALUES (
            $1, $2, $3, $4, $5,
            $6, $7, $8,
            $9, $10, $11, $12, $13,
            $14, $15, $16,
            $17, $18, $19,
            $20::jsonb, $21::jsonb,
            now()
        )
        """
        await conn.execute(
            sql,
            trade_date,
            stock_id,
            stock_name,
            subject_key,
            theme_name,
            watch_status,
            watch_score,
            watch_priority,
            relay_role,
            cycle_state,
            mainline_strength_score,
            fade_watch,
            fade_confirmed,
            pool_entry_type,
            promoted_to_candidate,
            removed_reason,
            support_type,
            support_level,
            support_score,
            json.dumps(labels, ensure_ascii=False),
            json.dumps(evidence, ensure_ascii=False),
        )

```
