from __future__ import annotations

import json
from pathlib import Path

from stock_service.config import StockServiceConfig
from stock_service.models import MarketReport
from stock_service.services.recap_service import RecapService
from stock_service.services.report_snapshot_service import ReportSnapshotService


class _FakeReportRepository:
    def __init__(self):
        self.config = StockServiceConfig(project_root=Path("/tmp/ai_theme_app_test"))

    async def fetch_market_environment_judgement(self, trade_date: str):
        return {
            "market_health_score": 76.5,
            "market_bias": "risk_on",
            "breadth_status": "市场广度强",
            "short_term_sentiment_status": "短线情绪活跃",
            "relay_sentiment_status": "接力生态健康",
            "intraday_fade_status": "冲高回落风险可控",
            "action_bias": "主做",
            "conclusion": "大环境提供保护，可围绕主线前排与高辨识度个股积极进攻",
            "evidence": [
                "上涨 3400 / 下跌 1200 / 平盘 200",
                "涨停 82 / 跌停 4；涨跌停比 20.50",
            ],
        }

    async def fetch_pre_market_execution_plans(self, trade_date: str, limit: int = 30, include_avoid: bool = False):
        return [
            {
                "subject_key": "9025631",
                "theme_name": "创新药",
                "theme_status": "弱化",
                "leader_stock_id": "300436.SZ",
                "leader_stock_name": "广生堂",
                "leader_status": "继续成立",
                "action_today": "watch",
                "action_bias": "警惕高潮",
                "watch_reason": "创新药 当前 climax，核心观察 广生堂；K线位置 接近前高；K线形态 放量突破。",
                "auction_focus_stock_id": "300436.SZ",
                "auction_focus_stock_name": "广生堂",
                "auction_signal_level": "watch",
                "auction_signal_type": "弱转强候选",
                "auction_action_today": "watch",
                "auction_signal_score": 58.6,
                "auction_hard_reject_reason": "",
                "invalid_conditions": ["若高开一致性过强且无承接，避免追高"],
            }
        ]

    async def fetch_recent_auction_signal_validations(self, trade_date: str, limit: int = 20):
        return [
            {
                "trade_date": "2026-04-02",
                "stock_id": "300436.SZ",
                "stock_name": "广生堂",
                "subject_key": "9025631",
                "theme_name": "创新药",
                "role_label": "龙头",
                "auction_signal_level": "watch",
                "auction_signal_score": 58.6,
                "signal_type": "弱转强候选",
                "action_today": "watch",
                "close_pct": 4.26,
                "close_price": 32.4,
                "hit_limit_up": False,
                "close_rank_order": 1,
                "close_is_leader": True,
                "validation_result": "watch_upgraded",
                "signal_validated": True,
                "validation_note": "观察信号升级为强势表现",
            }
        ]

    async def fetch_mainline_judgements(self, trade_date: str, limit: int = 30):
        return [
            {
                "subject_key": "9025631",
                "theme_name": "创新药",
                "event_chain_score": 21.0,
                "market_recognition_score": 100.0,
                "mainline_stability_score": 70.0,
                "theme_tier": "main",
                "limit_up_count": 23,
            }
        ]

    async def fetch_theme_environment_judgements(self, trade_date: str, limit: int = 30):
        return [
            {
                "subject_key": "9025631",
                "theme_name": "创新药",
                "board_health_status": "板块过热",
                "board_effect_status": "板块联动明显",
                "leader_support_status": "龙头强带队",
                "follow_strength_status": "后排跟随强",
                "action_bias": "警惕高潮",
                "conclusion": "板块过热；板块联动明显；龙头强带队；后排跟随强。当前阶段 climax，板块动作建议：警惕高潮",
                "evidence": ["涨停 23 家；强势股 61 家；成分股 80 家"],
            }
        ]

    async def fetch_cycle_judgements(self, trade_date: str, limit: int = 30):
        return [
            {
                "subject_key": "9025631",
                "theme_name": "创新药",
                "primary_cycle_stage": "climax",
                "action_bias": "警惕高潮",
                "conclusion": "主线过热，需警惕高潮后分歧",
            }
        ]

    async def fetch_leader_candidates(self, trade_date: str, limit: int = 80):
        return [
            {
                "stock_id": "300436.SZ",
                "stock_name": "广生堂",
                "subject_key": "9025631",
                "rank_order": 1,
                "candidate_rank": 1,
                "role_label": "龙头",
                "composite_score": 67.92,
                "volume_ratio": 11.76,
            }
        ]

    async def fetch_dragon_tiger_objects(self, trade_date: str, limit: int = 120):
        return [
            {
                "stock_id": "300436.SZ",
                "stock_name": "广生堂",
                "reason": "日涨幅偏离值达到7%的证券",
                "net_amount": 85000000.0,
                "institution_seat_count": 2,
                "seat_summary": ["机构专用 买入席位 净额 45000000.00"],
                "source_trace_id": "abc123trace",
            }
        ]

    async def fetch_money_flow_enhanced(self, trade_date: str, limit: int = 120):
        return [
            {
                "subject_key": "9025631",
                "theme_name": "创新药",
                "stock_id": "300436.SZ",
                "stock_name": "广生堂",
                "role_label": "龙头",
                "role_enhanced": "龙头/资金共振",
                "candidate_rank": 1,
                "money_flow_score": 72.4,
                "money_flow_tier": "HIGH",
                "explanation": ["角色 龙头 -> 龙头/资金共振"],
                "sources": ["theme_leader_candidate", "dragon_tiger_object"],
            }
        ]

    async def fetch_leader_llm_judgements(self, trade_date: str, limit: int = 30):
        return [
            {
                "subject_key": "9025631",
                "theme_name": "创新药",
                "leader_stock_id": "300436.SZ",
                "leader_status": "继续成立",
                "confirmation_basis": "二连板确认",
                "runner_up_stock_id": "",
                "card_position_stock_id": "",
                "supplement_stock_id": "",
                "eliminated_stock_id": "",
                "judgement_json": {
                    "per_stock_reasoning": [
                        {
                            "stock_id": "300436.SZ",
                            "role_label": "龙头",
                            "reason": "两日连续领涨，且题材辨识度最高。",
                        }
                    ]
                },
            }
        ]

    async def fetch_stock_abnormal_signals(self, trade_date: str, limit: int = 120):
        return []

    async def fetch_hot_money_activities(self, trade_date: str, limit: int = 300):
        return []

    async def fetch_subject_theme_links_for_stocks(self, trade_date: str, stock_ids: list[str]):
        return []


