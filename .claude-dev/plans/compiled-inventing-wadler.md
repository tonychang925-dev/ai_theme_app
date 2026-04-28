# Plan: 新链 Layer A 增强版复刻 + 对比测试

## Context

在 `stock_processing_service` (新链) 架构基础上，完整复刻旧链 `EnhancedMainlineJudgementService` + `MainlineJudgementService` 的 Layer A 算法逻辑。复刻后的算法以 JSON 文件输出中间数据，完成后与 4/7、4/15 旧链 `theme_mainline_judgement` 表输出做对比测试。

**约束：**
- 不能影响旧链业务逻辑
- 不允许修改数据库，不能破坏数据库真源
- 所有中间数据以 JSON 文件写入 `tmp/layer_a/` 目录
- 只复刻算法逻辑，不写数据库
- 数据读取统一经新链 StockReadPort 方法（仅用现有 3 个方法，不新增）

**核心发现（来自代码审查）：**
- `EnhancedMainlineJudgementService` 继承 `MainlineJudgementService`，其 `build_enhanced_judgement()` 调用 `super().build_judgement()`，必须同时复刻父子类
- 6 增强维度（novelty/timing/influence/capital_persistence/institution/retail）在旧链中均为 DB schema 预留字段，所有计算逻辑为空，复刻时保持一致（默认 0.0）
- 两个 K 线占位方法（`_estimate_theme_return_3d`、`_compute_theme_support_score`）在旧链中就是硬编码 TODO，复刻时保持一致

## 新增文件

### 1. `stock_processing_service/domain/services/enhanced_mainline_judgement_service.py`

纯算法复刻，零外部依赖（无 asyncpg、无 SQL、无数据库访问）。包含：

- `ThemeEventStats` dataclass（从旧链原样复制）
- `ThemeMarketStats` dataclass（从旧链原样复制）
- `KEY_EVENT_KEYWORDS` 常量
- `_clip()` 工具函数
- `MainlineJudgementService` 类（父类，185 行）：
  - `compute_event_chain_score()` — 事件链评分
  - `compute_event_chain_continuity_score()` — 事件连续性评分
  - `compute_market_recognition_score()` — 市场承认评分
  - `compute_mainline_stability_score()` — 主线稳定性评分
  - `classify_theme_tier()` — 三档主线分类（main/strong_branch/failed）
  - `build_evidence_logic()` / `build_evidence_market()` — 证据文本构建
  - `build_judgement()` — 基础判定主入口
  - `count_key_events()` — 关键事件关键词匹配（staticmethod）
- `ThemeEvidenceLayers` dataclass（四层证据）
- `EnhancedMainlineInputs` dataclass
- `EnhancedMainlineJudgementService` 类（子类，262 行）：
  - `compute_evidence_layers()` — 四层证据计算
  - `compute_mainline_strength_score()` — 主线强度评分（0-100）
  - `determine_mainline_alive()` — 主线存活判定
  - `build_enhanced_judgement()` — 增强判定主入口
  - 7 个辅助方法（`_estimate_event_count_3d` 等）
- `build_mainline_judgement()` — 兼容性包装函数
- `ThemeMainlineJudgement` dataclass（从旧链 models.py 84-93 行原样复制）

**复刻策略：逐行 1:1 复制旧链逻辑，不优化、不重构。** 仅做以下适配：
- 导入路径改为新链包路径（无跨链依赖）
- `ThemeMainlineJudgement` 在文件内定义（避免跨链依赖旧链 models.py）

### 2. `stock_processing_service/tests/replay/_layer_a_replay_runner.py`

数据获取 + 适配 + 执行 + 对比输出。复用 `_ReplayDatabaseStockFacade` 适配器模式（从 `_post_market_replay_runner.py` 第 56-185 行）。

模块组成：
- `_ReplayDatabaseStockFacade` — 复用已有实现，适配 DatabaseGateway 到 StockReadPort
- `_build_theme_event_stats()` — 从 `SubjectContextDTO.metadata` 构造 `ThemeEventStats`
- `_build_theme_market_stats()` — 从 `StockBarDTO` + `SubjectStockPoolDTO` 分组计算 `ThemeMarketStats`
- `_compute_diagnostics()` — 为每个 subject_key 标注数据来源质量
- `run_layer_a_replay(trade_date, sample_name)` — 主编排函数
- `run_layer_a_compare(trade_date, sample_name)` — 对比函数（读旧链 DB → 对账 → 生成 diff.json）
- `--mode {replay,compare}` CLI 入口

## 数据适配策略

### ThemeEventStats 映射（从 SubjectContextDTO.metadata）

| ThemeEventStats 字段 | 优先映射 | 回退策略 |
|---------------------|---------|---------|
| `subject_key` | `SubjectContextDTO.subject_key` | `SubjectStockPoolDTO.subject_key` |
| `theme_name` | `SubjectContextDTO.subject_name` | `SubjectStockPoolDTO.subject_name` |
| `today_event_count` | `metadata.get("today_event_count")` | 0 |
| `recent_event_count` | `metadata.get("event_count_7d")` | `metadata.get("recent_event_count", 0)` |
| `distinct_event_days` | `metadata.get("distinct_event_days")` | `min(metadata.get("event_recency_days", 0), 7)` |
| `key_event_count` | `metadata.get("key_event_count")` | `count_key_events(sample_summaries)` |
| `sample_summaries` | `metadata.get("sample_summaries")` | `[theme_event_summary]` if non-empty, else `[]` |

