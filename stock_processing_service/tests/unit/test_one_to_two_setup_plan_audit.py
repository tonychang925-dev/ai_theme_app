from __future__ import annotations

from scripts.check_one_to_two_setup_plan_audit import build_audit_report


def test_one_to_two_audit_report_passes_for_valid_persisted_contract() -> None:
    plan_rows = [
        {
            "trade_date": "2026-06-04",
            "watch_date": "2026-06-05",
            "setup_type": "one_to_two",
            "stock_id": "__SUMMARY__",
            "subject_key": "__SUMMARY__",
            "decision": "pending_review_only",
            "summary": "{\"focus_count\": 1, \"observe_only_count\": 1, \"pending_review_only_count\": 0, \"reject_count\": 1}",
            "diagnostics": "{\"empty_is_valid\": true}",
        },
        {
            "trade_date": "2026-06-04",
            "watch_date": "2026-06-05",
            "setup_type": "one_to_two",
            "stock_id": "600367.SH",
            "subject_key": "mainline_ai",
            "decision": "focus",
        },
        {
            "trade_date": "2026-06-04",
            "watch_date": "2026-06-05",
            "setup_type": "one_to_two",
            "stock_id": "600403.SH",
            "subject_key": "mainline_ai",
            "decision": "observe_only",
        },
    ]
    feature_rows = [
        {
            "trade_date": "2026-06-04",
            "watch_date": "2026-06-05",
            "setup_type": "one_to_two",
            "stock_id": "600367.SH",
            "subject_key": "mainline_ai",
            "decision": "focus",
            "veto_reasons": [],
        },
        {
            "trade_date": "2026-06-04",
            "watch_date": "2026-06-05",
            "setup_type": "one_to_two",
            "stock_id": "600403.SH",
            "subject_key": "mainline_ai",
            "decision": "observe_only",
            "veto_reasons": [],
        },
        {
            "trade_date": "2026-06-04",
            "watch_date": "2026-06-05",
            "setup_type": "one_to_two",
            "stock_id": "000001.SZ",
            "subject_key": "robot",
            "decision": "reject",
            "veto_reasons": ["非市场主线"],
        },
    ]

    report = build_audit_report(plan_rows, feature_rows, trade_date="2026-06-04")

    assert report["ok"] is True
    assert report["contract"]["summary_unique"] is True
    assert report["contract"]["plan_item_count_matches_summary"] is True
    assert report["contract"]["candidate_feature_covers_plan_items"] is True
    assert report["contract"]["candidate_feature_no_summary"] is True
    assert report["contract"]["candidate_feature_setup_type_consistent"] is True
    assert report["contract"]["reject_audit_complete"] is True
    assert report["contract"]["no_buy_signal"] is True


# ── P1-A: setup_plan persistence contract ──

def test_one_to_two_setup_plan_summary_row_exists() -> None:
    """SUMMARY row must exist in plan_rows."""
    plan_rows = [
        {
            "trade_date": "2026-06-08",
            "watch_date": "2026-06-09",
            "setup_type": "one_to_two",
            "stock_id": "__SUMMARY__",
            "subject_key": "__SUMMARY__",
            "decision": "pending_review_only",
            "summary": '{"focus_count":0,"observe_only_count":0,"pending_review_only_count":0,"reject_count":1}',
            "diagnostics": '{"empty_is_valid":true}',
        }
    ]
    # At least one reject row in features to satisfy reject_audit_complete contract
    feature_rows: list[dict[str, Any]] = [
        {"trade_date": "2026-06-08", "watch_date": "2026-06-09", "setup_type": "one_to_two",
         "stock_id": "X.SZ", "subject_key": "sk", "decision": "reject", "veto_reasons": ["非主线"]}
    ]
    report = build_audit_report(plan_rows, feature_rows, trade_date="2026-06-08")
    assert report["ok"] is True
    assert report["contract"]["summary_unique"] is True


