from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class ThemeMatchRequest:
    event_id: int
    news_id: int
    title: str
    content: str
    summary: str
    event_type: str
    entities: List[str] = field(default_factory=list)
    causal_claim: List[str] = field(default_factory=list)
    evidence_set: Dict[str, Any] = field(default_factory=dict)
    raw_event_json: Dict[str, Any] = field(default_factory=dict)
    trace_id: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    def event_text(self) -> str:
        parts: List[str] = []
        if self.title:
            parts.append(f"标题：{self.title}")
        if self.summary:
            parts.append(f"摘要：{self.summary}")
        if self.event_type:
            parts.append(f"事件类型：{self.event_type}")
        if self.entities:
            parts.append("实体：" + "、".join(self.entities[:12]))
        if self.causal_claim:
            parts.append("事件要点：" + "；".join(self.causal_claim[:10]))
        if self.content:
            parts.append(f"正文：{self.content[:1200]}")
        return "\n".join(parts)


@dataclass
class ThemeProfile:
    subject_key: str
    subject_name: str
    theme_master_id: Optional[int]
    concept: str
    semantic_type: str
    strategy_type: str
    ontology_json: Dict[str, Any]
    gate_json: Dict[str, Any]
    must_terms: List[str]
    should_terms: List[str]
    not_terms: List[str]
    strong_terms: List[str]
    weak_terms: List[str]
    negative_terms: List[str]
    search_text: str
    quality: str
    rerank_text: str = ""
    aliases: List[str] = field(default_factory=list)
    entity_hints: List[str] = field(default_factory=list)
    core_objects: List[str] = field(default_factory=list)

    def compact_text(self) -> str:
        parts = [
            self.subject_name,
            self.concept,
            self.semantic_type,
            self.strategy_type,
            " ".join(self.core_objects[:8]),
            " ".join(self.must_terms[:8]),
            " ".join(self.strong_terms[:8]),
            self.rerank_text[:220] if self.rerank_text else self.search_text[:180],
        ]
        return " ".join(p for p in parts if p).strip()


@dataclass
class ThemeDecisionEnvelope:
    decision: str
    event_id: int
    news_id: int
    confidence: float
    reason_code: str
    matched_subject_key: str = ""
    matched_theme_name: str = ""
    matched_theme_id: Optional[int] = None
    related_matches: List[Dict[str, Any]] = field(default_factory=list)
    review_required: bool = False
    audit: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)
