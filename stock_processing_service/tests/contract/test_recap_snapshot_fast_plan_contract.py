"""合约测试：recap_snapshot fast 模式只允许 recap_data 步骤。

冻结规则：
- force_rebuild_truth_source=false 时，plan.steps 只能包含 recap_data
- 不得包含任何 Producer/Checker 步骤
- 违反此合约 → 测试失败 → 禁止合并
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

FORBIDDEN_FAST_KEYS = frozenset({
    "stock_kline_judgements",
    "recap_prerequisites",
    "market_environment_daily",
    "theme_capital_flow_daily",
    "money_flow_enhanced",
    "abnormal_signal",
})

REQUIRED_FULL_KEYS = frozenset({
    "stock_kline_judgements",
    "recap_prerequisites",
    "recap_data",
})


def _make_plan(force_truth: bool):
    from stock_processing_service.application.services.collection_orchestrator import (
        CollectionCommandPlanner,
    )
    planner = CollectionCommandPlanner(python_bin=sys.executable, project_root=ROOT)
    return planner.build_task_plan(
        task_key="recap_snapshot",
        trade_date="2026-05-26",
        payload={"options": {"force_rebuild_truth_source": force_truth}},
        env={},
    )


def test_fast_plan_no_producer_steps():
    """force_rebuild_truth_source=false → 只能有 recap_data。"""
    plan = _make_plan(force_truth=False)
    step_keys = [s.key for s in plan.steps]
    forbidden = [k for k in step_keys if k in FORBIDDEN_FAST_KEYS]

    assert not forbidden, (
        f"FAST mode contains forbidden Producer/Checker steps: {forbidden}\n"
        f"  All keys: {step_keys}"
    )
    assert "recap_data" in step_keys, f"FAST must have recap_data. keys={step_keys}"
    assert "FORCE REBUILD" not in " ".join(plan.pre_logs)
    print(f"PASS fast: keys={step_keys}")


def test_full_plan_includes_producers():
    """force_rebuild_truth_source=true → 包含 Producer 步骤。"""
    plan = _make_plan(force_truth=True)
    step_keys = [s.key for s in plan.steps]
    missing = REQUIRED_FULL_KEYS - set(step_keys)
    assert not missing, f"FORCE REBUILD missing: {missing}. keys={step_keys}"
    assert "FORCE REBUILD" in " ".join(plan.pre_logs)
    print(f"PASS full: keys={step_keys}")


if __name__ == "__main__":
    test_fast_plan_no_producer_steps()
    test_full_plan_includes_producers()
    print("\nALL CONTRACT TESTS PASSED")