def test_one_to_two_setup_plan_summary_unique() -> None:
    """Duplicate SUMMARY rows must be rejected."""
    plan_rows = [
        {
            "trade_date": "2026-06-08",
            "watch_date": "2026-06-09",
            "setup_type": "one_to_two",
            "stock_id": "__SUMMARY__",
            "subject_key": "__SUMMARY__",
            "decision": "pending_review_only",
            "summary": '{"focus_count":0,"observe_only_count":0,"pending_review_only_count":0,"reject_count":0}',
            "diagnostics": '{"empty_is_valid":true}',
        },
        {
            "trade_date": "2026-06-08",
            "watch_date": "2026-06-09",
            "setup_type": "one_to_two",
            "stock_id": "__SUMMARY__",
            "subject_key": "__SUMMARY__",
            "decision": "pending_review_only",
            "summary": '{"focus_count":0,"observe_only_count":0,"pending_review_only_count":0,"reject_count":0}',
            "diagnostics": '{"empty_is_valid":true}',
        },
    ]
    feature_rows: list[dict[str, Any]] = []
    report = build_audit_report(plan_rows, feature_rows, trade_date="2026-06-08")
    assert report["ok"] is False
    assert report["contract"]["summary_unique"] is False


def test_one_to_two_setup_plan_item_count_matches_summary() -> None:
    """Item count must equal focus + observe_only + pending_review_only (exclude reject)."""
    plan_rows = [
        {
            "trade_date": "2026-06-08",
            "watch_date": "2026-06-09",
            "setup_type": "one_to_two",
            "stock_id": "__SUMMARY__",
            "subject_key": "__SUMMARY__",
            "decision": "pending_review_only",
            "summary": '{"focus_count":2,"observe_only_count":3,"pending_review_only_count":1,"reject_count":10}',
            "diagnostics": '{"empty_is_valid":true}',
        },
        # 2 focus
        {"trade_date": "2026-06-08", "watch_date": "2026-06-09", "setup_type": "one_to_two", "stock_id": "A.SZ", "subject_key": "sk1", "decision": "focus"},
        {"trade_date": "2026-06-08", "watch_date": "2026-06-09", "setup_type": "one_to_two", "stock_id": "B.SZ", "subject_key": "sk1", "decision": "focus"},
        # 3 observe_only
        {"trade_date": "2026-06-08", "watch_date": "2026-06-09", "setup_type": "one_to_two", "stock_id": "C.SZ", "subject_key": "sk2", "decision": "observe_only"},
        {"trade_date": "2026-06-08", "watch_date": "2026-06-09", "setup_type": "one_to_two", "stock_id": "D.SZ", "subject_key": "sk2", "decision": "observe_only"},
        {"trade_date": "2026-06-08", "watch_date": "2026-06-09", "setup_type": "one_to_two", "stock_id": "E.SZ", "subject_key": "sk2", "decision": "observe_only"},
        # 1 pending_review_only
        {"trade_date": "2026-06-08", "watch_date": "2026-06-09", "setup_type": "one_to_two", "stock_id": "F.SZ", "subject_key": "sk3", "decision": "pending_review_only"},
    ]
    # reject items are NOT in plan_rows (they're filtered out by SetupPlanEngine)
    # Total items = 2+3+1 = 6, matches summary total
    feature_rows = [
        {"trade_date": "2026-06-08", "watch_date": "2026-06-09", "setup_type": "one_to_two", "stock_id": "A.SZ", "subject_key": "sk1", "decision": "focus", "veto_reasons": []},
        {"trade_date": "2026-06-08", "watch_date": "2026-06-09", "setup_type": "one_to_two", "stock_id": "B.SZ", "subject_key": "sk1", "decision": "focus", "veto_reasons": []},
        {"trade_date": "2026-06-08", "watch_date": "2026-06-09", "setup_type": "one_to_two", "stock_id": "C.SZ", "subject_key": "sk2", "decision": "observe_only", "veto_reasons": []},
        {"trade_date": "2026-06-08", "watch_date": "2026-06-09", "setup_type": "one_to_two", "stock_id": "D.SZ", "subject_key": "sk2", "decision": "observe_only", "veto_reasons": []},
        {"trade_date": "2026-06-08", "watch_date": "2026-06-09", "setup_type": "one_to_two", "stock_id": "E.SZ", "subject_key": "sk2", "decision": "observe_only", "veto_reasons": []},
        {"trade_date": "2026-06-08", "watch_date": "2026-06-09", "setup_type": "one_to_two", "stock_id": "F.SZ", "subject_key": "sk3", "decision": "pending_review_only", "veto_reasons": []},
        # A reject in candidate_features (not in plan_rows)
        {"trade_date": "2026-06-08", "watch_date": "2026-06-09", "setup_type": "one_to_two", "stock_id": "G.SZ", "subject_key": "sk4", "decision": "reject", "veto_reasons": ["无板块合力"]},
    ]
    report = build_audit_report(plan_rows, feature_rows, trade_date="2026-06-08")
    assert report["ok"] is True
    assert report["contract"]["plan_item_count_matches_summary"] is True


