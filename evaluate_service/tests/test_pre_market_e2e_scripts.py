from __future__ import annotations

import pytest

from evaluate_service.e2e.pre_market_brief.common import (
    default_output_dir,
    ensure_no_gold_leak,
    repo_root,
    require_safe_db,
)
from evaluate_service.e2e.pre_market_brief.evaluate_pre_market_brief import (
    _is_commercial_space_neighbor,
    _is_generic_only_related,
    _matches_gold,
    _snapshot_theme_name_quality,
    _wrong_related_attribution_row,
)
from evaluate_service.e2e.pre_market_brief.parse_test_cases import parse_test_cases_file
from evaluate_service.e2e.pre_market_brief.replay_akshare_raw_news import build_stream_payload
from evaluate_service.e2e.pre_market_brief.run_pre_market_e2e import build_parser, _build_rebuild_payload
from evaluate_service.e2e.pre_market_brief.run_phase0_decision_services import build_parser as build_phase0_parser
from evaluate_service.e2e.pre_market_brief.run_raw_news_services import build_parser as build_raw_services_parser
from evaluate_service.e2e.pre_market_brief.trace_pre_market_e2e_run import _extract_decision_payload_trace


def test_repo_root_and_default_output_dir_are_project_relative():
    assert repo_root().name == "ai_theme_app"
    assert default_output_dir("x").as_posix().endswith("evaluate_service/output/pre_market_e2e/x")


def test_parse_test_cases_splits_input_and_gold_labels(tmp_path):
    source = tmp_path / "test_cases.txt"
    source.write_text(
        "\n".join(
            [
                "测试集1:题材名称:AI/AR眼镜",
                "- Meta发布智能眼镜新品。",
                "- 苹果重启AR眼镜计划。",
                "测试集2:题材名称:SpaceX",
                "- SpaceX星舰试飞。",
            ]
        ),
        encoding="utf-8",
    )

    input_rows, gold_rows = parse_test_cases_file(
        source,
        run_id="pm_e2e_test",
        trade_date="2026-05-16",
    )

    assert len(input_rows) == 3
    assert len(gold_rows) == 3
    assert gold_rows[0]["gold_theme_name"] == "AI/AR眼镜"
    assert "gold_theme_name" not in input_rows[0]
    assert "theme_name" not in input_rows[0]
    assert input_rows[0]["publish_date"] == "2026-05-16"
    assert input_rows[0]["external_id"] == "pm_e2e_test:pm_case_0001"


def test_stream_payload_rejects_gold_label_leak():
    row = {
        "external_id": "run:pm_case_0001",
        "news_id": "run:pm_case_0001",
        "title": "测试新闻",
        "content": "测试内容",
        "source": "akshare_replay",
        "publish_date": "2026-05-16",
        "publish_time": "2026-05-16T07:00:01",
        "run_id": "run",
        "case_id": "pm_case_0001",
        "gold_theme_name": "AI/AR眼镜",
    }

    with pytest.raises(ValueError):
        build_stream_payload(row, run_id="run", trade_date="2026-05-16")


def test_safe_db_refuses_stock_data_test_by_default():
    with pytest.raises(SystemExit):
        require_safe_db("stock_data_test")

    require_safe_db("stock_data")
    require_safe_db("stock_data_test", allow_production=True)


def test_alias_match_for_gold_labels():
    assert _matches_gold("AI/AR眼镜", "智能眼镜")
    assert _matches_gold("SpaceX", "卫星互联网")
    assert not _matches_gold("可控核聚变", "AI智能眼镜")


def test_commercial_space_neighbor_is_separate_from_wrong_related():
    assert _is_commercial_space_neighbor("卫星互联", "卫星互联网", "商业航天8大IPO")
    assert _is_commercial_space_neighbor("SpaceX", "蓝箭航天IPO", "航天发射场")
    assert not _is_commercial_space_neighbor("AI/AR眼镜", "AR眼镜", "商业航天8大IPO")


def test_trace_extracts_event_id_from_nested_payload():
    payload = {
        "payload": '{"event_data": {"event_id": 12345}, "match_result": {"reason_code": "UNKNOWN"}}',
    }

    assert _extract_decision_payload_trace(payload)["event_id"] == 12345


def test_trace_extracts_event_id_from_top_level_event_data_field():
    fields = {
        "payload": '{"action": "publish_clustering"}',
        "event_data": '{"event_id": 7934, "case_id": "pm_case_0030"}',
    }

    assert _extract_decision_payload_trace(fields)["event_id"] == 7934


def test_trace_extracts_event_id_from_event_data_without_payload_field():
    fields = {
        "event_data": '{"event_id": 7962, "case_id": "pm_case_0055"}',
        "reason_code": "pending_unknown",
    }

    assert _extract_decision_payload_trace(fields)["event_id"] == 7962


