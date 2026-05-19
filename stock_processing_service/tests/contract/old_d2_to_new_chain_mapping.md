# Old-Chain D2 → New-Chain Auction Confirmation Mapping

> 状态：FINAL
> 日期：2026-05-19
> 前提：v2.0 FROZEN，不改 UseCase，不写生产表

---

## 0. Executive Summary

### v2.2a Data Readiness Result: **BLOCKED**

```
real_auction:      0/192 (  0.0%)  ← ZERO real auction timeline data
daily_open_proxy: 12/192 (  6.2%)  ← single-point snapshots only
missing:          180/192 ( 93.8%)  ← no auction data at all
```

**结论**：当前数据库中没有真实集合竞价分时数据。即使迁移旧链 D2 业务逻辑，也无法运行真实竞价确认。v2.2 只能做 **proxy-only framework validation**。

### Old-chain D2 can be partially migrated

旧链 `WeakToStrongAuctionScorer` 的四维评分+硬否决规则 **值得迁移**，但旧链的 SQL/IO/生产写入层 **必须重写**。

---

## 1. Old-Chain D2 File Inventory

### 1.1 `stock_service/services/weak_to_strong_auction_scorer.py` (267 lines)

**Role**: Core business logic — 4-dim scoring + hard rules + level classification

**Functions**:

| Function | Input | Output | Logic |
|----------|-------|--------|-------|
| `score(row)` | `AuctionFeatureRow` | `AuctionScoreBreakdown` | 入口：硬规则→四维评分→等级判定 |
| `_hard_rule_check(row)` | `AuctionFeatureRow` | `List[str]` | 7条硬否决规则 |
| `_price_strength(row)` | `AuctionFeatureRow` | `float` (0-30) | 开盘强度：预期区间+红盘+尾段抬升 |
| `_pattern_stability(row)` | `AuctionFeatureRow` | `float` (0-25) | 形态稳定性：波动+尾段形态+急拉砸控制 |
| `_last_minute_grab(row)` | `AuctionFeatureRow` | `float` (0-25) | 末分钟抢筹：量比+价格抬升+共振 |
| `_plate_follow(row)` | `AuctionFeatureRow` | `float` (0-20) | 板块联动：红盘率+龙头强度+共振 |
| `_risk_penalty(row)` | `AuctionFeatureRow` | `float` (0-30) | 风险扣分：尾段急跌+退潮+低开+高开溢价+板块 |
| `to_evidence(row, breakdown)` | `AuctionFeatureRow`, `AuctionScoreBreakdown` | `Dict` | 证据JSON序列化 |

**Hard Reject Rules** (7条):
1. `not_in_candidate_pool` — 不在候选池
2. `fade_confirmed` — 主线退潮确认
3. `pool_entry_not_formal` — 非formal候选
4. `volatility_too_high` — 竞价波动>70
5. `no_last_minute_grab` — 需要抢筹但没有
6. `close_not_red_and_support_weak` — 低开且支撑弱
7. `tail_drop` — 尾段急跌
8. `plate_retreat` — 板块退潮
9. `data_status=missing|delayed` — 无数据/延迟

**Scoring Dimensions** (100-point scale):
```
price_strength        0-30  (max 30)
pattern_stability     0-25  (max 25)
last_minute_grab      0-25  (max 25)
plate_follow          0-20  (max 20)
risk_penalty          0-30  (subtracted)
────────────────────────────────
confirmation_score    0-100
```

**Level Thresholds**:
- A: ≥ 75 → decision="confirmed"
- B: ≥ 55 → decision="watch"
- C: < 55 → decision="reject"
- X: hard_reject → decision="no_decision" or "observe_only"

**Verdict**: ✅ **FULLY MIGRATABLE** — Pure business logic, zero SQL, zero I/O. This is the gold standard for new-chain `AuctionConfirmationService`.

---

### 1.2 `stock_service/services/weak_to_strong_auction_data_adapter.py` (388 lines)

**Role**: Data I/O layer — loads candidates, auction snapshots, plate context from DB.

**Key Methods**:

