"""PR4.2.38a — AI Observation Direction Draft Service.

Generates daily observation direction candidates from market evidence
(capital flows + hotspot subjects + cycle states) through LLM.

Best-effort: missing API key, timeout, or invalid response returns None.
Follows the same pattern as PostMarketMarketSummaryLlmService.
"""

from __future__ import annotations

import asyncio
import json as _json
import logging
import os
from dataclasses import dataclass
from datetime import date, datetime, timezone
from typing import Any, Callable

logger = logging.getLogger(__name__)


def _env_value(key: str) -> str:
    return (os.getenv(key) or "").strip()


@dataclass
class ObservationDirectionDraftService:
    """Generate AI observation direction candidates from capital evidence.

    Consumes recap snapshot data + capital flow evidence to produce
    3-5 GROUP_DIRECTION candidates with theme bindings.
    """

    parser_factory: Callable[[], Any] | None = None
    model_name: str = os.getenv("DEEPSEEK_MODEL", "deepseek-chat")
    timeout_sec: int = int(os.getenv("DIRECTION_DRAFT_LLM_TIMEOUT_SEC", "30"))

    async def build(self, *, trade_date: Any, context: dict[str, Any]) -> dict[str, Any] | None:
        if not self._enabled():
            logger.info("direction draft LLM disabled (no API key or env flag)")
            return None
        prompt = self.build_prompt(trade_date=trade_date, context=context)
        parser = None
        try:
            parser = self.parser_factory() if self.parser_factory else self._default_parser()
            response = await asyncio.wait_for(parser.parse_content(prompt), timeout=self.timeout_sec)
            return self.normalize_response(response)
        except asyncio.TimeoutError:
            logger.warning("direction draft LLM timeout after %ss", self.timeout_sec)
            return None
        except Exception as exc:
            logger.warning("direction draft LLM skipped: %s", exc)
            return None
        finally:
            close_fn = getattr(parser, "close", None) if parser is not None else None
            if callable(close_fn):
                try:
                    await close_fn()
                except Exception:
                    pass

    def _enabled(self) -> bool:
        if str(os.getenv("DIRECTION_DRAFT_LLM_ENABLED", "1")).strip().lower() in {"0", "false", "no"}:
            return False
        return bool(_env_value("DEEPSEEK_API_KEY"))

    def _default_parser(self) -> Any:
        from model_service.llm_parser.reliable_deepseek_parser import ReliableDeepSeekParser
        return ReliableDeepSeekParser(
            model_name=self.model_name,
            config={
                "max_retries": 2,
                "timeout": self.timeout_sec,
                "temperature": 0.1,
                "enable_cache": True,
                "cache_ttl": 7200,
                "failure_threshold": 3,
                "recovery_timeout": 120,
            },
        )

    # ── Prompt ──

    @staticmethod
    def build_prompt(*, trade_date: Any, context: dict[str, Any]) -> str:
        """Build LLM prompt from capital evidence context."""
        td = str(trade_date)
        market = _json.dumps(context.get("market_summary", {}), ensure_ascii=False, indent=2)[:1500]
        hotspots = _json.dumps(context.get("hotspot_subjects", [])[:15], ensure_ascii=False, indent=2)[:2000]
        capital = _json.dumps(context.get("theme_capital_flows", [])[:10], ensure_ascii=False, indent=2)[:1500]
        directions = _json.dumps(context.get("existing_directions", []), ensure_ascii=False)[:500]
        stocks = _json.dumps(context.get("strong_stocks", [])[:20], ensure_ascii=False, indent=2)[:1500]

        return f"""你是A股市场分析师。根据以下 {td} 的收盘数据，生成3-5个观察方向候选。

## 约束
1. **必须资金支持**: 每个方向必须引用实际资金数据，不能仅基于概念热度
2. **优先GROUP_DIRECTION**: 输出主题组合方向（如"AI高速互联"），而非单个主题（如"PCB"）
3. **去重**: 不要重复已有系统方向: {directions}
4. **每个方向2-4个主题**，标注核心(CORE)与辅助(SUPPORT)
5. candidate_key使用英文大写下划线，candidate_name使用中文
6. **必须输出style_profile**: 每个方向评估机构/游资/事件三个维度的属性评分(0-1)
   - institution: 机构资金持续流入、大单占比高、周期处于发酵/启动阶段
   - hot_money: 涨停扩散、连板活跃、游资席位参与
   - event: 产业事件催化、政策驱动、突发事件
   - 一个方向可以同时拥有多个属性（如：机构0.92 + 游资0.65 + 事件0.88）

## 市场数据
{market}

## 强势热点主题（含周期状态）
{hotspots}

## 主题资金流（net_flow_yuan为当日净流入，元）
{capital}

## 强势个股样本
{stocks}

## 输出格式（严格JSON）
```json
{{
  "directions": [
    {{
      "candidate_key": "AI_HIGH_SPEED_INTERCONNECT",
      "candidate_name": "AI高速互联",
      "candidate_type": "GROUP_DIRECTION",
      "confidence": 0.88,
      "rationale": "PCB+覆铜板+铜连接 资金同步流入+38亿，英伟达Rubin驱动",
      "style_profile": {{
        "institution": {{ "score": 0.92, "reason": "大资金持续流入PCB/覆铜板" }},
        "hot_money": {{ "score": 0.65, "reason": "CPO涨停扩散" }},
        "event": {{ "score": 0.88, "reason": "英伟达Rubin发布" }}
      }},
      "evidence_json": {{
        "capital_score": 5,
        "event_score": 4,
        "limit_up_score": 3
      }},
      "theme_bindings": [
        {{
          "subject_key": "9018144",
          "theme_name": "PCB印制电路板",
          "weight": 0.35,
          "role": "CORE",
          "evidence": ["资金+15亿", "核心股票3只"]
        }}
      ]
    }}
  ]
}}
```

只返回JSON，不要其他文本。"""

    # ── Normalize ──

    @staticmethod
    def normalize_response(response: Any) -> dict[str, Any] | None:
        """Validate and normalize LLM response."""
        if not isinstance(response, dict):
            return None
        directions = response.get("directions")
        if not isinstance(directions, list) or len(directions) == 0:
            return None

        normalized = []
        for d in directions[:5]:
            if not isinstance(d, dict):
                continue
            dk = str(d.get("candidate_key", "")).strip().upper().replace(" ", "_")[:50]
            dn = str(d.get("candidate_name", "")).strip()[:200]
            if not dk or not dn:
                continue

            bindings = d.get("theme_bindings", [])
            if not isinstance(bindings, list):
                bindings = []
            norm_bindings = []
            for b in bindings[:6]:
                if not isinstance(b, dict):
                    continue
                sk = str(b.get("subject_key", "")).strip()
                if not sk:
                    continue
                norm_bindings.append({
                    "subject_key": sk,
                    "theme_name": str(b.get("theme_name", "")).strip()[:100],
                    "weight": float(b.get("weight", 0.25)),
                    "role": str(b.get("role", "SUPPORT")).upper()[:20],
                    "evidence": b.get("evidence", []) if isinstance(b.get("evidence"), list) else [],
                })

            evidence = d.get("evidence_json", {})
            if not isinstance(evidence, dict):
                evidence = {}

            # Normalize style_profile
            sp = d.get("style_profile", {})
            if not isinstance(sp, dict):
                sp = {}
            norm_sp = {}
            for st in ("institution", "hot_money", "event"):
                si = sp.get(st, {})
                if isinstance(si, dict):
                    norm_sp[st] = {
                        "score": min(1.0, max(0.0, float(si.get("score", 0.5)))),
                        "reason": str(si.get("reason", ""))[:200],
                    }
                else:
                    norm_sp[st] = {"score": 0.5, "reason": ""}

            normalized.append({
                "candidate_key": dk,
                "candidate_name": dn,
                "candidate_type": str(d.get("candidate_type", "GROUP_DIRECTION"))[:20],
                "confidence": min(1.0, max(0.1, float(d.get("confidence", 0.5)))),
                "rationale": str(d.get("rationale", ""))[:500],
                "style_profile": norm_sp,
                "evidence_json": {
                    "capital_score": int(evidence.get("capital_score", 3)),
                    "event_score": int(evidence.get("event_score", 3)),
                    "limit_up_score": int(evidence.get("limit_up_score", 3)),
                },
                "theme_bindings": norm_bindings,
            })

        return {"directions": normalized} if normalized else None
