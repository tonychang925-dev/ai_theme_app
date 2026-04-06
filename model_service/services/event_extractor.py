# model_service/services/event_extractor.py
"""
事件结构化提取器。

P2.phase0 要求：
- 只负责 `news_raw -> structured news_event`
- 不再输出题材创建/聚类动作语义
- 对外保留 `extract_event()` 入口，返回以 `news_event` 落库为中心的结构化结果
- 为旧调用方保留最薄兼容字段，但不再承载旧架构决策含义
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, List, Optional

from model_service.llm_parser.base import LLMParser
from model_service.llm_parser.factory import LLMParserFactory

logger = logging.getLogger(__name__)

STRUCTURING_VERSION = "p2.phase0.v1"


def _safe_str(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip()
    return str(value).strip()


def _clip_text(text: str, limit: int) -> str:
    text = _safe_str(text)
    if len(text) <= limit:
        return text
    return text[:limit].rstrip()


def _normalize_confidence(value: Any, default: float = 0.5) -> float:
    if isinstance(value, (int, float)):
        value = float(value)
        if 1.0 < value <= 100.0:
            value = value / 100.0
        return max(0.0, min(1.0, value))
    return default


def _normalize_source_weight(value: Any, default: float = 1.0) -> float:
    if isinstance(value, (int, float)):
        return max(0.0, float(value))
    return default


def _normalize_direction(value: Any) -> str:
    text = _safe_str(value).lower()
    if text in {"positive", "bullish", "利好"}:
        return "利好"
    if text in {"negative", "bearish", "利空"}:
        return "利空"
    return "中性"


def _normalize_string_list(value: Any) -> List[str]:
    if value is None:
        return []
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return []
        try:
            parsed = json.loads(text)
            if isinstance(parsed, list):
                return [_safe_str(v) for v in parsed if _safe_str(v)]
        except Exception:
            pass
        if "," in text:
            return [_safe_str(v) for v in text.split(",") if _safe_str(v)]
        return [text]
    if isinstance(value, list):
        return [_safe_str(v) for v in value if _safe_str(v)]
    return []


def _normalize_entities(value: Any) -> List[Dict[str, str]]:
    entities: List[Dict[str, str]] = []
    if not isinstance(value, list):
        return entities
    for item in value:
        if isinstance(item, dict):
            name = _safe_str(item.get("name"))
            if not name:
                continue
            entities.append(
                {
                    "name": name,
                    "type": _safe_str(item.get("type")),
                    "normalized": _safe_str(item.get("normalized") or name),
                }
            )
        else:
            name = _safe_str(item)
            if name:
                entities.append({"name": name, "type": "", "normalized": name})
    return entities


def _normalize_causal_claim(value: Any) -> List[str]:
    if isinstance(value, list):
        return [_clip_text(_safe_str(v), 60) for v in value if _safe_str(v)]
    if isinstance(value, str):
        text = _safe_str(value)
        if not text:
            return []
        if "->" in text:
            return [_clip_text(_safe_str(v), 60) for v in text.split("->") if _safe_str(v)]
        return [_clip_text(text, 60)]
    return []


def _normalize_evidence_set(value: Any, title: str, content: str) -> Dict[str, Any]:
    evidence = value if isinstance(value, dict) else {}
    tech_phrases = _normalize_string_list(evidence.get("tech_phrases"))
    core_concepts = _normalize_string_list(evidence.get("core_concepts"))

    normalized_terms = evidence.get("normalized_terms")
    if not isinstance(normalized_terms, dict):
        normalized_terms = {}

    evidence_spans = evidence.get("evidence_spans")
    if not isinstance(evidence_spans, list):
        evidence_spans = []

    if not evidence_spans:
        span_text = _clip_text(title or content, 80)
        if span_text:
            evidence_spans = [{"text": span_text, "start": 0, "end": len(span_text)}]

    return {
        "tech_phrases": tech_phrases,
        "normalized_terms": normalized_terms,
        "evidence_spans": evidence_spans,
        "core_concepts": core_concepts,
    }


def _normalize_event_time(value: Any, fallback: Any) -> Optional[str]:
    for candidate in (value, fallback):
        text = _safe_str(candidate)
        if not text:
            continue
        return text
    return None


@dataclass
class EventExtractionPromptBuilder:
    """冻结结构化输出字段语义。当前主要用于运行时元信息与后续真实 prompt 接入。"""

    version: str = STRUCTURING_VERSION

    def build(self, news_data: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "version": self.version,
            "title": _safe_str(news_data.get("title")),
            "content_preview": _clip_text(_safe_str(news_data.get("content")), 300),
            "required_fields": [
                "event_type",
                "impact_industries",
                "direction",
                "confidence",
                "summary",
                "severity_score",
                "source_weight",
                "event_time",
                "entities",
                "causal_claim",
                "evidence_set",
            ],
        }


class EventExtractionSchemaValidator:
    """校验并过滤旧动作语义。"""

    _banned_keys = {"theme_discovery_directive", "action", "decision_confidence"}
    _banned_values = {"create_new", "cluster"}

    def validate(self, parsed_result: Dict[str, Any]) -> Dict[str, Any]:
        if not isinstance(parsed_result, dict):
            raise ValueError("LLM parser result must be a dict")

        event_info = parsed_result.get("event_info")
        base = event_info if isinstance(event_info, dict) else parsed_result

        for key in self._banned_keys:
            value = parsed_result.get(key)
            if isinstance(value, str) and value.strip().lower() in self._banned_values:
                raise ValueError(f"legacy theme directive value is not allowed: {value}")

        summary = _safe_str(base.get("summary") or parsed_result.get("summary"))
        if not summary:
            title = _safe_str(parsed_result.get("title"))
            content = _safe_str(parsed_result.get("content"))
            summary = _clip_text(title or content, 60)

        return {
            "event_type": _safe_str(base.get("event_type") or parsed_result.get("event_type") or "其他"),
            "impact_industries": _normalize_string_list(
                base.get("impact_industries") or parsed_result.get("impact_industries")
            ),
            "direction": _normalize_direction(base.get("direction") or parsed_result.get("direction")),
            "confidence": _normalize_confidence(
                base.get("event_confidence") or base.get("confidence") or parsed_result.get("confidence"),
                default=0.5,
            ),
            "summary": summary,
            "severity_score": _normalize_confidence(
                base.get("severity_score") or parsed_result.get("severity_score"), default=0.5
            ),
            "source_weight": _normalize_source_weight(
                base.get("source_weight") or parsed_result.get("source_weight"), default=1.0
            ),
            "event_time": _normalize_event_time(
                base.get("timestamp") or base.get("event_time") or parsed_result.get("timestamp"),
                parsed_result.get("date"),
            ),
            "entities": _normalize_entities(base.get("entities") or parsed_result.get("entities")),
            "causal_claim": _normalize_causal_claim(
                base.get("causal_claim") or parsed_result.get("causal_claim")
            ),
            "evidence_set": base.get("evidence_set") or parsed_result.get("evidence_set") or {},
        }


@dataclass
class EventExtractionNormalizer:
    version: str = STRUCTURING_VERSION

    def normalize(
        self,
        validated: Dict[str, Any],
        news_data: Dict[str, Any],
        parsed_result: Dict[str, Any],
    ) -> Dict[str, Any]:
        title = _safe_str(news_data.get("title"))
        content = _safe_str(news_data.get("content"))
        news_id = news_data.get("news_id")
        llm_request_id = _safe_str(parsed_result.get("llm_request_id") or parsed_result.get("request_id"))

        evidence_set = _normalize_evidence_set(validated.get("evidence_set"), title, content)

        result = {
            "news_id": news_id,
            "event_type": validated["event_type"] or "其他",
            "impact_industries": validated["impact_industries"],
            "direction": validated["direction"],
            "confidence": validated["confidence"],
            "summary": _clip_text(validated["summary"], 60),
            "severity_score": validated["severity_score"],
            "source_weight": validated["source_weight"],
            "event_time": validated["event_time"],
            "entities": validated["entities"],
            "causal_claim": validated["causal_claim"],
            "evidence_set": evidence_set,
            "raw_event_json": {
                "event_type": validated["event_type"] or "其他",
                "impact_industries": validated["impact_industries"],
                "direction": validated["direction"],
                "confidence": validated["confidence"],
                "summary": _clip_text(validated["summary"], 60),
                "severity_score": validated["severity_score"],
                "source_weight": validated["source_weight"],
                "event_time": validated["event_time"],
                "entities": validated["entities"],
                "causal_claim": validated["causal_claim"],
                "evidence_set": evidence_set,
                "structuring_version": self.version,
                "llm_request_id": llm_request_id,
            },
            "structuring_version": self.version,
            "llm_request_id": llm_request_id,
            # 兼容字段：保留旧调用方需要的内容，但不再输出旧动作语义。
            "event_info": {
                "event_type": validated["event_type"] or "其他",
                "impact_industries": validated["impact_industries"],
                "direction": validated["direction"],
                "event_confidence": validated["confidence"],
                "summary": _clip_text(validated["summary"], 60),
                "confidence": validated["confidence"],
                "severity_score": validated["severity_score"],
                "source_weight": validated["source_weight"],
                "entities": validated["entities"],
                "causal_claim": validated["causal_claim"],
                "evidence_set": evidence_set,
                "event_time": validated["event_time"],
            },
            "theme_discovery_directive": {
                "action": "",
                "decision_confidence": 0.0,
                "reason": "deprecated_compat",
            },
            "original_news": {
                "title": title,
                "content": content,
                "content_length": len(content),
                "date": news_data.get("date") or news_data.get("publish_date"),
            },
            "original_data": {
                "title": title,
                "content": content,
                "publish_date": news_data.get("publish_date") or news_data.get("date"),
                "source": news_data.get("source"),
            },
            "data_integrity": {
                "has_content": bool(content),
                "content_length": len(content),
                "has_title": bool(title),
            },
            "ai_response": parsed_result,
            "raw_ai_response": parsed_result,
        }
        return result


class AIEventExtractor:
    """生产入口使用的事件结构化提取器。"""

    def __init__(
        self,
        llm_parser: Optional[LLMParser] = None,
        prompt_builder: Optional[EventExtractionPromptBuilder] = None,
        schema_validator: Optional[EventExtractionSchemaValidator] = None,
        normalizer: Optional[EventExtractionNormalizer] = None,
    ):
        self.llm_parser = llm_parser or LLMParserFactory.create_parser_from_env()
        self.prompt_builder = prompt_builder or EventExtractionPromptBuilder()
        self.schema_validator = schema_validator or EventExtractionSchemaValidator()
        self.normalizer = normalizer or EventExtractionNormalizer()
        provider = getattr(self.llm_parser, "provider", getattr(self.llm_parser, "model_name", type(self.llm_parser).__name__))
        logger.info(f"AI事件提取器已初始化，使用 {provider} 提供商")

    async def extract_event(self, news_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        title = _safe_str(news_data.get("title"))
        content = _safe_str(news_data.get("content"))
        news_id = news_data.get("news_id")

        if not title and not content:
            logger.warning(f"新闻数据为空，跳过处理。news_id={news_id}")
            return None

        start_time = datetime.now()
        _ = self.prompt_builder.build(news_data)

        parsed_result = await self.llm_parser.parse_news(title, content)
        if not parsed_result:
            logger.warning(f"LLM解析失败，未提取到事件。news_id={news_id}")
            return None

        if hasattr(parsed_result, "__dict__") and not isinstance(parsed_result, dict):
            parsed_result = dict(parsed_result.__dict__)

        if not isinstance(parsed_result, dict):
            logger.warning(f"LLM解析结果格式错误，跳过处理。news_id={news_id}, type={type(parsed_result)}")
            return None

        try:
            validated = self.schema_validator.validate(parsed_result)
            event_result = self.normalizer.normalize(validated, news_data, parsed_result)
        except Exception as exc:
            logger.error(f"事件结构化校验失败 news_id={news_id}: {exc}")
            return None

        processing_time = (datetime.now() - start_time).total_seconds()
        logger.info(
            "✅ 事件提取完成: news_id=%s, event_type=%s, confidence=%.2f, content_length=%s, 耗时=%.2fs",
            news_id,
            event_result.get("event_type", "其他"),
            event_result.get("confidence", 0.0),
            len(content),
            processing_time,
        )
        return event_result

    async def health_check(self) -> bool:
        if not self.llm_parser:
            return False
        return await self.llm_parser.health_check()

    async def close(self):
        if self.llm_parser:
            await self.llm_parser.close()
            logger.info("AI事件提取器资源已释放")