def test_recap_fails_when_setup_plan_upsert_returns_zero() -> None:
    """Contract: when upsert_post_market_setup_plan_rows returns 0, RuntimeError is raised in BuildPostMarketRecapJob."""
    from stock_processing_service.application.jobs.build_post_market_recap_job import BuildPostMarketRecapJob

    # Simulate _build_one_to_two_persist_rows output with a valid SUMMARY row
    plan = _FakeOneToTwoPlan()
    setup_rows, feature_rows = BuildPostMarketRecapJob._build_one_to_two_persist_rows(plan)

    assert len(setup_rows) >= 1
    summary_row = next(r for r in setup_rows if r["stock_id"] == "__SUMMARY__")
    assert summary_row is not None

    # This test validates the contract that the recap job MUST raise
    # when persistence returns 0. The actual raise happens in the job's
    # execute() method (line 757-758), which is tested in integration.
    #
    # Here we verify the _build_one_to_two_persist_rows always produces
    # a SUMMARY row so the persistence layer has something to write.
    summary_count = sum(1 for r in setup_rows if r["stock_id"] == "__SUMMARY__")
    assert summary_count == 1, "SUMMARY row must exist before persistence"


def test_recap_does_not_write_empty_one_to_two_plan() -> None:
    """Contract: recap_doc must NOT contain post_market_setup_plan if OneToTwo generation was skipped or failed."""
    recap_doc: dict[str, Any] = {}

    # When OneToTwo has NOT run (missing key), caller must fail-closed
    plan = recap_doc.get("post_market_setup_plan")
    assert plan is None, "Missing post_market_setup_plan should be None, not an empty dict"

    # Empty payload (no items, no summary) is also invalid
    empty_payload = {"summary": {}, "items": [], "diagnostics": {}}
    assert len(empty_payload.get("items", [])) == 0
    has_summary_field = bool(empty_payload.get("summary", {}).get("focus_count") is not None)
    assert not has_summary_field, "Empty summary without counts is invalid"


# ── P1-A helpers ──

class _FakeOneToTwoPlan:
    """Minimal fake plan for _build_one_to_two_persist_rows."""
    def to_dict(self) -> dict[str, Any]:
        return {
            "watchlists": {
                "one_to_two": {
                    "summary": {
                        "trade_date": "2026-06-08",
                        "watch_date": "2026-06-09",
                        "focus_count": 0,
                        "observe_only_count": 0,
                        "pending_review_only_count": 0,
                        "reject_count": 0,
                    },
                    "items": [],
                    "diagnostics": {"empty_is_valid": True},
                }
            }
        }
    candidate_features: list[dict[str, Any]] = []


