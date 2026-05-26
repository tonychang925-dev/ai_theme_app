"""P1-I-2: 弱转强支撑承接观察告警服务。

组合 D1候选 + D2确认 + 支撑位状态 → 承接观察告警。
不输出买卖建议，只做观察/风险提示。

数据流:
  weak_to_strong_candidate_pool (D1)
  + W2SConfirmService (D2)
  + KlineBreakDetector (支撑状态)
  + strong_stock_watch_pool (支撑位数据)
  + jyhf_stock_quote_snapshot (当前价)
  → w2s_support_*_alert → Redis Stream stream:w2s:alerts
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from typing import Any

import asyncpg

logger = logging.getLogger("sps.w2s_support_alert")

TZ_CN = timezone(timedelta(hours=8))


@dataclass
class W2SSupportAlert:
    trade_date: str
    candidate_trade_date: str
    candidate_id: int
    stock_id: str
    stock_name: str
    theme_name: str
    candidate_type: str
    weak_type: str
    confirm_level: str          # A / B / C
    confirm_score: float
    support_type: str
    support_level: float
    support_strength: float
    support_level_age_days: int
    current: float
    distance_pct: float
    support_state: str          # recover_support / touch_support / near_support
    alert_type: str             # w2s_support_reclaim_alert / w2s_support_hold_alert / w2s_support_observe
    severity: str               # important / warning / observe
    confidence: float
    position_label: str
    pattern_labels: list[str]
    evidence_rules: list[str]
    generated_at: str
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass
class W2SSupportAlertResult:
    alerts: list[W2SSupportAlert]
    total_candidates: int
    confirmed_count: int
    with_quotes: int


class W2SSupportAlertService:
    """弱转强支撑承接观察告警。"""

    def __init__(self, dsn: str):
        self._dsn = dsn
        self._pool: asyncpg.Pool | None = None

    async def _get_pool(self) -> asyncpg.Pool:
        if self._pool is None:
            self._pool = await asyncpg.create_pool(self._dsn, min_size=1, max_size=3)
        return self._pool

    # ── 加载 ──

    async def load_confirmed_candidates(self, candidate_trade_date: str,
                                        confirm_trade_date: str) -> list[dict]:
        """加载 D1 候选 + D2 竞价确认 (via W2SConfirmService fallback) + 支撑位数据。"""
        pool = await self._get_pool()

        # 1. 先从 DB 加载 D1 候选 + 支撑位
        rows = await pool.fetch(
            """SELECT
                 c.id AS candidate_id,
                 c.stock_id,
                 c.stock_name,
                 COALESCE(c.theme_name, '') AS theme_name,
                 c.candidate_type,
                 c.weak_type,
                 c.candidate_score,
                 COALESCE(c.next_trade_date::text, '') AS next_trade_date,
                 sw.support_type,
                 sw.support_level,
                 sw.support_score AS support_strength,
                 sw.last_trade_date AS support_last_trade_date
               FROM weak_to_strong_candidate_pool c
               LEFT JOIN strong_stock_watch_pool sw
                 ON split_part(sw.stock_id, '.', 1) = split_part(c.stock_id, '.', 1)
                 AND COALESCE(sw.watch_status, '') != 'removed'
               WHERE c.trade_date = $1::date
               ORDER BY c.candidate_score DESC""",
            date.fromisoformat(candidate_trade_date),
        )
        candidates_raw = [dict(r) for r in rows]

        # 2. 尝试从 weak_to_strong_auction_signal 读 D2 确认
        signal_rows = await pool.fetch(
            """SELECT candidate_id, signal_level, confirmation_score
               FROM weak_to_strong_auction_signal
               WHERE trade_date = $1::date""",
            date.fromisoformat(confirm_trade_date),
        )
        signal_by_cid = {r["candidate_id"]: dict(r) for r in signal_rows}

        # 3. 若 signal 缺失，用 W2SConfirmService fallback
        from stock_processing_service.domain.services.w2s_alert_service import W2SAlertService
        from stock_processing_service.domain.services.w2s_confirm_service import W2SConfirmService, W2SConfirmedPick
        from stock_processing_service.domain.services.w2s_auction_scorer import W2SAuctionScorer
        from stock_processing_service.contracts.dto import StockAuctionDTO
        from stock_processing_service.domain.services.w2s_candidate_service import W2SCandidate
        from decimal import Decimal
        import json as _json

        fallback_picks: dict[int, W2SConfirmedPick] = {}
        need_fallback = [r for r in candidates_raw if r.get("candidate_id") not in signal_by_cid]

        if need_fallback:
            # 构建 W2SCandidate 列表
            w2s_candidates = []
            for r in need_fallback:
                sid = str(r.get("stock_id") or "")
                w2s_candidates.append(W2SCandidate(
                    trade_date=candidate_trade_date,
                    stock_id=sid,
                    stock_name=str(r.get("stock_name") or ""),
                    subject_key="",
                    subject_name=str(r.get("theme_name") or ""),
                    support_score=Decimal(str(r.get("support_strength") or 0)),
                    momentum_score=Decimal("0"),
                    candidate_score=Decimal(str(r.get("candidate_score") or 0)),
                    candidate_level=str(r.get("candidate_type") or "observe"),
                    candidate_source="strong_watch",
                    evidence_rules=[],
                ))

            # 加载竞价数据
            codes = [c.stock_id.replace(".SZ", "").replace(".SH", "").replace(".BJ", "") for c in w2s_candidates]
            auc_rows = await pool.fetch(
                """SELECT trade_date, stock_id, auction_open_price, auction_open_pct,
                          auction_volume, auction_amount, carry_ratio,
                          price_path_stability_score, last_minute_ratio, shape_features
                   FROM pre_market_auction_snapshot
                   WHERE trade_date = $1::date
                     AND split_part(stock_id, '.', 1) = ANY($2::text[])""",
                date.fromisoformat(confirm_trade_date), codes,
            )
            code_to_sid = {c.stock_id.replace(".SZ", "").replace(".SH", "").replace(".BJ", ""): c.stock_id for c in w2s_candidates}
            auctions = []
            for ar in auc_rows:
                raw_code = str(ar["stock_id"]).replace(".SZ", "").replace(".SH", "").replace(".BJ", "")
                mapped_sid = code_to_sid.get(raw_code, str(ar["stock_id"]))
                shapes_raw = ar.get("shape_features")
                if isinstance(shapes_raw, list):
                    shapes = tuple(str(s) for s in shapes_raw)
                elif isinstance(shapes_raw, str):
                    try:
                        shapes = tuple(s.strip() for s in _json.loads(shapes_raw))
                    except Exception:
                        shapes = ()
                else:
                    shapes = ()
                auctions.append(StockAuctionDTO(
                    trade_date=ar["trade_date"], stock_id=mapped_sid,
                    auction_open_price=_to_dec(ar.get("auction_open_price")),
                    auction_open_pct=_to_dec(ar.get("auction_open_pct")),
                    auction_volume=_to_dec(ar.get("auction_volume")),
                    auction_amount=_to_dec(ar.get("auction_amount")),
                    carry_ratio=_to_dec(ar.get("carry_ratio")),
                    price_path_stability_score=_to_dec(ar.get("price_path_stability_score")),
                    last_minute_ratio=_to_dec(ar.get("last_minute_ratio")),
                    shape_features=shapes,
                ))

            scorer = W2SAuctionScorer()
            confirmer = W2SConfirmService(scorer)
            picks = confirmer.confirm(w2s_candidates, auctions)
            for pick in picks:
                for r in need_fallback:
                    if str(r.get("stock_id") or "") == pick.stock_id:
                        fallback_picks[int(r["candidate_id"])] = pick
                        break

        # 合并结果
        for r in candidates_raw:
            cid = r.get("candidate_id")
            if cid in signal_by_cid:
                sig = signal_by_cid[cid]
                r["confirm_level"] = sig.get("signal_level", "")
                r["confirm_score"] = float(sig.get("confirmation_score") or 0)
            elif cid in fallback_picks:
                pick = fallback_picks[cid]
                r["confirm_level"] = pick.confirm_level
                r["confirm_score"] = float(pick.confirm_score)
                r["_fallback"] = True
            else:
                r["confirm_level"] = ""
                r["confirm_score"] = 0.0

        return candidates_raw

    async def load_latest_quotes(self, stock_ids: list[str]) -> dict[str, dict]:
        """加载最新报价。"""
        if not stock_ids:
            return {}
        pool = await self._get_pool()
        codes = [sid.replace(".SZ", "").replace(".SH", "").replace(".BJ", "") for sid in stock_ids]
        rows = await pool.fetch(
            """SELECT DISTINCT ON (stock_id)
                 split_part(stock_id, '.', 1) AS code, current, pct_chg, ts
               FROM jyhf_stock_quote_snapshot
               WHERE split_part(stock_id, '.', 1) = ANY($1::text[])
                 AND current IS NOT NULL
               ORDER BY stock_id, ts DESC""",
            codes,
        )
        return {r["code"]: {"current": float(r["current"]), "pct_chg": float(r["pct_chg"] or 0), "ts": str(r["ts"])} for r in rows}

    async def load_position_pattern(self, trade_date: str, stock_ids: list[str]) -> dict[str, dict]:
        """加载位置/形态判断。"""
        if not stock_ids:
            return {}
        pool = await self._get_pool()
        pos_rows = await pool.fetch(
            """SELECT stock_id, position_label, ma_alignment_status
               FROM stock_position_judgement WHERE trade_date = $1::date AND stock_id = ANY($2::text[])""",
            date.fromisoformat(trade_date), stock_ids,
        )
        pat_rows = await pool.fetch(
            """SELECT stock_id, pattern_labels
               FROM stock_pattern_judgement WHERE trade_date = $1::date AND stock_id = ANY($2::text[])""",
            date.fromisoformat(trade_date), stock_ids,
        )
        import json as _json
        result = {}
        for r in pos_rows:
            sid = str(r["stock_id"])
            result.setdefault(sid, {})["position_label"] = str(r.get("position_label") or "")
            result.setdefault(sid, {})["ma_alignment"] = str(r.get("ma_alignment_status") or "")
        for r in pat_rows:
            sid = str(r["stock_id"])
            raw = r.get("pattern_labels")
            if isinstance(raw, list):
                labels = [str(s) for s in raw]
            elif isinstance(raw, str):
                try:
                    labels = list(_json.loads(raw))
                except Exception:
                    labels = []
            else:
                labels = []
            result.setdefault(sid, {})["pattern_labels"] = labels
        return result

    # ── 支撑状态判定 ──

    def classify_support(self, current: float, support_level: float) -> str:
        """判定支撑位状态 (简化版，与 KlineBreakDetector 对齐)。"""
        if support_level <= 0:
            return "unknown"
        if current < support_level * 0.98:
            return "strong_break_support"
        if current < support_level * 0.995:
            return "break_support"
        if current <= support_level * 1.005 and current >= support_level * 0.995:
            return "touch_support"
        if current <= support_level * 1.03:
            return "near_support"
        if current > support_level * 1.005:
            return "recover_support"  # 从break恢复到上方
        return "above"

    # ── 主流程 ──

    async def build_alerts(self, candidate_trade_date: str,
                           confirm_trade_date: str | None = None) -> W2SSupportAlertResult:
        if confirm_trade_date is None:
            confirm_trade_date = candidate_trade_date

        now_str = datetime.now(TZ_CN).isoformat()
        rows = await self.load_confirmed_candidates(candidate_trade_date, confirm_trade_date)

        stock_ids = [str(r.get("stock_id") or "") for r in rows if r.get("stock_id")]
        quotes = await self.load_latest_quotes(stock_ids)
        positions = await self.load_position_pattern(confirm_trade_date, stock_ids)

        alerts: list[W2SSupportAlert] = []
        confirmed_count = 0
        with_quotes = 0

        now_date = datetime.now(TZ_CN).date()

        for r in rows:
            sid = str(r.get("stock_id") or "")
            code = sid.replace(".SZ", "").replace(".SH", "").replace(".BJ", "")
            cid = r.get("candidate_id")
            if not cid:
                continue

            # D2 确认等级
            confirm_level = str(r.get("confirm_level") or "")
            if not confirm_level:
                continue
            confirmed_count += 1
            if confirm_level == "X":
                continue  # hard reject → 不观察

            # 支撑位
            support_level = float(r.get("support_level") or 0)
            support_type = str(r.get("support_type") or "")
            if support_level <= 0 or not support_type:
                continue

            q = quotes.get(code)
            if q is None:
                continue
            with_quotes += 1
            current = q["current"]

            # 支撑状态
            support_state = self.classify_support(current, support_level)

            # 过滤：仅 near/touch/recover 进入观察
            if support_state not in ("near_support", "touch_support", "recover_support"):
                continue

            # break/strong_break 不推观察告警（这属于 KlineBreakDetector 范畴）
            if support_state in ("break_support", "strong_break_support"):
                continue

            distance_pct = round((current - support_level) / support_level * 100, 2)

            # 支撑位年龄
            last_td = r.get("support_last_trade_date")
            age_days = 999
            if last_td:
                try:
                    if isinstance(last_td, str):
                        last_td = datetime.strptime(last_td[:10], "%Y-%m-%d").date()
                    age_days = (now_date - last_td).days
                except Exception:
                    pass

            # 告警类型 + severity
            if support_state == "recover_support":
                if confirm_level in ("A", "B"):
                    alert_type = "w2s_support_reclaim_alert"
                    severity = "important"
                else:
                    alert_type = "w2s_support_observe"
                    severity = "observe"
            elif support_state == "touch_support":
                if confirm_level in ("A", "B"):
                    alert_type = "w2s_support_hold_alert"
                    severity = "warning"
                else:
                    alert_type = "w2s_support_observe"
                    severity = "observe"
            elif support_state == "near_support":
                alert_type = "w2s_support_observe"
                severity = "observe"
            else:
                continue

            # 置信度
            confidence = 1.0
            if age_days > 14:
                confidence -= 0.2
            elif age_days > 7:
                confidence -= 0.1
            if confirm_level == "C":
                confidence = min(confidence, 0.6)
            confidence = round(max(0.2, confidence), 2)

            # 位置/形态
            pos = positions.get(sid, positions.get(code, {}))
            position_label = pos.get("position_label", "")
            pattern_labels = pos.get("pattern_labels", [])

            # evidence
            evidence_rules = [
                f"candidate_id={cid}",
                f"confirm_level={confirm_level}",
                f"support_state={support_state}",
                f"distance={distance_pct}%",
            ]

            alerts.append(W2SSupportAlert(
                trade_date=confirm_trade_date,
                candidate_trade_date=candidate_trade_date,
                candidate_id=int(cid),
                stock_id=sid,
                stock_name=str(r.get("stock_name") or ""),
                theme_name=str(r.get("theme_name") or ""),
                candidate_type=str(r.get("candidate_type") or ""),
                weak_type=str(r.get("weak_type") or ""),
                confirm_level=confirm_level,
                confirm_score=float(r.get("confirm_score") or 0),
                support_type=support_type,
                support_level=support_level,
                support_strength=float(r.get("support_strength") or 0),
                support_level_age_days=age_days,
                current=current,
                distance_pct=distance_pct,
                support_state=support_state,
                alert_type=alert_type,
                severity=severity,
                confidence=confidence,
                position_label=position_label,
                pattern_labels=pattern_labels,
                evidence_rules=evidence_rules,
                generated_at=now_str,
                extra={"pct_chg": q.get("pct_chg", 0), "quote_ts": q.get("ts", "")},
            ))

        return W2SSupportAlertResult(
            alerts=alerts,
            total_candidates=len(rows),
            confirmed_count=confirmed_count,
            with_quotes=with_quotes,
        )

    async def close(self) -> None:
        if self._pool:
            await self._pool.close()
            self._pool = None


def _to_dec(value) -> "Decimal":
    from decimal import Decimal as D, InvalidOperation
    if value is None:
        return D("0")
    try:
        return D(str(value))
    except (ValueError, InvalidOperation):
        return D("0")
