from __future__ import annotations

from stock_processing_service.application.services.post_market_engine_report_composer import (
    PostMarketEngineReportComposer,
)
from stock_processing_service.application.services.post_market_evidence_layer_composer import (
    PostMarketEvidenceLayerComposer,
)


def _sample_evidence_doc() -> dict[str, object]:
    return {
        "market_summary": {
            "market_bias": "弱势",
            "action_bias": "防守",
            "breadth_status": "偏弱",
            "short_term_sentiment_status": "中性偏弱",
            "relay_sentiment_status": "谨慎",
            "intraday_fade_status": "分歧",
            "conclusion": "观察为主",
            "highlights": ["热点轮动明显", "主线分歧仍在"],
            "risk_flags": ["指数偏弱", "情绪回落"],
        },
        "market_overview_review": {
            "theme_limitup_matrix": {
                "columns": [
                    {
                        "subject_key": "pcb",
                        "theme_name": "PCB",
                        "limit_up_count": 8,
                        "active_mainline": True,
                        "lifecycle_state": "divergence",
                        "trade_action": "主线分歧",
                    },
                    {
                        "subject_key": "power",
                        "theme_name": "电力运营",
                        "limit_up_count": 5,
                        "active_mainline": True,
                        "lifecycle_state": "fade_watch",
                        "trade_action": "观察",
                    },
                    {
                        "subject_key": "cpo",
                        "theme_name": "CPO",
                        "limit_up_count": 4,
                        "active_mainline": False,
                        "lifecycle_state": "watch",
                        "trade_action": "轮动观察",
                    },
                ],
                "max_rows": 0,
                "count_method": "display_by_theme",
            },
            "limit_up_total": 17,
            "limit_down_total": 0,
            "up_count": 2860,
            "down_count": 1220,
            "total_amount": 123456789012,
            "diagnostics": {"theme_count": 3, "stock_count": 12},
        },
        "market_regime_review": {
            "broad_market_regime": "bearish_adverse",
            "short_term_sentiment": "weak",
            "mainline_environment": "observe_only",
            "allow_trade": False,
            "trade_mode": "no_trade",
            "position_limit": 0,
            "no_trade_blocking_rule": "broad_market_regime_bearish_adverse",
            "no_trade_reasons": ["大盘弱势不利"],
            "index_data_ready": True,
            "index_technical_reviews": [
                {
                    "index_code": "000001.SH",
                    "index_name": "上证指数",
                    "trend_state": "bearish_trend",
                    "support_level": 3100,
                    "resistance_level": 3200,
                    "index_trade_hint": "关注支撑是否失守",
                }
            ],
        },
        "mainline_daily_states": [
            {
                "mainline_id": "pcb",
                "mainline_name": "PCB",
                "canonical_subject_key": "pcb",
                "lifecycle_state": "divergence",
                "mainline_strength_score": 86.2,
                "fade_risk_score": 27.5,
                "strong_pool_count": 8,
                "d1_count": 1,
                "focus_count": 0,
                "action_advice": "观察分歧修复",
                "conclusion": "主线仍有资金，但处于分歧阶段",
            },
            {
                "mainline_id": "power",
                "mainline_name": "电力运营",
                "canonical_subject_key": "power",
                "lifecycle_state": "watch",
                "mainline_strength_score": 83.0,
                "fade_risk_score": 38.0,
                "strong_pool_count": 4,
                "d1_count": 0,
                "focus_count": 0,
                "action_advice": "观察",
                "conclusion": "资金活跃但确认不足",
            },
            {
                "mainline_id": "cpo",
                "mainline_name": "CPO",
                "canonical_subject_key": "cpo",
                "lifecycle_state": "watch",
                "mainline_strength_score": 79.0,
                "fade_risk_score": 33.0,
                "strong_pool_count": 3,
                "d1_count": 0,
                "focus_count": 0,
                "action_advice": "观察",
                "conclusion": "轮动观察",
            },
            {
                "mainline_id": "robot",
                "mainline_name": "机器人",
                "canonical_subject_key": "robot",
                "lifecycle_state": "fade_confirmed",
                "mainline_strength_score": 60.0,
                "fade_risk_score": 61.0,
                "strong_pool_count": 2,
                "d1_count": 0,
                "focus_count": 0,
                "action_advice": "回避",
                "conclusion": "退潮确认",
            },
        ],
        "active_mainline_universe": {
            "trade_date": "2026-06-02",
            "active_mainlines": [
                {"mainline_id": "pcb", "mainline_name": "PCB", "canonical_subject_key": "pcb"},
                {"mainline_id": "power", "mainline_name": "电力运营", "canonical_subject_key": "power"},
                {"mainline_id": "cpo", "mainline_name": "CPO", "canonical_subject_key": "cpo"},
                {"mainline_id": "robot", "mainline_name": "机器人", "canonical_subject_key": "robot"},
            ],
            "active_subject_keys": ["pcb", "power", "cpo", "robot"],
        },
        "post_market_decision_v2": {
            "trading_permission": {"allow_trade": False, "trade_mode": "no_trade", "position_limit": 0},
            "weak_to_strong_d1_reviews": [
                {
                    "stock_id": "1",
                    "stock_name": "A",
                    "mainline_id": "pcb",
                    "subject_key": "pcb",
                    "theme_name": "PCB",
                    "candidate_level": "observe_only",
                }
            ],
            "next_day_focus_stocks": [],
            "strong_stock_pool_reviews": [
                {
                    "stock_id": "1",
                    "stock_name": "A",
                    "mainline_id": "pcb",
                    "mainline_name": "PCB",
                    "subject_key": "pcb",
                    "theme_name": "PCB",
                    "pool_entry_type": "formal",
                    "relay_role": "leader",
                    "watch_score": 88,
                    "support_score": 70,
                    "watch_priority": 1,
                },
                {
                    "stock_id": "2",
                    "stock_name": "B",
                    "mainline_id": "power",
                    "mainline_name": "电力运营",
                    "subject_key": "power",
                    "theme_name": "电力运营",
                    "pool_entry_type": "formal",
                    "relay_role": "runner",
                    "watch_score": 84,
                    "support_score": 66,
                    "watch_priority": 2,
                },
                {
                    "stock_id": "4",
                    "stock_name": "D",
                    "mainline_id": "cpo",
                    "mainline_name": "CPO",
                    "subject_key": "cpo",
                    "theme_name": "CPO",
                    "pool_entry_type": "formal",
                    "relay_role": "runner",
                    "watch_score": 80,
                    "support_score": 60,
                    "watch_priority": 3,
                },
            ],
            "diagnostics": {"d1_algorithm": "BuildWeakToStrongCandidateUseCase"},
        },
        "abnormal_reviews": [
            {
                "stock_id": "1",
                "stock_code": "1",
                "stock_name": "A",
                "subject_key": "pcb",
                "theme_name": "PCB",
                "abnormal_score": 86.2,
                "volume_ratio": 2.1,
                "conclusion": "放量异动",
                "labels": ["异动", "放量"],
            }
        ],
        "money_flow_reviews": [
            {
                "stock_id": "2",
                "stock_code": "2",
                "stock_name": "B",
                "subject_key": "power",
                "theme_name": "电力运营",
                "active_mainline": True,
                "in_layer_c": False,
                "mainline_name": "电力运营",
                "lifecycle_state": "watch",
                "trade_action": "主线参与",
                "main_net_inflow": 460000000,
                "money_flow_tier": "强",
                "role_enhanced": "主线加速",
                "conclusion": "资金持续流入",
                "kline": {"position_label": "强势", "pattern_labels": ["量价齐升"]},
            }
        ],
        "dragon_tiger_reviews": [
            {
                "stock_id": "3",
                "stock_code": "3",
                "stock_name": "C",
                "subject_key": "robot",
                "theme_name": "机器人",
                "net_buy": -21000000,
                "buy_amount": 30000000,
                "sell_amount": 51000000,
                "seat_type": "HOT_MONEY",
                "hot_money_name": "某游资",
                "reason": "分歧出货",
                "side_summary": "净卖出",
                "seat_summary": ["某游资"],
            }
        ],
        "stock_capital_reviews": [
            {
                "stock_id": "4",
                "stock_code": "4",
                "stock_name": "D",
                "subject_key": "cpo",
                "theme_name": "CPO",
                "main_net_inflow": 120000000,
                "rank_order": 1,
                "f10_capital": {
                    "source": "tdx_f10",
                    "section": "资金动向",
                    "summary": "主力净流入1.07亿，超大单净流入1.26亿",
                    "capital_flow": {"summary": "主力净流入1.07亿", "main_net_inflow": 107000000, "latest_date": "2026-06-12"},
                    "trade_date": "2026-06-12",
                    "dragon_tiger": {"latest_date": "2025-12-25", "summary": "●交易日期:2025-12-25 信息类型:跌幅偏离值达7%的证券"},
                    "margin_trading": {"summary": "融资偿还额2346.53万元"},
                },
            }
        ],
        "evidence_alignment_index": {
            "by_stock": {
                "1": {
                    "active_mainline": True,
                    "mainline_name": "PCB",
                    "lifecycle_state": "divergence",
                    "in_layer_c": False,
                    "is_d1_candidate": True,
                    "is_focus_stock": False,
                    "trade_action": "观察",
                },
                "2": {
                    "active_mainline": True,
                    "mainline_name": "电力运营",
                    "lifecycle_state": "watch",
                    "in_layer_c": False,
                    "is_d1_candidate": False,
                    "is_focus_stock": False,
                    "trade_action": "主线参与",
                },
                "3": {
                    "active_mainline": False,
                    "mainline_name": "机器人",
                    "lifecycle_state": "fade_confirmed",
                    "in_layer_c": False,
                    "is_d1_candidate": False,
                    "is_focus_stock": False,
                    "trade_action": "回避",
                },
                "4": {
                    "active_mainline": True,
                    "mainline_name": "CPO",
                    "lifecycle_state": "watch",
                    "in_layer_c": True,
                    "is_d1_candidate": False,
                    "is_focus_stock": False,
                    "trade_action": "分歧低吸",
                },
            },
            "indexed_stocks": 4,
            "indexed_subjects": 0,
        },
    }


