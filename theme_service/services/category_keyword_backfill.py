from __future__ import annotations

import json
from collections import defaultdict
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List


@dataclass
class CategoryKeywordBackfillResult:
    updates: Dict[str, List[str]]
    l1_derived_keywords: Dict[str, List[str]]
    l2_derived_keywords: Dict[str, List[str]]
    metrics: Dict[str, float]


def _to_dict(obj: Any) -> Dict[str, Any]:
    if isinstance(obj, dict):
        return obj
    if hasattr(obj, "to_dict"):
        return obj.to_dict()
    return {}


def _normalize_keywords(values: Iterable[Any]) -> List[str]:
    dedup = set()
    ordered: List[str] = []
    for raw in values:
        if raw is None:
            continue
        kw = str(raw).strip()
        if len(kw) < 2:
            continue
        if kw in dedup:
            continue
        dedup.add(kw)
        ordered.append(kw)
    return ordered


def _parse_tags(tags: Any) -> Dict[str, Any]:
    if isinstance(tags, dict):
        return tags
    if isinstance(tags, str) and tags.strip():
        try:
            parsed = json.loads(tags)
            if isinstance(parsed, dict):
                return parsed
        except Exception:
            return {}
    if hasattr(tags, "to_dict"):
        parsed = tags.to_dict()
        if isinstance(parsed, dict):
            return parsed
    return {}


def _extract_theme_keywords(theme: Any) -> List[str]:
    data = _to_dict(theme)
    tags = _parse_tags(data.get("tags"))
    return _normalize_keywords(tags.get("keywords", []))


def _get_theme_field(theme: Any, key: str) -> Any:
    if isinstance(theme, dict):
        return theme.get(key)
    return getattr(theme, key, None)


def _get_category_field(category: Dict[str, Any], key: str, default: Any = None) -> Any:
    return category.get(key, default)


def build_category_keyword_backfill(
    categories: List[Dict[str, Any]],
    themes: List[Any],
) -> CategoryKeywordBackfillResult:
    """Build keyword backfill plan with strict inheritance:
    - L2 keywords <- L3 theme tags.keywords
    - L1 keywords <- aggregated L2 keywords
    """
    level2_codes = {
        c.get("category_code")
        for c in categories
        if _get_category_field(c, "category_level") == 2 and c.get("category_code")
    }

    category_by_code = {
        c.get("category_code"): c for c in categories if c.get("category_code")
    }
    l2_by_parent: Dict[str, List[str]] = defaultdict(list)
    for c in categories:
        if _get_category_field(c, "category_level") != 2:
            continue
        code = c.get("category_code")
        parent = c.get("parent_code")
        if code and parent:
            l2_by_parent[parent].append(code)

    l2_derived: Dict[str, List[str]] = {}
    l2_collect: Dict[str, List[str]] = defaultdict(list)
    for theme in themes:
        status = _get_theme_field(theme, "status")
        if status and status != "active":
            continue
        cat2 = _get_theme_field(theme, "category2_code")
        if not cat2 or cat2 not in level2_codes:
            continue
        kws = _extract_theme_keywords(theme)
        if kws:
            l2_collect[cat2].extend(kws)

    for cat2, kws in l2_collect.items():
        l2_derived[cat2] = _normalize_keywords(kws)

    l1_derived: Dict[str, List[str]] = {}
    for c in categories:
        if _get_category_field(c, "category_level") != 1:
            continue
        l1_code = c.get("category_code")
        if not l1_code:
            continue
        acc: List[str] = []
        for child_l2 in l2_by_parent.get(l1_code, []):
            acc.extend(l2_derived.get(child_l2, []))
        l1_derived[l1_code] = _normalize_keywords(acc)

    updates: Dict[str, List[str]] = {}
    l1_total = l1_non_empty_before = l1_non_empty_after = 0
    l2_total = l2_non_empty_before = l2_non_empty_after = 0

    for c in categories:
        code = c.get("category_code")
        level = _get_category_field(c, "category_level")
        if code is None or level not in (1, 2):
            continue
        existing = _normalize_keywords(c.get("keywords", []))
        derived = l1_derived.get(code, []) if level == 1 else l2_derived.get(code, [])
        merged = _normalize_keywords(existing + derived)
        if merged != existing:
            updates[code] = merged

        if level == 1:
            l1_total += 1
            if existing:
                l1_non_empty_before += 1
            if merged:
                l1_non_empty_after += 1
        else:
            l2_total += 1
            if existing:
                l2_non_empty_before += 1
            if merged:
                l2_non_empty_after += 1

    def _rate(num: int, den: int) -> float:
        return (num / den) if den else 0.0

    metrics = {
        "l1_non_empty_rate_before": _rate(l1_non_empty_before, l1_total),
        "l1_non_empty_rate_after": _rate(l1_non_empty_after, l1_total),
        "l2_non_empty_rate_before": _rate(l2_non_empty_before, l2_total),
        "l2_non_empty_rate_after": _rate(l2_non_empty_after, l2_total),
        "category_keyword_coverage_before": _rate(
            l1_non_empty_before + l2_non_empty_before, l1_total + l2_total
        ),
        "category_keyword_coverage_after": _rate(
            l1_non_empty_after + l2_non_empty_after, l1_total + l2_total
        ),
        "updated_category_count": float(len(updates)),
    }

    return CategoryKeywordBackfillResult(
        updates=updates,
        l1_derived_keywords=l1_derived,
        l2_derived_keywords=l2_derived,
        metrics=metrics,
    )