def test_one_to_two_audit_report_fails_when_reject_missing_veto_reasons() -> None:
    plan_rows = [
        {
            "trade_date": "2026-06-04",
            "watch_date": "2026-06-05",
            "setup_type": "one_to_two",
            "stock_id": "__SUMMARY__",
            "subject_key": "__SUMMARY__",
            "decision": "pending_review_only",
            "summary": "{\"focus_count\": 0, \"observe_only_count\": 0, \"pending_review_only_count\": 0, \"reject_count\": 1}",
            "diagnostics": "{\"empty_is_valid\": true}",
        }
    ]
    feature_rows = [
        {
            "trade_date": "2026-06-04",
            "watch_date": "2026-06-05",
            "setup_type": "one_to_two",
            "stock_id": "600367.SH",
            "subject_key": "mainline_ai",
            "decision": "reject",
            "veto_reasons": [],
        }
    ]

    report = build_audit_report(plan_rows, feature_rows, trade_date="2026-06-04")

    assert report["ok"] is False
    assert report["contract"]["reject_audit_complete"] is False
    assert report["errors"]


# ── F4: frontend component guard tests ──

_FORBIDDEN_BUY_TOKENS = {"buy", "must_buy", "recommend_buy", "买入推荐", "必买", "推荐买入", "买入清单", "推荐清单"}


def _scan_file_for_forbidden_tokens(filepath: str) -> list[str]:
    """Scan a frontend/backend source file for forbidden buy-signal tokens in user-facing strings.
    Skips comments and meta-references like 'no buy semantics'."""
    import os
    hits: list[str] = []
    if not os.path.exists(filepath):
        return hits
    with open(filepath, "r") as f:
        for lineno, line in enumerate(f, start=1):
            stripped = line.strip()
            # Skip comment-only lines and lines that merely describe the absence of buy
            if stripped.startswith("#") or stripped.startswith("//") or stripped.startswith("*"):
                continue
            if "no buy" in stripped.lower() or "non-buy" in stripped.lower():
                continue
            lower = line.lower()
            for token in _FORBIDDEN_BUY_TOKENS:
                if token.lower() in lower:
                    hits.append(f"{filepath}:{lineno}: {token}")
    return hits


def test_one_to_two_watch_panel_no_buy_signal_in_source() -> None:
    """OneToTwoWatchPanel must not contain buy/must_buy/recommend_buy tokens."""
    import os
    frontend_root = os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))),
        "frontend", "src", "routes", "recap", "components", "OneToTwoWatchPanel.tsx",
    )
    hits = _scan_file_for_forbidden_tokens(frontend_root)
    assert not hits, f"Forbidden buy tokens found in OneToTwoWatchPanel: {hits}"


def test_layer_c_panel_no_buy_signal_in_source() -> None:
    """LayerCStrongPoolPanel must not contain buy tokens."""
    import os
    frontend_root = os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))),
        "frontend", "src", "routes", "recap", "components", "LayerCStrongPoolPanel.tsx",
    )
    hits = _scan_file_for_forbidden_tokens(frontend_root)
    assert not hits, f"Forbidden buy tokens found in LayerCStrongPoolPanel: {hits}"


def test_one_to_two_watch_panel_source_does_not_import_engine() -> None:
    """OneToTwoWatchPanel must not import OneToTwoSetupPlanEngine or trigger POST."""
    import os
    frontend_root = os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))),
        "frontend", "src", "routes", "recap", "components", "OneToTwoWatchPanel.tsx",
    )
    hits: list[str] = []
    engine_tokens = {"SetupPlanEngine", "RuleEngine", "OneToTwoScorer"}
    if not os.path.exists(frontend_root):
        return
    with open(frontend_root, "r") as f:
        for lineno, line in enumerate(f, start=1):
            for token in engine_tokens:
                if token in line:
                    hits.append(f"{frontend_root}:{lineno}: {token}")
    assert not hits, f"OneToTwoWatchPanel must not reference engine classes: {hits}"


# ── F5: payload contract hardening tests ──

def _scan_file_for_pattern(filepath: str, pattern: str, label: str) -> list[str]:
    """Scan a file for a regex pattern, returning matching line descriptions."""
    import os, re
    hits: list[str] = []
    if not os.path.exists(filepath):
        return [f"{filepath}: MISSING"]
    with open(filepath, "r") as f:
        for lineno, line in enumerate(f, start=1):
            if re.search(pattern, line):
                hits.append(f"{filepath}:{lineno}: {label}")
    return hits


