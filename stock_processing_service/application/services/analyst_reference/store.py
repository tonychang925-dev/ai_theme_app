"""Phase 4.2 — Analyst Reference Store.

Append-only store for AnalystReferenceRecord backed by JSONL + manifest.
"""

from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any

from .contracts import AnalystReferenceRecord, ExtractionStatus
from .repository import (
    Manifest,
    ManifestEntry,
    ReferenceRepository,
    ValidationReport,
    _serialize_record,
    compute_record_hash,
)


class AnalystReferenceStore:
    """Append-only persistence for analyst ground truth records.

    Usage:
        store = AnalystReferenceStore(base_dir="tmp/analyst_reference")
        record = parser.parse_file("analyst_recap_0707.md")
        store.append(record)
        loaded = store.get_by_date(date(2026, 7, 7))
    """

    def __init__(self, base_dir: str = "tmp/analyst_reference"):
        self._repo = ReferenceRepository(base_dir)

    # ── Write ──

    def append(self, record: AnalystReferenceRecord) -> str:
        """Append a record to the store. Returns content_hash.

        Versioning:
          - same date + same content → skip (no-op, return existing hash)
          - same date + diff content → add new version, update latest_hash
          - new date                 → add with single version
        """
        record_dict = _serialize_record(record)
        # Content hash excludes volatile fields (ingested_at)
        content_hash = self._content_hash(record_dict)
        date_str = record.trade_date.isoformat()

        # Read existing manifest
        manifest = self._repo.read_manifest()
        existing = manifest.records.get(date_str)

        if existing is not None:
            # Check if this exact content already exists
            if content_hash in existing.versions:
                return content_hash  # skip duplicate

            # Same date, different content → new version
            existing.versions.append(content_hash)
            existing.latest_hash = content_hash
            existing.extraction_status = record.quality.extraction_status.value
            existing.ingested_at = datetime.now(timezone.utc).isoformat()
        else:
            # New date
            if date_str not in manifest.dates:
                manifest.dates = sorted(set(manifest.dates + [date_str]))

            manifest.records[date_str] = ManifestEntry(
                trade_date=date_str,
                latest_hash=content_hash,
                versions=[content_hash],
                extraction_status=record.quality.extraction_status.value,
                ingested_at=datetime.now(timezone.utc).isoformat(),
            )

        # Persist JSONL
        self._repo.append_jsonl(record_dict)

        manifest.record_count = len(manifest.dates)
        self._repo.write_manifest(manifest)

        return content_hash

    def _content_hash(self, record_dict: dict[str, Any]) -> str:
        """Compute hash over stable fields (excludes ingested_at timestamp)."""
        stable = {k: v for k, v in record_dict.items() if k != "ingested_at"}
        return compute_record_hash(stable)

    # ── Read ──

    def get_by_date(self, trade_date: date) -> AnalystReferenceRecord | None:
        """Retrieve a record by trade date. Returns None if not found."""
        raw = self._repo.read_jsonl_by_date(trade_date)
        if raw is None:
            return None
        return self._dict_to_record(raw)

    def list_dates(self) -> list[date]:
        """All stored trade dates, sorted."""
        manifest = self._repo.read_manifest()
        return sorted(date.fromisoformat(d) for d in manifest.dates if d)

    def load_all(self) -> dict[date, AnalystReferenceRecord]:
        """Load all records into memory."""
        result: dict[date, AnalystReferenceRecord] = {}
        for rec_dict in self._repo.read_all_jsonl():
            td_str = rec_dict.get("trade_date", "")
            if td_str:
                td = date.fromisoformat(td_str)
                result[td] = self._dict_to_record(rec_dict)
        return result

    # ── Integrity ──

    def validate_manifest(self) -> ValidationReport:
        """Validate JSONL records against manifest."""
        return self._repo.validate()

    def rebuild_manifest(self) -> Manifest:
        """Rebuild manifest from JSONL (repair tool)."""
        return self._repo.rebuild_manifest()

    # ── Internal ──

    def _dict_to_record(self, d: dict[str, Any]) -> AnalystReferenceRecord:
        """Reconstruct AnalystReferenceRecord from JSONL dict."""
        from .contracts import (
            AnalystReferenceQuality,
            EmotionLabel,
            ExternalEnvironment,
            ExtractionStatus,
            LeaderState,
            LimitUpAttribution,
            MarketFacts,
            RelayLabel,
            StrategyLabel,
            ThemeLifecycleEntry,
        )

        mf = d.get("market_facts", {})
        facts = MarketFacts(
            limit_up_count=mf.get("limit_up_count"),
            chain_board_count=mf.get("chain_board_count"),
            max_board_height=mf.get("max_board_height"),
            active_capital_yi=mf.get("active_capital_yi"),
            market_up_ratio=mf.get("market_up_ratio"),
            loss_effect_ratio=mf.get("loss_effect_ratio"),
            composite_score=mf.get("composite_score"),
            down_below_minus5=mf.get("down_below_minus5"),
        )

        el = d.get("emotion_label", {})
        emotion = EmotionLabel(
            market_phase=el.get("market_phase", ""),
            risk_level=el.get("risk_level", ""),
            emotion_momentum=el.get("emotion_momentum"),
            cycle_score=el.get("cycle_score"),
            strategy=el.get("strategy", ""),
        )

        rl = d.get("relay_label", {})
        relay = RelayLabel(
            max_board_height=rl.get("max_board_height"),
            max_board_stock=rl.get("max_board_stock", ""),
            first_board_success_rate=rl.get("first_board_success_rate"),
            promotion_1_to_2=rl.get("promotion_1_to_2"),
            promotion_2_to_3=rl.get("promotion_2_to_3"),
            promotion_3_to_4=rl.get("promotion_3_to_4"),
            promotion_4_to_5=rl.get("promotion_4_to_5"),
            promotion_5_to_6=rl.get("promotion_5_to_6"),
            promotion_6_to_7=rl.get("promotion_6_to_7"),
        )

        themes = [
            ThemeLifecycleEntry(
                theme_name=t.get("theme_name", ""),
                state=t.get("state", ""),
                day_count=t.get("day_count", 0),
                style=t.get("style", ""),
                notes=t.get("notes", ""),
            )
            for t in d.get("theme_lifecycle", [])
        ]

        lu_attr = []
        for a in d.get("limitup_attribution", []):
            lu_attr.append(LimitUpAttribution(
                theme_name=a.get("theme_name", ""),
                board_heights=a.get("board_heights", []),
                stock_count=a.get("stock_count", 0),
                key_stocks=a.get("key_stocks", []),
            ))

        leaders = []
        for l in d.get("leader_state", []):
            leaders.append(LeaderState(
                stock_code=l.get("stock_code", ""),
                stock_name=l.get("stock_name", ""),
                board_height=l.get("board_height", 0),
                role=l.get("role", ""),
                theme=l.get("theme", ""),
                death_type=l.get("death_type", ""),
                board_str=l.get("board_str", ""),
            ))

        sl = d.get("strategy_label", {})
        strategy = StrategyLabel(
            allowed=sl.get("allowed", []),
            forbidden=sl.get("forbidden", []),
            watch_points=sl.get("watch_points", []),
            summary=sl.get("summary", ""),
        )

        ee = d.get("external_env", {})
        external = ExternalEnvironment(
            korea_index=ee.get("korea_index", {}),
            us_market=ee.get("us_market", {}),
            key_events=ee.get("key_events", []),
        )

        q = d.get("quality", {})
        status_str = q.get("extraction_status", d.get("extraction_status", "partial"))
        try:
            extraction_status = ExtractionStatus(status_str)
        except ValueError:
            extraction_status = ExtractionStatus.PARTIAL

        quality = AnalystReferenceQuality(
            extraction_status=extraction_status,
            required_field_coverage=q.get("required_field_coverage", 0.0),
            optional_field_coverage=q.get("optional_field_coverage", 0.0),
            missing_fields=tuple(q.get("missing_fields", [])),
            low_confidence_fields=tuple(q.get("low_confidence_fields", [])),
        )

        record = AnalystReferenceRecord(
            trade_date=date.fromisoformat(d.get("trade_date", "")),
            source_type=d.get("source_type", ""),
            source_path=d.get("source_path", ""),
            market_facts=facts,
            emotion_label=emotion,
            relay_label=relay,
            theme_lifecycle=themes,
            limitup_attribution=lu_attr,
            leader_state=leaders,
            strategy_label=strategy,
            external_env=external,
            quality=quality,
            confidence=d.get("confidence", 1.0),
            raw_text=d.get("raw_text", ""),
        )
        record.sync_legacy_fields()
        return record
