from __future__ import annotations

import copy
import importlib.util
import sys
from pathlib import Path


MODULE_PATH = Path(__file__).with_name("m8_extractor.py")
SPEC = importlib.util.spec_from_file_location("m8_extractor", MODULE_PATH)
assert SPEC and SPEC.loader
m8 = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = m8
SPEC.loader.exec_module(m8)


def _minimal_payload() -> dict:
    payload = copy.deepcopy(m8.M8_TEMPLATE)
    payload.update(
        {
            "extraction_status": "success",
            "schema_version": m8.REFERENCE_SCHEMA_VERSION,
            "trade_date": "2026-07-14",
            "source_title": "7月14日复盘",
        }
    )
    payload["market_facts"].update(
        {
            "limit_up_count": 42,
            "chain_board_count": 8,
            "max_board_height": 4,
            "max_board_stock": "测试股份",
            "market_up_ratio": 0.67,
            "loss_effect_ratio": 0.12,
        }
    )
    payload["relay_ecology"].update(
        {
            "max_board_height": 4,
            "max_board_stock": "测试股份",
            "chain_board_count": 8,
            "daily_rows": [
                {
                    "date": "7.14",
                    "max_board_height": 4,
                    "first_board_success_count": 32,
                    "first_board_total_count": 40,
                    "first_board_success_rate": "80%",
                    "one_to_two_success_count": 8,
                    "one_to_two_total_count": 20,
                    "one_to_two_rate": 0.4,
                }
            ],
        }
    )
    payload["emotion_label"].update(
        {
            "market_phase": "REBOUND",
            "risk_level": "MEDIUM_HIGH",
            "phase_cn": "反弹",
            "phase_chain": ["PANIC", "REBOUND"],
        }
    )
    payload["strategy_label"].update(
        {
            "watch_points": ["观察连板修复"],
            "allowed": ["低吸核心"],
            "forbidden": ["追高后排"],
        }
    )
    payload["leader_history"] = [{"date": "7.14", "stock": "测试股份", "height": 4}]
    payload["hot_money_directions"] = [{"direction": "AI", "status": "回流"}]
    payload["limitup_themes"] = [{"theme": "AI应用", "status": "强", "stock_count": 1}]
    payload["limitup_attribution"] = [
        {
            "board_level": "4板",
            "stock_code": "600000",
            "stock_name": "测试股份",
            "limit_time": "09:35:00",
            "theme": "AI应用",
            "reason": "测试原因",
        }
    ]
    payload["board_ladder"] = [{"date": "7.14", "height": 4, "stock": "测试股份"}]
    return payload


def test_reference_markdown_roundtrip_exposes_cli_summary_fields(tmp_path):
    # TC-M8EXTRACTOR-REF-01: reference renderer must be validatable by --validate-md.
    article = m8.ArticleData(
        title="7月14日复盘",
        author="测试作者",
        publish_time="2026年7月14日 18:00",
        trade_date="2026-07-14",
        body_text="测试正文",
        images=[],
    )
    md = m8.render_markdown(article, _minimal_payload(), tmp_path / "out.md")

    parsed = m8.validate_markdown(md)

    assert parsed["schema_version"] == m8.REFERENCE_SCHEMA_VERSION
    assert parsed["extraction_status"] == "reference_markdown"
    assert parsed["quality"]["validation_passed"] is True
    assert parsed["quality"]["missing_fields"] == []
    assert "32/40, 80%" in md
    assert "| 2026-07-14 | 4 | 测试股份 |" in md


def test_reference_markdown_validation_requires_json_sections():
    # TC-M8EXTRACTOR-REF-02: template validation should fail without section-17 JSON blocks.
    md = "\n".join(
        [f"# {idx}. {title}" for idx, title in enumerate(m8.REFERENCE_SECTION_TITLES, 1)]
        + [
            "| 指标 |",
            "| 日期 | 指数势能 |",
            "| 日期 | 情绪动能 |",
            "| 日期 | 成交量(亿) |",
            "| 日期 | 最高板 | 首板封板率 |",
            "| 板型 | 代码 | 名称 | 时间 | 题材 | 原因 |",
        ]
    )

    try:
        m8.validate_markdown(md)
    except m8.ValidationError as exc:
        assert "缺少参考JSON块" in str(exc)
    else:
        raise AssertionError("validate_markdown should reject missing reference JSON blocks")


