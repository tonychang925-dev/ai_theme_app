#!/usr/bin/env python3
from __future__ import annotations

import argparse
import asyncio
import json
import os
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import aiohttp
import asyncpg

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _parse_date(raw: str) -> date:
    return datetime.strptime(raw, "%Y-%m-%d").date()


def _load_env_file(env_file_path: Path) -> Dict[str, str]:
    env_vars: Dict[str, str] = {}
    if not env_file_path.exists():
        return env_vars
    with open(env_file_path, "r", encoding="utf-8") as f:
        for raw_line in f:
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            env_vars[key.strip()] = value.strip()
    return env_vars


def _get_env_value(name: str, *, default: str = "") -> str:
    v = os.getenv(name, "").strip()
    if v:
        return v
    env_theme = _load_env_file(PROJECT_ROOT / ".env.theme")
    return str(env_theme.get(name, default)).strip()


def _dsn_from_env() -> str:
    host = _get_env_value("POSTGRES_HOST", default="localhost")
    port = _get_env_value("POSTGRES_PORT", default="5432")
    db = _get_env_value("POSTGRES_DATABASE", default="stock_data_test")
    user = _get_env_value("POSTGRES_USER", default="postgres")
    pwd = _get_env_value("POSTGRES_PASSWORD", default="zxbzj~925")
    return f"postgresql://{user}:{pwd}@{host}:{port}/{db}"


@dataclass
class MainlineDecision:
    subject_key: str
    theme_name: str
    pct_chg: float
    his_pct_chg: float
    event_chain_score: float
    event_chain_continuity_score: float
    market_recognition_score: float
    mainline_stability_score: float
    strong_event_count_7d: int
    event_recency_days: Optional[int]
    limit_up_count: int
    final_cycle_state: str
    fade_watch: bool
    fade_confirmed: bool
    composite_score: float
    logic_dimension_ok: bool
    market_dimension_ok: bool
    is_main_theme_core_rule: bool
    llm_applied: bool
    is_main_theme_core_llm: Optional[bool]
    llm_confidence: Optional[int]
    llm_reasons: List[str]
    is_main_theme_core_final: bool


def _rule_judge(row: asyncpg.Record) -> Dict[str, Any]:
    event_chain_score = float(row.get("event_chain_score") or 0.0)
    event_continuity_score = float(row.get("event_chain_continuity_score") or 0.0)
    market_recognition_score = float(row.get("market_recognition_score") or 0.0)
    mainline_stability_score = float(row.get("mainline_stability_score") or 0.0)
    strong_event_count_7d = int(row.get("strong_event_count_7d") or 0)
    event_recency_days = row.get("event_recency_days")
    limit_up_count = int(row.get("limit_up_count") or 0)
    his_pct_chg = float(row.get("his_pct_chg") or 0.0)

    event_total = event_chain_score + event_continuity_score
    logic_primary = strong_event_count_7d >= 1 and (
        event_recency_days is None or int(event_recency_days) <= 3
    )
    logic_backup = event_total >= 35.0
    logic_dimension_ok = logic_primary or logic_backup

    market_dimension_ok = (
        market_recognition_score >= 60.0
        and mainline_stability_score >= 45.0
        and limit_up_count >= 2
        and his_pct_chg >= 0.0
    )
    strong_market_override = (
        event_total >= 30.0
        and market_recognition_score >= 75.0
        and mainline_stability_score >= 55.0
    )
    is_main_theme_core_rule = (logic_dimension_ok and market_dimension_ok) or strong_market_override
    composite_score = (
        event_total * 0.45
        + market_recognition_score * 0.30
        + mainline_stability_score * 0.25
    )

    return {
        "logic_dimension_ok": logic_dimension_ok,
        "market_dimension_ok": market_dimension_ok,
        "is_main_theme_core_rule": is_main_theme_core_rule,
        "composite_score": round(composite_score, 3),
    }


def _build_llm_prompt(trade_date: str, row: asyncpg.Record, rule_out: Dict[str, Any]) -> str:
    return f"""你是A股主线判定复核专家。必须严格遵守以下置顶规则：
1) 主线定义必须同时满足两维：逻辑维度 + 市场维度，缺一不可。
2) 逻辑维度看：新颖度/时机/影响广度（由事件强度、连续性、时效性代理）。
3) 市场维度看：持续资金认可（由市场认可、稳定性、涨停家数、题材走势代理）。
4) 任一维度证据不足，is_main_theme_core_llm 必须为 false。
5) 禁止把“一日游题材/单日异动”判为主线。

交易日：{trade_date}
题材：{row.get("theme_name") or row.get("subject_key")}
subject_key：{row.get("subject_key")}

硬证据：
- event_chain_score={float(row.get("event_chain_score") or 0.0):.2f}
- event_chain_continuity_score={float(row.get("event_chain_continuity_score") or 0.0):.2f}
- strong_event_count_7d={int(row.get("strong_event_count_7d") or 0)}
- event_recency_days={row.get("event_recency_days")}
- market_recognition_score={float(row.get("market_recognition_score") or 0.0):.2f}
- mainline_stability_score={float(row.get("mainline_stability_score") or 0.0):.2f}
- limit_up_count={int(row.get("limit_up_count") or 0)}
- his_pct_chg={float(row.get("his_pct_chg") or 0.0):.2f}

规则层结果：
- logic_dimension_ok={rule_out["logic_dimension_ok"]}
- market_dimension_ok={rule_out["market_dimension_ok"]}
- is_main_theme_core_rule={rule_out["is_main_theme_core_rule"]}

请仅输出 JSON：
{{
  "is_main_theme_core_llm": true/false,
  "confidence": 0-100,
  "reasons": ["最多3条证据理由"],
  "risk_flags": ["最多3条风险标记"]
}}
"""


