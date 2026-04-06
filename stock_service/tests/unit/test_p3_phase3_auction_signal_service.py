from __future__ import annotations

from stock_service.services.auction_signal_service import (
    AuctionCandidateInput,
    AuctionSignalService,
    AuctionSnapshotInput,
    AuctionTimelinePoint,
)


def _candidate(**kwargs) -> AuctionCandidateInput:
    base = dict(
        trade_date="2026-04-03",
        stock_id="600001",
        stock_name="测试龙头",
        subject_key="9018216",
        theme_name="石油",
        role_label="龙头",
        is_main_theme=True,
        action_bias="主做",
        is_reversal_watch=False,
    )
    base.update(kwargs)
    return AuctionCandidateInput(**base)


def _snapshot_input(candidate: AuctionCandidateInput, **kwargs) -> AuctionSnapshotInput:
    base = dict(
        candidate=candidate,
        pre_close=10.0,
        auction_open_price=10.42,
        auction_volume=100000.0,
        auction_amount=50000000.0,
        prev_day_max_intraday_amount=90000000.0,
        last_minute_amount=20000000.0,
        points=(
            AuctionTimelinePoint("09:20:00", 10.18, 5000000.0),
            AuctionTimelinePoint("09:22:00", 10.20, 12000000.0),
            AuctionTimelinePoint("09:24:00", 10.33, 30000000.0),
            AuctionTimelinePoint("09:24:30", 10.38, 38000000.0),
            AuctionTimelinePoint("09:25:00", 10.42, 50000000.0),
        ),
    )
    base.update(kwargs)
    return AuctionSnapshotInput(**base)


def test_candidate_eligibility_respects_mainline_and_role_filter():
    service = AuctionSignalService()
    assert service.is_candidate_eligible(_candidate(role_label="龙头")) is True
    assert service.is_candidate_eligible(_candidate(role_label="补涨")) is False
    assert service.is_candidate_eligible(_candidate(is_main_theme=False, action_bias="放弃")) is False
    assert service.is_candidate_eligible(_candidate(is_main_theme=False, action_bias="关注弱转强", role_label="卡位")) is True


def test_build_snapshot_extracts_core_auction_features():
    service = AuctionSignalService()
    snapshot = service.build_snapshot(_snapshot_input(_candidate()))

    assert snapshot.auction_open_pct > 3.0
    assert snapshot.carry_ratio > 0.5
    assert snapshot.last_minute_ratio > 0.35
    assert snapshot.is_red_zone is True
    assert snapshot.has_end_spike is True
    assert snapshot.has_end_drop is False
    assert "red_zone" in snapshot.shape_features


def test_build_signal_marks_strong_leader_when_carry_and_end_spike_are_both_good():
    service = AuctionSignalService()
    candidate = _candidate(position_label="接近前高", pattern_labels=("放量突破",))
    snapshot = service.build_snapshot(_snapshot_input(candidate))

    signal = service.build_signal(snapshot, candidate)

    assert signal.auction_signal_level == "strong"
    assert signal.signal_type == "龙头承接强"
    assert signal.leader_status == "继续成立"
    assert signal.action_today == "act"
    assert signal.hard_reject_reason == ""
    assert any("K线位置 接近前高" in item for item in signal.evidence)
    assert any("K线形态 放量突破" in item for item in signal.evidence)


def test_build_signal_marks_invalid_when_end_drop_and_path_unstable():
    service = AuctionSignalService()
    candidate = _candidate(role_label="卡位")
    payload = _snapshot_input(
        candidate,
        auction_open_price=9.85,
        auction_amount=10000000.0,
        last_minute_amount=1000000.0,
        prev_day_max_intraday_amount=100000000.0,
        points=(
            AuctionTimelinePoint("09:20:00", 10.05, 2000000.0),
            AuctionTimelinePoint("09:22:00", 9.90, 4000000.0),
            AuctionTimelinePoint("09:24:00", 10.15, 8500000.0),
            AuctionTimelinePoint("09:24:30", 9.70, 9200000.0),
            AuctionTimelinePoint("09:25:00", 9.55, 10000000.0),
        ),
    )
    snapshot = service.build_snapshot(payload)
    signal = service.build_signal(snapshot, candidate)

    assert signal.auction_signal_level == "invalid"
    assert signal.action_today == "avoid"
    assert signal.hard_reject_reason in {"路径不稳", "末端跳水", "承接不足", "低开不及预期"}
