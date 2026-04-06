from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from stock_service.models import ThemeLeaderLlmJudgement


def _to_float(value: Any) -> float:
    try:
        return float(value or 0)
    except Exception:
        return 0.0


def _short_text(value: Any, limit: int = 60) -> str:
    text = str(value or "").strip()
    if len(text) <= limit:
        return text
    return f"{text[:limit]}..."


@dataclass(frozen=True)
class ThemeLeaderLlmCandidateInput:
    trade_date: str
    subject_key: str
    theme_name: str
    stock_id: str
    stock_name: str
    rank_order: int
    pct_chg: float
    is_leader: bool
    is_limit_up: bool
    turnover_rate: float
    volume_ratio: float
    main_net_inflow: float
    amount: float
    open_price: float
    high_price: float
    low_price: float
    close_price: float
    pre_close: float
    role_label: str = ""
    candidate_rank: int = 0
    purity_score: float = 0.0
    leading_score: float = 0.0
    capital_score: float = 0.0
    structure_score: float = 0.0
    resilience_score: float = 0.0
    composite_score: float = 0.0
    position_label: str = ""
    pattern_labels: tuple[str, ...] = ()
    stock_remark: str = ""


class ThemeLeaderLlmJudgementService:
    prompt_version = "theme_leader_llm_judgement.v2"

    def _board_nature_candidate(self, row: ThemeLeaderLlmCandidateInput) -> str:
        open_pct = ((row.open_price / row.pre_close) - 1) * 100 if row.pre_close and row.open_price else 0.0
        if row.is_limit_up:
            if row.open_price and row.high_price and row.low_price and row.close_price:
                if (
                    abs(row.open_price - row.high_price) < 1e-4
                    and abs(row.open_price - row.low_price) < 1e-4
                    and abs(row.open_price - row.close_price) < 1e-4
                ):
                    return "一字板"
            if open_pct >= 3:
                return "高开强封板"
            if open_pct > 0:
                return "高开换手板"
            if open_pct < 0:
                return "低开分歧板"
            return "平开换手板"
        if row.pct_chg >= 8:
            return "大阳领涨"
        if row.pct_chg >= 5:
            return "强势前排"
        if row.pct_chg >= 0:
            return "跟随上行"
        return "走弱掉队"

    def _candidate_record(self, row: ThemeLeaderLlmCandidateInput) -> dict[str, Any]:
        return {
            "stock_id": row.stock_id,
            "stock_name": row.stock_name,
            "rank_order": row.rank_order,
            "is_leader": bool(row.is_leader),
            "role_label": row.role_label,
            "candidate_rank": row.candidate_rank,
            "price_facts": {
                "pct_chg": round(row.pct_chg, 2),
                "open_price": round(row.open_price, 4),
                "close_price": round(row.close_price, 4),
                "pre_close": round(row.pre_close, 4),
                "board_nature_candidate": self._board_nature_candidate(row),
                "is_limit_up": bool(row.is_limit_up),
            },
            "capital_facts": {
                "turnover_rate": round(row.turnover_rate, 2),
                "volume_ratio": round(row.volume_ratio, 2),
                "main_net_inflow_yi": round(row.main_net_inflow / 1e8, 2),
                "amount_yi": round(row.amount / 1e8, 2),
            },
            "kline_facts": {
                "position_label": row.position_label,
                "pattern_labels": list(row.pattern_labels),
            },
            "candidate_scores": {
                "purity_score": round(row.purity_score, 2),
                "leading_score": round(row.leading_score, 2),
                "capital_score": round(row.capital_score, 2),
                "structure_score": round(row.structure_score, 2),
                "resilience_score": round(row.resilience_score, 2),
                "composite_score": round(row.composite_score, 2),
                "weights": {
                    "purity_score": 0.25,
                    "leading_score": 0.25,
                    "capital_score": 0.20,
                    "structure_score": 0.15,
                    "resilience_score": 0.15,
                },
            },
            "theme_relation_text": _short_text(row.stock_remark),
        }

    def build_candidate_payload(self, rows: list[ThemeLeaderLlmCandidateInput]) -> dict[str, Any]:
        if not rows:
            return {}
        base = rows[0]
        ordered = sorted(rows, key=lambda item: (item.rank_order, -item.pct_chg, item.stock_id))
        return {
            "trade_date": base.trade_date,
            "subject_key": base.subject_key,
            "theme_name": base.theme_name,
            "task": "请基于候选池事实层，判断龙头/龙二/卡位/补涨/淘汰，并给出理由。",
            "candidates": [self._candidate_record(row) for row in ordered],
            "output_schema": {
                "leader_stock_id": "string",
                "leader_status": "当日领涨候选|待确认龙头|确认龙头",
                "confirmation_basis": "首板领涨|二板确认|三板强化|分歧后继续领涨|仅当日最强未确认",
                "runner_up_stock_id": "string",
                "card_position_stock_id": "string",
                "supplement_stock_id": "string",
                "eliminated_stock_id": "string",
                "reasoning_summary": "string",
                "per_stock_reasoning": [
                    {
                        "stock_id": "string",
                        "role_label": "龙头|龙二|卡位|补涨|淘汰",
                        "reason": "string",
                    }
                ],
            },
        }

    def build_prompt_text(self, payload: dict[str, Any]) -> str:
        theme_name = payload.get("theme_name") or "--"
        lines = [
            "你是A股短线复盘裁决器。",
            "任务：基于同一题材内全部候选股的事实证据，判断龙头、龙二、卡位、补涨、淘汰，并明确龙头确认状态。",
            "约束：",
            "1. 只能依据提供的事实字段，不得编造封板时间、秒板等不存在事实。",
            "2. 龙头定义优先是短线当日成立性，不是长期产业链最正宗标的。",
            "3. 权重优先顺序：当日领涨成立性 > 题材正宗性 > 资金量能 > 结构位置 > 抗跌承接。",
            "4. 当日领涨成立性必须优先看：rank_order、is_leader、candidate_rank、涨幅、是否涨停、板性质。",
            "5. 如果某只股票 rank_order=1 且 is_leader=true，且涨停/大涨已成立，除非存在明确负面证据，否则优先认定为龙头候选。",
            "6. 不允许仅因主营更正宗、主力净流入更大，就推翻已经成立的当日龙头。",
            "7. 若题材仍处于启动/发酵初期，且尚未出现连续两次领涨或二板确认，不要武断输出“确认龙头”，优先输出“当日领涨候选”或“待确认龙头”。",
            "8. leader_status 只能取：当日领涨候选、待确认龙头、确认龙头。",
            "9. confirmation_basis 只能取：首板领涨、二板确认、三板强化、分歧后继续领涨、仅当日最强未确认。",
            "10. 若证据不足，明确说明不足点。",
            f"题材：{theme_name}",
            "候选池：",
        ]
        for item in payload.get("candidates") or []:
            price = item.get("price_facts") or {}
            capital = item.get("capital_facts") or {}
            kline = item.get("kline_facts") or {}
            scores = item.get("candidate_scores") or {}
            lines.append(
                f"- {item.get('stock_name')}({item.get('stock_id')}) | 排序 {item.get('rank_order')} | "
                f"JYHF龙头标记 {item.get('is_leader')} | 规则候选位次 {item.get('candidate_rank')} | "
                f"涨幅 {price.get('pct_chg')}% | 板性质 {price.get('board_nature_candidate')} | "
                f"换手 {capital.get('turnover_rate')}% | 量比 {capital.get('volume_ratio')} | "
                f"主力净流入 {capital.get('main_net_inflow_yi')}亿 | "
                f"K线位置 {kline.get('position_label') or '--'} | "
                f"K线形态 {'/'.join(kline.get('pattern_labels') or []) or '--'} | "
                f"题材关系 {item.get('theme_relation_text') or '--'} | "
                f"候选综合分 {scores.get('composite_score')}"
            )
        lines.extend(
            [
                "输出要求：严格返回 JSON 对象。",
                "JSON字段：leader_stock_id, leader_status, confirmation_basis, runner_up_stock_id, card_position_stock_id, supplement_stock_id, eliminated_stock_id, reasoning_summary, per_stock_reasoning",
            ]
        )
        return "\n".join(lines)

    def build_placeholder_judgement(self, rows: list[ThemeLeaderLlmCandidateInput]) -> ThemeLeaderLlmJudgement:
        if not rows:
            raise ValueError("rows must not be empty")
        payload = self.build_candidate_payload(rows)
        prompt_text = self.build_prompt_text(payload)
        base = rows[0]
        return ThemeLeaderLlmJudgement(
            trade_date=base.trade_date,
            subject_key=base.subject_key,
            theme_name=base.theme_name,
            candidate_payload=payload,
            prompt_text=prompt_text,
            model_name="",
            prompt_version=self.prompt_version,
            source_trace_id=f"{base.trade_date}:{base.subject_key}",
            source_trace={
                "candidate_count": len(rows),
                "sources": [
                    "subject_stock_daily_snapshot",
                    "theme_leader_candidate",
                    "stock_position_judgement",
                    "stock_pattern_judgement",
                    "subject_stock_detail_staging",
                ],
            },
            source_version=self.prompt_version,
            rule_version=self.prompt_version,
        )

    def parse_llm_response(self, payload: dict[str, Any], response: dict[str, Any]) -> dict[str, Any]:
        if isinstance(response.get("response"), str):
            raw_text = str(response.get("response") or "").strip()
            if raw_text.startswith("```json"):
                raw_text = raw_text[7:]
            if raw_text.endswith("```"):
                raw_text = raw_text[:-3]
            raw_text = raw_text.strip()
            try:
                parsed_wrapper = json.loads(raw_text)
                if isinstance(parsed_wrapper, dict):
                    response = parsed_wrapper
            except Exception:
                pass

        candidates = payload.get("candidates") or []
        valid_stock_ids = {str(item.get("stock_id") or "").strip() for item in candidates}
        per_stock_reasoning = response.get("per_stock_reasoning") or []
        if isinstance(per_stock_reasoning, dict):
            per_stock_reasoning = [
                {
                    "stock_id": stock_id,
                    "role_label": "",
                    "reason": reason,
                }
                for stock_id, reason in per_stock_reasoning.items()
            ]
        normalized_reasoning = []
        for item in per_stock_reasoning:
            if not isinstance(item, dict):
                continue
            stock_id = str(item.get("stock_id") or "").strip()
            if not stock_id or stock_id not in valid_stock_ids:
                continue
            normalized_reasoning.append(
                {
                    "stock_id": stock_id,
                    "role_label": str(item.get("role_label") or "").strip(),
                    "reason": str(item.get("reason") or "").strip(),
                }
            )

        def _pick(field: str) -> str:
            raw_value = response.get(field)
            if isinstance(raw_value, list):
                raw_value = raw_value[0] if raw_value else ""
            value = str(raw_value or "").strip()
            return value if value in valid_stock_ids else ""

        return {
            "leader_stock_id": _pick("leader_stock_id"),
            "leader_status": str(response.get("leader_status") or "").strip(),
            "confirmation_basis": str(response.get("confirmation_basis") or "").strip(),
            "runner_up_stock_id": _pick("runner_up_stock_id"),
            "card_position_stock_id": _pick("card_position_stock_id"),
            "supplement_stock_id": _pick("supplement_stock_id"),
            "eliminated_stock_id": _pick("eliminated_stock_id"),
            "reasoning_summary": str(response.get("reasoning_summary") or "").strip(),
            "judgement_json": {
                "per_stock_reasoning": normalized_reasoning,
            },
        }

    def apply_llm_response(self, judgement: ThemeLeaderLlmJudgement, response: dict[str, Any], model_name: str) -> ThemeLeaderLlmJudgement:
        parsed = self.parse_llm_response(judgement.candidate_payload, response)
        merged_json = {
            **parsed.get("judgement_json", {}),
            "raw_response": response,
        }
        return ThemeLeaderLlmJudgement(
            trade_date=judgement.trade_date,
            subject_key=judgement.subject_key,
            theme_name=judgement.theme_name,
            candidate_payload=judgement.candidate_payload,
            prompt_text=judgement.prompt_text,
            leader_stock_id=parsed.get("leader_stock_id", ""),
            leader_status=parsed.get("leader_status", ""),
            confirmation_basis=parsed.get("confirmation_basis", ""),
            runner_up_stock_id=parsed.get("runner_up_stock_id", ""),
            card_position_stock_id=parsed.get("card_position_stock_id", ""),
            supplement_stock_id=parsed.get("supplement_stock_id", ""),
            eliminated_stock_id=parsed.get("eliminated_stock_id", ""),
            judgement_json=merged_json,
            reasoning_summary=parsed.get("reasoning_summary", ""),
            model_name=model_name,
            prompt_version=judgement.prompt_version,
            source_type=judgement.source_type,
            source_trace_id=judgement.source_trace_id,
            source_trace=judgement.source_trace,
            source_version=judgement.source_version,
            rule_version=judgement.rule_version,
        )