async def _llm_review(
    prompt: str,
    *,
    api_key: str,
    api_base: str,
    model_name: str,
) -> Dict[str, Any]:
    url = f"{api_base}/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": model_name,
        "messages": [
            {"role": "system", "content": "你是主线判定复核专家，必须输出JSON。"},
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.1,
        "max_tokens": 1200,
        "response_format": {"type": "json_object"},
    }
    async with aiohttp.ClientSession() as session:
        async with session.post(url, headers=headers, json=payload, timeout=45) as resp:
            if resp.status != 200:
                text = await resp.text()
                raise RuntimeError(f"LLM API {resp.status}: {text[:300]}")
            data = await resp.json()
    content = data["choices"][0]["message"]["content"]
    return json.loads(content)


async def _fetch_theme_rows(
    conn: asyncpg.Connection,
    trade_date: date,
    subject_keys: Optional[List[str]],
    max_themes: int,
) -> List[asyncpg.Record]:
    sql = """
    SELECT
        r.subject_key,
        COALESCE(m.theme_name, r.subject_key) AS theme_name,
        COALESCE(r.pct_chg, 0) AS pct_chg,
        COALESCE(r.his_pct_chg, 0) AS his_pct_chg,
        COALESCE(m.event_chain_score, 0) AS event_chain_score,
        COALESCE(m.event_chain_continuity_score, 0) AS event_chain_continuity_score,
        COALESCE(m.market_recognition_score, 0) AS market_recognition_score,
        COALESCE(m.mainline_stability_score, 0) AS mainline_stability_score,
        COALESCE(m.strong_event_count_7d, 0) AS strong_event_count_7d,
        m.event_recency_days,
        COALESCE(m.limit_up_count, 0) AS limit_up_count,
        COALESCE(v2.final_cycle_state, '') AS final_cycle_state,
        COALESCE(v2.fade_watch, FALSE) AS fade_watch,
        COALESCE(v2.fade_confirmed, FALSE) AS fade_confirmed
    FROM subject_rank_daily r
    LEFT JOIN theme_mainline_judgement m
      ON m.trade_date = r.rank_date
     AND m.subject_key = r.subject_key
    LEFT JOIN theme_cycle_judgement_v2 v2
      ON v2.trade_date = r.rank_date
     AND v2.subject_key = r.subject_key
    WHERE r.rank_date = $1::date
      AND ($2::varchar[] IS NULL OR r.subject_key = ANY($2::varchar[]))
    ORDER BY COALESCE(r.his_pct_chg, 0) DESC, r.subject_key
    LIMIT $3
    """
    return await conn.fetch(sql, trade_date, subject_keys if subject_keys else None, max_themes)


def _parse_subject_keys(raw: str) -> Optional[List[str]]:
    text = (raw or "").strip()
    if not text:
        return None
    parts = [x.strip() for x in text.split(",")]
    keys = [x for x in parts if x]
    return keys or None


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="按交易日测试主线判定（subject_rank_daily + 规则 + LLM复核）")
    parser.add_argument("--trade-date", required=True, help="交易日 YYYY-MM-DD")
    parser.add_argument("--subject-keys", default="", help="可选，逗号分隔 subject_key 列表")
    parser.add_argument("--max-themes", type=int, default=120, help="最多评估题材数")
    parser.add_argument("--max-mainlines", type=int, default=10, help="最终主线最多保留条数")
    parser.add_argument("--disable-llm", action="store_true", help="只跑规则，不调用LLM")
    parser.add_argument("--output-json", default="", help="可选，输出JSON文件路径")
    return parser.parse_args()