def test_generic_only_related_metric_detects_support_only_evidence():
    assert _is_generic_only_related(
        {
            "evidence_json": {
                "related_match": {
                    "evidence": {
                        "support_hits": ["供应链"],
                        "anchor_hits": [],
                        "object_hits": [],
                        "must_hits": [],
                        "strong_hits": [],
                        "entity_hits": [],
                    }
                }
            }
        }
    )
    assert not _is_generic_only_related(
        {
            "evidence_json": {
                "related_match": {
                    "evidence": {
                        "support_hits": ["供应链"],
                        "anchor_hits": ["蓝箭航天"],
                    }
                }
            }
        }
    )


def test_wrong_related_attribution_extracts_evidence_roles():
    row = {"case_id": "pm_case_x", "event_title": "测试事件"}
    item = {
        "subject_key": "9036559",
        "theme_name": "ASIC芯片",
        "confidence": "0.65",
        "match_reason": "top_candidate_evidence_related",
        "evidence_json": {
            "related_match": {
                "evidence": {
                    "hit_terms": ["芯片", "Meta"],
                    "hit_term_roles": {"芯片": "main_anchor", "Meta": "main_anchor"},
                    "evidence_summary": {"anchor_terms": ["芯片", "Meta"]},
                }
            }
        },
    }

    out = _wrong_related_attribution_row(row, item, "AI/AR眼镜", "AR眼镜")

    assert out["wrong_subject_key"] == "9036559"
    assert out["wrong_theme_name"] == "ASIC芯片"
    assert out["hit_terms"] == "芯片|Meta"
    assert "Meta:main_anchor" in out["hit_term_roles"]
    assert out["root_cause"] == "profile_boundary_missing"


def test_snapshot_theme_name_quality_detects_numeric_display_names():
    sections = {
        "matched_themes": [
            {"subject_key": "9060949", "theme_name": "9060949"},
            {"subject_key": "9024880", "theme_name": "液冷数据中心"},
            {"subject_key": "9017950", "name": ""},
        ],
        "event_driven_opportunities": [
            {"subject_key": "9043089", "subject_name": "9043089"},
        ],
    }

    quality = _snapshot_theme_name_quality(sections)

    assert quality["numeric_theme_name_count"] == 2
    assert quality["subject_key_chip_count"] == 2
    assert quality["unnamed_theme_count"] == 1


def test_ensure_no_gold_leak_accepts_clean_payload():
    ensure_no_gold_leak({"title": "新闻", "case_id": "pm_case_0001"})


def test_rebuild_payload_includes_source_and_explicit_limit():
    args = build_parser().parse_args(
        [
            "--trade-date",
            "2026-05-16",
            "--run-id",
            "pm_e2e",
            "--limit",
            "100",
            "--force-rebuild",
        ]
    )

    assert _build_rebuild_payload(args) == {
        "trade_date": "2026-05-16",
        "source": "db_first",
        "limit": 100,
        "force": True,
        "dry_run": False,
    }


def test_pre_market_e2e_defaults_to_sps_without_legacy_bff():
    args = build_parser().parse_args(
        [
            "--trade-date",
            "2026-05-16",
            "--run-id",
            "pm_e2e",
        ]
    )

    assert args.sps_base_url == "http://127.0.0.1:8090"
    assert not hasattr(args, "bff_base_url")
    assert not hasattr(args, "legacy_bff_base_url")


def test_pre_market_e2e_snapshot_copy_is_explicit_opt_in():
    default_args = build_parser().parse_args(
        [
            "--trade-date",
            "2026-05-16",
            "--run-id",
            "pm_e2e",
        ]
    )
    copy_args = build_parser().parse_args(
        [
            "--trade-date",
            "2026-05-16",
            "--run-id",
            "pm_e2e",
            "--copy-snapshot-to-db",
            "stock_data_test",
        ]
    )

    assert default_args.copy_snapshot_to_db is None
    assert copy_args.copy_snapshot_to_db == "stock_data_test"


def test_pre_market_e2e_trade_date_cleanup_is_explicit_opt_in():
    default_args = build_parser().parse_args(
        [
            "--trade-date",
            "2026-05-16",
            "--run-id",
            "pm_e2e",
        ]
    )
    clean_args = build_parser().parse_args(
        [
            "--trade-date",
            "2026-05-16",
            "--run-id",
            "pm_e2e",
            "--force-clean",
            "--clean-trade-date-all-e2e",
        ]
    )

    assert default_args.clean_trade_date_all_e2e is False
    assert clean_args.clean_trade_date_all_e2e is True


def test_e2e_service_groups_default_to_run_scoped_names():
    raw_args = build_raw_services_parser().parse_args(["--run-id", "pm_e2e_run"])
    phase0_args = build_phase0_parser().parse_args(["--run-id", "pm_e2e_run"])

    assert raw_args.storage_group is None
    assert raw_args.processor_group is None
    assert phase0_args.decision_consumer_group is None


def test_pre_market_e2e_http_timeout_defaults_to_long_rebuild_window():
    args = build_parser().parse_args(
        [
            "--trade-date",
            "2026-05-16",
            "--run-id",
            "pm_e2e",
        ]
    )

    assert args.http_timeout >= 180
