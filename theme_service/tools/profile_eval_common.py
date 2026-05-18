from __future__ import annotations

from typing import Any

from theme_service.services.theme_match_engine import ThemeMatchEngine
from theme_service.services.theme_match_types import ThemeMatchRequest

from theme_service.tools.profile_quality_common import is_generic_term, normalize_list, safe_str


def request_from_hard_negative(row: dict[str, Any], event_id: int = 0) -> ThemeMatchRequest:
    text = safe_str(row.get("event_text") or row.get("content") or row.get("summary"))
    return ThemeMatchRequest(
        event_id=event_id,
        news_id=0,
        title=safe_str(row.get("title") or "hard_negative_case"),
        content=text,
        summary=text[:300],
        event_type="hard_negative",
        entities=normalize_list(row.get("entities")),
        raw_event_json=row,
        trace_id=safe_str(row.get("case_id")),
    )


def disable_llm_for_engine(engine: ThemeMatchEngine, *, gate_only: bool = False) -> None:
    """Hard-negative regression should be deterministic and local by default."""
    if getattr(engine, "_judge", None) is not None:
        engine._judge.api_key = ""
    if getattr(engine, "_event_profile_extractor", None) is not None:
        engine._event_profile_extractor.api_key = ""
    if not gate_only:
        return
    async def _no_dense_recall(request, event_profile):
        return []

    def _no_embedding_rerank(request, candidate_rows, profile_map, event_profile=None):
        rows = []
        for row in candidate_rows or []:
            item = dict(row)
            item["semantic_score"] = 0.0
            item["feature_score"] = float(item.get("feature_recall_score") or 0.0)
            item["rerank_score"] = float(item.get("feature_recall_score") or 0.0)
            item["evidence"] = item.get("feature_recall_evidence") or item.get("evidence") or {}
            rows.append(item)
        rows.sort(
            key=lambda x: (
                -float(x.get("rerank_score") or 0.0),
                -float(x.get("dense_score") or 0.0),
                safe_str(x.get("subject_key")),
            )
        )
        return rows

    engine._dense_recall = _no_dense_recall
    engine._rerank = _no_embedding_rerank


def result_subject_keys(result: Any) -> list[str]:
    keys = []
    if safe_str(result.matched_subject_key):
        keys.append(safe_str(result.matched_subject_key))
    for item in result.related_matches or []:
        key = safe_str(item.get("subject_key"))
        if key:
            keys.append(key)
    return keys


def result_theme_names(result: Any) -> list[str]:
    names = []
    if safe_str(result.matched_theme_name):
        names.append(safe_str(result.matched_theme_name))
    for item in result.related_matches or []:
        name = safe_str(item.get("theme_name"))
        if name:
            names.append(name)
    return names


def hard_negative_wrong_hits(result: Any, case: dict[str, Any]) -> dict[str, list[str]]:
    must_not_keys = set(normalize_list(case.get("must_not_subject_keys")))
    must_not_names = normalize_list(case.get("must_not_theme_names"))
    keys = result_subject_keys(result)
    names = result_theme_names(result)
    wrong_keys = [key for key in keys if key in must_not_keys]
    wrong_names = [
        name
        for name in names
        if any(_must_not_name_matches(blocked, name) for blocked in must_not_names)
    ]
    return {"subject_keys": wrong_keys, "theme_names": wrong_names}


def _must_not_name_matches(blocked: str, actual: str) -> bool:
    blocked = safe_str(blocked)
    actual = safe_str(actual)
    if not blocked or not actual:
        return False
    if blocked == actual:
        return True
    # Allow a full must-not alias to catch shorter actual aliases, but do not let
    # broad labels like "半导体" reject specific children like "半导体设备".
    return actual in blocked and len(actual) >= 3


def is_hard_negative_rejected(result: Any, case: dict[str, Any]) -> bool:
    hits = hard_negative_wrong_hits(result, case)
    return not hits["subject_keys"] and not hits["theme_names"]


def count_wrong_related(result: Any, case: dict[str, Any]) -> int:
    must_not_keys = set(normalize_list(case.get("must_not_subject_keys")))
    must_not_names = normalize_list(case.get("must_not_theme_names"))
    count = 0
    for item in result.related_matches or []:
        key = safe_str(item.get("subject_key"))
        name = safe_str(item.get("theme_name"))
        if key in must_not_keys or any(_must_not_name_matches(blocked, name) for blocked in must_not_names):
            count += 1
    return count


def _related_anchor_terms(item: dict[str, Any]) -> list[str]:
    evidence = item.get("evidence") if isinstance(item.get("evidence"), dict) else {}
    terms: list[str] = []
    for key in (
        "anchor_terms",
        "profile_anchor_hits",
        "object_hits",
        "must_hits",
        "strong_hits",
        "entity_hits",
        "theme_name_hit_terms",
    ):
        terms.extend(normalize_list(evidence.get(key)))
    return terms


def count_generic_only_related(result: Any) -> int:
    count = 0
    for item in result.related_matches or []:
        terms = _related_anchor_terms(item)
        if terms and all(is_generic_term(term) for term in terms):
            count += 1
    return count


def hard_negative_row(case: dict[str, Any], result: Any, prefix: str = "") -> dict[str, Any]:
    wrong_hits = hard_negative_wrong_hits(result, case)
    key = f"{prefix}_" if prefix else ""
    return {
        f"{key}decision": result.decision,
        f"{key}subject_key": result.matched_subject_key,
        f"{key}theme_name": result.matched_theme_name,
        f"{key}related_count": len(result.related_matches or []),
        f"{key}wrong_subject_keys": wrong_hits["subject_keys"],
        f"{key}wrong_theme_names": wrong_hits["theme_names"],
        f"{key}wrong_related_count": count_wrong_related(result, case),
        f"{key}generic_only_related_count": count_generic_only_related(result),
        f"{key}rejected": not wrong_hits["subject_keys"] and not wrong_hits["theme_names"],
    }
