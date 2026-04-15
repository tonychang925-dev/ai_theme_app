from __future__ import annotations

import asyncio
import json
import logging
import os
from datetime import date
from pathlib import Path
from typing import Any, Dict, List, Tuple

from model_service.llm_parser.reliable_deepseek_parser import ReliableDeepSeekParser
from stock_service.repositories.stock_screener_repository import StockScreenerRepository
from stock_service.services.theme_leader_llm_judgement_service import ThemeLeaderLlmJudgementService
from stock_service.stock_screener_models import ScreeningResult

logger = logging.getLogger(__name__)


def load_env_file(env_file_path: str = ".env.theme") -> Dict[str, str]:
    """从.env.theme文件加载环境变量"""
    env_vars = {}
    try:
        env_path = Path(env_file_path)
        if env_path.exists():
            with open(env_path, 'r') as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith('#') and '=' in line:
                        key, value = line.split('=', 1)
                        env_vars[key.strip()] = value.strip()
            logger.info(f"从 {env_file_path} 加载了 {len(env_vars)} 个环境变量")
        else:
            logger.warning(f"环境文件 {env_file_path} 不存在")
    except Exception as e:
        logger.error(f"加载环境文件 {env_file_path} 失败: {e}")
    return env_vars


def get_deepseek_api_key() -> str:
    """获取DEEPSEEK_API_KEY，优先从.env.theme文件读取"""
    # 首先尝试从.env.theme文件读取
    env_vars = load_env_file()
    api_key = env_vars.get("DEEPSEEK_API_KEY", "").strip()

    # 如果.env.theme中没有，尝试从环境变量读取
    if not api_key:
        api_key = os.getenv("DEEPSEEK_API_KEY", "").strip()

    return api_key


