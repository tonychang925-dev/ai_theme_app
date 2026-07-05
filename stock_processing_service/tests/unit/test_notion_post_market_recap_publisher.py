from __future__ import annotations

import json
from typing import Any

from stock_processing_service.publishers.notion_post_market_recap_publisher import (
    NotionPostMarketRecapPublisher,
)


LEGACY_HEADINGS = {
    "一、复盘概览",
    "二、弱转强候选 Top",
    "三、正式候选",
    "四、观察候选",
    "五、强势股观察池历史",
    "六、候选诊断",
    "七、旧链文本报告（兼容）",
}


def _heading_text(block: dict[str, Any]) -> str | None:
    block_type = block.get("type")
    if block_type not in {"heading_1", "heading_2", "heading_3"}:
        return None
    payload = block.get(str(block_type))
    if not isinstance(payload, dict):
        return None
    rich_text = payload.get("rich_text")
    if not isinstance(rich_text, list) or not rich_text:
        return None
    first = rich_text[0]
    if not isinstance(first, dict):
        return None
    text = first.get("text")
    if not isinstance(text, dict):
        return None
    content = text.get("content")
    return str(content) if content is not None else None


def _headings(blocks: list[dict[str, Any]]) -> list[str]:
    return [text for block in blocks if (text := _heading_text(block))]


def test_tc_notion_001_empty_snapshot_has_only_data_quality_not_empty_business_sections() -> None:
    blocks = NotionPostMarketRecapPublisher.build_blocks({"recap_doc": {}}, "2026-07-03")
    headings = _headings(blocks)

    assert headings == ["2026-07-03 盘后复盘", "数据质量"]
    assert LEGACY_HEADINGS.isdisjoint(headings)


def test_tc_notion_002_engine_sections_render_without_silent_loss() -> None:
    payload = {
        "recap_doc": {
            "engine_summary": {
                "allow_trade": False,
                "trade_mode": "no_trade",
                "position_limit": None,
                "no_trade_blocking_rule": "market_risk",
                "no_trade_reasons": ["市场风险不支持新开仓"],
                "next_day_strategy": "只观察修复信号",
                "conclusion": "防守",
            },
            "market_regime_review": {
                "broad_market_regime": "bearish_adverse",
                "short_term_sentiment": "weak",
                "mainline_environment": "divergence",
                "index_data_ready": False,
            },
            "mainline_daily_states": [
                {
                    "mainline_name": "机器人",
                    "lifecycle_state": "divergence",
                    "mainline_trade_alive": True,
                    "strong_pool_count": 5,
                    "d1_count": 0,
                    "focus_count": 0,
                    "action_advice": "仅观察",
                }
            ],
        }
    }

    blocks = NotionPostMarketRecapPublisher.build_blocks(payload, "2026-07-02")
    headings = _headings(blocks)

    assert headings[:4] == ["2026-07-02 盘后复盘", "交易结论", "市场环境", "主线状态"]
    assert LEGACY_HEADINGS.isdisjoint(headings)


def test_tc_notion_003_daily_review_v2_renders_only_populated_business_modules() -> None:
    payload = {
        "recap_doc": {
            "daily_review_v2": {
                "daily_recap_essentials": {
                    "headline": "指数承压，主线分歧",
                    "summary_points": ["机器人保持活跃", "仓位继续防守"],
                    "next_day_strategy": "观察核心标的承接",
                },
                "limit_up_ladder": {
                    "summary": "2板 3只",
                    "board_rows": [
                        {
                            "board_label": "2板",
                            "stock_count": 3,
                            "stocks": [{"stock_name": "示例股份", "board_count": 2, "theme_name": "机器人"}],
                        }
                    ],
                },
                "new_high_summary": {
                    "summary": "今日创新高 6只",
                    "industry_summary": [
                        {"industry_name": "电子", "count": 3, "representative_stocks": [{"stock_name": "样例科技"}]}
                    ],
                },
                "seat_money_summary": {
                    "summary": "机构净买入集中于电子",
                    "institution_top_buys": [
                        {"stock_name": "样例科技", "net_buy": 10000000, "theme_name": "电子"}
                    ],
                },
                "watchlist_reviews": [],
                "dragon_tiger_reviews": [],
            }
        }
    }

    blocks = NotionPostMarketRecapPublisher.build_blocks(payload, "2026-07-02")
    headings = _headings(blocks)

    assert headings == [
        "2026-07-02 盘后复盘",
        "今日复盘要点",
        "涨停结构",
        "创新高与行业趋势",
        "资金验证",
    ]
    assert "次日计划" not in headings
    assert "龙虎榜" not in headings
    assert LEGACY_HEADINGS.isdisjoint(headings)


