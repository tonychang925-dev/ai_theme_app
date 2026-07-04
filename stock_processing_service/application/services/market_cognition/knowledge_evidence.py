from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timedelta, timezone
from typing import Any

from stock_processing_service.contracts.market_cognition import (
    EvidenceItem,
    EvidenceRef,
    MarketEvidenceSnapshot,
    MarketKnowledgeBundle,
    QualityEnvelope,
    SourceCoverage,
    canonical_hash,
)


_MODULES = (
    "engine_summary",
    "market_regime_review",
    "daily_recap_essentials",
    "mainline_states",
    "theme_reviews",
    "limit_up_theme_events",
    "new_high_summary",
    "seat_money_summary",
    "watchlists",
    "post_market_setup_plan",
)

_MODULE_ALIASES: dict[str, tuple[str, ...]] = {
    "engine_summary": ("engine_summary",),
    "market_regime_review": ("market_regime_review",),
    "daily_recap_essentials": ("daily_recap_essentials",),
    "mainline_states": (
        "mainline_states",
        "mainline_daily_states",
        "mainline_reviews",
    ),
    "theme_reviews": ("theme_reviews",),
    "limit_up_theme_events": ("limit_up_theme_events",),
    "new_high_summary": ("new_high_summary",),
    "seat_money_summary": ("seat_money_summary",),
    "watchlists": ("watchlists",),
    "post_market_setup_plan": ("post_market_setup_plan",),
}


def _default_as_of(trade_date: str) -> datetime:
    day = datetime.fromisoformat(trade_date)
    china_timezone = timezone(timedelta(hours=8))
    return day.replace(hour=15, minute=30, second=0, tzinfo=china_timezone)


def _extract_document(payload: dict[str, Any]) -> dict[str, Any]:
    recap_doc = payload.get("recap_doc")
    if isinstance(recap_doc, dict) and recap_doc:
        return recap_doc
    return payload


def _row_count(value: Any) -> int:
    if isinstance(value, list):
        return len([item for item in value if isinstance(item, dict)])
    if isinstance(value, dict):
        return 1 if value else 0
    return 1 if value is not None else 0


def _module_value(document: dict[str, Any], module: str) -> Any:
    v2 = document.get("daily_review_v2")
    v2 = v2 if isinstance(v2, dict) else {}
    for source in (document, v2):
        for field in _MODULE_ALIASES[module]:
            value = source.get(field)
            if value not in (None, {}, []):
                return value
    return None


class MarketKnowledgeBundleBuilder:
    """Assemble existing post-market knowledge without recalculation."""

    @classmethod
    def build(
        cls,
        payload: dict[str, Any],
        trade_date: str,
        *,
        as_of: datetime | None = None,
    ) -> MarketKnowledgeBundle:
        if not isinstance(payload, dict) or not payload:
            raise ValueError("empty market knowledge payload")
        document = _extract_document(payload)
        if not isinstance(document, dict) or not document:
            raise ValueError("empty recap document")

        effective_as_of = as_of or _default_as_of(trade_date)
        knowledge: dict[str, Any] = {}
        for module in _MODULES:
            value = _module_value(document, module)
            if value not in (None, {}, []):
                knowledge[module] = deepcopy(value)
        coverage = tuple(
            SourceCoverage(
                module=module,
                status="ready" if module in knowledge else "missing",
                row_count=_row_count(knowledge.get(module)),
            )
            for module in _MODULES
        )
        missing_modules = tuple(
            item.module for item in coverage if item.status == "missing"
        )
        ready_count = len(coverage) - len(missing_modules)
        quality = QualityEnvelope(
            status="ready" if not missing_modules else "partial",
            score=round(ready_count / len(coverage), 6),
            missing_modules=missing_modules,
        )
        producer_versions = tuple(
            (module, str(document.get(f"{module}_version") or "existing"))
            for module in knowledge
        )
        source_snapshot_ids = tuple(
            str(value)
            for value in (
                payload.get("snapshot_id"),
                payload.get("report_id"),
                document.get("snapshot_id"),
            )
            if value
        )
        hash_input = {
            "schema_version": "market_knowledge_bundle.v1",
            "trade_date": trade_date,
            "as_of": effective_as_of.isoformat(),
            "knowledge": knowledge,
            "source_snapshot_ids": source_snapshot_ids,
            "producer_versions": producer_versions,
            "coverage": coverage,
            "quality": quality,
        }
        content_hash = canonical_hash(hash_input)
        return MarketKnowledgeBundle(
            bundle_id=f"mkb:{trade_date}:{content_hash[:16]}",
            schema_version="market_knowledge_bundle.v1",
            trade_date=trade_date,
            as_of=effective_as_of,
            knowledge=knowledge,
            source_snapshot_ids=source_snapshot_ids,
            producer_versions=producer_versions,
            module_coverage=coverage,
            quality=quality,
            content_hash=content_hash,
        )