def test_post_market_evidence_layer_composer_groups_and_items() -> None:
    doc = _sample_evidence_doc()
    review = PostMarketEvidenceLayerComposer().compose(
        doc,
        evidence_alignment_index=doc["evidence_alignment_index"],  # type: ignore[arg-type]
    )

    assert review["summary"]
    assert len(review["evidence_groups"]) >= 4
    assert len(review["abnormal_evidence"]) == 1
    assert len(review["money_flow_evidence"]) == 1
    assert len(review["dragon_tiger_evidence"]) == 1
    assert len(review["stock_capital_evidence"]) == 1
    assert review["stock_capital_evidence"][0]["amount"] == 107000000
    assert "主力净流入1.07亿" in review["stock_capital_evidence"][0]["description"]
    assert "龙虎榜" not in review["stock_capital_evidence"][0]["description"]
    groups = {group["group_key"]: group for group in review["evidence_groups"]}
    assert groups["d1"]["item_count"] == 1
    assert groups["layer_c"]["item_count"] == 1
    assert groups["mainline"]["item_count"] == 1
    assert groups["risk"]["item_count"] == 1
    assert groups["d1"]["top_stocks"]
    assert review["source"] == "structured"


def test_post_market_evidence_layer_composer_filters_institution_dragon_tiger_rows() -> None:
    doc = _sample_evidence_doc()
    doc["dragon_tiger_reviews"] = [  # type: ignore[index]
        {
            "stock_id": "5",
            "stock_code": "5",
            "stock_name": "E",
            "subject_key": "bank",
            "theme_name": "银行",
            "net_buy": 12000000,
            "buy_amount": 30000000,
            "sell_amount": 18000000,
            "seat_type": "INSTITUTION",
            "institution_seat_count": 10,
            "reason": "机构席位",
            "side_summary": "净买入",
        }
    ]

    review = PostMarketEvidenceLayerComposer().compose(
        doc,
        evidence_alignment_index=doc["evidence_alignment_index"],  # type: ignore[arg-type]
    )

    assert review["dragon_tiger_evidence"] == []
    assert review["diagnostics"]["dragon_tiger_count"] == 0