def test_tc_notion_004_partial_coverage_is_consolidated_in_data_quality() -> None:
    payload = {
        "recap_doc": {
            "daily_review_v2": {
                "market_summary": {
                    "conclusion": "震荡分化",
                    "highlights": ["主线内部轮动"],
                    "risk_flags": [],
                },
                "diagnostics": {
                    "module_coverage": {
                        "market_summary": {
                            "status": "ready",
                            "row_count": 1,
                            "required": True,
                            "message": "ready",
                        },
                        "watchlist_reviews": {
                            "status": "empty",
                            "row_count": 0,
                            "required": True,
                            "message": "上游观察清单未产出",
                        },
                        "theme_reviews": {
                            "status": "partial",
                            "row_count": 20,
                            "required": True,
                            "missing_fields": ["event_score", "market_score"],
                            "message": "部分字段缺失",
                        },
                    }
                },
            }
        }
    }

    headings = _headings(NotionPostMarketRecapPublisher.build_blocks(payload, "2026-07-02"))

    assert "市场摘要" in headings
    assert headings[-1] == "数据质量"
    assert LEGACY_HEADINGS.isdisjoint(headings)


def test_tc_notion_005_capital_validation_resolves_themes_and_filters_invalid_rows() -> None:
    hot_money = {
        "hot_money_name": "章盟主系",
        "net_buy": 9968936641.21,
        "buy_entries": [{"theme_name": "机器人", "stock_name": "示例股份"}],
        "sell_entries": [],
    }
    payload = {
        "recap_doc": {
            "daily_review_v2": {
                "theme_name_map": {"9014636": "机器人"},
                "seat_money_summary": {
                    "institution_top_buys": [
                        {
                            "stock_name": "示例科技",
                            "net_buy": 1125034608.3,
                            "theme_name": "9014636",
                        }
                    ],
                    "hot_money_top_buys": [hot_money],
                    "hot_money_top_sells": [
                        hot_money,
                        {
                            "hot_money_name": "成都系",
                            "net_buy": -1111583616,
                            "buy_entries": [],
                            "sell_entries": [{"theme_name": "航天材料", "stock_name": "样例材料"}],
                        },
                    ],
                },
                "theme_capital_reviews": [
                    {
                        "theme_name": "机器人",
                        "total_inflow": 0,
                        "top3_inflow": 0,
                        "cycle_stage": "divergence",
                    }
                ],
                "stock_capital_reviews": [
                    {
                        "stock_name": "示例股份",
                        "theme_name": "机器人",
                        "main_net_inflow": 0,
                    }
                ],
                "dragon_tiger_reviews": [
                    {
                        "stock_name": "示例科技",
                        "seat_type": "INSTITUTION",
                        "net_buy": 1125034608.3,
                        "side_summary": "净买入",
                    }
                ],
            }
        }
    }

    serialized = json.dumps(
        NotionPostMarketRecapPublisher.build_blocks(payload, "2026-07-03"),
        ensure_ascii=False,
    )

    assert "9014636" not in serialized
    assert serialized.count("章盟主系") == 1
    assert "成都系" in serialized
    assert "题材资金 Top" not in serialized
    assert "个股资金 Top" not in serialized
    assert "龙虎榜" not in serialized


def test_tc_notion_006_one_to_two_plan_uses_human_fields_instead_of_internal_ids() -> None:
    payload = {
        "recap_doc": {
            "daily_review_v2": {
                "theme_name_map": {"9014636": "机器人"},
                "watchlists": {
                    "one_to_two": {
                        "items": [
                            {
                                "stock_name": "埃斯顿",
                                "subject_key": "9014636",
                                "subject_name": "机器人",
                                "watch_level": "C",
                                "tomorrow_plan": {
                                    "expected_behavior": "市场环境 no_trade，仅观察不主动关注。",
                                    "auction_watch": ["仅保留数据跟踪，不做主动观察。"],
                                },
                            }
                        ]
                    }
                },
            }
        }
    }

    serialized = json.dumps(
        NotionPostMarketRecapPublisher.build_blocks(payload, "2026-07-03"),
        ensure_ascii=False,
    )

    assert "9014636" not in serialized
    assert "机器人" in serialized
    assert "C级观察" in serialized
    assert "市场环境 不交易，仅观察不主动关注。" in serialized
    assert "no_trade" not in serialized
    assert "仅保留数据跟踪，不做主动观察。" in serialized


