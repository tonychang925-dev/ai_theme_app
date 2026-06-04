from __future__ import annotations

import asyncio
import json
import logging
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

logger = logging.getLogger(__name__)


MARKET_SUMMARY_LLM_PROMPT_VERSION = "post_market.market_summary.llm.v1"


def _env_value(name: str) -> str:
    value = os.getenv(name, "").strip()
    if value:
        return value
    try:
        path = Path(".env.theme")
        if not path.exists():
            return ""
        for line in path.read_text(encoding="utf-8").splitlines():
            raw = line.strip()
            if not raw or raw.startswith("#") or "=" not in raw:
                continue
            key, val = raw.split("=", 1)
            if key.strip() == name:
                return val.strip()
    except Exception:
        return ""
    return ""


def _short(value: Any, limit: int = 80) -> str:
    text = str(value or "").strip()
    if len(text) <= limit:
        return text
    return f"{text[:limit]}..."


def _to_float(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except Exception:
        return None


def _compact_rows(rows: list[Any], fields: tuple[str, ...], *, limit: int) -> list[dict[str, Any]]:
    compacted: list[dict[str, Any]] = []
    for row in rows[:limit]:
        item = dict(row or {})
        compacted.append({field: item.get(field) for field in fields if item.get(field) not in (None, "", [])})
    return compacted


@dataclass
class PostMarketMarketSummaryLlmService:
    """Build a structured market summary from collected facts through LLM.

    The service is best-effort. Missing API key, timeout, invalid JSON or schema
    mismatch returns None, so the post-market recap can continue with rule-based
    summary lines.
    """

    parser_factory: Callable[[], Any] | None = None
    model_name: str = os.getenv("DEEPSEEK_MODEL", "deepseek-chat")
    timeout_sec: int = int(os.getenv("POST_MARKET_SUMMARY_LLM_TIMEOUT_SEC", "25"))

    async def build(self, *, trade_date: Any, report_context: dict[str, Any]) -> dict[str, Any] | None:
        if not self._enabled():
            return None
        prompt = self.build_prompt(trade_date=trade_date, report_context=report_context)
        parser = None
        try:
            parser = self.parser_factory() if self.parser_factory else self._default_parser()
            response = await asyncio.wait_for(parser.parse_content(prompt), timeout=self.timeout_sec)
            return self.normalize_response(response)
        except asyncio.TimeoutError:
            logger.warning("market summary LLM timeout after %ss", self.timeout_sec)
            return None
        except Exception as exc:
            logger.warning("market summary LLM skipped: %s", exc)
            return None
        finally:
            close_fn = getattr(parser, "close", None) if parser is not None else None
            if callable(close_fn):
                try:
                    await close_fn()
                except Exception:
                    pass

    def _enabled(self) -> bool:
        if str(os.getenv("POST_MARKET_SUMMARY_LLM_ENABLED", "1")).strip().lower() in {"0", "false", "no"}:
            return False
        return bool(_env_value("DEEPSEEK_API_KEY"))

    def _default_parser(self) -> Any:
        from model_service.llm_parser.reliable_deepseek_parser import ReliableDeepSeekParser

        return ReliableDeepSeekParser(
            model_name=self.model_name,
            config={
                "max_retries": 1,
                "timeout": self.timeout_sec,
                "temperature": 0.1,
                "enable_cache": True,
                "cache_ttl": 3600,
                "failure_threshold": 3,
                "recovery_timeout": 120,
            },
        )

    @staticmethod
    def build_input_payload(*, trade_date: Any, report_context: dict[str, Any]) -> dict[str, Any]:
        market = dict(report_context.get("market") or {})
        return {
            "trade_date": str(trade_date),
            "market": {
                key: market.get(key)
                for key in (
                    "market_bias",
                    "action_bias",
                    "market_health_score",
                    "stock_count",
                    "up_count",
                    "down_count",
                    "limit_up_count",
                    "limit_down_count",
                    "market_total_amount",
                    "market_amount_change_pct",
                    "shanghai_index_pct_chg",
                    "shenzhen_index_pct_chg",
                    "chinext_index_pct_chg",
                    "breadth_status",
                    "short_term_sentiment_status",
                    "relay_sentiment_status",
                    "intraday_fade_status",
                )
            },
            "index_quotes": market.get("index_quotes") or [],
            "theme_gainers": _compact_rows(
                list(report_context.get("theme_gainers") or []),
                (
                    "subject_key",
                    "theme_name",
                    "stock_count",
                    "avg_pct_chg",
                    "max_pct_chg",
                    "limit_up_count",
                    "top_stocks",
                ),
                limit=10,
            ),
            "theme_capital_flow": _compact_rows(
                list(report_context.get("theme_capital_flow") or []),
                (
                    "subject_key",
                    "resolved_theme_name",
                    "theme_name",
                    "main_net_inflow_sum",
                    "leader_main_net_inflow",
                    "positive_inflow_stock_count",
                    "final_cycle_state",
                    "mainline_strength_score",
                    "fade_risk_score",
                ),
                limit=8,
            ),
            "cycles": _compact_rows(
                list(report_context.get("cycles") or []),
                (
                    "subject_key",
                    "theme_name",
                    "final_cycle_state",
                    "final_mainline_alive",
                    "fade_watch",
                    "fade_confirmed",
                    "mainline_strength_score",
                    "fade_risk_score",
                ),
                limit=8,
            ),
            "active_stocks": _compact_rows(
                list(report_context.get("stock_facts") or []),
                (
                    "subject_key",
                    "theme_name",
                    "stock_id",
                    "stock_name",
                    "rank_order",
                    "pct_chg",
                    "limit_up",
                    "is_leader",
                    "turnover_rate",
                    "main_net_inflow",
                    "leader_composite_score",
                    "position_label",
                    "pattern_labels",
                ),
                limit=18,
            ),
            "money_flow": _compact_rows(
                list(report_context.get("money_flow") or []),
                (
                    "subject_key",
                    "resolved_theme_name",
                    "theme_name",
                    "stock_id",
                    "stock_name",
                    "pct_chg",
                    "main_net_inflow",
                    "money_flow_score",
                    "money_flow_tier",
                ),
                limit=12,
            ),
            "dragon_tiger": _compact_rows(
                list(report_context.get("dragon_tiger") or []),
                (
                    "subject_key",
                    "theme_name",
                    "stock_id",
                    "stock_name",
                    "net_amount",
                    "seat_summary",
                ),
                limit=8,
            ),
        }

    @classmethod
    def build_prompt(cls, *, trade_date: Any, report_context: dict[str, Any]) -> str:
        payload = cls.build_input_payload(trade_date=trade_date, report_context=report_context)
        return (
            "你是A股盘后复盘分析助手。请只依据输入JSON做大盘环境结构化总结，严禁编造输入中没有的指数、题材、个股和涨跌幅。\n"
            "输出必须是严格JSON，不要Markdown，不要额外解释。\n"
            "目标风格参考：同花顺每日复盘的结构，但不能复制任何外部原文。\n"
            "JSON字段固定如下：\n"
            "{\n"
            '  "market_overview": "一句话概括指数、量能、广度与市场定性",\n'
            '  "top_gain_concepts": ["题材 +平均涨幅，最多3项；必须优先使用theme_gainers.avg_pct_chg"],\n'
            '  "index_performance": ["指数 +涨跌幅，最多4项；没有指数数据则返回[]"],\n'
            '  "mainstream_focus": ["主流看点，2到4项"],\n'
            '  "activity_context": "用一段话描述活跃方向、代表股、拖累方向或分歧点",\n'
            '  "board_efficiency": "较好/一般/偏弱/--",\n'
            '  "risk_notes": ["风险提示，最多3项"],\n'
            '  "action_bias": "主做主线/精选弱转强/防守观察/等待确认",\n'
            '  "confidence": 0.0\n'
            "}\n"
            "要求：confidence为0到1；数组元素使用中文短句；如果输入证据不足，降低confidence并写明风险提示。\n"
            f"输入JSON：{json.dumps(payload, ensure_ascii=False, default=str)}"
        )

    @staticmethod
    def normalize_response(response: Any) -> dict[str, Any] | None:
        if not isinstance(response, dict):
            return None
        if isinstance(response.get("response"), str):
            try:
                response = json.loads(response["response"])
            except Exception:
                return None
        if not isinstance(response, dict):
            return None

        def _list(key: str, limit: int) -> list[str]:
            raw = response.get(key)
            if not isinstance(raw, list):
                raw = [raw] if raw else []
            return [_short(item, 80) for item in raw if str(item or "").strip()][:limit]

        summary = {
            "source": "llm",
            "prompt_version": MARKET_SUMMARY_LLM_PROMPT_VERSION,
            "market_overview": _short(response.get("market_overview"), 160),
            "top_gain_concepts": _list("top_gain_concepts", 3),
            "index_performance": _list("index_performance", 4),
            "mainstream_focus": _list("mainstream_focus", 4),
            "activity_context": _short(response.get("activity_context"), 260),
            "board_efficiency": _short(response.get("board_efficiency") or "--", 12),
            "risk_notes": _list("risk_notes", 3),
            "action_bias": _short(response.get("action_bias"), 40),
            "confidence": _to_float(response.get("confidence")) or 0.0,
        }
        if not summary["market_overview"] or not summary["activity_context"]:
            return None
        if summary["board_efficiency"] not in {"较好", "一般", "偏弱", "--"}:
            summary["board_efficiency"] = "--"
        summary["confidence"] = max(0.0, min(1.0, float(summary["confidence"])))
        return summary