def test_post_market_evidence_layer_composer_uses_legacy_dragon_tiger_sections() -> None:
    doc = _sample_evidence_doc()
    doc["dragon_tiger_reviews"] = [  # type: ignore[index]
        {
            "stock_id": "5",
            "stock_code": "5",
            "stock_name": "E",
            "subject_key": "bank",
            "theme_name": "银行",
            "net_buy": 12000000,
            "buy_amount": 30000000,
            "sell_amount": 18000000,
            "seat_type": "INSTITUTION",
            "institution_seat_count": 10,
            "reason": "机构席位",
            "side_summary": "净买入",
        }
    ]
    doc["report"] = {
        "sections": [
            {
                "heading": "龙虎榜",
                "items": [
                    "成都系：有色十大第一 / 锡业股份(000960) / 买入0.99亿",
                    "章盟主系：数据中心电力设备 / 福达合金(603045) / 买入1.15亿",
                ],
            }
        ]
    }

    review = PostMarketEvidenceLayerComposer().compose(
        doc,
        evidence_alignment_index=doc["evidence_alignment_index"],  # type: ignore[arg-type]
    )

    assert len(review["dragon_tiger_evidence"]) == 2
    assert review["dragon_tiger_evidence"][0]["stock_name"] in {"锡业股份", "福达合金"}
    assert review["diagnostics"]["dragon_tiger_count"] == 2


