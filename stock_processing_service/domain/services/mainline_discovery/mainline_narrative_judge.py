"""MainlineNarrativeJudge — Phase 1 PR-4B.

LLM-based narrative arbitrator. Only answers one question:
  Do the input events constitute a mainline-level narrative?

Does NOT:
  - Judge market acceptance
  - Confirm mainline
  - Output trading decisions

Requires parser_factory injection. Tests use mock parsers.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Any, Callable

from .models import NarrativeJudgeResult

logger = logging.getLogger(__name__)

# ── Prompt ──

SYSTEM_PROMPT = """你是一个 A 股主线叙事裁判（Mainline Narrative Judge）。

你只能依据输入 JSON 中的事件链判断，**严禁**补充任何外部事实、市场表现、个股涨跌幅或资金流向。
你的任务不是判断是否可买入，也不是判断市场是否买单。
你的唯一任务是判断：**这些事件是否构成"主线级叙事"**。

必须区分：
1. **strong** — 主线级叙事：事件密集、逻辑一致、具备产业链级或全社会级影响，可能持续数周或更久
2. **moderate** — 分支级叙事：有明确产业/政策/技术背景，但强度或广度未达主线级
3. **watch** — 观察级：有一定逻辑但事件不够密集或不够强，需观察后续发酵
4. **insufficient** — 证据不足：事件数量不足（< 2 条关键事件），或事件之间缺少逻辑关联
5. **noise** — 噪音：单一孤立的普通消息，不构成任何叙事