**诊断标注**：每个 subject_key 输出 `diagnostics.event_stats_source`：
- `"metadata"` — 所有字段来自 metadata
- `"approximated"` — 部分字段使用回退策略
- `"empty"` — 无 metadata，全部默认值

**注意**：`SubjectContextDTO.metadata` 实际字段取决于 `StockReadGatewayAdapter` 的查询。`BuildIdentityJob` 已确认使用 `strong_event_count_7d`、`event_count_3d`、`event_recency_days` 等字段。对于 metadata 中不存在的字段，runner 使用保守默认值并在 diagnostics 中标注缺失字段列表。

### ThemeMarketStats 映射（从 StockBarDTO + SubjectStockPoolDTO 分组计算）

| ThemeMarketStats 字段 | 计算方式 |
|----------------------|---------|
| `subject_key` | 分组 key |
| `theme_name` | pool_rows[0].subject_name |
| `limit_up_count` | `bar.close_price >= bar.limit_up_price` 的个股数（Decimal 比较需量化处理） |
| `strong_stock_count` | `float(bar.pct_chg) >= 5.0` 的个股数 |
| `leader_pct_chg` | pool_rank=1 个股的 `float(bar.pct_chg)`，若无 bar 则取 max pct_chg |
| `member_count` | pool_rows 总数 |
| `leader_limit_up` | leader 的 `close_price >= limit_up_price` |

**诊断标注**：`diagnostics.market_stats_source`：
- `"bars_grouped"` — 所有字段从 StockBarDTO 成功计算
- `"partial"` — 部分个股缺 bar 数据（leader 需回退）

## 协议兼容性约束

仅使用 `StockReadPort` / `DatabaseGatewayStockFacade` Protocol 的 3 个**现有**读取方法。不新增任何方法签名。

| 方法 | 返回类型 | 用途 |
|------|---------|------|
| `get_subject_stock_pool_by_trade_date(trade_date)` | `list[SubjectStockPoolDTO]` | 获取 subject_key、pool_rank（推断 leader）、member_count |
| `get_subject_context_by_subject_keys(subject_keys, trade_date)` | `list[SubjectContextDTO]` | 获取 metadata 构造 ThemeEventStats |
| `get_stock_daily_bars(trade_date)` | `list[StockBarDTO]` | 分组计算 ThemeMarketStats（涨停数、强势股数、leader_pct_chg、leader_limit_up） |

数据读取在 **runner 层**完成适配，算法层（`enhanced_mainline_judgement_service.py`）只接收 `ThemeEventStats` + `ThemeMarketStats` 纯数据对象，零外部依赖。

## JSON 文件管理规范

### 目录结构
```
tmp/layer_a/
├── 2026-04-07_baseline/
│   ├── replay.json          # 新链复刻输出
│   ├── old_chain.json        # 旧链 theme_mainline_judgement 表 dump（对比模式）
│   └── diff.json             # 差异报告
├── 2026-04-15_baseline/
│   ├── replay.json
│   ├── old_chain.json
│   └── diff.json
```

### 命名规则
- 目录名：`{trade_date}_{sample_name}`
- 回放输出：`replay.json`
- 旧链基线：`old_chain.json`
- 差异报告：`diff.json`

### replay.json 结构
```json
{
  "meta": {
    "trade_date": "2026-04-07",
    "sample_name": "baseline",
    "generated_at": "2026-04-27T...",
    "subject_count": 668,
    "with_event_stats": 520,
    "with_market_stats": 668
  },
  "results": [
    {
      "subject_key": "9064088",
      "theme_name": "商业航天",
      "base_judgement": { "...ThemeMainlineJudgement 全字段..." },
      "enhanced_judgement": { "...含 evidence_layers + mainline_strength_score + mainline_alive..." },
      "diagnostics": {
        "event_stats_source": "metadata",
        "market_stats_source": "bars_grouped",
        "missing_metadata_fields": [],
        "data_quality": "full"
      }
    }
  ]
}
```

每个 subject_key 带 `diagnostics` 标注数据来源质量，差异分析时直接定位根因（数据源缺失 vs 算法差异）。

## 对比测试方案

### 判定标准
- **exact**：评分字段小数点后 2 位一致，布尔字段一致，tier 分类一致
- **approx**：评分差异 ≤ 5.0（预期根因：旧链直读 news_event 表，新链经 metadata 近似映射），tier 分类一致
- **mismatch**：评分差异 > 5.0 或 tier 分类不同（需逐字段分析根因）

### 对比字段
`event_chain_score`, `event_chain_continuity_score`, `market_recognition_score`, `mainline_stability_score`, `is_main_theme`, `theme_tier`, `mainline_strength_score`, `mainline_alive`

