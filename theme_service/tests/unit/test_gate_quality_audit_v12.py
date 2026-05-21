from gate_quality_audit import GateRecord, compute_audit_rows


def test_gate_quality_audit_v12_rebuilds_public_news_only_must_gate() -> None:
    rows, _ = compute_audit_rows(
        [
            GateRecord(
                subject_key="9043458",
                subject_name="中国星际之门",
                strategy_type="policy_driven",
                semantic_type="政策驱动型产业集群",
                must=["政府企业集群", "政府"],
                should=["集群"],
                not_terms=[],
                strong=[],
                aliases=[],
                entity_hints=[],
                core_objects=[],
                evidence_refs=[],
                quality="weak",
            )
        ],
        {},
        {},
    )

    row = rows[0]
    assert row["risk_level"] == "A"
    assert row["suggested_action"] == "REBUILD"
    assert row["illegal_must_terms"] == ["政府企业集群", "政府"]
    assert "ILLEGAL_MUST_TERM" in row["risk_flags"]
    assert "NO_HARD_ANCHOR" in row["risk_flags"]
    assert "PUBLIC_NEWS_FALSE_POSITIVE_RISK" in row["risk_flags"]