**硬性要求：**
- 必须输出严格 JSON，不要 markdown code block
- supporting_event_ids 必须来自输入 event_chain 中的 event_id，不能编造
- 如果 supporting_event_ids 为空，narrative_level 必须为 insufficient
- 如果事件数量 < 2 且所有事件 impact_score < 0.7，则 narrative_level 只能为 watch 或 insufficient
- 不允许编造输入中不存在的政策名称、公司名、涨跌幅、市场表现
"""


def _build_user_payload(event_chain, event_series, event_stats, major_event=None, subject_key="", theme_name=""):
    payload = {
        "subject_key": subject_key,
        "theme_name": theme_name,
        "lookback_days": 7,
        "event_chain": [
            {
                "event_id": ev.get("event_id"),
                "event_date": ev.get("event_date") or str(ev.get("occurred_at", ""))[:10],
                "title": ev.get("title"),
                "summary": ev.get("summary", ""),
                "event_type": ev.get("event_type"),
                "impact_score": ev.get("impact_score"),
                "confidence": ev.get("confidence"),
                "source_table": ev.get("source_table", ev.get("source_channel", "unknown")),
            }
            for ev in event_chain[:20]  # limit to 20 to avoid context overflow
        ],
        "event_series": [
            {
                "series_id": s.get("series_id"),
                "series_type": s.get("series_type"),
                "event_count": s.get("event_count"),
                "active_days_7d": s.get("active_days_7d"),
                "first_seen": s.get("first_seen"),
                "last_seen": s.get("last_seen"),
                "key_events": s.get("key_events", [])[:5],
            }
            for s in (event_series or [])[:5]
        ],
        "event_stats": {
            "today_event_count": event_stats.get("recent_event_count", 0) if isinstance(event_stats, dict) else 0,
            "recent_event_count": event_stats.get("recent_event_count", 0) if isinstance(event_stats, dict) else 0,
            "distinct_event_days": event_stats.get("distinct_event_days", 0) if isinstance(event_stats, dict) else 0,
            "key_event_count": event_stats.get("key_event_count", 0) if isinstance(event_stats, dict) else 0,
        } if isinstance(event_stats, dict) else {},
    }
    if major_event:
        payload["major_event_classification"] = major_event
    return payload


@dataclass
class MainlineNarrativeJudge:
    """LLM-based narrative judge.

    Inject parser via parser_factory for testability.
    """

    parser_factory: Callable[[], Any] | None = None
    model_name: str = "deepseek-chat"
    timeout_sec: int = 30

    async def judge(
        self,
        *,
        subject_key: str = "",
        theme_name: str = "",
        event_chain: list[dict[str, Any]] | None = None,
        event_series: list[dict[str, Any]] | None = None,
        event_stats: dict[str, Any] | None = None,
        major_event_classification: dict[str, Any] | None = None,
    ) -> NarrativeJudgeResult:
        chain = event_chain or []
        series = event_series or []
        stats = event_stats or {}

        # ── 1. precheck: empty events → no LLM call ──
        if not chain:
            return NarrativeJudgeResult(
                is_mainline_logic=False,
                narrative_score=None,
                narrative_level="insufficient",
                supporting_event_ids=[],
                negative_reasons=["事件链为空，无法判断主线叙事"],
                confidence=0.0,
                diagnostics={"skip_reason": "empty_event_chain"},
            )

        # ── 2. precheck: single non-major event → insufficient ──
        all_ids = {str(ev.get("event_id") or "") for ev in chain}
        all_ids.discard("")
        if len(chain) < 2:
            has_major = False
            if major_event_classification:
                has_major = bool(major_event_classification.get("is_fast_line_trigger"))
                score = float(major_event_classification.get("major_event_score", 0) or 0)
                has_major = has_major and score >= 85
            if not has_major:
                return NarrativeJudgeResult(
                    is_mainline_logic=False,
                    narrative_score=None,
                    narrative_level="insufficient",
                    supporting_event_ids=list(all_ids),
                    negative_reasons=["事件数量不足（< 2条），且非重大事件"],
                    confidence=0.0,
                    diagnostics={
                        "skip_reason": "single_non_major_event",
                        "event_count": len(chain),
                    },
                )

        # ── 3. build payload ──
        payload = _build_user_payload(chain, series, stats, major_event_classification, subject_key, theme_name)

        # ── 4. call LLM ──
        raw_result = await self._call_llm(payload)
        if raw_result is None:
            return NarrativeJudgeResult(
                is_mainline_logic=False,
                narrative_score=None,
                narrative_level="unavailable",
                supporting_event_ids=list(all_ids),
                negative_reasons=["LLM 调用失败或超时，无法生成叙事判断"],
                confidence=0.0,
                diagnostics={"skip_reason": "llm_failure"},
            )

        # ── 5. normalize + validate ──
        return self._normalize(raw_result, chain, all_ids)

    async def _call_llm(self, payload: dict[str, Any]) -> dict[str, Any] | None:
        if self.parser_factory is None:
            return None
        try:
            parser = self.parser_factory()
            response = await parser.parse_content(
                prompt=json.dumps(payload, ensure_ascii=False),
                system_prompt=SYSTEM_PROMPT,
                model=self.model_name,
                timeout=self.timeout_sec,
            )
            if isinstance(response, str):
                # Strip markdown code fences if present
                text = response.strip()
                if text.startswith("```"):
                    lines = text.split("\n")
                    lines = [l for l in lines if not l.startswith("```")]
                    text = "\n".join(lines)
                return json.loads(text)
            if isinstance(response, dict):
                return response
            return None
        except json.JSONDecodeError:
            logger.warning("LLM narrative judge returned invalid JSON")
            return None
        except Exception:
            logger.exception("LLM narrative judge call failed")
            return None

    def _normalize(
        self,
        raw: dict[str, Any],
        event_chain: list[dict[str, Any]],
        all_event_ids: set[str],
    ) -> NarrativeJudgeResult:
        # ── extract raw fields ──
        is_ml = bool(raw.get("is_mainline_logic", False))
        score = _clamp_float(raw.get("narrative_score"), 0, 100)
        level = str(raw.get("narrative_level") or "insufficient")
        logic_type = str(raw.get("logic_type") or "unknown")
        impact = str(raw.get("impact_scope") or "unknown")
        horizon = str(raw.get("time_horizon") or "unknown")
        consistency = _clamp_float(raw.get("narrative_consistency_score"), 0, 100)
        novelty = _clamp_float(raw.get("novelty_score"), 0, 100)
        continuity = str(raw.get("event_continuity_assessment") or "insufficient")
        raw_ids = list(raw.get("supporting_event_ids") or [])
        neg_reasons = list(raw.get("negative_reasons") or [])
        summary = str(raw.get("logic_summary") or "")
        confidence = _clamp_float(raw.get("confidence"), 0, 1) or 0.0

        # ── validate supporting_event_ids ──
        valid_ids = [eid for eid in raw_ids if str(eid) in all_event_ids]
        invalid_count = len(raw_ids) - len(valid_ids)
        diag: dict[str, Any] = {}
        if invalid_count > 0:
            diag["invalid_event_ids_removed"] = invalid_count

        # ── forced downgrade rules ──
        if not valid_ids:
            is_ml = False
            level = "insufficient"
            if score is not None:
                score = min(score, 49.0)
            neg_reasons.append("supporting_event_ids 为空，强制降级为 insufficient")
            diag["forced_downgrade"] = "empty_supporting_ids"
        else:
            diag["valid_event_count"] = len(valid_ids)

        # Clamp score
        if score is not None:
            score = max(0.0, min(100.0, score))
        if confidence is not None:
            confidence = max(0.0, min(1.0, confidence))

        # Map strong to check
        if level == "strong" and score is not None and score < 50:
            level = "moderate"
            diag["forced_downgrade"] = "strong_but_low_score"

        return NarrativeJudgeResult(
            is_mainline_logic=is_ml,
            narrative_score=score,
            narrative_level=level,
            logic_type=logic_type,
            impact_scope=impact,
            time_horizon=horizon,
            narrative_consistency_score=consistency,
            novelty_score=novelty,
            event_continuity_assessment=continuity,
            supporting_event_ids=valid_ids,
            negative_reasons=neg_reasons,
            logic_summary=summary,
            confidence=confidence,
            method="llm_narrative_judge_v1",
            diagnostics=diag,
        )


def _clamp_float(val: Any, lo: float, hi: float) -> float | None:
    if val is None:
        return None
    try:
        return max(lo, min(hi, float(val)))
    except Exception:
        return None
