from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
LAYER_ABCD_CONTRACT = ROOT / "docs/project_control/PHASE_CONTRACT_LAYER_ABCD.md"
EXECUTION_GUARDRAILS = ROOT / "docs/project_control/EXECUTION_GUARDRAILS.md"


def test_layer_abcd_contract_forbids_undocumented_business_rules() -> None:
    text = LAYER_ABCD_CONTRACT.read_text(encoding="utf-8")

    required_fragments = [
        "禁止编造不符合设计文档的逻辑和规则",
        "任何新增/修改规则无法映射到设计文档章节或 ADR 编号时",
        "只允许 fail-fast 或不输出该命题判断",
        "不得把缺失解释成 `true`、`false`、`start`、`observed`、`reject`、`observe_only`",
        "Layer C 两连板独立路径必须严格按设计文档",
        "只有连续两个交易日涨停（两连板）可以定义为独立龙头路径",
        "三天两板、近 7 日多次涨停并延续强势只能定义为强势股信号",
        "仍必须受 Layer A/B 主线约束",
        "`entry_path=independent_leader`、`identity_scope=independent_stock_signal`、`strong_gene_seed=true`",
        "不得伪造 Layer A/B 状态字段",
    ]
    missing = [fragment for fragment in required_fragments if fragment not in text]
    assert missing == []


def test_unified_guardrails_require_design_traceability_before_implementation() -> None:
    text = EXECUTION_GUARDRAILS.read_text(encoding="utf-8")

    required_fragments = [
        "设计文档优先与禁止编造规则",
        "不允许编造不符合设计文档的逻辑和规则",
        "必须能追溯到阶段设计文档、旧链等价函数或已登记 ADR",
        "必须先更新设计文档或登记 ADR 并完成评审，再进入实现",
        "只允许 fail-fast 或不输出该命题判断",
        "mock/stub/fake/fallback 不得作为核心业务判断依据",
        "质量门禁必须失败",
    ]
    missing = [fragment for fragment in required_fragments if fragment not in text]
    assert missing == []