class StockScreenerLlmReviewService:
    """复用现有 LLM 复核基础设施（ReliableDeepSeekParser）对选股结果做二次复核。"""

    def __init__(self, screener_repo: StockScreenerRepository):
        self.screener_repo = screener_repo
        self.api_key = get_deepseek_api_key()
        self.model_name = os.getenv("DEEPSEEK_MODEL", "deepseek-chat")
        self.max_retries = int(os.getenv("SCREENER_LLM_MAX_RETRIES", "3"))
        self.timeout_sec = int(os.getenv("SCREENER_LLM_TIMEOUT_SEC", "45"))
        self.max_concurrency = int(os.getenv("SCREENER_LLM_MAX_CONCURRENCY", "3"))
        self.prompt_version = ThemeLeaderLlmJudgementService.screener_prompt_version
        self.parser: ReliableDeepSeekParser | None = None

    async def review_results(
        self,
        *,
        execution_id: str,
        strategy_id: str,
        trade_date: date,
        results: List[ScreeningResult],
        top_k: int = 20,
    ) -> Tuple[Dict[str, Dict[str, Any]], str, Dict[str, int]]:
        if not results or top_k <= 0:
            return {}, "skipped_no_candidates", {"pass": 0, "watch": 0, "reject": 0, "failed": 0}
        if not self.api_key:
            logger.warning("LLM复核跳过：DEEPSEEK_API_KEY 未配置")
            return {}, "skipped_no_api_key", {"pass": 0, "watch": 0, "reject": 0, "failed": 0}
        if self.parser is None:
            self.parser = ReliableDeepSeekParser(
                model_name=self.model_name,
                config={
                    "max_retries": self.max_retries,
                    "timeout": self.timeout_sec,
                    "temperature": 0.1,
                    "model_name": self.model_name,
                },
            )

        candidates = results[:top_k]
        sem = asyncio.Semaphore(max(1, self.max_concurrency))

        async def _run_one(item: ScreeningResult) -> Dict[str, Any]:
            async with sem:
                return await self._review_one(item)

        raw_reviews = await asyncio.gather(*[_run_one(item) for item in candidates], return_exceptions=True)

        review_map: Dict[str, Dict[str, Any]] = {}
        summary = {"pass": 0, "watch": 0, "reject": 0, "failed": 0}

        for item, raw in zip(candidates, raw_reviews):
            if isinstance(raw, Exception):
                logger.error("LLM复核异常 %s: %s", item.stock_id, raw)
                review = self._failed_review(item, f"review exception: {raw}")
            else:
                review = raw

            decision = str(review.get("decision", "failed")).lower()
            if decision not in {"pass", "watch", "reject", "failed"}:
                decision = "failed"
                review["decision"] = decision
            summary[decision] += 1
            review_map[item.result_id or ""] = review

        status = "completed" if summary["failed"] == 0 else "partial_failed"

        persist_payload = [
            {
                "result_id": item.result_id,
                "stock_id": item.stock_id,
                "decision": review_map.get(item.result_id or "", {}).get("decision", "failed"),
                "llm_score": review_map.get(item.result_id or "", {}).get("score"),
                "confidence": review_map.get(item.result_id or "", {}).get("confidence"),
                "reasoning": review_map.get(item.result_id or "", {}).get("reasoning", ""),
                "risk_flags": review_map.get(item.result_id or "", {}).get("risk_flags", []),
                "evidence_refs": review_map.get(item.result_id or "", {}).get("evidence_refs", []),
                "model_name": review_map.get(item.result_id or "", {}).get("model_name", self.model_name),
                "prompt_version": self.prompt_version,
            }
            for item in candidates
            if item.result_id
        ]
        if persist_payload:
            await self.screener_repo.save_llm_reviews(
                execution_id=execution_id,
                strategy_id=strategy_id,
                trade_date=trade_date,
                reviews=persist_payload,
            )

        return review_map, status, summary

    def _failed_review(self, item: ScreeningResult, reason: str) -> Dict[str, Any]:
        return {
            "decision": "failed",
            "score": 0.0,
            "confidence": 0.0,
            "reasoning": reason,
            "risk_flags": [],
            "evidence_refs": [],
            "model_name": self.model_name,
            "review_version": self.prompt_version,
            "stock_id": item.stock_id,
        }

    async def _review_one(self, item: ScreeningResult) -> Dict[str, Any]:
        prompt = self._build_prompt(item)
        try:
            assert self.parser is not None
            response = await self.parser.parse_content(prompt)
        except Exception as e:
            return self._failed_review(item, f"llm request failed: {e}")

        parsed = self._normalize_response(response)
        if not parsed:
            return self._failed_review(item, "llm response parse failed")

        return {
            "decision": str(parsed.get("decision", "failed")).lower(),
            "score": float(parsed.get("score", 0) or 0),
            "confidence": float(parsed.get("confidence", 0) or 0),
            "reasoning": str(parsed.get("reasoning", "") or ""),
            "risk_flags": list(parsed.get("risk_flags", []) or []),
            "evidence_refs": list(parsed.get("evidence_refs", []) or []),
            "model_name": self.model_name,
            "review_version": self.prompt_version,
            "stock_id": item.stock_id,
        }

    def _normalize_response(self, response: Any) -> Dict[str, Any]:
        parsed = ThemeLeaderLlmJudgementService.parse_screener_review_response(response)
        return parsed if isinstance(parsed, dict) else {}

    def _build_prompt(self, item: ScreeningResult) -> str:
        dim = item.dimension_scores
        theme_info = item.theme_info or {}
        return ThemeLeaderLlmJudgementService.build_screener_review_prompt(
            trade_date=item.trade_date,
            stock_id=item.stock_id,
            stock_name=item.stock_name,
            composite_score=item.composite_score,
            mainline_score=dim.mainline,
            cycle_score=dim.cycle,
            leader_score=dim.leader,
            technical_score=dim.technical,
            theme_info_json=json.dumps(theme_info, ensure_ascii=False),
            screening_reason=item.screening_reason,
        )