def test_post_market_evidence_layer_composer_dedupes_stock_capital_by_stock_id() -> None:
    doc = _sample_evidence_doc()
    doc["stock_capital_reviews"] = [  # type: ignore[index]
        {
            "stock_id": "300581",
            "stock_code": "300581",
            "stock_name": "晨曦航空",
            "subject_key": "air",
            "theme_name": "军工",
            "main_net_inflow": 12000000,
            "rank_order": 1,
        },
        {
            "stock_id": "300581.SZ",
            "stock_code": "300581.SZ",
            "stock_name": "晨曦航空",
            "subject_key": "air2",
            "theme_name": "导弹",
            "main_net_inflow": 9000000,
            "rank_order": 2,
        },
        {
            "stock_id": "688010",
            "stock_code": "688010",
            "stock_name": "福光股份",
            "subject_key": "optic",
            "theme_name": "光学",
            "main_net_inflow": 8000000,
            "rank_order": 3,
        },
    ]

    review = PostMarketEvidenceLayerComposer().compose(
        doc,
        evidence_alignment_index=doc["evidence_alignment_index"],  # type: ignore[arg-type]
    )

    assert len(review["stock_capital_evidence"]) == 2
    assert {row["stock_id"] for row in review["stock_capital_evidence"]} == {"300581", "688010"}


def test_post_market_engine_report_composer_includes_evidence_layer_review() -> None:
    doc = _sample_evidence_doc()
    report = PostMarketEngineReportComposer().compose(doc)  # type: ignore[arg-type]

    assert "evidence_layer_review" in report
    evidence_layer = report["evidence_layer_review"]
    assert evidence_layer["summary"]
    assert len(evidence_layer["evidence_groups"]) >= 3
    assert len(evidence_layer["abnormal_evidence"]) == 1
    assert len(evidence_layer["money_flow_evidence"]) == 1
    assert len(evidence_layer["dragon_tiger_evidence"]) == 1
    assert len(evidence_layer["stock_capital_evidence"]) == 1