def test_tc_notion_007_data_quality_hides_legacy_internals_and_translates_actionable_issue() -> None:
    payload = {
        "recap_doc": {
            "daily_review_v2": {
                "diagnostics": {
                    "module_coverage": {
                        "theme_reviews": {
                            "status": "partial",
                            "row_count": 20,
                            "required": True,
                            "missing_fields": ["event_score", "market_score"],
                        },
                        "watchlist_reviews": {
                            "status": "empty",
                            "row_count": 0,
                            "required": True,
                            "message": "legacy section is available",
                        },
                        "theme_driver_events": {
                            "status": "empty",
                            "row_count": 0,
                            "required": True,
                            "message": "legacy section count=0",
                        },
                    },
                    "warnings": [
                        "legacy sections are available; modules without ready structured rows should fallback"
                    ],
                }
            }
        }
    }

    serialized = json.dumps(
        NotionPostMarketRecapPublisher.build_blocks(payload, "2026-07-03"),
        ensure_ascii=False,
    )

    assert "legacy" not in serialized
    assert "watchlist_reviews" not in serialized
    assert "theme_driver_events" not in serialized
    assert "主线题材" in serialized
    assert "事件分、市场分" in serialized


def test_tc_notion_008_engine_gate_overrides_conflicting_summary_and_conditional_mainline_state() -> None:
    payload = {
        "recap_doc": {
            "engine_summary": {
                "allow_trade": False,
                "trade_mode": "no_trade",
                "position_limit": 0,
                "no_trade_blocking_rule": "short_term_sentiment_dead",
                "no_trade_reasons": ["短线情绪死亡"],
                "conclusion": "当前不交易",
            },
            "market_regime_review": {
                "broad_market_regime": "downtrend_rebound",
                "short_term_sentiment": "dead",
                "mainline_environment": "mainline_tradable",
            },
            "index_technical_reviews": [{"index_code": str(index)} for index in range(6)],
            "mainline_daily_states": [
                {
                    "mainline_name": "机器人",
                    "lifecycle_state": "divergence",
                    "mainline_trade_alive": True,
                    "strong_pool_count": 5,
                    "action_advice": "分歧低吸",
                }
            ],
            "daily_review_v2": {
                "market_summary": {
                    "source": "llm",
                    "action_bias": "主做主线",
                    "market_overview": "短线情绪强，市场定性为进攻格局。",
                    "risk_notes": ["量能萎缩"],
                },
                "limit_up_ladder": {
                    "summary": "暂无结构化连板梯队数据",
                    "board_rows": [
                        {"board_label": "4板", "stock_count": 0, "stocks": []},
                        {"board_label": "首板", "stock_count": 0, "stocks": []},
                    ],
                    "diagnostics": {"source": "none"},
                },
                "limit_up_theme_events": {
                    "summary": "涨停事件聚焦机器人",
                    "rows": [
                        {
                            "theme_name": "机器人",
                            "limit_up_count": 44,
                            "representative_stocks": [{"stock_name": "中大力德"}],
                            "catalyst_events": [
                                {
                                    "summary": "【驱动事件：宇树科技IPO获批】\n宇树科技IPO获批，后续长篇新闻正文不应完整进入表格。（新闻来源：测试）",
                                    "match_reason": "direct_theme_name_hit",
                                },
                                {
                                    "summary": "与机器人无关且没有匹配依据的新闻",
                                    "match_reason": None,
                                },
                                {
                                    "summary": "机器人产业链订单持续增长",
                                    "match_reason": None,
                                },
                            ],
                        }
                    ],
                },
            },
        }
    }

    serialized = json.dumps(
        NotionPostMarketRecapPublisher.build_blocks(payload, "2026-07-03"),
        ensure_ascii=False,
    )

    for internal_code in (
        "no_trade",
        "short_term_sentiment_dead",
        "downtrend_rebound",
        '"dead"',
        "mainline_tradable",
        "divergence",
    ):
        assert internal_code not in serialized
    assert "进攻格局" not in serialized
    assert "市场摘要与交易结论冲突" in serialized
    assert "指数数据：就绪（6）" in serialized
    assert "4板" not in serialized
    assert "首板" not in serialized
    assert "仅观察" in serialized
    assert "等待解除全局交易阻断" in serialized
    assert "宇树科技IPO获批" in serialized
    assert "机器人产业链订单持续增长" in serialized
    assert "后续长篇新闻正文不应完整进入表格" not in serialized
    assert "与机器人无关且没有匹配依据的新闻" not in serialized