async def test_build_post_market_report():
    service = RecapService(_FakeReportRepository())
    report = await service.build_post_market_report("2026-04-01")

    assert isinstance(report, MarketReport)
    assert report.report_type == "post_market"
    assert report.trade_date == "2026-04-01"
    assert "市场偏向 risk_on" in report.highlights[0]
    assert report.sections[0][0] == "大盘环境总结"
    assert report.sections[1][0] == "板块环境总结"
    assert report.sections[2][0] == "主线与支线"
    assert report.sections[3][0] == "周期与动作"
    assert report.sections[4][0] == "强势股分层"
    assert report.sections[5][0] == "当日异动股与资金行为"
    assert report.sections[6][0] == "资金行为增强"
    assert report.sections[7][0] == "龙虎榜"
    assert "板块过热" in report.sections[1][1][0]
    assert "层级 main" in report.sections[2][1][0]
    assert "主线存活 " in report.sections[2][1][0]
    assert "状态 " in report.sections[2][1][0]
    assert "主线强度 " in report.sections[2][1][0]
    assert "HIGH / 龙头/资金共振" in report.sections[4][1][0]
    assert "LLM裁决角色 龙头" in report.sections[4][1][0]
    assert "LLM确认状态 继续成立" in report.sections[4][1][0]
    assert "龙头/资金共振" in report.sections[6][1][0]


class _FakeReportRepositoryLargeLlm(_FakeReportRepository):
    async def fetch_leader_llm_judgements(self, trade_date: str, limit: int = 30):
        if limit < 500:
            return []
        return await super().fetch_leader_llm_judgements(trade_date, limit=limit)


async def test_build_post_market_report_fetches_enough_llm_rows():
    service = RecapService(_FakeReportRepositoryLargeLlm())
    report = await service.build_post_market_report("2026-04-01")

    assert "LLM裁决角色 龙头" in report.sections[4][1][0]


async def test_build_pre_market_report():
    service = RecapService(_FakeReportRepository())
    report = await service.build_pre_market_report("2026-04-01")

    assert isinstance(report, MarketReport)
    assert report.report_type == "pre_market"
    assert report.sections[0][0] == "可做主线与支线"
    assert report.sections[1][0] == "盘前重点盯盘个股"
    assert report.sections[2][0] == "竞价确认"
    assert report.sections[3][0] == "竞价验证回看"
    assert "K线位置 接近前高" in report.sections[1][1][0]
    assert "弱转强候选" in report.sections[2][1][0]
    assert "watch_upgraded" in report.sections[3][1][0]


def test_write_report_snapshot(tmp_path: Path):
    config = StockServiceConfig(
        project_root=tmp_path,
        report_snapshot_root=tmp_path / "report_snapshots",
    )
    service = ReportSnapshotService(config)
    report = MarketReport(
        report_type="post_market",
        trade_date="2026-04-01",
        title="2026-04-01 盘后复盘",
        summary="测试摘要",
        highlights=["亮点1"],
        sections=[("题材强度与龙头", ["创新药：龙头 广生堂"])],
    )

    result = service.write_report_snapshot(report, batch_id="batch001")

    json_path = Path(result.json_path)
    markdown_path = Path(result.markdown_path)
    assert json_path.exists()
    assert markdown_path.exists()
    data = json.loads(json_path.read_text(encoding="utf-8"))
    assert data["report_type"] == "post_market"
    assert "创新药" in markdown_path.read_text(encoding="utf-8")