class MarketEvidenceAdapter:
    """Map producer-owned knowledge to referenced evidence items."""

    _PATHS: tuple[tuple[str, str, str], ...] = (
        ("engine_summary", "allow_trade", "decision.allow_trade"),
        ("engine_summary", "trade_mode", "decision.trade_mode"),
        ("engine_summary", "blocking_rule", "decision.blocking_rule"),
        (
            "engine_summary",
            "no_trade_blocking_rule",
            "decision.blocking_rule",
        ),
        ("engine_summary", "position_limit", "decision.position_limit"),
        ("engine_summary", "next_day_strategy", "decision.next_day_strategy"),
        (
            "market_regime_review",
            "broad_market_regime",
            "market.broad_market_regime",
        ),
        (
            "market_regime_review",
            "short_term_sentiment",
            "market.short_term_sentiment",
        ),
        (
            "market_regime_review",
            "mainline_environment",
            "market.mainline_environment",
        ),
    )

    @classmethod
    def build(cls, bundle: MarketKnowledgeBundle) -> MarketEvidenceSnapshot:
        items: list[EvidenceItem] = []
        emitted_keys: set[str] = set()
        for module, field, key in cls._PATHS:
            value = bundle.knowledge.get(module)
            if (
                key in emitted_keys
                or not isinstance(value, dict)
                or field not in value
                or value[field] is None
            ):
                continue
            items.append(cls._item(bundle, module, field, key, deepcopy(value[field])))
            emitted_keys.add(key)

        setup_plan = bundle.knowledge.get("post_market_setup_plan")
        setup_summary = (
            setup_plan.get("summary")
            if isinstance(setup_plan, dict)
            else None
        )
        if (
            isinstance(setup_summary, dict)
            and setup_summary.get("watch_date")
            and "calendar.next_trade_date" not in emitted_keys
        ):
            items.append(
                cls._item(
                    bundle,
                    "post_market_setup_plan",
                    "summary.watch_date",
                    "calendar.next_trade_date",
                    deepcopy(setup_summary["watch_date"]),
                )
            )
            emitted_keys.add("calendar.next_trade_date")

        mainlines = bundle.knowledge.get("mainline_states")
        if isinstance(mainlines, list):
            for index, row in enumerate(mainlines):
                if not isinstance(row, dict):
                    continue
                for field, normalized in (
                    ("theme_name", "name"),
                    ("subject_name", "name"),
                    ("mainline_name", "name"),
                    ("lifecycle", "lifecycle"),
                    ("lifecycle_state", "lifecycle"),
                    ("state", "state"),
                    ("strong_stock_count", "strong_stock_count"),
                    ("strong_pool_count", "strong_stock_count"),
                ):
                    if field not in row or row[field] is None:
                        continue
                    key = f"mainline.{index}.{normalized}"
                    if key in emitted_keys:
                        continue
                    items.append(
                        cls._item(
                            bundle,
                            "mainline_states",
                            f"{index}.{field}",
                            key,
                            deepcopy(row[field]),
                        )
                    )
                    emitted_keys.add(key)

        hash_input = {
            "schema_version": "market_evidence.v1",
            "trade_date": bundle.trade_date,
            "as_of": bundle.as_of.isoformat(),
            "source_bundle_id": bundle.bundle_id,
            "evidence": items,
            "coverage": bundle.module_coverage,
            "quality": bundle.quality,
        }
        content_hash = canonical_hash(hash_input)
        return MarketEvidenceSnapshot(
            snapshot_id=f"mes:{bundle.trade_date}:{content_hash[:16]}",
            schema_version="market_evidence.v1",
            trade_date=bundle.trade_date,
            as_of=bundle.as_of,
            evidence=tuple(items),
            module_coverage=bundle.module_coverage,
            quality=bundle.quality,
            source_bundle_id=bundle.bundle_id,
            content_hash=content_hash,
        )

    @staticmethod
    def _item(
        bundle: MarketKnowledgeBundle,
        module: str,
        source_path: str,
        key: str,
        value: Any,
    ) -> EvidenceItem:
        ref = EvidenceRef(
            ref_id=f"ev:{bundle.bundle_id}:{module}:{source_path}",
            source_module=module,
            source_path=source_path,
            source_snapshot_id=bundle.bundle_id,
        )
        return EvidenceItem(
            key=key,
            value=value,
            ref=ref,
            observed_at=bundle.as_of,
        )
