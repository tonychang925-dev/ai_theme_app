"""Apply Reviewer Verdict to a pending record and write to Historical Dataset.

Usage: python scripts/apply_verdict.py
"""

import asyncio
import json
import sys
from datetime import date, datetime, timezone
from pathlib import Path

import asyncpg

sys.path.insert(0, "/Users/admin/Desktop/ai_theme_app")
sys.path.insert(0, "/Users/admin/Desktop/ai_theme_app/stock_processing_service")

from stock_processing_service.application.services.market_cognition.knowledge_evidence import (
    MarketEvidenceAdapter,
    MarketKnowledgeBundleBuilder,
)
from stock_processing_service.application.services.market_cognition.cognition import (
    Phase0CognitionPipeline,
)
from stock_processing_service.application.services.market_cognition.verification import (
    FrozenHypothesisSource,
    MarketThesisVerificationService,
    ReviewerVerdict,
    TodayReality,
)
from stock_processing_service.application.services.market_cognition.validation_dataset import (
    MarketThesisValidationDataset,
)
from stock_processing_service.contracts.market_cognition import (
    canonical_hash,
)
from stock_processing_service.contracts.market_thesis_validation import (
    VerificationFailureType,
    VerificationLabel,
)

DSN = "postgresql://localhost:5432/stock_data_test"
TABLE = "post_market_recap_snapshot"
CHINA_TZ = timezone(__import__("datetime").timedelta(hours=8))
OUTPUT = Path("/Users/admin/Desktop/ai_theme_app/datasets/market_thesis_validation/historical/202607")

# ── Verdict (Reviewer fills this) ──
THESIS_TRADE_DATE = "2026-07-02"
VERIFICATION_TRADE_DATE = "2026-07-03"
VERDICT_LABEL = VerificationLabel.NO
FAILURE_TYPE = VerificationFailureType.WRONG_DIRECTION
REASON = "07-03 没有出现修复。通信/半导体继续主跌，科技赛道全线走弱，高位加速杀跌，低位冲高回落。主线修复的假设被市场明确拒绝。"
OUTCOME = "主线未修复，全市场普跌，交易权限维持不交易。"

DATASET_ROOT = Path("/Users/admin/Desktop/ai_theme_app/datasets/market_thesis_validation")


async def main():
    conn = await asyncpg.connect(DSN)

    # Load 07-02 snapshot (source)
    row_d = await conn.fetchrow(
        f"SELECT payload FROM {TABLE} WHERE trade_date=$1::date ORDER BY created_at DESC LIMIT 1",
        date.fromisoformat(THESIS_TRADE_DATE),
    )
    payload_d = json.loads(row_d["payload"]) if isinstance(row_d["payload"], str) else row_d["payload"]

    # Load 07-03 snapshot (reality)
    row_next = await conn.fetchrow(
        f"SELECT payload FROM {TABLE} WHERE trade_date=$1::date ORDER BY created_at DESC LIMIT 1",
        date.fromisoformat(VERIFICATION_TRADE_DATE),
    )
    payload_next = json.loads(row_next["payload"]) if isinstance(row_next["payload"], str) else row_next["payload"]
    await conn.close()

    # Build cognition from 07-02
    bundle_d = MarketKnowledgeBundleBuilder.build(payload_d, THESIS_TRADE_DATE)
    evidence_d = MarketEvidenceAdapter.build(bundle_d)
    cognition = Phase0CognitionPipeline.build(evidence_d)

    hypotheses = cognition.cognition.hypotheses
    if not hypotheses:
        print("ERROR: No hypotheses in 07-02 snapshot")
        return
    primary = hypotheses[0]
    print(f"Hypothesis: {primary.statement}")
    print(f"Deadline: {primary.deadline}")
    print(f"Probability: {primary.probability}")

    # Build Reality from 07-03
    bundle_next = MarketKnowledgeBundleBuilder.build(payload_next, VERIFICATION_TRADE_DATE)
    evidence_next = MarketEvidenceAdapter.build(bundle_next)
    reality_hash = getattr(evidence_next, "content_hash", "") or canonical_hash({"reality": VERIFICATION_TRADE_DATE})

    # Freeze source
    source = FrozenHypothesisSource(
        thesis_trade_date=THESIS_TRADE_DATE,
        source_snapshot_id=getattr(bundle_d, "bundle_id", f"mkb:{THESIS_TRADE_DATE}"),
        source_as_of=datetime(2026, 7, 2, 15, 30, tzinfo=CHINA_TZ),
        source_knowledge_hash=getattr(bundle_d, "content_hash", ""),
        source_evidence_hash=getattr(evidence_d, "content_hash", ""),
        source_context_hash=getattr(cognition.context, "content_hash", ""),
        source_thesis_hash=getattr(cognition.thesis, "content_hash", ""),
        source_quality_status="ready",
        source_quality_score=0.90,
        source_policy_version="m8_phase0_cognition.v1",
        hypothesis=primary,
    )

    # Build Reality with EvidenceRefs from 07-03 evidence
    reality_refs = tuple(
        getattr(evidence_next, "evidence_refs", ())
    ) or (
        # fallback: use the source evidence ref structure
        tuple(getattr(evidence_d, "evidence_refs", ()))
    )
    if not reality_refs:
        # Last resort: construct minimal ref from the evidence hashes
        from stock_processing_service.contracts.market_cognition import EvidenceRef
        reality_refs = (
            EvidenceRef(
                ref_id=f"ev:reality:{VERIFICATION_TRADE_DATE}",
                source_module="post_market_recap_snapshot",
                source_path="recap_doc",
                source_snapshot_id=getattr(bundle_next, "bundle_id", f"mkb:{VERIFICATION_TRADE_DATE}"),
            ),
        )

    reality = TodayReality(
        trade_date=VERIFICATION_TRADE_DATE,
        available_at=datetime(2026, 7, 3, 15, 30, tzinfo=CHINA_TZ),
        evidence_hash=reality_hash,
        evidence_refs=reality_refs,
    )

    # Reviewer Verdict
    verdict = ReviewerVerdict(
        reviewer_id="reviewer:tony",
        label=VERDICT_LABEL,
        failure_type=FAILURE_TYPE,
        reason=REASON,
        outcome=OUTCOME,
        reviewed_at=datetime.now(CHINA_TZ),
    )

    # Verify and create Validation Record
    service = MarketThesisVerificationService(approved_reviewer_ids={"reviewer:tony"})
    record = service.verify(source, reality, verdict)

    # Write to Historical Dataset
    OUTPUT.mkdir(parents=True, exist_ok=True)
    dataset = MarketThesisValidationDataset(DATASET_ROOT)
    result = dataset.append(record)

    print(f"\nValidation Record:")
    print(f"  ID: {record.record_id}")
    print(f"  Label: {record.label.value}")
    print(f"  Failure: {record.failure_type.value if record.failure_type else 'N/A'}")
    print(f"  Probability: {record.prediction_probability}")
    print(f"  Quality: {record.source_quality_score}")
    print(f"  Dataset status: {getattr(result, 'status', 'unknown')}")
    print(f"  Dataset total: {getattr(result, 'total_after', '?')}")
    print(f"  Record hash: {record.record_hash[:16]}...")

    # Write manifest
    manifest = dataset.scan()
    manifest_path = DATASET_ROOT / "manifest.json"
    manifest_path.write_text(
        json.dumps(manifest.to_dict() if hasattr(manifest, "to_dict") else str(manifest),
                   ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"  Manifest: {manifest_path}")
    print(f"\nDone. Historical Dataset record count: {result.total_after}")


asyncio.run(main())