| Method | SQL/IO | Migratable? |
|--------|--------|-------------|
| `load_features(trade_date)` | YES — reads `weak_to_strong_candidate_pool` + `pre_market_auction_snapshot` + `auction_watch_universe` | ❌ Must rewrite via Ports |
| `_load_candidates(pool, trade_date)` | YES — `SELECT FROM weak_to_strong_candidate_pool WHERE next_trade_date = $1` | ❌ Reads PRODUCTION table |
| `_load_watch_universe_stock_ids(pool, trade_date)` | YES — `SELECT FROM auction_watch_universe` | ❌ Additional dependency |
| `_filter_candidates_by_watch_universe(rows, ids)` | NO — pure alias matching | ✅ Logic is migratable |
| `_load_auction_snapshots(pool, trade_date, stock_ids)` | YES — `SELECT FROM pre_market_auction_snapshot` | ❌ Direct SQL, but table is shared |
| `_load_plate_context(pool, trade_date)` | YES — `SELECT FROM pre_market_auction_snapshot GROUP BY subject_key` | ❌ Direct SQL, but logic is sound |
| `_calc_data_status(snapshot, now, trade_date)` | NO — pure classification | ✅ FULLY MIGRATABLE |
| `_stock_id_aliases(value)` | NO | ✅ Utility, already have equivalent |
| `_derive_ohlc_pct(open_pct, snapshot)` | NO — pure math | ✅ Logic migratable |

**AuctionFeatureRow** (28 fields):
Full feature vector bridging candidate + auction snapshot + plate context.

**Verdict**: ⚠️ **PARTIALLY MIGRATABLE** — The SQL queries must be replaced by ReadPorts. The data classification logic (`_calc_data_status`, `_stock_id_aliases`) is clean and reusable. The `AuctionFeatureRow` DTO should be adapted as new-chain `AuctionConfirmationInput`.

---

### 1.3 `stock_service/services/weak_to_strong_auction_service.py` (353 lines)

**Role**: Orchestrator — loads features, scores, writes to production table.

**Key Issues**:
1. Creates its own `asyncpg.Pool` — bypasses gateway
2. Writes to `weak_to_strong_auction_signal` — PRODUCTION table
3. Filters to only `pool_entry_type == "formal"` — hard-coded policy
4. Has `_delete_stale_rows` — mutates production data

**Verdict**: ❌ **MUST REWRITE** — Orchestration logic is simple (load → score → write) but all I/O paths are wrong for new chain. Replace with:
- `AuctionConfirmationUseCase.execute(trade_date)`
- ReadPorts for data loading
- WritePorts for isolated `w2s_auction_confirmation_rebuild`

---

### 1.4 `scripts/run_weak_to_strong_auction_confirm.py` (67 lines)

**Role**: CLI entrypoint — `--trade-date` → `WeakToStrongAuctionService.confirm()`

**Verdict**: ❌ **DO NOT MIGRATE** — Old runner pattern. Replace with contract test in new chain.

---

### 1.5 New-Chain Existing: `stock_processing_service/domain/services/w2s_auction_scorer.py` (57 lines)

**Current state**: MINIMAL STUB

```python
def score_one(self, auction: StockAuctionDTO) -> AuctionScore:
    open_pct = auction.auction_open_pct
    auction_amt = auction.auction_amount
    tail_vwap = auction.tail_auction_vwap
    # Simple linear: open*10+50, amount/1M*20, tail*5
    # No hard rules, no plate follow, no stability check
```

**Verdict**: ❌ **INSUFFICIENT** — Missing all 7 hard rules, 4-dim scoring, plate follow, risk penalty. This is a placeholder that must be replaced.

---

### 1.6 New-Chain Existing: `stock_processing_service/domain/services/w2s_confirm_service.py` (83 lines)

**Current state**: Thin wrapper over `W2SAuctionScorer`

```python
def confirm(self, candidates, auctions) -> list[W2SConfirmedPick]:
    # Match candidates to auctions, score, approve if A/B/C
```

**Verdict**: ⚠️ **Frame is correct, content is empty** — The orchestration pattern (match → score → level) is right. But it delegates to the stub scorer and has no hard rules, no plate context, no data_status handling.

