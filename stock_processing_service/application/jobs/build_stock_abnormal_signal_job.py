"""异动信号检测 Job — 完整新链 Gateway 架构。

所有数据读写通过 DatabaseGateway，不直接操作数据库。
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any

from stock_processing_service.contracts.dto import BuildResult


@dataclass
class AbnormalSignalConfig:
    min_turnover_rate: float = 3.0
    min_composite_score: float = 10.0
    require_turnover: bool = False
    require_main_net_inflow: bool = False
    require_hot_money_buy: bool = False
    require_institution_buy: bool = False
    require_tail_rush: bool = False


class BuildStockAbnormalSignalJob:
    """异动信号检测 Job — 全 Gateway 链路。

    Read:  subject_stock_daily_snapshot + stock_daily_snapshot (via Gateway)
    Write: stock_abnormal_signal (via Gateway)
    """

    def __init__(
        self,
        write_port: Any = None,
        config: AbnormalSignalConfig | None = None,
        db_gateway: Any = None,
    ) -> None:
        self._write_port = write_port
        self._config = config or AbnormalSignalConfig()
        self._db_gateway = db_gateway

    async def execute(
        self,
        trade_date: date,
        tushare_token: str = "",
        min_turnover_rate: float | None = None,
        min_composite_score: float | None = None,
        turnover_rate_map: dict[str, float] | None = None,
    ) -> BuildResult:
        import json as _json

        cfg = self._config
        _turnover_overrides = turnover_rate_map or {}
        td_str = trade_date.isoformat() if hasattr(trade_date, "isoformat") else str(trade_date)
        min_turn = min_turnover_rate if min_turnover_rate is not None else cfg.min_turnover_rate
        min_score = min_composite_score if min_composite_score is not None else cfg.min_composite_score

        gw = self._db_gateway
        if gw is None:
            return BuildResult(name="build_stock_abnormal_signal", trade_date=td_str,
                               affected_rows=0, status="failed: no db_gateway")

        # ── Step 1: 读取 JYHF 股票日快照 (subject_stock_daily_snapshot) ──
        try:
            subject_rows = await gw.get_subject_stock_daily_snapshot_by_trade_date(trade_date)
        except Exception as e:
            return BuildResult(name="build_stock_abnormal_signal", trade_date=td_str,
                               affected_rows=0, status=f"failed: subject read error: {e}")

        if not subject_rows:
            return BuildResult(name="build_stock_abnormal_signal", trade_date=td_str,
                               affected_rows=0, status="ok_no_inputs")

        # ── Step 1.5: 从 stock_daily_basic_snapshot 读取真实 turnover_rate ──
        if not _turnover_overrides:
            basic_rows = []
            try:
                basic_rows = await gw.get_stock_daily_basic_snapshot(trade_date)
            except Exception as e:
                return BuildResult(name="build_stock_abnormal_signal", trade_date=td_str,
                                   affected_rows=0, status=f"STOCK_DAILY_BASIC_SNAPSHOT_NOT_READY: {e}")
            if not basic_rows:
                return BuildResult(name="build_stock_abnormal_signal", trade_date=td_str,
                                   affected_rows=0, status="STOCK_DAILY_BASIC_SNAPSHOT_NOT_READY: empty rows")
            for br in basic_rows:
                sid = str(br.get("stock_id") or "").strip().upper()
                tr = br.get("turnover_rate")
                if sid and tr is not None:
                    try:
                        tr_val = float(tr)
                        if tr_val > 0:
                            _turnover_overrides[sid] = tr_val
                            bare = sid.split(".")[0]
                            if bare != sid:
                                _turnover_overrides[bare] = tr_val
                    except (ValueError, TypeError):
                        pass

        # ── Step 2: 构建 StockAbnormalInput ──
        from database_service.scripts.build_stock_abnormal_signal import (
            _is_st_stock, _to_float, StockAbnormalInput,
            apply_turnover_rank, apply_main_net_inflow_rank,
        )
        from stock_service.services.stock_abnormal_signal_service import (
            StockAbnormalSignalService, StockDailySnapshot,
        )

        inputs: list[StockAbnormalInput] = []
        for r in subject_rows:
            sname = str(r.get("stock_name") or "").strip()
            if _is_st_stock(sname):
                continue
            raw = r.get("raw_json") or {}
            if isinstance(raw, str):
                try:
                    raw = _json.loads(raw)
                except Exception:
                    raw = {}
            if isinstance(raw, list):
                turnover_rate = _to_float(raw[18] if len(raw) > 18 else None)
                main_net_inflow = _to_float(raw[35] if len(raw) > 35 else None)
            elif isinstance(raw, dict):
                # TushareJoin raw_json is a dict WITHOUT turnover_rate;
                # JYHF raw_json is a list WITH it at index 18.
                turnover_rate = _to_float(raw.get("turnover_rate"))
                # Fallback: when raw_json has no turnover_rate (TushareJoin),
                # use daily_basic override map for real turnover_rate.
                if turnover_rate <= 0 and _turnover_overrides:
                    stock_id = str(r.get("stock_id", "")).strip().upper()
                    override = _turnover_overrides.get(stock_id)
                    if override is None:
                        bare = stock_id.split(".")[0]
                        override = _turnover_overrides.get(bare, 0.0)
                    if override > 0:
                        turnover_rate = override
                main_net_inflow = _to_float(raw.get("main_net_inflow"))
            else:
                continue
            if turnover_rate < min_turn:
                continue
            inputs.append(StockAbnormalInput(
                trade_date=td_str,
                subject_key=str(r.get("subject_key", "")),
                theme_name="",
                stock_id=str(r.get("stock_id", "")).strip().upper(),
                stock_name=sname,
                open_price=_to_float(r.get("open_price")),
                high_price=_to_float(r.get("high_price")),
                low_price=_to_float(r.get("low_price")),
                close_price=_to_float(r.get("close_price")),
                pre_close=_to_float(r.get("pre_close")),
                pct_chg=_to_float(r.get("pct_chg")),
                volume=_to_float(r.get("volume")),
                amount=_to_float(r.get("amount")),
                volume_ratio=0.0,
                turnover_rate=turnover_rate,
                main_net_inflow=main_net_inflow,
            ))

        ranked = apply_main_net_inflow_rank(apply_turnover_rank(inputs))

        # ── Step 3: 读取 Tushare K 线 (stock_daily_snapshot) ──
        # Pass both full (000001.SZ) and bare (000001) codes for matching
        kline_stock_ids: list[str] = []
        _seen_kline: set[str] = set()
        for r in ranked:
            full = str(r.stock_id or "").strip().upper()
            if not full or full in _seen_kline:
                continue
            _seen_kline.add(full)
            kline_stock_ids.append(full)
            bare = full.split(".")[0]
            if bare != full and bare not in _seen_kline:
                _seen_kline.add(bare)
                kline_stock_ids.append(bare)
        bars_by_stock: dict[str, list[StockDailySnapshot]] = {}
        try:
            from datetime import timedelta as _td_ab
            lookback_start = trade_date - _td_ab(days=90)
            bar_rows = await gw.get_stock_daily_bars_range(
                start_date=lookback_start,
                end_date=trade_date,
                stock_ids=kline_stock_ids,
            )
            for br in bar_rows:
                full_id = str(br.get("stock_id", "")).strip().upper()
                short = full_id.split(".")[0]
                bars_by_stock.setdefault(short, []).append(StockDailySnapshot(
                    trade_date=str(br.get("trade_date", "")),
                    stock_id=short,
                    stock_name=str(br.get("stock_name") or ""),
                    open_price=_to_float(br.get("open_price")),
                    high_price=_to_float(br.get("high_price")),
                    low_price=_to_float(br.get("low_price")),
                    close_price=_to_float(br.get("close_price")),
                    pre_close=_to_float(br.get("pre_close")),
                    pct_chg=_to_float(br.get("pct_chg")),
                    volume=_to_float(br.get("volume")),
                    amount=_to_float(br.get("amount")),
                    source_name="tushare",
                ))
        except Exception as e:
            return BuildResult(name="build_stock_abnormal_signal", trade_date=td_str,
                               affected_rows=0, status=f"failed: kline read error: {e}")

        # ── Step 4: 生成异动信号 ──
        service = StockAbnormalSignalService()
        signals: list[dict] = []
        for item in ranked:
            short = item.stock_id.split(".")[0]
            bars = bars_by_stock.get(short, [])
            signal = service.build_signal(item, bars)
            if signal is None:
                continue
            composite = float(getattr(signal, "abnormal_composite_score", 0) or 0)
            if composite < min_score:
                continue
            labels = list(getattr(signal, "abnormal_labels", []) or [])
            signals.append({
                "trade_date": trade_date,
                "subject_key": getattr(signal, "subject_key", "") or "",
                "theme_name": getattr(signal, "theme_name", "") or "",
                "stock_id": getattr(signal, "stock_id", ""),
                "stock_name": getattr(signal, "stock_name", ""),
                "turnover_rate": float(getattr(signal, "turnover_rate", 0) or 0),
                "turnover_rank_in_theme": int(getattr(signal, "turnover_rank_in_theme", 0) or 0),
                "main_net_inflow": float(getattr(signal, "main_net_inflow", 0) or 0),
                "main_net_inflow_rank_in_theme": int(getattr(signal, "main_net_inflow_rank_in_theme", 0) or 0),
                "turnover_abnormal_score": float(getattr(signal, "turnover_abnormal_score", 0) or 0),
                "capital_focus_score": float(getattr(signal, "capital_focus_score", 0) or 0),
                "is_high_turnover": bool(getattr(signal, "is_high_turnover", False)),
                "is_extreme_turnover": bool(getattr(signal, "is_extreme_turnover", False)),
                "volume_ratio_to_ma50": float(getattr(signal, "volume_ratio_to_ma50", 0) or 0),
                "volume_abnormal_score": float(getattr(signal, "volume_abnormal_score", 0) or 0),
                "is_volume_breakout": bool(getattr(signal, "is_volume_breakout", False)),
                "is_double_volume": bool(getattr(signal, "is_double_volume", False)),
                "is_high_volume_bar": bool(getattr(signal, "is_high_volume_bar", False)),
                "tail_amount": float(getattr(signal, "tail_amount", 0) or 0),
                "tail_amount_ratio": float(getattr(signal, "tail_amount_ratio", 0) or 0),
                "tail_unmatched_buy_order": float(getattr(signal, "tail_unmatched_buy_order", 0) or 0),
                "tail_abnormal_score": float(getattr(signal, "tail_abnormal_score", 0) or 0),
                "has_tail_rush_buy": bool(getattr(signal, "has_tail_rush_buy", False)),
                "has_tail_large_unmatched_bid": bool(getattr(signal, "has_tail_large_unmatched_bid", False)),
                "hot_money_buy_names": list(getattr(signal, "hot_money_buy_names", []) or []),
                "institution_net_buy": float(getattr(signal, "institution_net_buy", 0) or 0),
                "institution_seat_count": int(getattr(signal, "institution_seat_count", 0) or 0),
                "has_hot_money_buy": bool(getattr(signal, "has_hot_money_buy", False)),
                "has_institution_buy": bool(getattr(signal, "has_institution_buy", False)),
                "abnormal_labels": [str(x) for x in labels],
                "abnormal_composite_score": composite,
                "conclusion": str(getattr(signal, "conclusion", "") or ""),
                "evidence": getattr(signal, "evidence", {}) or {},
                "source_type": "new_chain_job",
                "source_trace_id": "",
                "source_trace": {},
                "source_version": "v1.0",
                "rule_version": "new_chain_gateway",
            })

        # ── Step 5: 写入 (via Gateway) ──
        written = 0
        if signals:
            try:
                written = await gw.upsert_stock_abnormal_signal_rows(signals)
            except Exception as e:
                return BuildResult(name="build_stock_abnormal_signal", trade_date=td_str,
                                   affected_rows=0, status=f"failed: upsert error: {e}")

        return BuildResult(
            name="build_stock_abnormal_signal",
            trade_date=td_str,
            affected_rows=written,
            status="ok" if written > 0 else "ok_no_signals",
        )