def test_tc_notion_009_new_high_trend_excludes_unclassified_bucket() -> None:
    payload = {
        "recap_doc": {
            "daily_review_v2": {
                "new_high_summary": {
                    "summary": "今日创新高 71 家，集中在 未分类、工业机器人。",
                    "today_count": 71,
                    "industry_summary": [
                        {
                            "industry_name": "未分类",
                            "count": 17,
                            "representative_stocks": [{"stock_name": "未知股票"}],
                        },
                        {
                            "industry_name": "工业机器人",
                            "count": 2,
                            "representative_stocks": [{"stock_name": "埃斯顿"}],
                        },
                    ],
                    "representative_stocks": [{"stock_name": "绿的谐波"}],
                }
            }
        }
    }

    serialized = json.dumps(
        NotionPostMarketRecapPublisher.build_blocks(payload, "2026-07-03"),
        ensure_ascii=False,
    )

    assert "未分类" not in serialized
    assert "今日创新高 71 家" in serialized
    assert "工业机器人" in serialized
    assert "绿的谐波" in serialized


def test_tc_notion_010_filters_empty_mainlines_invalid_themes_and_duplicate_labels() -> None:
    payload = {
        "recap_doc": {
            "engine_summary": {
                "allow_trade": False,
                "trade_mode": "no_trade",
                "no_trade_blocking_rule": "short_term_sentiment_dead",
            },
            "daily_recap_essentials": {
                "headline": "仅观察",
                "summary_points": [
                    "市场状态：downtrend_rebound，短线情绪 dead，主线环境 mainline_tradable，交易模式 no_trade；阻断规则 short_term_sentiment_dead。"
                ],
            },
            "mainline_daily_states": [
                {
                    "mainline_name": "机器人",
                    "lifecycle_state": "divergence",
                    "mainline_trade_alive": True,
                    "strong_pool_count": 5,
                },
                {
                    "mainline_name": "空池主题",
                    "lifecycle_state": "start",
                    "mainline_trade_alive": True,
                    "strong_pool_count": 0,
                },
            ],
            "daily_review_v2": {
                "limit_up_theme_events": {
                    "rows": [
                        {
                            "theme_name": "热",
                            "limit_up_count": 3,
                            "representative_stocks": [{"stock_name": "示例股份"}],
                        },
                        {
                            "theme_name": "机器人",
                            "limit_up_count": 10,
                            "representative_stocks": [{"stock_name": "中大力德"}],
                        },
                    ]
                }
            },
        }
    }

    serialized = json.dumps(
        NotionPostMarketRecapPublisher.build_blocks(payload, "2026-07-03"),
        ensure_ascii=False,
    )

    assert "空池主题" not in serialized
    assert '"content": "热"' not in serialized
    assert "短线情绪 情绪冰点" not in serialized
    assert "短线情绪冰点" in serialized
    assert "主线环境 主线具备结构性机会" not in serialized


def test_tc_notion_011_mainline_table_uses_same_active_universe_as_summary() -> None:
    payload = {
        "recap_doc": {
            "mainline_daily_states": [
                {"mainline_name": "机器人", "subject_key": "9014636", "strong_pool_count": 5},
                {"mainline_name": "低空经济", "subject_key": "9015778", "strong_pool_count": 7},
            ],
            "daily_review_v2": {
                "limit_up_theme_matrix": {
                    "columns": [
                        {
                            "theme_name": "机器人",
                            "subject_key": "9014636",
                            "active_mainline": True,
                        },
                        {
                            "theme_name": "低空经济",
                            "subject_key": "9015778",
                            "active_mainline": False,
                        },
                    ]
                }
            },
        }
    }

    serialized = json.dumps(
        NotionPostMarketRecapPublisher.build_blocks(payload, "2026-07-03"),
        ensure_ascii=False,
    )

    assert "机器人" in serialized
    assert "低空经济" not in serialized


def test_tc_notion_012_subject_key_mapping_overrides_stale_plan_theme_name() -> None:
    payload = {
        "recap_doc": {
            "daily_review_v2": {
                "theme_name_map": {"9015778": "低空经济"},
                "watchlists": {
                    "one_to_two": {
                        "items": [
                            {
                                "stock_name": "朗迪集团",
                                "subject_key": "9015778",
                                "subject_name": "存储芯片",
                                "watch_level": "C",
                            }
                        ]
                    }
                },
            }
        }
    }

    serialized = json.dumps(
        NotionPostMarketRecapPublisher.build_blocks(payload, "2026-07-03"),
        ensure_ascii=False,
    )

    assert "低空经济" in serialized
    assert "存储芯片" not in serialized