async def main_async() -> int:
    args = parse_args()
    trade_date = _parse_date(args.trade_date)
    subject_keys = _parse_subject_keys(args.subject_keys)
    dsn = _dsn_from_env()
    api_key = _get_env_value("DEEPSEEK_API_KEY", default="")
    api_base = _get_env_value("DEEPSEEK_API_BASE", default="https://api.deepseek.com")
    model_name = _get_env_value("DEEPSEEK_MODEL", default="deepseek-chat")

    conn = await asyncpg.connect(dsn)
    try:
        rows = await _fetch_theme_rows(conn, trade_date, subject_keys, int(args.max_themes))
    finally:
        await conn.close()

    decisions: List[MainlineDecision] = []
    for row in rows:
        rule_out = _rule_judge(row)
        llm_applied = False
        llm_main: Optional[bool] = None
        llm_conf: Optional[int] = None
        llm_reasons: List[str] = []

        if not args.disable_llm and api_key and bool(rule_out["is_main_theme_core_rule"]):
            llm_applied = True
            try:
                prompt = _build_llm_prompt(args.trade_date, row, rule_out)
                llm_raw = await _llm_review(
                    prompt,
                    api_key=api_key,
                    api_base=api_base,
                    model_name=model_name,
                )
                llm_main = bool(llm_raw.get("is_main_theme_core_llm", False))
                llm_conf = int(llm_raw.get("confidence", 0))
                reasons_raw = llm_raw.get("reasons", [])
                if isinstance(reasons_raw, list):
                    llm_reasons = [str(x) for x in reasons_raw if str(x).strip()]
            except Exception as e:
                llm_reasons = [f"llm_error:{str(e)}"]
                llm_applied = False

        # 最终口径：规则与LLM双重通过（LLM未启用时仅规则）
        if llm_applied and llm_main is not None:
            is_final = bool(rule_out["is_main_theme_core_rule"]) and bool(llm_main)
        else:
            is_final = bool(rule_out["is_main_theme_core_rule"])

        decisions.append(
            MainlineDecision(
                subject_key=str(row.get("subject_key") or ""),
                theme_name=str(row.get("theme_name") or row.get("subject_key") or ""),
                pct_chg=float(row.get("pct_chg") or 0.0),
                his_pct_chg=float(row.get("his_pct_chg") or 0.0),
                event_chain_score=float(row.get("event_chain_score") or 0.0),
                event_chain_continuity_score=float(row.get("event_chain_continuity_score") or 0.0),
                market_recognition_score=float(row.get("market_recognition_score") or 0.0),
                mainline_stability_score=float(row.get("mainline_stability_score") or 0.0),
                strong_event_count_7d=int(row.get("strong_event_count_7d") or 0),
                event_recency_days=row.get("event_recency_days"),
                limit_up_count=int(row.get("limit_up_count") or 0),
                final_cycle_state=str(row.get("final_cycle_state") or ""),
                fade_watch=bool(row.get("fade_watch") or False),
                fade_confirmed=bool(row.get("fade_confirmed") or False),
                composite_score=float(rule_out["composite_score"]),
                logic_dimension_ok=bool(rule_out["logic_dimension_ok"]),
                market_dimension_ok=bool(rule_out["market_dimension_ok"]),
                is_main_theme_core_rule=bool(rule_out["is_main_theme_core_rule"]),
                llm_applied=llm_applied,
                is_main_theme_core_llm=llm_main,
                llm_confidence=llm_conf,
                llm_reasons=llm_reasons,
                is_main_theme_core_final=is_final,
            )
        )

    pre_rank_final = [d for d in decisions if d.is_main_theme_core_final]
    ranked_final = sorted(
        pre_rank_final,
        key=lambda x: (
            -x.composite_score,
            -x.market_recognition_score,
            -x.mainline_stability_score,
            -x.his_pct_chg,
            x.subject_key,
        ),
    )
    final_mainlines = ranked_final[: max(int(args.max_mainlines), 1)]
    final_key_set = {d.subject_key for d in final_mainlines}
    decisions = [
        MainlineDecision(
            **{
                **d.__dict__,
                "is_main_theme_core_final": d.subject_key in final_key_set,
            }
        )
        for d in decisions
    ]
    rule_mainlines = [d for d in decisions if d.is_main_theme_core_rule]
    llm_yes = [d for d in decisions if d.llm_applied and d.is_main_theme_core_llm is True]

    print(f"[SUMMARY] trade_date={args.trade_date} themes={len(decisions)}")
    print(
        f"[SUMMARY] rule_mainline={len(rule_mainlines)} "
        f"llm_yes={len(llm_yes)} pre_rank_final={len(pre_rank_final)} "
        f"final_mainline={len(final_mainlines)} "
        f"llm_enabled={not args.disable_llm and bool(api_key)}"
    )

    print("\n[MAINLINE_FINAL]")
    if not final_mainlines:
        print("(none)")
    for idx, d in enumerate(final_mainlines, 1):
        print(
            f"{idx:02d}. {d.subject_key} {d.theme_name} "
            f"his_pct={d.his_pct_chg:.2f} score={d.composite_score:.1f} "
            f"event={d.event_chain_score:.1f}/{d.event_chain_continuity_score:.1f} "
            f"market={d.market_recognition_score:.1f}/{d.mainline_stability_score:.1f} "
            f"cycle={d.final_cycle_state} llm={d.is_main_theme_core_llm}"
        )

    if args.output_json:
        payload = {
            "trade_date": args.trade_date,
            "summary": {
                "themes": len(decisions),
                "rule_mainline": len(rule_mainlines),
                "llm_yes": len(llm_yes),
                "pre_rank_final": len(pre_rank_final),
                "final_mainline": len(final_mainlines),
                "llm_enabled": (not args.disable_llm and bool(api_key)),
            },
            "decisions": [d.__dict__ for d in decisions],
        }
        out_path = Path(args.output_json)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
        print(f"\n[OUTPUT] json={out_path}")

    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main_async()))