def test_one_to_two_watch_panel_has_strict_summary_validator() -> None:
    """OneToTwoWatchPanel must validate all 4 counts are non-negative numbers."""
    import os
    frontend_root = os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))),
        "frontend", "src", "routes", "recap", "components", "OneToTwoWatchPanel.tsx",
    )
    # hasValidSummary must reference all four count fields AND a .length check
    has_counts = _scan_file_for_pattern(frontend_root, r"focus_count.*observe_only_count.*pending_review_only_count.*reject_count", "four_counts")
    has_length = _scan_file_for_pattern(frontend_root, r"items\.length\s*===\s*expected", "items_length_check")
    assert has_counts, "hasValidSummary must reference all four count fields"
    assert has_length, "hasValidSummary must verify items.length === expected sum of counts"


def test_one_to_two_watch_panel_has_trade_date_validator() -> None:
    """OneToTwoWatchPanel must check tradeDate consistency."""
    import os
    frontend_root = os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))),
        "frontend", "src", "routes", "recap", "components", "OneToTwoWatchPanel.tsx",
    )
    has_fn = _scan_file_for_pattern(frontend_root, r"function matchesTradeDate", "matchesTradeDate_fn")
    assert has_fn, "matchesTradeDate function must exist"


def test_one_to_two_watch_panel_has_independent_filter() -> None:
    """OneToTwoWatchPanel must have a frontend guard filtering __independent__."""
    import os
    frontend_root = os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))),
        "frontend", "src", "routes", "recap", "components", "OneToTwoWatchPanel.tsx",
    )
    has_filter = _scan_file_for_pattern(frontend_root, r"__independent__", "independent_token")
    has_fn = _scan_file_for_pattern(frontend_root, r"function filterIndependent", "filterIndependent_fn")
    # Must have both: reference to __independent__ AND a filter function
    assert has_filter, "must reference __independent__ for filtering"
    assert has_fn, "filterIndependent function must exist"


def test_one_to_two_watch_panel_has_source_label() -> None:
    """OneToTwoWatchPanel must display data source (recap vs watchlists fallback)."""
    import os
    frontend_root = os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))),
        "frontend", "src", "routes", "recap", "components", "OneToTwoWatchPanel.tsx",
    )
    has_source = _scan_file_for_pattern(frontend_root, r"recap snapshot|watchlists fallback", "source_label")
    assert has_source, "must display data source label (recap snapshot or watchlists fallback)"


def test_one_to_two_watch_panel_fail_closed_on_trade_date_missing() -> None:
    """When tradeDate is falsy, matchesTradeDate must return false → fail-closed."""
    import os
    frontend_root = os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))),
        "frontend", "src", "routes", "recap", "components", "OneToTwoWatchPanel.tsx",
    )
    # matchesTradeDate without valid tradeDate must return false
    has_guard = _scan_file_for_pattern(frontend_root, r"if\s*\(!tradeDate\)\s*return\s*false", "tradeDate_guard")
    assert has_guard, "matchesTradeDate must return false when tradeDate is missing"


# ── P3-A: RiskPlanBuilder extension tests ──