def test_known_0716_reference_profile_keeps_limitup_coverage_above_gate():
    # TC-M8EXTRACTOR-REF-03: 2026-07-16 profile has enough long-image rows but partial matrix.
    article = m8.ArticleData(
        title="7月16日，明早见",
        author="昊哥的复盘资料",
        publish_time="2026年7月16日 19:46",
        trade_date="2026-07-16",
        body_text="",
        images=[],
    )
    payload = m8.apply_known_reference_profile(copy.deepcopy(m8.M8_TEMPLATE), article)
    payload = m8.normalize_payload_enums(payload)
    payload = m8.normalize_payload_collections(payload)
    payload = m8.normalize_payload_semantics(payload)
    payload = m8.finalize_quality(payload)

    assert payload["market_facts"]["limit_up_count"] == 40
    assert payload["market_facts"]["max_board_height"] == 5
    assert payload["emotion_label"]["emotion_momentum"] == -4
    assert payload["active_capital_series"][-1]["value"] == 898
    errors = m8.validate_payload(payload)
    assert not any("涨停明细覆盖不足" in err for err in errors)
    assert any("机构资金矩阵日期列不足" in err for err in errors)


def test_known_0715_reference_profile_fails_incomplete_extraction_gates():
    # TC-M8EXTRACTOR-REF-05: 2026-07-15 profile must not masquerade as complete.
    article = m8.ArticleData(
        title="7月15日，医药连续走强的4天",
        author="昊哥的复盘资料",
        publish_time="2026年7月15日 19:49",
        trade_date="2026-07-15",
        body_text="",
        images=[],
    )
    payload = m8.apply_known_reference_profile(copy.deepcopy(m8.M8_TEMPLATE), article)
    payload = m8.normalize_payload_enums(payload)
    payload = m8.normalize_payload_collections(payload)
    payload = m8.normalize_payload_semantics(payload)

    errors = m8.validate_payload(payload)

    assert any("涨停明细覆盖不足" in err for err in errors)
    assert any("机构资金矩阵日期列不足" in err for err in errors)


def test_completeness_gates_reject_low_limitup_coverage_and_single_day_matrix():
    # TC-M8EXTRACTOR-REF-04: incomplete long-image and matrix extraction must not pass.
    payload = _minimal_payload()
    payload["market_facts"]["limit_up_count"] = 100
    payload["market_leader"]["total_stocks"] = 100
    payload["institutional_rhythm"] = [
        {"group": "AI", "daily_status": {"7.15": "启动第1天"}},
    ]

    errors = m8.validate_payload(payload)

    assert any("涨停明细覆盖不足" in err for err in errors)
    assert any("机构资金矩阵日期列不足" in err for err in errors)


def test_completeness_gate_uses_ceiling_and_real_institutional_dates_only():
    # TC-M8EXTRACTOR-REF-06: 70% coverage is strict and pseudo date labels do not count.
    payload = _minimal_payload()
    payload["market_facts"]["limit_up_count"] = 71
    payload["market_leader"]["total_stocks"] = 71
    payload["limitup_attribution"] = [
        {
            "board_level": "首板",
            "stock_code": f"{600000 + idx:06d}",
            "stock_name": f"测试{idx}",
            "limit_time": "09:30:00",
            "theme": "AI应用",
            "reason": "测试",
        }
        for idx in range(49)
    ]
    payload["institutional_rhythm"] = [
        {
            "group": "AI",
            "daily_status": {
                "当日": "启动第1天",
                "记录1": "调整第1天",
                "记录2": "调整第2天",
                "7.15": "启动第1天",
            },
        }
    ]

    errors = m8.validate_payload(payload)

    assert any("最低要求>=50" in err for err in errors)
    assert any("机构资金矩阵日期列不足: 1" in err for err in errors)

    payload["limitup_attribution"].append(
        {
            "board_level": "首板",
            "stock_code": "600999",
            "stock_name": "测试补足",
            "limit_time": "09:31:00",
            "theme": "AI应用",
            "reason": "测试",
        }
    )
    payload["institutional_rhythm"][0]["daily_status"].update(
        {"2026-07-14": "调整第1天", "2026/07/15": "启动第1天"}
    )

    errors = m8.validate_payload(payload)

    assert not any("涨停明细覆盖不足" in err for err in errors)
    assert not any("机构资金矩阵日期列不足" in err for err in errors)