### diff.json 结构（自动生成）
```json
{
  "meta": { "...same as replay..." },
  "summary": {
    "total_subjects": 668,
    "matched_in_old_chain": 520,
    "exact_match": 380,
    "approx_match": 105,
    "mismatch": 35,
    "only_in_new": 148,
    "only_in_old": 0
  },
  "field_stats": {
    "theme_tier": { "exact": 450, "approx": 0, "mismatch": 70 },
    "is_main_theme": { "exact": 480, "approx": 0, "mismatch": 40 },
    "event_chain_score": { "exact": 380, "approx": 110, "mismatch": 30 }
  },
  "mismatches": [
    {
      "subject_key": "9012345",
      "theme_name": "...",
      "field": "theme_tier",
      "new_value": "strong_branch",
      "old_value": "main",
      "delta": null,
      "root_cause": "event_chain_score diff — old=42.0 new=28.0: 旧链 today_event_count=3, 新链 metadata 缺失该字段→0"
    }
  ],
  "key_samples": {
    "002361.SZ": { "formal": true, "alive": true },
    "605060.SH": { "formal": true, "alive": false }
  }
}
```

### 关键样本验证
确保以下个股相关 subject_key 的 formal/alive 输出与旧链一致：
- **002361.SZ** (神剑) — 强主线代表
- **605060.SH** (联德) — 弱转强代表

### 数据源差异的预期影响
- 旧链 `build_event_stats()` 从 `news_event` 表直接聚合（today_event_count/recent_event_count/distinct_event_days 精确）
- 新链从 `SubjectContextDTO.metadata` 近似映射（依赖 metadata 预聚合字段，可能不完整）
- 旧链 `build_market_stats()` 从 `subject_stock_daily_snapshot` 表聚合（含 is_leader 字段，SQL GROUP BY 精确）
- 新链从 `StockBarDTO` 分组计算（limit_up 判断用 close_price >= limit_up_price，leader 用 pool_rank=1 推断）
- 预期：评分字段可能在 approx 范围（≤ 5.0），tier 分类和 is_main_theme 应基本对齐

## Layer B/C 衔接规划（后续，不阻塞本计划）

Layer A 复刻验证通过后：
1. **Layer B**：补齐 K 线层独立证据 + 6 退潮证据项 + LLM 复核策略。本计划的纯算法文件 + replay runner 模式可直接复用为模板
2. **Layer C**：UniverseBuilder 覆盖策略需与 A/B 对齐。当前 A 命中 276 key (41%)、B 命中 8 key (1%)，UniverseBuilder 将大量 key 归入 blocked/missing，需在 A/B 覆盖提升后重新评估

## 验证方式

```bash
# 1. 运行 4/7 回放
cd /Users/admin/Desktop/ai_theme_app && \
RUN_REPLAY_DB=1 REPLAY_DB_WRITE_OK=0 \
python -m stock_processing_service.tests.replay._layer_a_replay_runner \
  --trade-date 2026-04-07 --sample-name baseline --mode replay

# 2. 运行 4/15 回放
RUN_REPLAY_DB=1 REPLAY_DB_WRITE_OK=0 \
python -m stock_processing_service.tests.replay._layer_a_replay_runner \
  --trade-date 2026-04-15 --sample-name baseline --mode replay

# 3. 对比模式（需旧链 theme_mainline_judgement 表数据存在）
python -m stock_processing_service.tests.replay._layer_a_replay_runner \
  --trade-date 2026-04-07 --sample-name baseline --mode compare

# 4. 检查输出概览
python -c "
import json, sys
with open('tmp/layer_a/2026-04-07_baseline/replay.json') as f:
    data = json.load(f)
print(f'subjects: {data[\"meta\"][\"subject_count\"]}')
tiers = {}
for r in data['results']:
    t = r['base_judgement']['theme_tier']
    tiers[t] = tiers.get(t, 0) + 1
print(f'tiers: {tiers}')
print(f'alive: {sum(1 for r in data[\"results\"] if r.get(\"enhanced_judgement\",{}).get(\"mainline_alive\"))}')
"

# 5. 查看差异统计
python -m json.tool tmp/layer_a/2026-04-07_baseline/diff.json | head -50
```

## 实施步骤

1. **创建 `enhanced_mainline_judgement_service.py`** — 逐行 1:1 复制旧链父子类算法，适配新链路径，内联 `ThemeMainlineJudgement` dataclass
2. **创建 `_layer_a_replay_runner.py`** — 复用 `_ReplayDatabaseStockFacade`，实现数据映射 + 编排 + JSON 输出 + diff.json 自动统计
3. **单元验证** — 用旧链 `test_p3_phase2_mainline_judgement_service.py` 的 3 个数据样本验证算法输出完全一致
4. **集成回放** — 4/7 和 4/15 两个日期运行 replay + compare，生成 diff.json
5. **差异分析** — 对 mismatch 的 subject_key 逐字段分析根因（数据源缺失 vs 算法偏差），输出根因分类统计