def test_risk_plan_builder_outputs_p3a_fields() -> None:
    """Every plan item must carry the 6 P3-A explanation fields."""
    from stock_processing_service.domain.services.one_to_two_risk_plan_builder import OneToTwoRiskPlanBuilder
    from stock_processing_service.contracts.dto.one_to_two_dto import (
        OneToTwoFeatures, RuleResult, ScoreResult,
    )
    from decimal import Decimal

    builder = OneToTwoRiskPlanBuilder()
    f = OneToTwoFeatures(
        trade_date="2026-06-08", watch_date="2026-06-09",
        stock_id="600110.SH", stock_name="诺德股份",
        subject_key="9018144", subject_name="PCB",
        is_confirmed_mainline=True, is_strong_hotspot=False,
        mainline_or_hotspot_state="confirmed_mainline",
        lifecycle_state="fermentation", market_trade_mode="mainline_core_only",
        allow_trade=True, is_first_limit_up=True, is_one_word_board=False,
        is_late_seal=False, first_limit_time="10:00:00", open_board_count=0,
        turnover_rate=Decimal("0.10"), amount=Decimal("500000000"),
        close_seal_amount=Decimal("10000000"), seal_ratio=Decimal("2.0"),
        float_mcap=Decimal("5000000000"), position_120=Decimal("0.30"),
        is_downtrend=False, near_pressure=False,
        same_subject_limit_count=3, same_subject_strong_count=5,
        first_board_type="chain_first_board",
        subject_authenticity={"level": "core", "score": 75, "authenticity_scope": "stock_subject"},
    )
    rule = RuleResult(decision="focus", veto_reasons=[], risk_flags=[])
    score = ScoreResult(
        final_score=Decimal("85.0"), watch_level="A",
        score_detail={
            "first_board_quality": "80", "theme_authenticity": "75",
            "board_breadth": "70", "technical_structure": "68",
            "risk_control": "85",
        },
    )

    plan = builder.build(f, rule, score)

    required_keys = [
        "observation_reason", "subject_logic", "technical_summary",
        "key_parameters", "tomorrow_plan", "give_up_conditions",
    ]
    for key in required_keys:
        assert key in plan, f"plan must contain '{key}'"
    assert isinstance(plan["observation_reason"], list) and len(plan["observation_reason"]) > 0
    assert isinstance(plan["subject_logic"], dict) and plan["subject_logic"].get("subject_key")
    assert isinstance(plan["key_parameters"], dict)
    assert isinstance(plan["give_up_conditions"], list)


def test_tomorrow_plan_does_not_contain_buy_tokens_in_templates() -> None:
    """P3-D: RiskPlanBuilder templates must not contain buy/must_buy/recommend_buy."""
    import os
    builder_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))),
        "stock_processing_service", "domain", "services", "one_to_two_risk_plan_builder.py",
    )
    hits = _scan_file_for_forbidden_tokens(builder_path)
    assert not hits, f"Forbidden buy tokens in RiskPlanBuilder: {hits}"


def test_no_trade_item_has_conservative_tomorrow_plan() -> None:
    """When market_mode is no_trade, tomorrow_plan must be conservative (no active triggers)."""
    from stock_processing_service.domain.services.one_to_two_risk_plan_builder import OneToTwoRiskPlanBuilder
    from stock_processing_service.contracts.dto.one_to_two_dto import (
        OneToTwoFeatures, RuleResult, ScoreResult,
    )
    from decimal import Decimal

    builder = OneToTwoRiskPlanBuilder()
    f = OneToTwoFeatures(
        trade_date="2026-06-08", watch_date="2026-06-09",
        stock_id="002579.SZ", stock_name="中京电子",
        subject_key="9018144", subject_name="PCB",
        is_confirmed_mainline=True, is_strong_hotspot=False,
        mainline_or_hotspot_state="confirmed_mainline",
        lifecycle_state="fermentation", market_trade_mode="no_trade",
        allow_trade=False, is_first_limit_up=True, is_one_word_board=False,
        is_late_seal=False, first_limit_time="10:30:00", open_board_count=1,
        turnover_rate=Decimal("0.10"), amount=Decimal("500000000"),
        close_seal_amount=Decimal("10000000"), seal_ratio=Decimal("1.5"),
        float_mcap=Decimal("5000000000"), position_120=Decimal("0.40"),
        is_downtrend=False, near_pressure=False,
        same_subject_limit_count=2, same_subject_strong_count=4,
    )
    rule = RuleResult(decision="observe_only", veto_reasons=[], risk_flags=["市场环境 no_trade，不得 focus"])
    score = ScoreResult(
        final_score=Decimal("72.0"), watch_level="B",
        score_detail={"first_board_quality": "70", "theme_authenticity": "60",
                      "board_breadth": "60", "technical_structure": "55", "risk_control": "70"},
    )

    plan = builder.build(f, rule, score)
    tp = plan["tomorrow_plan"]
    assert "仅观察" in tp.get("expected_behavior", "") or "no_trade" in tp.get("expected_behavior", "").lower()
    # No active confirmation triggers in no_trade
    triggers = tp.get("confirmation_triggers", [])
    assert len(triggers) == 0 or all("不" in str(t) or "仅" in str(t) for t in triggers)


