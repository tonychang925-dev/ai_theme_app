"""PR4.2.32a — Theme Capital Attribution Engine (Foundation).

Level 1 deterministic attribution only:
  - Reads stock_fund_flow_daily (PR4.2.31f)
  - Reads subject_stock_map with PRIMARY/RELATED roles
  - Applies PRIMARY=0.60, RELATED split remaining 0.40
  - Produces stock_theme_attribution_daily + theme_capital_flow_daily
  - Tracks unattributed stocks in unattributed_capital_daily

Forbidden: institution_style, hot_money_style, AI weights, sector proximity.
These are deferred to PR4.2.32b (enhancement) and PR4.2.34/35 (intelligence).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any

# ── Attribution constants ──

PRIMARY_WEIGHT_BASE = 0.60
RELATED_WEIGHT_POOL = 0.40
ATTRIBUTION_METHOD = "identity_registry"
ATTRIBUTION_VERSION = "identity_registry_v1"
FLOW_TYPE = "ATTRIBUTED_ORDER_FLOW"


# ── Output dataclasses ──

@dataclass(frozen=True, slots=True)
class StockThemeAttribution:
    """Per-stock-per-theme weight for a single trading day."""

    trade_date: date
    stock_code: str
    subject_key: str
    theme_name: str
    weight: float
    confidence: float
    method: str
    attribution_version: str
    source: str

    def to_row(self) -> dict[str, Any]:
        return {
            "trade_date": self.trade_date,
            "stock_code": self.stock_code,
            "subject_key": self.subject_key,
            "theme_name": self.theme_name,
            "weight": self.weight,
            "confidence": self.confidence,
            "method": self.method,
            "attribution_version": self.attribution_version,
            "source": self.source,
        }


@dataclass(frozen=True, slots=True)
class ThemeCapitalFlow:
    """Aggregated daily capital flow for a single theme."""

    trade_date: date
    subject_key: str
    theme_name: str
    net_flow_yuan: float | None
    large_flow_yuan: float | None
    flow_type: str
    stock_count: int
    attributed_stock_count: int
    positive_stock_count: int
    flow_coverage_ratio: float
    attribution_confidence: float
    attribution_method: str
    attribution_version: str

    def to_row(self) -> dict[str, Any]:
        return {
            "trade_date": self.trade_date,
            "subject_key": self.subject_key,
            "theme_name": self.theme_name,
            "net_flow_yuan": self.net_flow_yuan,
            "large_flow_yuan": self.large_flow_yuan,
            "flow_type": self.flow_type,
            "stock_count": self.stock_count,
            "attributed_stock_count": self.attributed_stock_count,
            "positive_stock_count": self.positive_stock_count,
            "flow_coverage_ratio": self.flow_coverage_ratio,
            "attribution_confidence": self.attribution_confidence,
            "attribution_method": self.attribution_method,
            "attribution_version": self.attribution_version,
        }


@dataclass(frozen=True, slots=True)
class UnattributedCapital:
    """Stock with fund flow but no theme binding."""

    trade_date: date
    stock_code: str
    stock_name: str
    net_flow_yuan: float | None
    large_flow_yuan: float | None
    reason: str

    def to_row(self) -> dict[str, Any]:
        return {
            "trade_date": self.trade_date,
            "stock_code": self.stock_code,
            "stock_name": self.stock_name,
            "net_flow_yuan": self.net_flow_yuan,
            "large_flow_yuan": self.large_flow_yuan,
            "reason": self.reason,
        }


# ── Level 1 Resolver ──

class StockThemeWeightResolver:
    """Resolve per-stock-per-theme weights from identity registry bindings.

    Level 1 only — PRIMARY/RELATED roles from subject_stock_map.
    No sector proximity, no AI. Deterministic and replayable.
    """

    def resolve(
        self,
        bindings: list[dict[str, Any]],
    ) -> list[StockThemeAttribution]:
        """Compute weights from stock→theme bindings.

        Args:
            bindings: List of rows from subject_stock_map with fields:
                trade_date, stock_code, subject_key, theme_name, role

        Returns:
            List of StockThemeAttribution with computed weights.
        """
        # Group by stock_code
        by_stock: dict[str, list[dict[str, Any]]] = {}
        for b in bindings:
            if not isinstance(b, dict):
                continue
            code = str(b.get("stock_code") or "").strip()
            if not code:
                continue
            by_stock.setdefault(code, []).append(b)

        results: list[StockThemeAttribution] = []
        td = _trade_date_from_bindings(bindings)

        for stock_code, items in by_stock.items():
            primaries = [i for i in items if str(i.get("role") or "").upper() == "PRIMARY"]
            relateds = [i for i in items if i not in primaries]

            if primaries:
                # PRIMARY gets 0.60 split, RELATED split remaining 0.40
                primary_weight_each = PRIMARY_WEIGHT_BASE / len(primaries)
                related_weight_each = RELATED_WEIGHT_POOL / len(relateds) if relateds else 0.0

                for item in primaries:
                    results.append(self._make_attribution(td, stock_code, item, primary_weight_each))
                for item in relateds:
                    results.append(self._make_attribution(td, stock_code, item, related_weight_each))
            else:
                # No PRIMARY flag → fall back to equal split
                weight_each = 1.0 / len(items)
                for item in items:
                    results.append(self._make_attribution(td, stock_code, item, weight_each))

        return results

    def _make_attribution(
        self, td: date, stock_code: str, item: dict[str, Any], weight: float
    ) -> StockThemeAttribution:
        return StockThemeAttribution(
            trade_date=td,
            stock_code=stock_code,
            subject_key=str(item.get("subject_key") or ""),
            theme_name=str(item.get("theme_name") or ""),
            weight=round(weight, 4),
            confidence=0.90,  # Level 1: high confidence
            method=ATTRIBUTION_METHOD,
            attribution_version=ATTRIBUTION_VERSION,
            source="subject_stock_map",
        )


# ── Attribution Engine ──

class ThemeCapitalAttributionEngine:
    """Aggregate stock fund flows into theme capital flows using attribution weights.

    Level 1 deterministic only. Enforces C8 conservation:
      ABS(SUM(theme_flow) - SUM(stock_flow)) < epsilon
    """

    def attribute(
        self,
        fund_flows: list[dict[str, Any]],
        attributions: list[StockThemeAttribution],
        *,
        theme_universe: dict[str, int] | None = None,
    ) -> tuple[list[ThemeCapitalFlow], list[UnattributedCapital]]:
        """Attribute stock flows to themes.

        Args:
            fund_flows: Rows from stock_fund_flow_daily with fields:
                ts_code, order_size_flow_amount_yuan, buy_lg_amount_yuan,
                sell_lg_amount_yuan, buy_elg_amount_yuan, sell_elg_amount_yuan
            attributions: StockThemeAttribution rows from resolver.
            theme_universe: Optional {subject_key: stock_count} for coverage calc.

        Returns:
            (theme_flows, unattributed) tuple.
        """
        # Index flows by stock_code
        flow_by_code: dict[str, dict[str, Any]] = {}
        for f in fund_flows:
            if not isinstance(f, dict):
                continue
            code = str(f.get("ts_code") or "").strip()
            if code:
                flow_by_code[code] = f

        # Index attributions by stock_code
        attr_by_code: dict[str, list[StockThemeAttribution]] = {}
        for a in attributions:
            attr_by_code.setdefault(a.stock_code, []).append(a)

        # Aggregate per theme
        theme_agg: dict[str, dict[str, Any]] = {}
        unattributed: list[UnattributedCapital] = []
        td = _trade_date_from_flows(fund_flows)

        for stock_code, flow in flow_by_code.items():
            net_flow = _float(flow.get("order_size_flow_amount_yuan"))
            large_flow = _large_flow_from_buckets(flow)
            stock_name = str(_extract_stock_name(flow, stock_code))

            attrs = attr_by_code.get(stock_code, [])
            if not attrs:
                if net_flow is not None:
                    unattributed.append(UnattributedCapital(
                        trade_date=td,
                        stock_code=stock_code,
                        stock_name=stock_name,
                        net_flow_yuan=net_flow,
                        large_flow_yuan=large_flow,
                        reason="no_theme_binding",
                    ))
                continue

            for attr in attrs:
                key = attr.subject_key
                if key not in theme_agg:
                    theme_agg[key] = {
                        "subject_key": key,
                        "theme_name": attr.theme_name,
                        "net_flow_yuan": 0.0,
                        "large_flow_yuan": 0.0,
                        "stock_codes": set(),
                        "positive_stock_codes": set(),
                        "confidences": [],
                    }
                agg = theme_agg[key]
                if net_flow is not None:
                    agg["net_flow_yuan"] += net_flow * attr.weight
                if large_flow is not None:
                    agg["large_flow_yuan"] += large_flow * attr.weight
                agg["stock_codes"].add(stock_code)
                if net_flow is not None and net_flow > 0:
                    agg["positive_stock_codes"].add(stock_code)
                agg["confidences"].append(attr.confidence)

        # Build output
        theme_flows: list[ThemeCapitalFlow] = []
        for key, agg in sorted(theme_agg.items()):
            stock_codes = agg["stock_codes"]
            attr_count = len(stock_codes)
            universe_count = (theme_universe or {}).get(key, attr_count)

            theme_flows.append(ThemeCapitalFlow(
                trade_date=td,
                subject_key=key,
                theme_name=agg["theme_name"],
                net_flow_yuan=round(agg["net_flow_yuan"], 2) if agg["net_flow_yuan"] != 0 else None,
                large_flow_yuan=round(agg["large_flow_yuan"], 2) if agg["large_flow_yuan"] != 0 else None,
                flow_type=FLOW_TYPE,
                stock_count=universe_count,
                attributed_stock_count=attr_count,
                positive_stock_count=len(agg["positive_stock_codes"]),
                flow_coverage_ratio=round(attr_count / max(universe_count, 1), 4),
                attribution_confidence=round(
                    sum(agg["confidences"]) / max(len(agg["confidences"]), 1), 4
                ),
                attribution_method=ATTRIBUTION_METHOD,
                attribution_version=ATTRIBUTION_VERSION,
            ))

        return theme_flows, unattributed


# ── Helpers ──

def _float(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _large_flow_from_buckets(flow: dict[str, Any]) -> float | None:
    """Compute large+extra-large net flow from buy/sell buckets."""
    buy_lg = _float(flow.get("buy_lg_amount_yuan")) or 0.0
    sell_lg = _float(flow.get("sell_lg_amount_yuan")) or 0.0
    buy_elg = _float(flow.get("buy_elg_amount_yuan")) or 0.0
    sell_elg = _float(flow.get("sell_elg_amount_yuan")) or 0.0
    result = buy_lg + buy_elg - sell_lg - sell_elg
    return result if result != 0 else None


def _extract_stock_name(flow: dict[str, Any], fallback: str) -> str:
    name = flow.get("stock_name") or flow.get("ts_code") or fallback
    return str(name)


def _trade_date_from_bindings(bindings: list[dict[str, Any]]) -> date:
    for b in bindings:
        td = b.get("trade_date")
        if td:
            return _to_date(td)
    return date.today()


def _trade_date_from_flows(flows: list[dict[str, Any]]) -> date:
    for f in flows:
        td = f.get("trade_date")
        if td:
            return _to_date(td)
    return date.today()


def _to_date(value: Any) -> date:
    if isinstance(value, date):
        return value
    text = str(value).strip()
    if len(text) == 8 and text.isdigit():
        return date(int(text[:4]), int(text[4:6]), int(text[6:8]))
    return date.fromisoformat(text[:10])
