from stock_service.services.theme_leader_llm_judgement_service import (
    ThemeLeaderLlmCandidateInput,
    ThemeLeaderLlmJudgementService,
)


def test_build_candidate_payload_contains_fact_layers():
    service = ThemeLeaderLlmJudgementService()
    rows = [
        ThemeLeaderLlmCandidateInput(
            trade_date="2026-04-03",
            subject_key="theme:ai_fiber",
            theme_name="AI光纤",
            stock_id="600869.SH",
            stock_name="远东股份",
            rank_order=1,
            pct_chg=8.37,
            is_leader=True,
            is_limit_up=False,
            turnover_rate=12.3,
            volume_ratio=4.2,
            main_net_inflow=250000000,
            amount=980000000,
            open_price=12.88,
            high_price=13.82,
            low_price=12.82,
            close_price=13.72,
            pre_close=12.66,
            role_label="龙头",
            candidate_rank=1,
            purity_score=45,
            leading_score=88,
            capital_score=72,
            structure_score=64,
            resilience_score=60,
            composite_score=68,
            position_label="突破前高",
            pattern_labels=("放量突破", "均线多头"),
            stock_remark="公司是国内电缆领域的领先企业，在光伏、风电、特高压等新兴领域有望实现快速增长。",
        )
    ]

    payload = service.build_candidate_payload(rows)
    candidate = payload["candidates"][0]
    assert payload["theme_name"] == "AI光纤"
    assert candidate["price_facts"]["board_nature_candidate"] == "大阳领涨"
    assert candidate["capital_facts"]["main_net_inflow_yi"] == 2.5
    assert candidate["kline_facts"]["position_label"] == "突破前高"
    assert candidate["theme_relation_text"].startswith("公司是国内电缆领域的领先企业")


def test_build_prompt_text_mentions_constraints():
    service = ThemeLeaderLlmJudgementService()
    rows = [
        ThemeLeaderLlmCandidateInput(
            trade_date="2026-04-03",
            subject_key="theme:cpo",
            theme_name="共封装光学CPO",
            stock_id="300812.SZ",
            stock_name="易天股份",
            rank_order=1,
            pct_chg=20.0,
            is_leader=True,
            is_limit_up=True,
            turnover_rate=16.3,
            volume_ratio=24.2,
            main_net_inflow=93000000,
            amount=850000000,
            open_price=34.2,
            high_price=40.89,
            low_price=33.8,
            close_price=40.89,
            pre_close=34.08,
            role_label="龙头",
            candidate_rank=1,
            purity_score=45,
            leading_score=100,
            capital_score=64.5,
            structure_score=65,
            resilience_score=63.7,
            composite_score=68.4,
            position_label="平台整理",
            pattern_labels=(),
            stock_remark="主营平板显示模组组装设备，并已向半导体微组装设备、Mini LED 巨量转移生产设备等领域拓展。",
        )
    ]
    payload = service.build_candidate_payload(rows)
    prompt = service.build_prompt_text(payload)
    assert "不得编造封板时间、秒板等不存在事实" in prompt
    assert "正宗性/领涨性 > 资金量能 > 结构位置 > 抗跌承接" in prompt
    assert "易天股份(300812.SZ)" in prompt


def test_apply_llm_response_keeps_only_valid_stock_ids():
    service = ThemeLeaderLlmJudgementService()
    rows = [
        ThemeLeaderLlmCandidateInput(
            trade_date="2026-04-03",
            subject_key="theme:cpo",
            theme_name="共封装光学CPO",
            stock_id="300812.SZ",
            stock_name="易天股份",
            rank_order=1,
            pct_chg=20.0,
            is_leader=True,
            is_limit_up=True,
            turnover_rate=16.3,
            volume_ratio=24.2,
            main_net_inflow=93000000,
            amount=850000000,
            open_price=34.2,
            high_price=40.89,
            low_price=33.8,
            close_price=40.89,
            pre_close=34.08,
        ),
        ThemeLeaderLlmCandidateInput(
            trade_date="2026-04-03",
            subject_key="theme:cpo",
            theme_name="共封装光学CPO",
            stock_id="688195.SH",
            stock_name="腾景科技",
            rank_order=2,
            pct_chg=19.22,
            is_leader=False,
            is_limit_up=True,
            turnover_rate=14.4,
            volume_ratio=8.6,
            main_net_inflow=129000000,
            amount=3640000000,
            open_price=57.2,
            high_price=65.01,
            low_price=56.7,
            close_price=65.01,
            pre_close=54.53,
        ),
    ]
    seed = service.build_placeholder_judgement(rows)
    updated = service.apply_llm_response(
        seed,
        {
            "leader_stock_id": "300812.SZ",
            "runner_up_stock_id": "688195.SH",
            "card_position_stock_id": "BAD.ID",
            "reasoning_summary": "易天股份辨识度最高，腾景科技次之",
            "per_stock_reasoning": [
                {"stock_id": "300812.SZ", "role_label": "龙头", "reason": "涨停且排序第一"},
                {"stock_id": "BAD.ID", "role_label": "淘汰", "reason": "无效"},
            ],
        },
        "deepseek-chat",
    )
    assert updated.leader_stock_id == "300812.SZ"
    assert updated.runner_up_stock_id == "688195.SH"
    assert updated.card_position_stock_id == ""
    assert updated.model_name == "deepseek-chat"
    assert updated.judgement_json["per_stock_reasoning"] == [
        {"stock_id": "300812.SZ", "role_label": "龙头", "reason": "涨停且排序第一"}
    ]