---

## 2. Migration Mapping

### 2.1 What to KEEP from old chain

| Old Chain | → | New Chain Target |
|-----------|------|-----------------|
| `WeakToStrongAuctionScorer._hard_rule_check()` | → | `AuctionConfirmationService._hard_rules()` |
| `WeakToStrongAuctionScorer._price_strength()` | → | `AuctionConfirmationService._price_strength()` |
| `WeakToStrongAuctionScorer._pattern_stability()` | → | `AuctionConfirmationService._pattern_stability()` |
| `WeakToStrongAuctionScorer._last_minute_grab()` | → | `AuctionConfirmationService._last_minute_grab()` |
| `WeakToStrongAuctionScorer._plate_follow()` | → | `AuctionConfirmationService._plate_follow()` |
| `WeakToStrongAuctionScorer._risk_penalty()` | → | `AuctionConfirmationService._risk_penalty()` |
| `WeakToStrongAuctionScorer.to_evidence()` | → | `AuctionConfirmationService._build_evidence()` |
| `AuctionScoreBreakdown` dataclass | → | `AuctionConfirmationResult` DTO |
| `AuctionFeatureRow` DTO structure | → | `AuctionConfirmationInput` DTO |
| `_calc_data_status()` logic | → | `_classify_data_status()` |
| `_derive_ohlc_pct()` logic | → | `_derive_auction_range()` |
| Scoring thresholds (A≥75, B≥55) | → | Same thresholds |
| 100-point composite formula | → | Same formula |

### 2.2 What to REPLACE

| Old Chain | Problem | New Chain Solution |
|-----------|---------|--------------------|
| `WeakToStrongAuctionDataAdapter._load_candidates()` | Reads `weak_to_strong_candidate_pool` (production) | ReadPorts → `w2s_candidate_rebuild` (isolated) |
| `WeakToStrongAuctionDataAdapter._load_auction_snapshots()` | Direct asyncpg SQL | ReadPorts → `get_auction_snapshot_for_candidates()` |
| `WeakToStrongAuctionDataAdapter._load_plate_context()` | Direct asyncpg SQL | ReadPorts → `get_subject_auction_board_context()` |
| `WeakToStrongAuctionService._upsert()` | Writes to `weak_to_strong_auction_signal` (production) | WritePorts → `w2s_auction_confirmation_rebuild` (isolated) |
| `WeakToStrongAuctionService._delete_stale_rows()` | Mutates production data | No delete — rebuild table is date-partitioned |
| `asyncpg.Pool` creation in service | Bypasses gateway | Use `DatabaseGateway` via Ports |
| CLI runner `run_weak_to_strong_auction_confirm.py` | Old runner pattern | Contract test `test_v2_2_auction_confirm_contract.py` |

### 2.3 What to DISCARD

| Old Chain | Reason |
|-----------|--------|
| `auction_watch_universe` dependency | Additional table not in v2.0 pipeline |
| `_filter_candidates_by_watch_universe()` | Extra filter not validated by v2.0 |
| `pool_entry_type == "formal"` only filter | v2.0 supports both formal + observe_only |
| `weak_to_strong_auction_signal` table writes | Use isolated rebuild table |
| `get_replay_by_candidate_id()` / `list_replay_by_trade_date()` | Query methods belong in ReadPorts, not domain service |
| Real-time `delayed` latency check for today | v2.2 is historical backtest, not real-time |

---

## 3. Target Architecture

### New files to create:

```
stock_processing_service/
  domain/services/
    auction_confirmation_service.py    # ← NEW: Migrated scorer logic
  application/use_cases/
    build_auction_confirmation.py      # ← NEW: UseCase orchestrator
  tests/contract/
    test_v2_2_auction_confirm_contract.py  # ← NEW: Contract test
```

### Files to replace:

```
stock_processing_service/domain/services/
  w2s_auction_scorer.py   → auction_confirmation_service.py (replaces stub)
  w2s_confirm_service.py  → merged into auction_confirmation_service.py
```

### Ports to add (in HistoricalBacktestReadPorts + WritePorts):

