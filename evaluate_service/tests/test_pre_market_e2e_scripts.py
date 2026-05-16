from __future__ import annotations

import pytest

from evaluate_service.e2e.pre_market_brief.common import (
    default_output_dir,
    ensure_no_gold_leak,
    repo_root,
    require_safe_db,
)
from evaluate_service.e2e.pre_market_brief.evaluate_pre_market_brief import _matches_gold
from evaluate_service.e2e.pre_market_brief.parse_test_cases import parse_test_cases_file
from evaluate_service.e2e.pre_market_brief.replay_akshare_raw_news import build_stream_payload
from evaluate_service.e2e.pre_market_brief.run_pre_market_e2e import build_parser, _build_rebuild_payload


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
