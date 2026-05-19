# v2.2b AuctionConfirmationService — Implementation Report

> 状态：COMPLETE
> 日期：2026-05-19
> Contract tests: 18/18 PASS

---

## 1. What was built

### New file: `stock_processing_service/domain/services/auction_confirmation_service.py` (~430 lines)

Pure domain service migrating old-chain `WeakToStrongAuctionScorer` business logic to new-chain architecture.

**No SQL, no I/O, no asyncpg, no production table writes.**

### Service API

```python
service = AuctionConfirmationService()
result = service.confirm(candidate, auction, board)
```

### Input DTOs

| DTO | Role | Key Fields |
|-----|------|------------|
| `CandidateAuctionContext` | D1 candidate context | stock_id, candidate_type, support_type, support_strength, pool_entry_type, fade_confirmed, expected_open_low/high |
| `AuctionSnapshotData` | T+1 auction snapshot | auction_open_pct, price_path_stability_score, last_minute_ratio, has_end_drop/spike, data_status |
| `BoardAuctionData` | Subject-level board context | plate_red_ratio, plate_leader_strength |

### Output DTO: `AuctionConfirmationResult`

| Field | Type | Description |
|-------|------|-------------|
| `auction_confirm_score` | float | 0–100 composite score |
| `auction_confirm_level` | str | A/B/C/X or proxy_A/proxy_B/proxy_C/proxy_X |
| `auction_confirm_source` | str | real_auction / daily_open_proxy / missing |
| `data_status` | str | real_auction / daily_open_proxy / missing |
| `price_strength_score` | float | 0–30 |
| `pattern_stability_score` | float | 0–25 |
| `last_minute_grab_score` | float | 0–25 |
| `plate_follow_score` | float | 0–20 |
| `risk_penalty` | float | 0–30 |
| `decision` | str | confirmed / watch / reject / observe_only / no_decision |
| `approved` | bool | True if hard reject empty AND decision in {confirmed, watch} |
| `hard_reject_reasons` | list[str] | List of triggered hard reject rules |
| `reject_reason` | str | Human-readable reject summary |
| `evidence_json` | str | Full traceable JSON evidence |
| `rule_version` | str | "auction_confirmation.v2" |

---

## 2. Migrated rules from old-chain

### 4-Dim Scoring (from `WeakToStrongAuctionScorer`)

| Dimension | Max | Source | Key Factors |
|-----------|-----|--------|-------------|
| price_strength | 30 | `_price_strength()` | Expected open range, red zone, support-based acceptance, tail lift, mild low-open recovery |
| pattern_stability | 25 | `_pattern_stability()` | Path volatility (≤15→+10, ≤30→+8, ≤50→+5), tail pattern, no sharp reversal |
| last_minute_grab | 25 | `_last_minute_grab()` | Volume surge (≥0.35→+10, ≥0.20→+7, ≥0.10→+4), price lift, volume+price resonance |
| plate_follow | 20 | `_plate_follow()` | Red ratio (≥0.65→+8, ≥0.45→+6, ≥0.30→+4), leader strength, red+leader resonance |

### 9 Hard Reject Rules (from `_hard_rule_check`)

| # | Rule | Trigger |
|---|------|---------|
| 1 | `data_status=missing\|delayed` | No usable auction data |
| 2 | `not_in_candidate_pool` | Empty stock_id |
| 3 | `fade_confirmed` | Mainline fade confirmed |
| 4 | `pool_entry_not_formal` | Non-formal pool entry |
| 5 | `volatility_too_high` | Path volatility > 70 |
| 6 | `no_last_minute_grab` | Need grab but not present |
| 7 | `close_not_red_and_support_weak` | Close < -1% AND support < 30 |
| 8 | `tail_drop` | Auction ended with price drop |
| 9 | `plate_retreat` | Need plate follow AND red_ratio < 0.20 |

### Risk Penalty (5 factors)

| Factor | Max Penalty |
|--------|-------------|
| tail_drop | -12 |
| fade_watch | -3 |
| close negative | -4 to -6 |
| open too high (chasing risk) | -6 |
| weak plate (<30% red) | -4 |

---

## 3. data_status handling (NEW — not in old chain)

The old chain had basic data_status checks. v2.2b adds strict source separation:

| data_status | Level Output | Can Trade? | Purpose |
|-------------|-------------|------------|---------|
| `real_auction` | A / B / C / X | A/B only | Full formal confirmation |
| `daily_open_proxy` | proxy_A / proxy_B / proxy_C / proxy_X | Directional observation only, NOT formal signal | Proxy validation |
| `missing` | X | No | Hard reject, reason=auction_data_missing |

**Key constraint**: `daily_open_proxy` results MUST NOT be treated as formal A/B/C signals. The `proxy_` prefix prevents accidental mixing.

---

## 4. Contract test results: 18/18 PASS

| # | Test | Status |
|---|------|--------|
| 1 | missing auction → X with auction_data_missing | PASS |
| 2 | data_status=missing in auction → X | PASS |
| 3 | daily_open_proxy → proxy_A/B/C levels | PASS |
| 4 | real_auction → formal A/B/C/X levels | PASS |
| 5 | fade_confirmed → hard reject | PASS |
| 6 | pool_entry_not_formal → observe_only | PASS |
| 7 | tail_drop → hard reject | PASS |
| 8 | volatility > 70 → hard reject | PASS |
| 9 | need_last_minute_grab missing → hard reject | PASS |
| 10 | close_not_red + support_weak → hard reject | PASS |
| 11 | plate_retreat → hard reject | PASS |
| 12 | strong signal → score >= A threshold | PASS (score=100) |
| 13 | weak signal → score < B threshold | PASS (score=28) |
| 14 | evidence_json complete and parseable | PASS |
| 15 | no SQL/IO in domain service | PASS |
| 16 | score components within bounds | PASS |
| 17 | edge case: support_strength=0 | PASS |
| 18 | edge case: extreme open >7% risk penalty | PASS |

---

## 5. What was NOT done (and why)

| Item | Reason |
|------|--------|
| ReadPorts / WritePorts for auction data | v2.2b scope = domain service only. Ports come in v2.2c. |
| `w2s_auction_confirmation_rebuild` table creation | Requires WritePorts first. DDL is specified in old_d2_to_new_chain_mapping.md. |
| v2.2c backtest comparison | Requires real auction data (currently 0%). Will do proxy-only smoke test when data improves. |
| Modifying old-chain files | Old chain untouched. v2.2b is NEW code only. |
| Performance/optimization | MVP correctness first. |

---

## 6. Files changed

| File | Action | Description |
|------|--------|-------------|
| `domain/services/auction_confirmation_service.py` | **NEW** | ~430 lines, pure domain service |
| `domain/services/__init__.py` | MODIFIED | Added 5 new exports |
| `tests/contract/test_v2_2_auction_confirm_contract.py` | **NEW** | 18 contract tests |
| `tests/contract/old_d2_to_new_chain_mapping.md` | Created earlier | Old-chain D2 audit + migration plan |

---

## 7. Next steps

1. **v2.2c**: Add ReadPorts/WritePorts + isolated table + UseCase orchestrator
2. **Data pipeline**: Collect real auction timeline data (9:20-9:25 tick-level)
3. **v2.2d**: After real_auction coverage >30%, run backtest comparison