```python
# ReadPorts
async def get_auction_snapshot_for_candidates(
    trade_date: date, stock_ids: list[str]
) -> list[dict[str, Any]]: ...

async def get_subject_auction_board_context(
    trade_date: date, subject_keys: list[str]
) -> dict[str, dict[str, float]]: ...

# WritePorts
async def upsert_auction_confirmation_rebuild_rows(
    rows: list[dict[str, Any]]
) -> int: ...
```

### Isolated table:

```sql
CREATE TABLE IF NOT EXISTS w2s_auction_confirmation_rebuild (
    id BIGSERIAL PRIMARY KEY,
    candidate_trade_date DATE NOT NULL,
    confirm_trade_date DATE NOT NULL,
    stock_id TEXT NOT NULL,
    stock_name TEXT NOT NULL DEFAULT '',
    subject_key TEXT NOT NULL DEFAULT '',
    theme_name TEXT NOT NULL DEFAULT '',

    -- D1 context
    candidate_score NUMERIC(8,2),
    candidate_type TEXT,
    support_type TEXT,
    support_strength NUMERIC(8,2),
    weak_type TEXT,

    -- D2 scoring
    price_strength_score NUMERIC(8,2),
    pattern_stability_score NUMERIC(8,2),
    last_minute_grab_score NUMERIC(8,2),
    plate_follow_score NUMERIC(8,2),
    risk_penalty NUMERIC(8,2),
    auction_confirm_score NUMERIC(8,2),
    auction_confirm_level TEXT,        -- A/B/C/X
    auction_confirm_source TEXT,        -- real_auction/daily_open_proxy/missing

    -- Auction raw data
    auction_open_pct NUMERIC(8,4),
    auction_amount NUMERIC(18,2),
    auction_path_volatility NUMERIC(8,2),
    last_minute_volume_ratio NUMERIC(8,4),
    has_end_drop BOOLEAN,
    has_end_spike BOOLEAN,
    is_red_zone BOOLEAN,
    plate_red_ratio NUMERIC(8,4),
    plate_leader_strength NUMERIC(8,4),

    -- Evidence
    evidence_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    rule_version TEXT NOT NULL DEFAULT 'auction_confirmation.v2',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    UNIQUE(candidate_trade_date, confirm_trade_date, stock_id)
);
```

---

## 4. v2.2 Adjusted Plan

Given **0% real_auction + 6.2% proxy + 93.8% missing**, v2.2 must adapt:

### v2.2b: AuctionConfirmationService (framework-only)

- Migrate old-chain scorer logic into new domain service
- Add `data_status` as primary classifier: `real_auction` / `daily_open_proxy` / `missing`
- When `data_status = missing` → hard reject (level=X, reason=no_auction_data)
- When `data_status = daily_open_proxy` → score with reduced weights, mark `auction_confirm_source = daily_open_proxy`
- When `data_status = real_auction` → full 4-dim scoring (currently unreachable)
- All results explicitly labeled with `data_status`

### v2.2c: Proxy-only validation

- Run auction confirmation on v2.0 candidates with available proxy data
- Due to 6.2% proxy coverage, this is a **framework smoke test** only
- Output comparison but **flag all results as proxy-limited**
- Do NOT draw strategy conclusions from proxy-only results
- Document that real auction data collection is prerequisite for v2.2 conclusions

### Data engineering prerequisite

Before v2.2 can produce meaningful results:
1. Need Tushare stk_auction timeline data (9:20-9:25 tick-level)
2. Need to run `build_pre_market_auction_snapshot.py` with timeline data
3. Need at least 30%+ real_auction coverage on candidate stocks

---

## 5. Hard Constraints (reconfirmed)

- [x] 不改 UseCase 阈值
- [x] 不修改 BuildWeakToStrongCandidateUseCase
- [x] 不修改 StrongStockTrackingService
- [x] 不读取 v0.x deprecated 候选
- [x] 不把 proxy auction 当 real auction
- [x] 不直接写生产表
- [x] 所有写入通过 WritePorts → isolated rebuild 表
- [x] 不做参数优化
- [x] v2.0 FROZEN
