from __future__ import annotations

import hashlib
from dataclasses import dataclass

from stock_service.models import PreMarketAuctionSignal, PreMarketAuctionSignalValidation


@dataclass(frozen=True)
class AuctionValidationMarketInput:
    close_pct: float
    close_price: float
    hit_limit_up: bool
    close_rank_order: int
    close_is_leader: bool
    has_daily_result: bool = True


class AuctionSignalValidationService:
    """
    第一版仅做日频结果验证：
    - strong 是否兑现为强势收盘/涨停
    - watch 是否至少保持正反馈
    - invalid 是否确实应放弃
    """

    def derive_validation_result(
        self,
        signal: PreMarketAuctionSignal,
        market: AuctionValidationMarketInput,
    ) -> tuple[str, bool, str]:
        if not market.has_daily_result:
            return "pending_daily_result", False, "当日日频结果尚未入库，暂不做盘后验证"
        level = signal.auction_signal_level
        close_pct = market.close_pct

        if level == "strong":
            if market.hit_limit_up or close_pct >= 5.0:
                return "confirmed_strong", True, "强信号兑现为强势收盘"
            if close_pct >= 0:
                return "partial_strong", False, "强信号未充分兑现，仅维持正反馈"
            return "failed_strong", False, "强信号未兑现，收盘转弱"

        if level == "watch":
            if market.hit_limit_up or close_pct >= 3.0:
                return "watch_upgraded", True, "观察信号升级为强势表现"
            if close_pct >= 0:
                return "watch_neutral", True, "观察信号维持中性偏强"
            return "watch_failed", False, "观察信号失效，收盘走弱"

        if level in {"weak", "invalid"}:
            if close_pct <= 0 and not market.hit_limit_up:
                return "reject_confirmed", True, "放弃判断正确，未出现强兑现"
            return "reject_missed", False, "放弃判断失误，后续走势偏强"

        return "unknown", False, "无可用验证结论"

    def build_validation(
        self,
        signal: PreMarketAuctionSignal,
        market: AuctionValidationMarketInput,
    ) -> PreMarketAuctionSignalValidation:
        validation_result, signal_validated, validation_note = self.derive_validation_result(signal, market)
        trace_id = hashlib.md5(
            f"{signal.trade_date}|{signal.stock_id}|{signal.subject_key}|{signal.auction_signal_level}|{market.close_pct:.2f}|{market.hit_limit_up}".encode(
                "utf-8"
            )
        ).hexdigest()[:16]
        return PreMarketAuctionSignalValidation(
            trade_date=signal.trade_date,
            stock_id=signal.stock_id,
            stock_name=signal.stock_name,
            subject_key=signal.subject_key,
            theme_name=signal.theme_name,
            role_label=signal.role_label,
            auction_signal_level=signal.auction_signal_level,
            auction_signal_score=signal.auction_signal_score,
            signal_type=signal.signal_type,
            action_today=signal.action_today,
            close_pct=market.close_pct,
            close_price=market.close_price,
            hit_limit_up=market.hit_limit_up,
            close_rank_order=market.close_rank_order,
            close_is_leader=market.close_is_leader,
            validation_result=validation_result,
            signal_validated=signal_validated,
            validation_note=validation_note,
            source_trace_id=trace_id,
            source_trace={
                "validation_mode": "daily_only",
                "close_pct": market.close_pct,
                "hit_limit_up": market.hit_limit_up,
                "close_rank_order": market.close_rank_order,
                "close_is_leader": market.close_is_leader,
            },
        )
