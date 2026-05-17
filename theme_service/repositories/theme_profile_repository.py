from __future__ import annotations

import json
import logging
import os
import re
from typing import Any, Dict, List

from theme_service.services.theme_match_types import ThemeProfile

logger = logging.getLogger(__name__)

CANONICAL_SUBJECT_KEY_MAP: Dict[str, str] = {
    "9037499": "9030409",
}


def _safe_str(value: Any) -> str:
    return "" if value is None else str(value).strip()


def _load_json(value: Any) -> Dict[str, Any]:
    if isinstance(value, dict):
        return value
    if isinstance(value, str) and value.strip():
        try:
            parsed = json.loads(value)
            return parsed if isinstance(parsed, dict) else {}
        except Exception:
            return {}
    return {}


def _normalize_list(value: Any) -> List[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [_safe_str(x) for x in value if _safe_str(x)]
    if isinstance(value, tuple):
        return [_safe_str(x) for x in value if _safe_str(x)]
    if isinstance(value, str):
        s = value.strip()
        if not s:
            return []
        try:
            parsed = json.loads(s)
            if isinstance(parsed, list):
                return [_safe_str(x) for x in parsed if _safe_str(x)]
        except Exception:
            pass
        return [x.strip() for x in s.split(",") if x.strip()]
    return []


def _unique_keep_order(items: List[str]) -> List[str]:
    out: List[str] = []
    seen = set()
    for item in items:
        value = _safe_str(item)
        if not value or value in seen:
            continue
        seen.add(value)
        out.append(value)
    return out


def _merge_profiles(profiles: List[ThemeProfile]) -> List[ThemeProfile]:
    merged: Dict[str, ThemeProfile] = {}
    for profile in profiles:
        subject_key = _safe_str(profile.subject_key)
        canonical_key = CANONICAL_SUBJECT_KEY_MAP.get(subject_key, subject_key)
        if canonical_key not in merged:
            if canonical_key != subject_key:
                profile.subject_key = canonical_key
            merged[canonical_key] = profile
            continue

        base = merged[canonical_key]
        base.aliases = _unique_keep_order(
            base.aliases
            + [profile.subject_name, profile.concept]
            + profile.aliases
        )
        base.entity_hints = _unique_keep_order(base.entity_hints + profile.entity_hints)
        base.core_objects = _unique_keep_order(base.core_objects + profile.core_objects)
        base.must_terms = _unique_keep_order(base.must_terms + profile.must_terms)
        base.should_terms = _unique_keep_order(base.should_terms + profile.should_terms)
        base.strong_terms = _unique_keep_order(base.strong_terms + profile.strong_terms)
        base.weak_terms = _unique_keep_order(base.weak_terms + profile.weak_terms)
        base.not_terms = _unique_keep_order(base.not_terms + profile.not_terms)
        base.negative_terms = _unique_keep_order(base.negative_terms + profile.negative_terms)
        base.search_text = _safe_str(" ".join([base.search_text, profile.search_text]))
        if not _safe_str(base.rerank_text) and _safe_str(profile.rerank_text):
            base.rerank_text = profile.rerank_text
    return list(merged.values())


class ThemeProfileRepository:
    """基于 DatabaseGateway 的题材画像领域适配层"""

    def __init__(self, database_gateway):
        self.database_gateway = database_gateway

    async def load_active_profiles(self) -> List[ThemeProfile]:
        rows = await self.database_gateway.load_theme_match_profiles()
        v1_profiles = self._rows_to_v1_profiles(rows)
        if os.getenv("THEME_PROFILE_VERSION", "v1").lower() != "v2":
            merged_v1 = _merge_profiles(v1_profiles)
            logger.info("ThemeProfileRepository loaded v1 profiles count=%s", len(merged_v1))
            return merged_v1

        v2_rows = await self._load_v2_rows()
        v2_profiles = self._rows_to_v2_profiles(v2_rows)
        fallback_to_v1 = os.getenv("THEME_PROFILE_V2_FALLBACK_TO_V1", "true").lower() in {"1", "true", "yes", "on"}
        if not fallback_to_v1:
            merged_v2 = _merge_profiles(v2_profiles)
            logger.info(
                "ThemeProfileRepository loaded v2 only profiles v2_count=%s status=%s",
                len(merged_v2),
                os.getenv("THEME_PROFILE_V2_STATUS", "draft"),
            )
            return merged_v2

        merged = {profile.subject_key: profile for profile in _merge_profiles(v1_profiles)}
        merged_v2 = _merge_profiles(v2_profiles)
        for profile in merged_v2:
            merged[profile.subject_key] = profile
        logger.info(
            "ThemeProfileRepository loaded v2 overlay profiles v1_count=%s v2_loaded_count=%s "
            "v1_fallback_count=%s status=%s subject_key_filter_count=%s",
            len(_merge_profiles(v1_profiles)),
            len(merged_v2),
            max(0, len(merged) - len(merged_v2)),
            os.getenv("THEME_PROFILE_V2_STATUS", "draft"),
            len([item for item in re.split(r"[,，\s]+", os.getenv("THEME_PROFILE_V2_SUBJECT_KEYS", "")) if item.strip()]),
        )
        return list(merged.values())

    async def _load_v2_rows(self) -> List[Dict[str, Any]]:
        fn = getattr(self.database_gateway, "load_theme_profile_v2_profiles", None)
        if not callable(fn):
            return []
        status = os.getenv("THEME_PROFILE_V2_STATUS", "draft")
        subject_keys_raw = os.getenv("THEME_PROFILE_V2_SUBJECT_KEYS", "")
        subject_keys = [
            item.strip()
            for item in re.split(r"[,，\s]+", subject_keys_raw)
            if item.strip()
        ]
        return await fn(status=status, subject_keys=subject_keys or None)

    def _rows_to_v1_profiles(self, rows: List[Dict[str, Any]]) -> List[ThemeProfile]:
        profiles: List[ThemeProfile] = []
        generic_alias_stopwords = {"AI", "AR", "VR", "XR", "IPO", "APP", "GPT", "AIGC"}

        for row in rows:
            ontology = _load_json(row.get("ontology_json"))
            gate = _load_json(row.get("gate_json"))
            aliases: List[str] = []
            entity_hints: List[str] = []
            core_objects: List[str] = []

            for key in ["aliases", "synonyms", "alias", "same_as"]:
                aliases.extend(_normalize_list(ontology.get(key)))
                aliases.extend(_normalize_list(gate.get(key)))

            for key in ["entities", "entity_hints", "brands", "products", "companies"]:
                entity_hints.extend(_normalize_list(ontology.get(key)))
                entity_hints.extend(_normalize_list(gate.get(key)))

            for key in ["core_objects", "objects", "anchors", "anchor_terms"]:
                core_objects.extend(_normalize_list(ontology.get(key)))
                core_objects.extend(_normalize_list(gate.get(key)))

            base_subject_name = _safe_str(row.get("subject_name"))
            base_concept = _safe_str(row.get("concept"))
            auto_aliases = [base_subject_name, base_concept]
            for source_text in [base_subject_name, base_concept]:
                if not source_text:
                    continue
                for tok in re.findall(r"[A-Za-z][A-Za-z0-9._-]{1,}", source_text):
                    token = _safe_str(tok)
                    if not token or token.upper() in generic_alias_stopwords:
                        continue
                    auto_aliases.append(token)

            must_terms = _normalize_list(row.get("must_terms"))
            for tok in must_terms:
                token = _safe_str(tok)
                if token and token.upper() not in generic_alias_stopwords:
                    auto_aliases.append(token)

            final_aliases = _unique_keep_order(aliases + auto_aliases)

            profiles.append(
                ThemeProfile(
                    subject_key=_safe_str(row.get("subject_key")),
                    subject_name=base_subject_name,
                    theme_master_id=int(row["theme_master_id"]) if row.get("theme_master_id") is not None else None,
                    concept=base_concept,
                    semantic_type=_safe_str(row.get("semantic_type")),
                    strategy_type=_safe_str(row.get("strategy_type")),
                    ontology_json=ontology,
                    gate_json=gate,
                    must_terms=must_terms,
                    should_terms=_normalize_list(row.get("should_terms")),
                    not_terms=_normalize_list(row.get("not_terms")),
                    strong_terms=_normalize_list(row.get("strong_terms")),
                    weak_terms=_normalize_list(row.get("weak_terms")),
                    negative_terms=_normalize_list(row.get("negative_terms")),
                    search_text=_safe_str(row.get("search_text")),
                    quality=_safe_str(row.get("quality")),
                    rerank_text=_safe_str(row.get("rerank_text")),
                    aliases=final_aliases,
                    entity_hints=_unique_keep_order(entity_hints),
                    core_objects=_unique_keep_order(core_objects + [base_subject_name, base_concept]),
                )
            )

        return profiles

    def _rows_to_v2_profiles(self, rows: List[Dict[str, Any]]) -> List[ThemeProfile]:
        profiles: List[ThemeProfile] = []
        for row in rows:
            subject_key = _safe_str(row.get("subject_key"))
            canonical_key = CANONICAL_SUBJECT_KEY_MAP.get(subject_key, subject_key)
            subject_name = _safe_str(row.get("subject_name"))
            anchors = _unique_keep_order(
                _normalize_list(row.get("entity_anchors"))
                + _normalize_list(row.get("domain_anchors"))
                + _normalize_list(row.get("product_anchors"))
                + _normalize_list(row.get("technology_anchors"))
            )
            aliases = _unique_keep_order([subject_name] + _normalize_list(row.get("aliases")))
            search_terms = _unique_keep_order(
                anchors
                + _normalize_list(row.get("must_terms"))
                + _normalize_list(row.get("strong_terms"))
                + _normalize_list(row.get("should_terms"))
            )
            gate_json = {
                "profile_version": "v2",
                "support_terms": _normalize_list(row.get("support_terms")),
                "weak_terms": _normalize_list(row.get("weak_terms")),
                "no_anchor_terms": _normalize_list(row.get("no_anchor_terms")),
                "boundary_rules": _load_json(row.get("boundary_rules")),
                "eval_metrics": _load_json(row.get("eval_metrics")),
            }
            profiles.append(
                ThemeProfile(
                    subject_key=canonical_key,
                    subject_name=subject_name,
                    theme_master_id=None,
                    concept=subject_name,
                    semantic_type="profile_v2",
                    strategy_type="event_driven",
                    ontology_json={},
                    gate_json=gate_json,
                    must_terms=_normalize_list(row.get("must_terms")),
                    should_terms=_normalize_list(row.get("should_terms")),
                    not_terms=[],
                    strong_terms=_normalize_list(row.get("strong_terms")),
                    weak_terms=_normalize_list(row.get("weak_terms")),
                    negative_terms=_normalize_list(row.get("negative_terms")),
                    search_text=" ".join(search_terms),
                    quality="v2",
                    rerank_text=" ".join(_unique_keep_order(anchors + _normalize_list(row.get("must_terms")) + _normalize_list(row.get("strong_terms")))),
                    aliases=aliases,
                    entity_hints=_normalize_list(row.get("entity_anchors")),
                    core_objects=anchors,
                )
            )
        return profiles

    async def semantic_recall_candidates(
        self,
        query_embedding: List[float],
        top_k: int = 20,
    ) -> List[Dict[str, Any]]:
        return await self.database_gateway.semantic_recall_theme_candidates(query_embedding, top_k)

    async def sparse_recall_candidates(
        self,
        query_text: str,
        top_k: int = 20,
    ) -> List[Dict[str, Any]]:
        return await self.database_gateway.sparse_recall_theme_candidates(query_text, top_k)