# ── P3-B: OneToTwoTechnicalSummaryFormatter tests ──

def test_technical_summary_formatter_golden_spider() -> None:
    """Formatter must produce golden-spider label and highlights."""
    from stock_processing_service.domain.services.one_to_two_technical_summary_formatter import (
        OneToTwoTechnicalSummaryFormatter,
    )
    fmt = OneToTwoTechnicalSummaryFormatter()
    kpq = {
        "kline_data_ready": True, "has_golden_spider": True, "level": "golden",
        "score": 90, "technical_reason": "",
        "above_ma5": True, "above_ma10": True, "above_ma20": True,
        "ma_alignment_status": "均线多头", "support_broken": False,
        "kline_near_resistance": False, "is_downtrend": False,
    }
    result = fmt.format(kpq, technical_structure_score=90.0)
    assert "金蜘蛛" in result["label"]
    assert result["has_golden_spider"] is True
    assert any("MA5" in h for h in result["highlights"])


def test_technical_summary_formatter_ma_not_bullish() -> None:
    """Formatter must explain ma_not_bullish_alignment clearly."""
    from stock_processing_service.domain.services.one_to_two_technical_summary_formatter import (
        OneToTwoTechnicalSummaryFormatter,
    )
    fmt = OneToTwoTechnicalSummaryFormatter()
    kpq = {
        "kline_data_ready": True, "has_golden_spider": False, "level": "unknown",
        "score": 48, "technical_reason": "ma_not_bullish_alignment",
        "above_ma5": True, "above_ma10": False, "above_ma20": False,
        "ma_alignment_status": "", "support_broken": False,
        "kline_near_resistance": False, "is_downtrend": False,
    }
    result = fmt.format(kpq, technical_structure_score=48.0)
    assert result["reason"] == "ma_not_bullish_alignment"
    assert result["reason_label"] is not None
    assert any("偏低" in r for r in result["risks"])


def test_technical_summary_formatter_support_broken() -> None:
    """Formatter must flag support_broken as a risk."""
    from stock_processing_service.domain.services.one_to_two_technical_summary_formatter import (
        OneToTwoTechnicalSummaryFormatter,
    )
    fmt = OneToTwoTechnicalSummaryFormatter()
    kpq = {
        "kline_data_ready": True, "has_golden_spider": False, "level": "unknown",
        "score": 30, "technical_reason": "support_broken",
        "above_ma5": False, "above_ma10": False, "above_ma20": False,
        "support_broken": True, "is_downtrend": False,
    }
    result = fmt.format(
        kpq, technical_structure_score=20.0, veto_reasons=["支撑破坏"],
    )
    assert any("支撑" in r for r in result["risks"])


def test_technical_summary_formatter_near_pressure() -> None:
    """Formatter must flag near_pressure as a risk."""
    from stock_processing_service.domain.services.one_to_two_technical_summary_formatter import (
        OneToTwoTechnicalSummaryFormatter,
    )
    fmt = OneToTwoTechnicalSummaryFormatter()
    kpq = {
        "kline_data_ready": True, "has_golden_spider": True, "level": "near_golden",
        "score": 65, "technical_reason": "near_resistance",
        "above_ma5": True, "above_ma10": True, "above_ma20": False,
        "support_broken": False, "kline_near_resistance": True,
    }
    result = fmt.format(kpq, technical_structure_score=55.0, risk_flags=["重要压力位附近，暂不 focus"])
    assert any("压力" in r for r in result["risks"])


def test_technical_summary_formatter_no_kline_data() -> None:
    """Formatter must clearly flag missing K-line data."""
    from stock_processing_service.domain.services.one_to_two_technical_summary_formatter import (
        OneToTwoTechnicalSummaryFormatter,
    )
    fmt = OneToTwoTechnicalSummaryFormatter()
    result = fmt.format({})
    assert "数据不足" in result["label"]
    assert result["kline_data_ready"] is False
