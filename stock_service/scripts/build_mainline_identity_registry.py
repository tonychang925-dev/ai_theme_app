#!/usr/bin/env python3
from __future__ import annotations

import argparse
import asyncio
import json
import math
import os
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
import sys
from typing import Any, Dict, List, Optional

import aiohttp
import asyncpg

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from stock_service.config import StockServiceConfig


RULE_VERSION = "mainline_identity_registry.v7_open_source_kline"
LLM_RULE_VERSION = "mainline_identity_registry.v7_open_source_kline_llm"
MANUAL_OVERRIDE_RULE_VERSION = "mainline_identity_registry.v4_manual_override"
CLUSTER_COMP_RULE_VERSION = "mainline_identity_registry.v5_cluster_compensation"
UPGRADE_TRIGGER_RULE_VERSION = "mainline_identity_registry.v6_upgrade_trigger"
CLUSTER_BOOTSTRAP_RULE_VERSION = "mainline_identity_registry.v8_cluster_bootstrap_direct_confirm"
MANUAL_OVERRIDE_CONFIG_PATH = PROJECT_ROOT / "stock_service" / "configs" / "mainline_manual_overrides.json"
CLUSTER_RULES_CONFIG_PATH = PROJECT_ROOT / "stock_service" / "configs" / "mainline_cluster_rules.json"
DEFAULT_CLUSTER_RULES = [
    {
        "name": "commercial_space",
        "keywords": [
            "商业航天",
            "卫星互联网",
            "卫星",
            "星链",
            "航天",
            "航天国家队",
            "航天材料",
            "太空",
            "太空机器人",
            "太空旅游",
            "太空算力",
            "太空光伏",
            "火箭",
            "火箭发射",
            "可回收火箭",
            "海上火箭回收",
            "蓝箭航天",
            "商业航天8大IPO",
            "广州商业航天",
            "SpaceX",
            "spacex",
            "安徽商业航天",
        ],
        "core_tokens": ["商业航天", "卫星互联网", "SpaceX", "spacex", "火箭发射", "安徽商业航天"],
        "min_members": 3,
        "min_strength_members": 3,
        "min_limit_up_sum": 6,
        "min_continuity": 70.0,
    },
    {
        "name": "data_center",
        "keywords": ["数据中心", "液冷数据中心", "数据中心电力设备", "算力", "算力租赁", "国产算力", "英伟达算力", "算力基建"],
        "core_tokens": ["数据中心", "液冷数据中心"],
        "min_members": 2,
        "min_strength_members": 2,
        "min_limit_up_sum": 3,
        "min_continuity": 58.0,
    },
    {
        "name": "optical_comm",
        "keywords": ["光通信", "光模块", "共封装光学", "CPO", "AI光纤", "光纤光缆", "1.6T光模块", "硅光", "光芯片", "光互连"],
        "core_tokens": ["光通信", "光模块", "共封装光学", "CPO", "AI光纤"],
        "min_members": 2,
        "min_strength_members": 2,
        "min_limit_up_sum": 3,
        "min_continuity": 56.0,
    },
]


def _finite_float(value: Any, default: float = 0.0) -> float:
    try:
        v = float(value)
    except Exception:
        return default
    return v if math.isfinite(v) else default


def _analyze_theme_kline_shape_open_source(pct_series: List[float]) -> Dict[str, Any]:
    """
    使用开源技术分析库（优先 pandas_ta，fallback ta）分析题材K线形态。
    pct_series: 题材近N交易日涨跌幅序列（按时间升序，单位%）。
    """
    if not pct_series or len(pct_series) < 8:
        return {
            "ta_backend": "none",
            "kline_support_hold": False,
            "one_day_tour_kline_flag": False,
            "platform_breakout_flag": False,
            "platform_breakout_strength": 0.0,
            "ema10": 0.0,
            "ema20": 0.0,
            "rsi14": 0.0,
            "bb_lower": 0.0,
            "close_last": 0.0,
            "retrace_ratio_5d": 0.0,
        }

    # 用涨跌幅重建题材“合成收盘价”曲线（基准100）。
    closes: List[float] = []
    c = 100.0
    for p in pct_series:
        c *= max(0.01, 1.0 + float(p) / 100.0)
        closes.append(c)

    backend = "none"
    ema10 = ema20 = rsi14 = bb_lower = 0.0
    close_last = _finite_float(closes[-1], 0.0)
    retrace_ratio_5d = 0.0
    one_day_tour_kline_flag = False
    kline_support_hold = False
    platform_breakout_flag = False
    platform_breakout_strength = 0.0

    try:
        import pandas as pd  # type: ignore
        close_s = pd.Series(closes, dtype="float64")
        pct_s = pd.Series(pct_series, dtype="float64")

        try:
            import pandas_ta as pta  # type: ignore

            backend = "pandas_ta"
            ema10 = _finite_float(pta.ema(close_s, length=10).iloc[-1], close_last)
            ema20 = _finite_float(pta.ema(close_s, length=20).iloc[-1], ema10) if len(close_s) >= 20 else _finite_float(pta.ema(close_s, length=10).iloc[-1], ema10)
            rsi14 = _finite_float(pta.rsi(close_s, length=14).iloc[-1], 50.0) if len(close_s) >= 14 else 50.0
            bb = pta.bbands(close_s, length=20, std=2.0)
            if bb is not None and "BBL_20_2.0" in bb.columns:
                bb_lower = _finite_float(bb["BBL_20_2.0"].iloc[-1], 0.0)
        except Exception:
            from ta.momentum import RSIIndicator  # type: ignore
            from ta.trend import EMAIndicator  # type: ignore
            from ta.volatility import BollingerBands  # type: ignore

            backend = "ta"
            ema10 = _finite_float(EMAIndicator(close_s, window=10).ema_indicator().iloc[-1], close_last)
            ema20 = _finite_float(EMAIndicator(close_s, window=min(20, max(10, len(close_s)))).ema_indicator().iloc[-1], ema10)
            rsi14 = _finite_float(RSIIndicator(close_s, window=min(14, max(6, len(close_s)))).rsi().iloc[-1], 50.0)
            if len(close_s) >= 20:
                bb_lower = _finite_float(BollingerBands(close_s, window=20, window_dev=2).bollinger_lband().iloc[-1], 0.0)

        # 一日游形态：近期出现单日冲高后，5日内显著回撤且失守短均。
        spike = float(pct_s.max())
        spike_idx = int(pct_s.idxmax())
        window_end = min(len(close_s) - 1, spike_idx + 5)
        if window_end > spike_idx and close_s.iloc[spike_idx] > 0:
            min_after = float(close_s.iloc[spike_idx: window_end + 1].min())
            retrace_ratio_5d = max(0.0, (float(close_s.iloc[spike_idx]) - min_after) / float(close_s.iloc[spike_idx]))
        one_day_tour_kline_flag = bool(
            spike >= 7.0
            and retrace_ratio_5d >= 0.08
            and close_last < ema10 * 0.99
            and rsi14 < 48.0
        )

        # 支撑未破：收盘未明显跌破中期均线/布林下轨，且非极弱RSI。
        support_floor = max(ema20 * 0.98, bb_lower * 0.97 if bb_lower > 0 else 0.0)
        kline_support_hold = bool(close_last >= support_floor and rsi14 >= 35.0)

        # 平台突破：近20日大区间压缩后，当前收盘有效突破前高。
        if len(close_s) >= 22:
            prev_high_20 = float(close_s.shift(1).rolling(20).max().iloc[-1])
            prev_low_20 = float(close_s.shift(1).rolling(20).min().iloc[-1])
            range_ratio_20 = (prev_high_20 - prev_low_20) / prev_high_20 if prev_high_20 > 0 else 0.0
            breakout_ratio = (close_last - prev_high_20) / prev_high_20 if prev_high_20 > 0 else 0.0
            platform_breakout_flag = bool(range_ratio_20 <= 0.18 and breakout_ratio >= 0.01 and close_last > ema20)
            if platform_breakout_flag:
                platform_breakout_strength = min(100.0, breakout_ratio * 1000.0 + (0.18 - range_ratio_20) * 120.0)
    except Exception:
        pass

    return {
        "ta_backend": backend,
        "kline_support_hold": kline_support_hold,
        "one_day_tour_kline_flag": one_day_tour_kline_flag,
        "platform_breakout_flag": platform_breakout_flag,
        "platform_breakout_strength": round(_finite_float(platform_breakout_strength, 0.0), 4),
        "ema10": round(_finite_float(ema10, 0.0), 4),
        "ema20": round(_finite_float(ema20, 0.0), 4),
        "rsi14": round(_finite_float(rsi14, 0.0), 4),
        "bb_lower": round(_finite_float(bb_lower, 0.0), 4),
        "close_last": round(_finite_float(close_last, 0.0), 4),
        "retrace_ratio_5d": round(_finite_float(retrace_ratio_5d, 0.0), 4),
    }


@dataclass
class IdentityDecision:
    subject_key: str
    theme_name: str
    source_trade_date: date
    logic_score: float
    market_score: float
    composite_score: float
    logic_ok: bool
    market_ok: bool
    rule_is_main_theme: bool
    llm_applied: bool
    llm_is_main_theme: Optional[bool]
    llm_confidence: Optional[int]
    llm_reasons: List[str]
    llm_risk_flags: List[str]
    llm_model: str
    is_main_theme: bool
    identity_status: str
    evidence: Dict[str, object]


def _parse_date(raw: str) -> date:
    return datetime.strptime(raw, "%Y-%m-%d").date()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="构建主线身份注册表（初始化/增量）")
    parser.add_argument("--trade-date", required=True, help="交易日 YYYY-MM-DD")
    parser.add_argument("--mode", choices=["init", "incremental"], default="incremental")
    parser.add_argument("--lookback-days", type=int, default=20, help="热点回看窗口")
    parser.add_argument("--universe-size", type=int, default=180, help="初始化/复核的题材池上限")
    parser.add_argument("--top-k", type=int, default=20, help="打印前K条结果")
    parser.add_argument("--review-existing", action="store_true", help="incremental 模式下是否重评近期热点已存在题材")
    parser.add_argument("--deactivate-fade-days", type=int, default=2, help="连续 fade_confirmed 天数达到阈值则降级 inactive")
    parser.add_argument(
        "--subject-keys-file",
        default="",
        help="按文件指定 subject_key 定向复核（每行一个，支持逗号分隔；优先于热点池）",
    )
    parser.add_argument("--disable-llm", action="store_true", help="禁用 LLM 复核（不允许规则直通 confirmed，仅保留补偿/人工覆盖）")
    parser.add_argument("--allow-llm-fallback", action="store_true", help="允许 LLM 不可用时降级（默认不允许）")
    parser.add_argument("--llm-timeout-seconds", type=int, default=45, help="LLM 请求超时秒数")
    parser.add_argument(
        "--cluster-bootstrap-direct-confirm",
        action="store_true",
        help="历史主线补齐模式：簇内题材直接确认主线（仅用于初始化补漏，不用于新题材日常判定）",
    )
    parser.add_argument(
        "--allow-historical-overwrite",
        action="store_true",
        help="允许历史交易日覆盖当前身份状态（默认禁止，防止历史回放污染当前态）",
    )
    parser.add_argument(
        "--allow-unsafe-demotion",
        action="store_true",
        help="允许在无LLM复核结果时将 confirmed 降级为 observed（默认禁止）",
    )
    return parser.parse_args()


def _load_subject_keys_file(path: str) -> List[str]:
    if not path:
        return []
    p = Path(path).expanduser().resolve()
    if not p.exists() or not p.is_file():
        raise ValueError(f"--subject-keys-file 不存在或不是文件: {p}")
    text = p.read_text(encoding="utf-8", errors="ignore")
    values: List[str] = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        for token in line.split(","):
            key = token.strip()
            if key:
                values.append(key)
    dedup: List[str] = []
    seen = set()
    for key in values:
        if key in seen:
            continue
        seen.add(key)
        dedup.append(key)
    return dedup


async def _connect() -> asyncpg.Connection:
    cfg = StockServiceConfig()
    return await asyncpg.connect(
        host=cfg.postgres_host,
        port=cfg.postgres_port,
        database=cfg.postgres_database,
        user=cfg.postgres_user,
        password=cfg.postgres_password,
    )


async def ensure_table(conn: asyncpg.Connection) -> None:
    await conn.execute(
        """
        CREATE TABLE IF NOT EXISTS theme_mainline_identity_registry (
            subject_key VARCHAR(80) PRIMARY KEY,
            theme_name VARCHAR(200) NOT NULL DEFAULT '',
            is_main_theme BOOLEAN NOT NULL DEFAULT FALSE,
            identity_status VARCHAR(32) NOT NULL DEFAULT 'observed',
            first_seen_date DATE,
            first_confirmed_date DATE,
            last_review_date DATE,
            source_trade_date DATE,
            logic_score NUMERIC(8,3) NOT NULL DEFAULT 0,
            market_score NUMERIC(8,3) NOT NULL DEFAULT 0,
            composite_score NUMERIC(8,3) NOT NULL DEFAULT 0,
            evidence_json JSONB NOT NULL DEFAULT '{}'::jsonb,
            rule_is_main_theme BOOLEAN NOT NULL DEFAULT FALSE,
            llm_applied BOOLEAN NOT NULL DEFAULT FALSE,
            llm_is_main_theme BOOLEAN,
            llm_confidence INTEGER,
            llm_reasons JSONB NOT NULL DEFAULT '[]'::jsonb,
            llm_risk_flags JSONB NOT NULL DEFAULT '[]'::jsonb,
            llm_model VARCHAR(120) NOT NULL DEFAULT '',
            llm_reviewed_at TIMESTAMP,
            rule_version VARCHAR(64) NOT NULL DEFAULT '',
            created_at TIMESTAMP NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMP NOT NULL DEFAULT NOW()
        );
        CREATE INDEX IF NOT EXISTS idx_mainline_identity_status
          ON theme_mainline_identity_registry(identity_status, is_main_theme);
        """
    )
    await conn.execute("ALTER TABLE theme_mainline_identity_registry ADD COLUMN IF NOT EXISTS rule_is_main_theme BOOLEAN NOT NULL DEFAULT FALSE")
    await conn.execute("ALTER TABLE theme_mainline_identity_registry ADD COLUMN IF NOT EXISTS llm_applied BOOLEAN NOT NULL DEFAULT FALSE")
    await conn.execute("ALTER TABLE theme_mainline_identity_registry ADD COLUMN IF NOT EXISTS llm_is_main_theme BOOLEAN")
    await conn.execute("ALTER TABLE theme_mainline_identity_registry ADD COLUMN IF NOT EXISTS llm_confidence INTEGER")
    await conn.execute("ALTER TABLE theme_mainline_identity_registry ADD COLUMN IF NOT EXISTS llm_reasons JSONB NOT NULL DEFAULT '[]'::jsonb")
    await conn.execute("ALTER TABLE theme_mainline_identity_registry ADD COLUMN IF NOT EXISTS llm_risk_flags JSONB NOT NULL DEFAULT '[]'::jsonb")
    await conn.execute("ALTER TABLE theme_mainline_identity_registry ADD COLUMN IF NOT EXISTS llm_model VARCHAR(120) NOT NULL DEFAULT ''")
    await conn.execute("ALTER TABLE theme_mainline_identity_registry ADD COLUMN IF NOT EXISTS llm_reviewed_at TIMESTAMP")
    await conn.execute(
        """
        CREATE TABLE IF NOT EXISTS mainline_identity_review_queue (
            id BIGSERIAL PRIMARY KEY,
            trade_date DATE NOT NULL,
            subject_key VARCHAR(64) NOT NULL,
            theme_name VARCHAR(128),
            review_source VARCHAR(32) NOT NULL,
            review_status VARCHAR(24) NOT NULL DEFAULT 'pending',
            priority_score NUMERIC(8,3) NOT NULL DEFAULT 0,
            trigger_flags JSONB NOT NULL DEFAULT '[]'::jsonb,
            evidence_json JSONB NOT NULL DEFAULT '{}'::jsonb,
            created_at TIMESTAMP NOT NULL DEFAULT NOW(),
            reviewed_at TIMESTAMP,
            UNIQUE (trade_date, subject_key, review_source)
        );
        CREATE INDEX IF NOT EXISTS idx_mainline_identity_review_queue_status
          ON mainline_identity_review_queue(trade_date, review_status, priority_score DESC);
        """
    )


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


def _get_env_value(name: str, default: str = "") -> str:
    value = os.getenv(name, "").strip()
    if value:
        return value
    env_theme = _load_env_file(PROJECT_ROOT / ".env.theme")
    return str(env_theme.get(name, default)).strip()


def _load_manual_override_config(path: Path) -> Dict[str, List[str]]:
    if not path.exists():
        return {
            "subject_keys": [],
            "theme_name_exact": [],
            "theme_name_contains": [],
        }
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {
            "subject_keys": [],
            "theme_name_exact": [],
            "theme_name_contains": [],
        }
    if not isinstance(raw, dict):
        return {
            "subject_keys": [],
            "theme_name_exact": [],
            "theme_name_contains": [],
        }
    return {
        "subject_keys": [str(x).strip() for x in (raw.get("subject_keys") or []) if str(x).strip()],
        "theme_name_exact": [str(x).strip() for x in (raw.get("theme_name_exact") or []) if str(x).strip()],
        "theme_name_contains": [str(x).strip() for x in (raw.get("theme_name_contains") or []) if str(x).strip()],
    }


def _manual_override_match_reason(
    decision: IdentityDecision,
    cfg: Dict[str, List[str]],
) -> Optional[str]:
    subject_keys = set(cfg.get("subject_keys") or [])
    exact_names = set(cfg.get("theme_name_exact") or [])
    contains_names = list(cfg.get("theme_name_contains") or [])
    theme_name = (decision.theme_name or "").strip()

    if decision.subject_key in subject_keys:
        return f"subject_key:{decision.subject_key}"
    if theme_name in exact_names:
        return f"theme_name_exact:{theme_name}"
    for token in contains_names:
        if token and token in theme_name:
            return f"theme_name_contains:{token}"
    return None


def _apply_manual_mainline_overrides(decisions: List[IdentityDecision]) -> int:
    cfg = _load_manual_override_config(MANUAL_OVERRIDE_CONFIG_PATH)
    if not decisions:
        return 0

    applied = 0
    for d in decisions:
        reason = _manual_override_match_reason(d, cfg)
        if not reason:
            continue
        applied += 1
        d.rule_is_main_theme = True
        d.llm_is_main_theme = True
        if d.llm_confidence is None or d.llm_confidence < 90:
            d.llm_confidence = 90
        if "manual_override_mainline" not in d.llm_reasons:
            d.llm_reasons.append("manual_override_mainline")
        if reason not in d.llm_reasons:
            d.llm_reasons.append(reason)
        if "manual_override" not in d.llm_risk_flags:
            d.llm_risk_flags.append("manual_override")
        d.is_main_theme = True
        d.identity_status = "confirmed"
        d.evidence["manual_override_mainline"] = True
        d.evidence["manual_override_reason"] = reason
        d.evidence["manual_override_config"] = str(MANUAL_OVERRIDE_CONFIG_PATH)
    return applied


def _load_cluster_rules_config(path: Path) -> List[Dict[str, Any]]:
    if not path.exists():
        return list(DEFAULT_CLUSTER_RULES)
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return list(DEFAULT_CLUSTER_RULES)
    if not isinstance(raw, dict):
        return list(DEFAULT_CLUSTER_RULES)
    clusters = raw.get("clusters")
    if not isinstance(clusters, list):
        return list(DEFAULT_CLUSTER_RULES)
    rules: List[Dict[str, Any]] = []
    for row in clusters:
        if not isinstance(row, dict):
            continue
        name = str(row.get("name") or "").strip()
        keywords = [str(x).strip() for x in (row.get("keywords") or []) if str(x).strip()]
        core_tokens = [str(x).strip() for x in (row.get("core_tokens") or []) if str(x).strip()]
        if not name or not keywords:
            continue
        rules.append(
            {
                "name": name,
                "keywords": keywords,
                "core_tokens": core_tokens,
                "min_members": int(row.get("min_members") or 2),
                "min_strength_members": int(row.get("min_strength_members") or 2),
                "min_limit_up_sum": int(row.get("min_limit_up_sum") or 2),
                "min_continuity": float(row.get("min_continuity") or 55.0),
            }
        )
    return rules or list(DEFAULT_CLUSTER_RULES)


def _theme_matcher(tokens: List[str]):
    def _match(theme_name: str) -> bool:
        normalized = (theme_name or "").strip()
        normalized_lower = normalized.lower()
        return any((k in normalized) or (k.lower() in normalized_lower) for k in tokens)

    return _match


def _apply_cluster_compensation(decisions: List[IdentityDecision]) -> int:
    # 簇级规则增强：将“共簇一致性”转为 rule_precheck 增强，并补充 evidence；
    # 最终是否 confirmed 仍由 LLM 复核 + 硬门禁决定，不做直接晋级。
    cluster_rules_raw = _load_cluster_rules_config(CLUSTER_RULES_CONFIG_PATH)
    cluster_rules: List[Dict[str, Any]] = []
    for row in cluster_rules_raw:
        cluster_rules.append(
            {
                "name": row["name"],
                "is_member": _theme_matcher(list(row.get("keywords") or [])),
                "is_core": _theme_matcher(list(row.get("core_tokens") or [])),
                "min_members": int(row.get("min_members") or 2),
                "min_strength_members": int(row.get("min_strength_members") or 2),
                "min_limit_up_sum": int(row.get("min_limit_up_sum") or 2),
                "min_continuity": float(row.get("min_continuity") or 55.0),
            }
        )
    tagged = 0
    for rule in cluster_rules:
        members = [d for d in decisions if rule["is_member"](d.theme_name)]
        if not members:
            continue
        hot_members = [d for d in members if int(d.evidence.get("active_days_10d") or 0) >= 2]
        strength_members = [
            d
            for d in members
            if int(d.evidence.get("limit_up_count") or 0) >= 1
            and float(d.evidence.get("mainline_continuity_score") or 0.0) >= 45.0
        ]
        limit_up_sum = sum(int(d.evidence.get("limit_up_count") or 0) for d in members)
        max_continuity = max(float(d.evidence.get("mainline_continuity_score") or 0.0) for d in members)
        event_presence = any(int(d.evidence.get("event_count_3d") or 0) >= 1 for d in members)
        flow_presence = any(int(d.evidence.get("net_inflow_days_5d") or 0) >= 1 for d in members)
        cluster_pass = bool(
            len(members) >= int(rule["min_members"])
            and len(hot_members) >= 1
            and len(strength_members) >= int(rule["min_strength_members"])
            and limit_up_sum >= int(rule["min_limit_up_sum"])
            and max_continuity >= float(rule["min_continuity"])
            and event_presence
            and flow_presence
        )
        if not cluster_pass:
            continue

        for d in members:
            one_day_flag = bool(d.evidence.get("one_day_tour_flag"))
            if one_day_flag:
                continue
            active10 = int(d.evidence.get("active_days_10d") or 0)
            limit_up_count = int(d.evidence.get("limit_up_count") or 0)
            continuity = float(d.evidence.get("mainline_continuity_score") or 0.0)
            is_core = bool(rule["is_core"](d.theme_name))
            if is_core:
                member_pass = bool((active10 >= 1 or limit_up_count >= 1) and continuity >= 42.0)
            else:
                member_pass = bool((active10 >= 2 or limit_up_count >= 1) and continuity >= 50.0)
            if not member_pass:
                continue
            tagged += 1
            d.rule_is_main_theme = True
            d.evidence["cluster_compensation_mainline"] = True
            d.evidence["cluster_compensation_cluster"] = str(rule["name"])
            d.evidence["cluster_core_theme"] = is_core
            d.evidence["cluster_member_count"] = len(members)
            d.evidence["cluster_member_pass"] = True
    return tagged


def _apply_cluster_bootstrap_direct_confirm(
    decisions: List[IdentityDecision],
    *,
    enabled: bool,
) -> int:
    """
    历史补齐模式：
    对已命中簇规则的题材直接确认为主线，绕过“新题材当日硬证据门禁”。
    仅在显式开启 --cluster-bootstrap-direct-confirm 时生效。
    """
    if not enabled or not decisions:
        return 0
    cluster_rules_raw = _load_cluster_rules_config(CLUSTER_RULES_CONFIG_PATH)
    cluster_rules: List[Dict[str, Any]] = []
    for row in cluster_rules_raw:
        cluster_rules.append(
            {
                "name": row["name"],
                "is_member": _theme_matcher(list(row.get("keywords") or [])),
            }
        )
    promoted = 0
    for d in decisions:
        cluster_name = ""
        for rule in cluster_rules:
            if rule["is_member"](d.theme_name):
                cluster_name = str(rule["name"])
                break
        if not cluster_name:
            continue
        d.rule_is_main_theme = True
        d.is_main_theme = True
        d.identity_status = "confirmed"
        if d.llm_is_main_theme is None:
            d.llm_is_main_theme = True
        if "cluster_bootstrap_direct_confirm" not in d.llm_reasons:
            d.llm_reasons.append("cluster_bootstrap_direct_confirm")
        if "cluster_bootstrap" not in d.llm_risk_flags:
            d.llm_risk_flags.append("cluster_bootstrap")
        d.evidence["cluster_bootstrap_direct_confirm"] = True
        d.evidence["cluster_bootstrap_cluster"] = cluster_name
        promoted += 1
    return promoted


async def _apply_upgrade_trigger(
    conn: asyncpg.Connection,
    decisions: List[IdentityDecision],
    trade_date: date,
) -> Dict[str, int]:
    if not decisions:
        return {"candidate_count": 0, "review_pending_count": 0}

    subject_keys = [d.subject_key for d in decisions]
    prev_rows = await conn.fetch(
        """
        SELECT subject_key, evidence_json
        FROM theme_mainline_identity_registry
        WHERE subject_key = ANY($1::varchar[])
          AND last_review_date < $2::date
        """,
        subject_keys,
        trade_date,
    )
    prev_candidate_map: Dict[str, bool] = {}
    for r in prev_rows:
        ev = r.get("evidence_json")
        if isinstance(ev, str):
            try:
                ev = json.loads(ev)
            except Exception:
                ev = {}
        if not isinstance(ev, dict):
            ev = {}
        prev_candidate_map[str(r["subject_key"])] = bool(ev.get("upgrade_candidate"))

    candidate_count = 0
    review_pending_count = 0
    for d in decisions:
        if d.is_main_theme:
            continue

        e = d.evidence
        board_ok = bool(
            int(e.get("board_boom_days_5d") or 0) >= 2
            and int(e.get("limit_up_count") or 0) >= 2
            and float(e.get("limit_up_ratio_today") or 0.0) >= 0.02
        )
        event_ok = bool(
            int(e.get("event_count_3d") or 0) >= 1
            and int(e.get("event_recency_days") or 99) <= 3
            and int(e.get("strong_event_count_7d") or 0) >= 1
        )
        flow_ok = bool(
            int(e.get("net_inflow_days_5d") or 0) >= 3
            and float(e.get("net_inflow_sum_5d") or 0.0) > 0.0
        )
        logic_hard = bool(
            float(e.get("novelty_score") or 0.0) >= 55.0
            or float(d.logic_score) >= 65.0
        )
        continuity_ok = bool(float(e.get("mainline_continuity_score") or 0.0) >= 70.0)
        risk_ok = bool(float(e.get("one_day_tour_risk_score") or 100.0) < 70.0)
        base_candidate = bool(board_ok and event_ok and flow_ok and logic_hard and continuity_ok and risk_ok)

        if not base_candidate:
            continue

        candidate_count += 1
        e["upgrade_candidate"] = True
        e["upgrade_candidate_trade_date"] = trade_date.isoformat()
        e["upgrade_candidate_reasons"] = [
            "board_boom_sustained",
            "event_continuity_supported",
            "capital_inflow_supported",
            "logic_hard_supported",
        ]

        prev_candidate = bool(prev_candidate_map.get(d.subject_key, False))
        super_strong = bool(
            int(e.get("limit_up_count") or 0) >= 4
            and int(e.get("net_inflow_days_5d") or 0) >= 4
            and float(e.get("mainline_continuity_score") or 0.0) >= 80.0
        )
        if not (prev_candidate or super_strong):
            continue

        # 关键收口：upgrade_trigger 只负责“触发复核”，不允许旁路直通 confirmed。
        review_pending_count += 1
        d.llm_applied = False
        d.llm_is_main_theme = False
        d.llm_confidence = max(int(d.llm_confidence or 0), 72)
        if "upgrade_trigger_review_pending" not in d.llm_reasons:
            d.llm_reasons.append("upgrade_trigger_review_pending")
        if prev_candidate and "upgrade_trigger_prev_candidate_confirmed" not in d.llm_reasons:
            d.llm_reasons.append("upgrade_trigger_prev_candidate_confirmed")
        if super_strong and "upgrade_trigger_super_strong" not in d.llm_reasons:
            d.llm_reasons.append("upgrade_trigger_super_strong")
        if "upgrade_trigger" not in d.llm_risk_flags:
            d.llm_risk_flags.append("upgrade_trigger")
        d.is_main_theme = False
        d.identity_status = "review_pending"
        e["upgrade_trigger_review_pending"] = True
        e["upgrade_trigger_mode"] = "prev_candidate_or_super_strong"
        e["review_status"] = "pending"
        e["review_source"] = "upgrade_trigger"

    return {"candidate_count": candidate_count, "review_pending_count": review_pending_count}


def _to_review_queue_row(
    decision: IdentityDecision,
    trade_date: date,
) -> Optional[Tuple[date, str, str, str, str, float, str, str]]:
    if str(decision.identity_status).strip().lower() != "review_pending":
        return None
    evidence = decision.evidence if isinstance(decision.evidence, dict) else {}
    review_source = str(evidence.get("review_source") or "upgrade_trigger").strip().lower()
    if not review_source:
        review_source = "upgrade_trigger"
    review_source = review_source[:32]
    review_status = str(evidence.get("review_status") or "pending").strip().lower()[:24]
    if not review_status:
        review_status = "pending"
    continuity = float(evidence.get("mainline_continuity_score") or 0.0)
    priority = round(
        max(float(decision.composite_score), float(decision.logic_score), float(decision.market_score), continuity),
        3,
    )
    trigger_flags: List[str] = []
    if isinstance(decision.llm_reasons, list):
        trigger_flags.extend(str(x).strip() for x in decision.llm_reasons if str(x).strip())
    if isinstance(evidence.get("upgrade_candidate_reasons"), list):
        trigger_flags.extend(str(x).strip() for x in evidence.get("upgrade_candidate_reasons") if str(x).strip())
    trigger_flags = sorted(set(trigger_flags))
    queue_evidence = {
        "trade_date": trade_date.isoformat(),
        "subject_key": decision.subject_key,
        "theme_name": decision.theme_name,
        "logic_score": float(decision.logic_score),
        "market_score": float(decision.market_score),
        "composite_score": float(decision.composite_score),
        "logic_ok": bool(decision.logic_ok),
        "market_ok": bool(decision.market_ok),
        "rule_is_main_theme": bool(decision.rule_is_main_theme),
        "llm_applied": bool(decision.llm_applied),
        "llm_confidence": (int(decision.llm_confidence) if decision.llm_confidence is not None else None),
        "llm_reasons": list(decision.llm_reasons or []),
        "llm_risk_flags": list(decision.llm_risk_flags or []),
        "source_trade_date": str(decision.source_trade_date),
        "evidence": evidence,
    }
    return (
        trade_date,
        decision.subject_key,
        decision.theme_name,
        review_source,
        review_status,
        priority,
        json.dumps(trigger_flags, ensure_ascii=False),
        json.dumps(queue_evidence, ensure_ascii=False),
    )


async def _upsert_review_queue(
    conn: asyncpg.Connection,
    decisions: List[IdentityDecision],
    trade_date: date,
) -> int:
    rows: List[Tuple[date, str, str, str, str, float, str, str]] = []
    for decision in decisions:
        row = _to_review_queue_row(decision, trade_date)
        if row is not None:
            rows.append(row)
    if not rows:
        return 0
    sql = """
    INSERT INTO mainline_identity_review_queue (
        trade_date, subject_key, theme_name,
        review_source, review_status, priority_score,
        trigger_flags, evidence_json
    ) VALUES (
        $1::date, $2, $3,
        $4, $5, $6::numeric,
        $7::jsonb, $8::jsonb
    )
    ON CONFLICT (trade_date, subject_key, review_source) DO UPDATE
    SET
        theme_name = EXCLUDED.theme_name,
        review_status = EXCLUDED.review_status,
        priority_score = EXCLUDED.priority_score,
        trigger_flags = EXCLUDED.trigger_flags,
        evidence_json = EXCLUDED.evidence_json,
        reviewed_at = CASE
            WHEN EXCLUDED.review_status = 'pending' THEN NULL
            ELSE mainline_identity_review_queue.reviewed_at
        END
    """
    await conn.executemany(sql, rows)
    return len(rows)


async def _fetch_hot_subjects(
    conn: asyncpg.Connection,
    trade_date: date,
    lookback_days: int,
    universe_size: int,
    only_new: bool,
) -> List[asyncpg.Record]:
    sql = """
    WITH trading_window AS (
        SELECT rank_date
        FROM (
            SELECT DISTINCT r.rank_date
            FROM subject_rank_daily r
            WHERE r.rank_date <= $1::date
            ORDER BY r.rank_date DESC
            LIMIT $2::int
        ) t
    ),
    hot AS (
        SELECT
            r.subject_key,
            MAX(r.rank_date) AS latest_rank_date,
            COUNT(*) AS active_days,
            MAX(COALESCE(r.heat, 0)) AS max_heat,
            AVG(COALESCE(r.heat, 0)) AS avg_heat,
            MAX(COALESCE(r.his_pct_chg, 0)) AS max_his_pct
        FROM subject_rank_daily r
        JOIN trading_window tw
          ON tw.rank_date = r.rank_date
        GROUP BY r.subject_key
    ),
    alive AS (
        SELECT DISTINCT
            v2.subject_key
        FROM theme_cycle_judgement_v2 v2
        WHERE v2.trade_date = $1::date
          AND COALESCE(v2.final_mainline_alive, FALSE) = TRUE
    ),
    unified AS (
        SELECT
            h.subject_key,
            h.latest_rank_date,
            h.active_days,
            h.max_heat,
            h.avg_heat,
            h.max_his_pct,
            1 AS source_priority
        FROM hot h
        UNION ALL
        SELECT
            a.subject_key,
            $1::date AS latest_rank_date,
            0::bigint AS active_days,
            0::numeric AS max_heat,
            0::numeric AS avg_heat,
            0::numeric AS max_his_pct,
            0 AS source_priority
        FROM alive a
        WHERE NOT EXISTS (
            SELECT 1 FROM hot h WHERE h.subject_key = a.subject_key
        )
    ),
    dedup AS (
        SELECT DISTINCT ON (u.subject_key)
            u.subject_key,
            u.latest_rank_date,
            u.active_days,
            u.max_heat,
            u.avg_heat,
            u.max_his_pct,
            u.source_priority
        FROM unified u
        ORDER BY
            u.subject_key,
            u.source_priority ASC,
            u.latest_rank_date DESC
    )
    SELECT
        d.subject_key,
        d.latest_rank_date,
        d.active_days,
        d.max_heat,
        d.avg_heat,
        d.max_his_pct
    FROM dedup d
    LEFT JOIN theme_mainline_identity_registry mr
      ON mr.subject_key = d.subject_key
    WHERE ($3::boolean = FALSE OR mr.subject_key IS NULL)
    ORDER BY
        d.source_priority ASC,
        d.latest_rank_date DESC,
        d.max_heat DESC,
        d.avg_heat DESC,
        d.active_days DESC,
        d.max_his_pct DESC
    LIMIT $4
    """
    return await conn.fetch(sql, trade_date, max(int(lookback_days), 1), only_new, universe_size)


async def _fetch_cluster_subjects_for_review(
    conn: asyncpg.Connection,
    trade_date: date,
    lookback_days: int,
) -> List[str]:
    """
    主线簇纠偏兜底：
    当某簇存在“已确认主线核心题材”时，将该簇近期活跃成员补入 identity 复核候选池，
    防止因 rank/v2 候选宇宙裁剪导致簇成员长期漏审。
    """
    rules = _load_cluster_rules_config(CLUSTER_RULES_CONFIG_PATH)
    if not rules:
        return []

    window_days = max(30, int(lookback_days) * 3)
    collected: List[str] = []
    for rule in rules:
        keywords = [str(x).strip() for x in (rule.get("keywords") or []) if str(x).strip()]
        core_tokens = [str(x).strip() for x in (rule.get("core_tokens") or []) if str(x).strip()]
        if not keywords:
            continue
        core_patterns = [f"%{x}%" for x in (core_tokens or keywords)]
        has_confirmed_core = await conn.fetchval(
            """
            SELECT EXISTS (
              SELECT 1
              FROM theme_mainline_identity_registry mr
              WHERE COALESCE(mr.is_main_theme, FALSE) = TRUE
                AND COALESCE(NULLIF(LOWER(mr.identity_status), ''), 'observed') = 'confirmed'
                AND mr.theme_name ILIKE ANY($1::text[])
            )
            """,
            core_patterns,
        )
        has_v2_alive_core = await conn.fetchval(
            """
            SELECT EXISTS (
              SELECT 1
              FROM theme_cycle_judgement_v2 v2
              WHERE v2.trade_date BETWEEN ($1::date - INTERVAL '15 days') AND $1::date
                AND COALESCE(v2.final_mainline_alive, FALSE) = TRUE
                AND COALESCE(v2.fade_confirmed, FALSE) = FALSE
                AND COALESCE(v2.theme_name, '') ILIKE ANY($2::text[])
            )
            """,
            trade_date,
            core_patterns,
        )
        if not (bool(has_confirmed_core) or bool(has_v2_alive_core)):
            continue

        member_patterns = [f"%{x}%" for x in keywords]
        rows = await conn.fetch(
            """
            WITH candidate_names AS (
              SELECT DISTINCT v.subject_key, v.theme_name
              FROM vw_subject_theme_binding v
              UNION
              SELECT DISTINCT j.subject_key, j.theme_name
              FROM theme_cycle_judgement_v2 j
              WHERE j.trade_date BETWEEN ($2::date - ($3::int * INTERVAL '1 day')) AND $2::date
                AND COALESCE(j.theme_name, '') <> ''
              UNION
              SELECT DISTINCT e.subject_key, e.theme_name
              FROM theme_cycle_evidence_daily e
              WHERE e.trade_date BETWEEN ($2::date - ($3::int * INTERVAL '1 day')) AND $2::date
                AND COALESCE(e.theme_name, '') <> ''
            )
            SELECT DISTINCT c.subject_key
            FROM candidate_names c
            WHERE c.theme_name ILIKE ANY($1::text[])
              AND (
                EXISTS (
                  SELECT 1
                  FROM subject_rank_daily r
                  WHERE r.subject_key = c.subject_key
                    AND r.rank_date BETWEEN ($2::date - ($3::int * INTERVAL '1 day')) AND $2::date
                )
                OR EXISTS (
                  SELECT 1
                  FROM theme_cycle_judgement_v2 j
                  WHERE j.subject_key = c.subject_key
                    AND j.trade_date BETWEEN ($2::date - ($3::int * INTERVAL '1 day')) AND $2::date
                )
                OR EXISTS (
                  SELECT 1
                  FROM subject_stock_daily_snapshot s
                  WHERE s.subject_key = c.subject_key
                    AND s.trade_date BETWEEN ($2::date - ($3::int * INTERVAL '1 day')) AND $2::date
                )
                OR EXISTS (
                  SELECT 1
                  FROM theme_mainline_identity_registry mr
                  WHERE mr.subject_key = c.subject_key
                )
              )
            """,
            member_patterns,
            trade_date,
            window_days,
        )
        collected.extend(str(r["subject_key"]) for r in rows if str(r.get("subject_key") or "").strip())

    dedup: List[str] = []
    seen: set[str] = set()
    for key in collected:
        if key in seen:
            continue
        seen.add(key)
        dedup.append(key)
    return dedup


async def _fetch_latest_mainline_scores(
    conn: asyncpg.Connection,
    subject_key: str,
    trade_date: date,
) -> Optional[asyncpg.Record]:
    sql = """
    WITH tw_5 AS (
        SELECT rank_date
        FROM (
            SELECT DISTINCT r.rank_date
            FROM subject_rank_daily r
            WHERE r.rank_date <= $2::date
            ORDER BY r.rank_date DESC
            LIMIT 5
        ) t
    ),
    tw_10 AS (
        SELECT rank_date
        FROM (
            SELECT DISTINCT r.rank_date
            FROM subject_rank_daily r
            WHERE r.rank_date <= $2::date
            ORDER BY r.rank_date DESC
            LIMIT 10
        ) t
    ),
    tw_20 AS (
        SELECT rank_date
        FROM (
            SELECT DISTINCT r.rank_date
            FROM subject_rank_daily r
            WHERE r.rank_date <= $2::date
            ORDER BY r.rank_date DESC
            LIMIT 20
        ) t
    ),
    tw_30 AS (
        SELECT rank_date
        FROM (
            SELECT DISTINCT r.rank_date
            FROM subject_rank_daily r
            WHERE r.rank_date <= $2::date
            ORDER BY r.rank_date DESC
            LIMIT 30
        ) t
    ),
    rank_latest AS (
        SELECT
            r.subject_key,
            r.rank_date AS source_trade_date,
            COALESCE(r.heat, 0) AS heat_latest,
            COALESCE(r.his_pct_chg, 0) AS his_pct_chg_latest
        FROM subject_rank_daily r
        WHERE r.subject_key = $1
          AND r.rank_date <= $2::date
        ORDER BY r.rank_date DESC
        LIMIT 1
    ),
    rank_5d AS (
        SELECT
            r.subject_key,
            COALESCE(AVG(COALESCE(r.heat, 0)), 0) AS avg_heat_5d,
            COUNT(*) FILTER (WHERE COALESCE(r.heat, 0) >= 70) AS hot_days_5d
        FROM subject_rank_daily r
        JOIN tw_5
          ON tw_5.rank_date = r.rank_date
        WHERE r.subject_key = $1
        GROUP BY r.subject_key
    ),
    rank_20d AS (
        SELECT
            r.subject_key,
            COUNT(*) AS active_days_20d
        FROM subject_rank_daily r
        JOIN tw_20
          ON tw_20.rank_date = r.rank_date
        WHERE r.subject_key = $1
        GROUP BY r.subject_key
    ),
    rank_10d AS (
        SELECT
            r.subject_key,
            COUNT(*) AS active_days_10d
        FROM subject_rank_daily r
        JOIN tw_10
          ON tw_10.rank_date = r.rank_date
        WHERE r.subject_key = $1
        GROUP BY r.subject_key
    ),
    rank_30d AS (
        SELECT
            $1::varchar AS subject_key,
            ARRAY_AGG(COALESCE(r.his_pct_chg, 0)::numeric ORDER BY tw_30.rank_date ASC) AS his_pct_chg_30d
        FROM tw_30
        LEFT JOIN subject_rank_daily r
          ON r.subject_key = $1
         AND r.rank_date = tw_30.rank_date
    ),
    ev_latest AS (
        SELECT
            e.subject_key,
            e.trade_date,
            COALESCE(e.theme_name, '') AS theme_name,
            COALESCE(e.event_count_3d, 0) AS event_count_3d,
            COALESCE(e.event_count_7d, 0) AS event_count_7d,
            COALESCE(e.strong_event_count_7d, 0) AS strong_event_count_7d,
            COALESCE(e.event_continuity_score, 0) AS event_continuity_score,
            COALESCE(e.event_strength_score, 0) AS event_strength_score,
            COALESCE(e.event_recency_days, 99) AS event_recency_days,
            COALESCE(e.board_stock_count, 0) AS board_stock_count,
            COALESCE(e.limit_up_count, 0) AS limit_up_count,
            COALESCE(e.front_row_strength_score, 0) AS front_row_strength_score,
            COALESCE(e.front_row_survival_ratio, 0) AS front_row_alive_ratio,
            COALESCE(e.above_ma10, FALSE) AS above_ma10,
            COALESCE(e.above_ma20, FALSE) AS above_ma20,
            COALESCE(e.theme_support_score, 0) AS theme_support_score,
            COALESCE(e.theme_ret_10d, 0) AS theme_ret_10d
        FROM theme_cycle_evidence_daily e
        WHERE e.subject_key = $1
          AND e.trade_date <= $2::date
        ORDER BY e.trade_date DESC
        LIMIT 1
    ),
    ev_5d AS (
        SELECT
            e.subject_key,
            COUNT(*) FILTER (
                WHERE COALESCE(e.limit_up_count, 0) >= 2
                  AND (
                    CASE
                      WHEN COALESCE(e.board_stock_count, 0) > 0
                      THEN COALESCE(e.limit_up_count, 0)::numeric / e.board_stock_count::numeric
                      ELSE 0
                    END
                  ) >= 0.03
            ) AS board_boom_days_5d
        FROM theme_cycle_evidence_daily e
        JOIN tw_5
          ON tw_5.rank_date = e.trade_date
        WHERE e.subject_key = $1
        GROUP BY e.subject_key
    ),
    flow_daily AS (
        SELECT
            m.subject_key,
            m.trade_date,
            COALESCE(SUM(COALESCE(m.main_net_inflow, 0)), 0) AS net_inflow_day
        FROM money_flow_enhanced m
        JOIN tw_5
          ON tw_5.rank_date = m.trade_date
        WHERE m.subject_key = $1
        GROUP BY m.subject_key, m.trade_date
    ),
    flow_5d AS (
        SELECT
            subject_key,
            COALESCE(SUM(net_inflow_day), 0) AS net_inflow_sum_5d,
            COUNT(*) FILTER (WHERE net_inflow_day > 0) AS net_inflow_days_5d
        FROM flow_daily
        GROUP BY subject_key
    ),
    v2_latest AS (
        SELECT
            v2.subject_key,
            COALESCE(v2.final_mainline_alive, FALSE) AS v2_final_mainline_alive,
            COALESCE(v2.final_cycle_state, 'unknown') AS v2_final_cycle_state,
            COALESCE(v2.fade_watch, FALSE) AS v2_fade_watch,
            COALESCE(v2.fade_confirmed, FALSE) AS v2_fade_confirmed,
            COALESCE(v2.mainline_strength_score, 0) AS v2_mainline_strength_score
        FROM theme_cycle_judgement_v2 v2
        WHERE v2.subject_key = $1
          AND v2.trade_date <= $2::date
        ORDER BY v2.trade_date DESC
        LIMIT 1
    ),
    tw_v2_3 AS (
        SELECT trade_date
        FROM (
            SELECT DISTINCT trade_date
            FROM theme_cycle_judgement_v2
            WHERE trade_date <= $2::date
            ORDER BY trade_date DESC
            LIMIT 3
        ) t
    ),
    tw_v2_5 AS (
        SELECT trade_date
        FROM (
            SELECT DISTINCT trade_date
            FROM theme_cycle_judgement_v2
            WHERE trade_date <= $2::date
            ORDER BY trade_date DESC
            LIMIT 5
        ) t
    ),
    v2_recent AS (
        SELECT
            $1::varchar AS subject_key,
            (
                SELECT COUNT(*)
                FROM tw_v2_3 d3
                JOIN theme_cycle_judgement_v2 v2
                  ON v2.subject_key = $1
                 AND v2.trade_date = d3.trade_date
                WHERE COALESCE(v2.final_mainline_alive, FALSE)
            ) AS v2_alive_days_3d,
            (
                SELECT COUNT(*)
                FROM tw_v2_3 d3
                JOIN theme_cycle_judgement_v2 v2
                  ON v2.subject_key = $1
                 AND v2.trade_date = d3.trade_date
                WHERE COALESCE(v2.final_mainline_alive, FALSE)
                  AND COALESCE(v2.final_cycle_state, '') IN ('divergence', 'repair', '分歧', '修复')
            ) AS v2_div_repair_alive_days_3d,
            (
                SELECT COUNT(*)
                FROM tw_v2_5 d5
                JOIN theme_cycle_judgement_v2 v2
                  ON v2.subject_key = $1
                 AND v2.trade_date = d5.trade_date
                WHERE COALESCE(v2.final_mainline_alive, FALSE)
            ) AS v2_alive_days_5d
    ),
    base_subject AS (
        SELECT $1::varchar AS subject_key
    )
    SELECT
        b.subject_key,
        COALESCE(v2n.theme_name, ev.theme_name, v.theme_name, b.subject_key) AS theme_name,
        COALESCE(rl.source_trade_date, ev.trade_date, $2::date) AS source_trade_date,
        COALESCE(rl.heat_latest, 0) AS heat_latest,
        COALESCE(rl.his_pct_chg_latest, 0) AS his_pct_chg_latest,
        COALESCE(r5.avg_heat_5d, 0) AS avg_heat_5d,
        COALESCE(r5.hot_days_5d, 0) AS hot_days_5d,
        COALESCE(r10.active_days_10d, 0) AS active_days_10d,
        COALESCE(r20.active_days_20d, 0) AS active_days_20d,
        COALESCE(r30.his_pct_chg_30d, ARRAY[]::numeric[]) AS his_pct_chg_30d,
        COALESCE(ev.event_count_3d, 0) AS event_count_3d,
        COALESCE(ev.event_count_7d, 0) AS event_count_7d,
        COALESCE(ev.strong_event_count_7d, 0) AS strong_event_count_7d,
        COALESCE(ev.event_continuity_score, 0) AS event_continuity_score,
        COALESCE(ev.event_strength_score, 0) AS event_strength_score,
        COALESCE(ev.event_recency_days, 99) AS event_recency_days,
        COALESCE(ev.board_stock_count, 0) AS board_stock_count,
        COALESCE(ev.limit_up_count, 0) AS limit_up_count,
        COALESCE(ev.front_row_strength_score, 0) AS front_row_strength_score,
        COALESCE(ev.front_row_alive_ratio, 0) AS front_row_alive_ratio,
        COALESCE(ev.above_ma10, FALSE) AS above_ma10,
        COALESCE(ev.above_ma20, FALSE) AS above_ma20,
        COALESCE(ev.theme_support_score, 0) AS theme_support_score,
        COALESCE(ev.theme_ret_10d, 0) AS theme_ret_10d,
        COALESCE(ev5.board_boom_days_5d, 0) AS board_boom_days_5d,
        COALESCE(f5.net_inflow_sum_5d, 0) AS net_inflow_sum_5d,
        COALESCE(f5.net_inflow_days_5d, 0) AS net_inflow_days_5d,
        COALESCE(v2.v2_final_mainline_alive, FALSE) AS v2_final_mainline_alive,
        COALESCE(v2.v2_final_cycle_state, 'unknown') AS v2_final_cycle_state,
        COALESCE(v2.v2_fade_watch, FALSE) AS v2_fade_watch,
        COALESCE(v2.v2_fade_confirmed, FALSE) AS v2_fade_confirmed,
        COALESCE(v2.v2_mainline_strength_score, 0) AS v2_mainline_strength_score,
        COALESCE(v2r.v2_alive_days_3d, 0) AS v2_alive_days_3d,
        COALESCE(v2r.v2_div_repair_alive_days_3d, 0) AS v2_div_repair_alive_days_3d,
        COALESCE(v2r.v2_alive_days_5d, 0) AS v2_alive_days_5d
    FROM base_subject b
    LEFT JOIN rank_latest rl
      ON rl.subject_key = b.subject_key
    LEFT JOIN vw_subject_theme_binding v
      ON v.subject_key = b.subject_key
    LEFT JOIN (
      SELECT v2.subject_key, v2.theme_name
      FROM theme_cycle_judgement_v2 v2
      WHERE v2.subject_key = $1
        AND v2.trade_date <= $2::date
      ORDER BY v2.trade_date DESC
      LIMIT 1
    ) v2n
      ON v2n.subject_key = b.subject_key
    LEFT JOIN rank_5d r5
      ON r5.subject_key = b.subject_key
    LEFT JOIN rank_10d r10
      ON r10.subject_key = b.subject_key
    LEFT JOIN rank_20d r20
      ON r20.subject_key = b.subject_key
    LEFT JOIN rank_30d r30
      ON r30.subject_key = b.subject_key
    LEFT JOIN ev_latest ev
      ON ev.subject_key = b.subject_key
    LEFT JOIN ev_5d ev5
      ON ev5.subject_key = b.subject_key
    LEFT JOIN flow_5d f5
      ON f5.subject_key = b.subject_key
    LEFT JOIN v2_latest v2
      ON v2.subject_key = b.subject_key
    LEFT JOIN v2_recent v2r
      ON v2r.subject_key = b.subject_key
    """
    return await conn.fetchrow(sql, subject_key, trade_date)


def _decide_identity(row: asyncpg.Record) -> IdentityDecision:
    subject_key = str(row["subject_key"])
    theme_name = str(row.get("theme_name") or subject_key)
    source_trade_date = row["source_trade_date"]
    heat_latest_raw = float(row.get("heat_latest") or 0.0)
    avg_heat_5d_raw = float(row.get("avg_heat_5d") or 0.0)
    # 兼容热度量纲：subject_rank_daily.heat 可能是 0~1 或 0~100。
    heat_latest = heat_latest_raw * 100.0 if heat_latest_raw <= 1.2 else heat_latest_raw
    avg_heat_5d = avg_heat_5d_raw * 100.0 if avg_heat_5d_raw <= 1.2 else avg_heat_5d_raw
    hot_days_5d = int(row.get("hot_days_5d") or 0)
    active_days_10d = int(row.get("active_days_10d") or 0)
    active_days_20d = int(row.get("active_days_20d") or 0)
    his_pct_chg_30d_raw = row.get("his_pct_chg_30d") or []
    his_pct_chg_30d = [float(x or 0.0) for x in list(his_pct_chg_30d_raw)] if his_pct_chg_30d_raw else []
    his_pct_chg_latest = float(row.get("his_pct_chg_latest") or 0.0)
    event_count_3d = int(row.get("event_count_3d") or 0)
    event_count_7d = int(row.get("event_count_7d") or 0)
    strong_event_count_7d = int(row.get("strong_event_count_7d") or 0)
    event_continuity_score = float(row.get("event_continuity_score") or 0.0)
    event_strength_score = float(row.get("event_strength_score") or 0.0)
    event_recency_days = int(row.get("event_recency_days") or 99)
    board_stock_count = int(row.get("board_stock_count") or 0)
    limit_up_count = int(row.get("limit_up_count") or 0)
    front_row_strength_score = float(row.get("front_row_strength_score") or 0.0)
    front_row_alive_ratio = float(row.get("front_row_alive_ratio") or 0.0)
    above_ma10 = bool(row.get("above_ma10") or False)
    above_ma20 = bool(row.get("above_ma20") or False)
    theme_support_score = float(row.get("theme_support_score") or 0.0)
    theme_ret_10d = float(row.get("theme_ret_10d") or 0.0)
    board_boom_days_5d = int(row.get("board_boom_days_5d") or 0)
    net_inflow_sum_5d = float(row.get("net_inflow_sum_5d") or 0.0)
    net_inflow_days_5d = int(row.get("net_inflow_days_5d") or 0)
    v2_final_mainline_alive = bool(row.get("v2_final_mainline_alive") or False)
    v2_final_cycle_state = str(row.get("v2_final_cycle_state") or "unknown")
    v2_fade_watch = bool(row.get("v2_fade_watch") or False)
    v2_fade_confirmed = bool(row.get("v2_fade_confirmed") or False)
    v2_mainline_strength_score = float(row.get("v2_mainline_strength_score") or 0.0)
    v2_alive_days_3d = int(row.get("v2_alive_days_3d") or 0)
    v2_div_repair_alive_days_3d = int(row.get("v2_div_repair_alive_days_3d") or 0)
    v2_alive_days_5d = int(row.get("v2_alive_days_5d") or 0)
    limit_up_ratio_today = (float(limit_up_count) / float(board_stock_count)) if board_stock_count > 0 else 0.0
    fund_continuity_score = min(100.0, max(0.0, net_inflow_sum_5d / 1e8) * 10.0 + net_inflow_days_5d * 14.0)
    board_continuity_score = min(100.0, limit_up_count * 8.0 + limit_up_ratio_today * 550.0 + board_boom_days_5d * 18.0)
    kline_continuity_score = min(
        100.0,
        (20.0 if above_ma10 else 0.0)
        + (25.0 if above_ma20 else 0.0)
        + theme_support_score * 0.45
        + max(0.0, theme_ret_10d + 8.0) * 1.8,
    )
    mainline_continuity_score = (
        fund_continuity_score * 0.35
        + board_continuity_score * 0.35
        + kline_continuity_score * 0.30
    )
    pulse_risk_score = 65.0 if active_days_20d <= 1 else (42.0 if active_days_20d <= 2 else 12.0)
    capital_drop_risk = 25.0 if (net_inflow_days_5d <= 1 and net_inflow_sum_5d <= 0.0) else 0.0
    board_drop_risk = 20.0 if board_boom_days_5d == 0 else 0.0
    ta_kline = _analyze_theme_kline_shape_open_source(his_pct_chg_30d)
    kline_support_hold = bool(ta_kline.get("kline_support_hold") or False)
    one_day_tour_kline_flag = bool(ta_kline.get("one_day_tour_kline_flag") or False)
    platform_breakout_flag = bool(ta_kline.get("platform_breakout_flag") or False)
    platform_breakout_strength = float(ta_kline.get("platform_breakout_strength") or 0.0)

    kline_break_risk = 22.0 if (not above_ma10 and not above_ma20 and theme_support_score < 45.0 and not kline_support_hold) else 0.0
    deep_fall_risk = 12.0 if theme_ret_10d < -8.0 else 0.0
    one_day_tour_risk_score = min(
        100.0,
        pulse_risk_score + capital_drop_risk + board_drop_risk + kline_break_risk + deep_fall_risk,
    )
    one_day_tour_flag = bool(
        (one_day_tour_risk_score >= 70.0 and mainline_continuity_score < 45.0)
        or one_day_tour_kline_flag
    )
    jyhf_hot_mainline_flag = active_days_10d >= 4

    novelty_score = min(100.0, strong_event_count_7d * 18.0 + event_strength_score * 0.35)
    timing_score = min(100.0, max(0.0, 100.0 - max(event_recency_days - 1, 0) * 15.0))
    impact_score = min(
        100.0,
        front_row_strength_score * 0.55
        + limit_up_count * 9.0
        + front_row_alive_ratio * 25.0
        + (8.0 if platform_breakout_flag else 0.0)
        + min(platform_breakout_strength * 0.12, 8.0),
    )
    logic_score = novelty_score * 0.4 + timing_score * 0.3 + impact_score * 0.3

    heat_score = min(100.0, heat_latest * 0.65 + avg_heat_5d * 0.35)
    board_score = min(
        100.0,
        limit_up_count * 9.0
        + limit_up_ratio_today * 600.0
        + board_boom_days_5d * 15.0
        + front_row_strength_score * 0.30,
    )
    flow_score = min(100.0, max(0.0, net_inflow_sum_5d / 1e8) * 12.0 + net_inflow_days_5d * 14.0)
    fermentation_score = min(100.0, event_continuity_score * 0.7 + event_count_3d * 8.0 + hot_days_5d * 6.0)
    market_score = heat_score * 0.25 + board_score * 0.30 + flow_score * 0.25 + fermentation_score * 0.20
    composite_score = logic_score * 0.45 + market_score * 0.55

    # 逻辑维度由 LLM 最终裁决，这里仅做调用前置校验，避免明显噪声题材进入复核。
    logic_ok = bool(
        strong_event_count_7d >= 1
        and event_count_3d >= 1
        and event_recency_days <= 5
    )
    # 市场认可硬门禁：热度 + 板块强度 + 资金持续流入 + 事件持续发酵。
    fermentation_ok = bool(
        event_continuity_score >= 28.0
        and (event_count_3d >= 1 or hot_days_5d >= 2)
    )
    market_ok = bool(
        not one_day_tour_flag
        and
        mainline_continuity_score >= 50.0
        and
        heat_score >= 58.0
        and his_pct_chg_latest >= -1.0
        and limit_up_count >= 2
        and limit_up_ratio_today >= 0.02
        and board_boom_days_5d >= 1
        and (
            (net_inflow_sum_5d > 0.0 and net_inflow_days_5d >= 2)
            or (
                # 主线存续豁免：资金短期走弱但K线未破关键支撑，不判死。
                net_inflow_sum_5d > 0.0
                and net_inflow_days_5d >= 1
                and kline_support_hold
                and active_days_10d >= 2
            )
            or (
                # 主线晋级补偿：平台突破属于强结构信号，可放宽资金连续天数。
                platform_breakout_flag
                and platform_breakout_strength >= 20.0
                and net_inflow_sum_5d >= 0.0
                and active_days_10d >= 2
            )
        )
        and fermentation_ok
        and strong_event_count_7d >= 1
    )
    rule_is_main_theme = bool(logic_ok and market_ok)
    is_main_theme = False
    identity_status = "observed"

    evidence = {
        "heat_latest_raw": round(heat_latest_raw, 4),
        "avg_heat_5d_raw": round(avg_heat_5d_raw, 4),
        "heat_latest": round(heat_latest, 3),
        "avg_heat_5d": round(avg_heat_5d, 3),
        "hot_days_5d": hot_days_5d,
        "active_days_10d": active_days_10d,
        "active_days_20d": active_days_20d,
        "jyhf_hot_mainline_flag": jyhf_hot_mainline_flag,
        "one_day_tour_flag": one_day_tour_flag,
        "one_day_tour_kline_flag": one_day_tour_kline_flag,
        "one_day_tour_risk_score": round(one_day_tour_risk_score, 3),
        "kline_support_hold": kline_support_hold,
        "platform_breakout_flag": platform_breakout_flag,
        "platform_breakout_strength": round(platform_breakout_strength, 3),
        "kline_ta_backend": str(ta_kline.get("ta_backend") or ""),
        "kline_ta_ema10": float(ta_kline.get("ema10") or 0.0),
        "kline_ta_ema20": float(ta_kline.get("ema20") or 0.0),
        "kline_ta_rsi14": float(ta_kline.get("rsi14") or 0.0),
        "kline_ta_bb_lower": float(ta_kline.get("bb_lower") or 0.0),
        "kline_ta_close_last": float(ta_kline.get("close_last") or 0.0),
        "kline_ta_retrace_ratio_5d": float(ta_kline.get("retrace_ratio_5d") or 0.0),
        "mainline_continuity_score": round(mainline_continuity_score, 3),
        "fund_continuity_score": round(fund_continuity_score, 3),
        "board_continuity_score": round(board_continuity_score, 3),
        "kline_continuity_score": round(kline_continuity_score, 3),
        "his_pct_chg_latest": round(his_pct_chg_latest, 3),
        "event_count_3d": event_count_3d,
        "event_count_7d": event_count_7d,
        "strong_event_count_7d": strong_event_count_7d,
        "event_continuity_score": round(event_continuity_score, 3),
        "event_strength_score": round(event_strength_score, 3),
        "event_recency_days": event_recency_days,
        "board_stock_count": board_stock_count,
        "limit_up_count": limit_up_count,
        "limit_up_ratio_today": round(limit_up_ratio_today, 4),
        "front_row_strength_score": round(front_row_strength_score, 3),
        "front_row_alive_ratio": round(front_row_alive_ratio, 3),
        "above_ma10": above_ma10,
        "above_ma20": above_ma20,
        "theme_support_score": round(theme_support_score, 3),
        "theme_ret_10d": round(theme_ret_10d, 3),
        "board_boom_days_5d": board_boom_days_5d,
        "net_inflow_sum_5d": round(net_inflow_sum_5d, 3),
        "net_inflow_days_5d": net_inflow_days_5d,
        "novelty_score": round(novelty_score, 3),
        "timing_score": round(timing_score, 3),
        "impact_score": round(impact_score, 3),
        "heat_score": round(heat_score, 3),
        "board_score": round(board_score, 3),
        "flow_score": round(flow_score, 3),
        "fermentation_score": round(fermentation_score, 3),
        "fermentation_ok": fermentation_ok,
        "logic_ok": logic_ok,
        "market_ok": market_ok,
        "v2_final_mainline_alive": v2_final_mainline_alive,
        "v2_final_cycle_state": v2_final_cycle_state,
        "v2_fade_watch": v2_fade_watch,
        "v2_fade_confirmed": v2_fade_confirmed,
        "v2_mainline_strength_score": round(v2_mainline_strength_score, 3),
        "v2_alive_days_3d": v2_alive_days_3d,
        "v2_div_repair_alive_days_3d": v2_div_repair_alive_days_3d,
        "v2_alive_days_5d": v2_alive_days_5d,
    }

    return IdentityDecision(
        subject_key=subject_key,
        theme_name=theme_name,
        source_trade_date=source_trade_date,
        logic_score=round(logic_score, 3),
        market_score=round(market_score, 3),
        composite_score=round(composite_score, 3),
        logic_ok=logic_ok,
        market_ok=market_ok,
        rule_is_main_theme=rule_is_main_theme,
        llm_applied=False,
        llm_is_main_theme=None,
        llm_confidence=None,
        llm_reasons=[],
        llm_risk_flags=[],
        llm_model="",
        is_main_theme=is_main_theme,
        identity_status=identity_status,
        evidence=evidence,
    )


def _build_llm_prompt(trade_date: date, decision: IdentityDecision) -> str:
    evidence = decision.evidence
    return f"""你是A股主线身份判定复核专家。必须严格执行以下规则：
1) 你必须同时复核“逻辑维度 + 市场维度”，不能只看单维度。
2) 逻辑维度：新颖度、时机、影响广度。
3) 市场维度：热度、板块强度（涨停潮/前排强度）、资金持续流入、事件持续发酵。
4) 禁止自由发挥，必须严格依据输入硬数据与规则阈值判断。
5) 一日游题材、单日异动、缺乏持续性的题材，不得判为主线。
6) 输出必须是JSON，不要输出额外文本。

交易日：{trade_date.isoformat()}
题材：{decision.theme_name}
subject_key：{decision.subject_key}

逻辑维度硬证据：
- event_count_3d={int(evidence.get("event_count_3d") or 0)}
- event_count_7d={int(evidence.get("event_count_7d") or 0)}
- strong_event_count_7d={int(evidence.get("strong_event_count_7d") or 0)}
- event_continuity_score={float(evidence.get("event_continuity_score") or 0.0):.2f}
- event_recency_days={int(evidence.get("event_recency_days") or 99)}
- novelty_score={float(evidence.get("novelty_score") or 0.0):.2f}
- timing_score={float(evidence.get("timing_score") or 0.0):.2f}
- impact_score={float(evidence.get("impact_score") or 0.0):.2f}

市场维度硬证据：
- heat_latest={float(evidence.get("heat_latest") or 0.0):.2f}
- avg_heat_5d={float(evidence.get("avg_heat_5d") or 0.0):.2f}
- active_days_20d={int(evidence.get("active_days_20d") or 0)}
- active_days_10d={int(evidence.get("active_days_10d") or 0)}
- hot_days_5d={int(evidence.get("hot_days_5d") or 0)}
- one_day_tour_flag={bool(evidence.get("one_day_tour_flag") or False)}
- one_day_tour_risk_score={float(evidence.get("one_day_tour_risk_score") or 0.0):.2f}
- mainline_continuity_score={float(evidence.get("mainline_continuity_score") or 0.0):.2f}
- board_stock_count={int(evidence.get("board_stock_count") or 0)}
- limit_up_count={int(evidence.get("limit_up_count") or 0)}
- limit_up_ratio_today={float(evidence.get("limit_up_ratio_today") or 0.0):.4f}
- board_boom_days_5d={int(evidence.get("board_boom_days_5d") or 0)}
- net_inflow_sum_5d={float(evidence.get("net_inflow_sum_5d") or 0.0):.2f}
- net_inflow_days_5d={int(evidence.get("net_inflow_days_5d") or 0)}
- event_continuity_score={float(evidence.get("event_continuity_score") or 0.0):.2f}
- above_ma10={bool(evidence.get("above_ma10") or False)}
- above_ma20={bool(evidence.get("above_ma20") or False)}
- theme_support_score={float(evidence.get("theme_support_score") or 0.0):.2f}
- theme_ret_10d={float(evidence.get("theme_ret_10d") or 0.0):.2f}
- kline_ta_backend={str(evidence.get("kline_ta_backend") or "")}
- kline_ta_ema10={float(evidence.get("kline_ta_ema10") or 0.0):.2f}
- kline_ta_ema20={float(evidence.get("kline_ta_ema20") or 0.0):.2f}
- kline_ta_rsi14={float(evidence.get("kline_ta_rsi14") or 0.0):.2f}
- kline_ta_bb_lower={float(evidence.get("kline_ta_bb_lower") or 0.0):.2f}
- kline_ta_close_last={float(evidence.get("kline_ta_close_last") or 0.0):.2f}
- kline_ta_retrace_ratio_5d={float(evidence.get("kline_ta_retrace_ratio_5d") or 0.0):.4f}
- kline_support_hold={bool(evidence.get("kline_support_hold") or False)}
- one_day_tour_kline_flag={bool(evidence.get("one_day_tour_kline_flag") or False)}
- v2_final_mainline_alive={bool(evidence.get("v2_final_mainline_alive") or False)}
- v2_final_cycle_state={str(evidence.get("v2_final_cycle_state") or "unknown")}
- v2_alive_days_3d={int(evidence.get("v2_alive_days_3d") or 0)}
- v2_div_repair_alive_days_3d={int(evidence.get("v2_div_repair_alive_days_3d") or 0)}
- v2_fade_watch={bool(evidence.get("v2_fade_watch") or False)}
- v2_fade_confirmed={bool(evidence.get("v2_fade_confirmed") or False)}
- v2_mainline_strength_score={float(evidence.get("v2_mainline_strength_score") or 0.0):.2f}
- market_ok={decision.market_ok}
- cluster_compensation_mainline={bool(evidence.get("cluster_compensation_mainline") or False)}
- cluster_compensation_cluster={str(evidence.get("cluster_compensation_cluster") or "")}
- cluster_core_theme={bool(evidence.get("cluster_core_theme") or False)}
- cluster_member_count={int(evidence.get("cluster_member_count") or 0)}

规则层预判：
- logic_precheck={decision.logic_ok}
- market_gate={decision.market_ok}
- rule_precheck_pass={decision.rule_is_main_theme}

请严格按以下“硬规则阈值”复核（可按>=理解为满足）：
逻辑维度建议阈值：
主线逻辑可走两条路径（二选一）：
A. 新题材发酵路径：
   1. strong_event_count_7d >= 1
   2. event_count_3d >= 1
   3. event_recency_days <= 5
   4. event_continuity_score >= 28 或 novelty_score >= 50
B. 存续主线路径（用于成熟主线分歧/修复阶段）：
   1. cluster_compensation_mainline=true 且 cluster_core_theme=true
   2. mainline_continuity_score >= 60
   3. kline_support_hold=true
   4. v2_final_mainline_alive=true 且 v2_final_cycle_state 属于 divergence/repair
   5. v2_fade_confirmed=false

市场维度建议阈值：
1. heat_latest >= 58 或 avg_heat_5d >= 55
2. one_day_tour_risk_score < 70 且 mainline_continuity_score >= 50
3. limit_up_count >= 2 且 limit_up_ratio_today >= 0.02 且 board_boom_days_5d >= 1
4. 资金连续性满足以下任一：
   - net_inflow_sum_5d > 0 且 net_inflow_days_5d >= 2
   - （分歧容忍）net_inflow_sum_5d > 0 且 net_inflow_days_5d >= 1 且 mainline_continuity_score >= 75 且 active_days_10d >= 2
5. event_continuity_score >= 28 且 (event_count_3d >= 1 或 hot_days_5d >= 2)
6. 若 v2_final_mainline_alive=true 且 v2_final_cycle_state 属于 divergence/repair，可作为“非退潮的辅助证据”，但不能覆盖一日游/资金为负/事件缺失硬否决
7. 若 one_day_tour_kline_flag=true，必须判定为非主线；若 kline_support_hold=true，可作为主线存续强证据
8. 共簇一致性规则（必须执行）：
   - 若 cluster_compensation_mainline=true 且 cluster_core_theme=true，
     说明该题材属于核心簇（如 data_center/optical_comm/commercial_space）核心题材，应与同簇核心题材保持一致性。
   - 在不存在硬否决（one_day_tour_kline_flag=true 或 v2_fade_confirmed=true）的前提下，
     应优先判定 market_dimension_ok_llm=true，并据此评估是否可判主线。
   - 若存在硬否决，则必须判定为非主线。

综合判定规则（必须遵守）：
1. logic_dimension_ok_llm = 逻辑维度阈值整体成立
2. market_dimension_ok_llm = 市场维度阈值整体成立
3. is_main_theme_core_llm = logic_dimension_ok_llm AND market_dimension_ok_llm
4. 若任一维度不满足，is_main_theme_core_llm 必须为 false

请输出：
{{
  "logic_dimension_ok_llm": true/false,
  "market_dimension_ok_llm": true/false,
  "is_main_theme_core_llm": true/false,
  "confidence": 0-100,
  "reasons": ["最多3条"],
  "risk_flags": ["最多3条"]
}}
"""


async def _call_llm_review(
    *,
    prompt: str,
    api_key: str,
    api_base: str,
    model_name: str,
    timeout_seconds: int,
) -> Dict[str, Any]:
    url = f"{api_base}/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": model_name,
        "messages": [
            {"role": "system", "content": "你是主线身份复核专家，必须输出JSON。"},
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.1,
        "max_tokens": 1000,
        "response_format": {"type": "json_object"},
    }
    async with aiohttp.ClientSession() as session:
        async with session.post(url, headers=headers, json=payload, timeout=max(5, int(timeout_seconds))) as resp:
            if resp.status != 200:
                text = await resp.text()
                raise RuntimeError(f"llm_http_{resp.status}:{text[:300]}")
            data = await resp.json()
    content = data["choices"][0]["message"]["content"]
    return json.loads(content)


async def _apply_llm_review(
    decisions: List[IdentityDecision],
    *,
    trade_date: date,
    enable_llm: bool,
    require_llm: bool,
    timeout_seconds: int,
) -> None:
    if not decisions:
        return
    if not enable_llm:
        for d in decisions:
            d.llm_applied = False
            d.llm_is_main_theme = None
            d.llm_confidence = None
            d.llm_reasons = ["llm_disabled"]
            d.llm_risk_flags = []
            d.llm_model = ""
            # 禁用LLM时 fail-closed，避免“仅规则放行”进入 confirmed。
            # 仍允许后续补偿/人工覆盖模块在明示条件下晋级。
            d.is_main_theme = False
            d.identity_status = "observed"
        return

    api_key = _get_env_value("DEEPSEEK_API_KEY", "")
    api_base = _get_env_value("DEEPSEEK_API_BASE", "https://api.deepseek.com")
    model_name = _get_env_value("DEEPSEEK_MODEL", "deepseek-chat")
    rule_pass_decisions = [d for d in decisions if d.rule_is_main_theme]
    if not api_key:
        if require_llm and rule_pass_decisions:
            raise RuntimeError("mainline_identity_llm_required_but_missing_api_key")
        # 主线身份走双重门禁：无 key 时 fail-closed，避免“仅规则放行”
        for d in decisions:
            d.llm_applied = False
            d.llm_is_main_theme = False
            d.llm_confidence = 0
            d.llm_reasons = ["missing_deepseek_api_key"]
            d.llm_risk_flags = ["llm_not_available"]
            d.llm_model = model_name
            d.is_main_theme = False
            d.identity_status = "observed"
        return

    for d in decisions:
        # 近10日高活跃仅作为候选增强信号，不允许绕过规则+LLM双门禁直接晋级。
        if bool(d.evidence.get("jyhf_hot_mainline_flag")):
            d.evidence["compensation_direct_promote_candidate"] = True
        evidence = d.evidence
        heat_latest = float(evidence.get("heat_latest") or 0.0)
        avg_heat_5d = float(evidence.get("avg_heat_5d") or 0.0)
        one_day_tour_flag = bool(evidence.get("one_day_tour_flag") or False)
        mainline_continuity_score = float(evidence.get("mainline_continuity_score") or 0.0)
        event_continuity_score = float(evidence.get("event_continuity_score") or 0.0)
        net_inflow_days_5d = int(evidence.get("net_inflow_days_5d") or 0)
        net_inflow_sum_5d = float(evidence.get("net_inflow_sum_5d") or 0.0)
        board_boom_days_5d = int(evidence.get("board_boom_days_5d") or 0)
        limit_up_count = int(evidence.get("limit_up_count") or 0)
        active_days_10d = int(evidence.get("active_days_10d") or 0)
        v2_final_mainline_alive = bool(evidence.get("v2_final_mainline_alive") or False)
        v2_final_cycle_state = str(evidence.get("v2_final_cycle_state") or "").lower()
        v2_fade_confirmed = bool(evidence.get("v2_fade_confirmed") or False)
        v2_alive_days_3d = int(evidence.get("v2_alive_days_3d") or 0)
        v2_div_repair_alive_days_3d = int(evidence.get("v2_div_repair_alive_days_3d") or 0)
        kline_support_hold = bool(evidence.get("kline_support_hold") or False)
        v2_borderline_alive = bool(
            v2_final_mainline_alive
            and v2_final_cycle_state in {"divergence", "repair", "分歧", "修复"}
            and (
                v2_div_repair_alive_days_3d >= 2
                or (v2_div_repair_alive_days_3d >= 1 and active_days_10d >= 3)
            )
            and (not v2_fade_confirmed)
            and kline_support_hold
        )
        borderline_llm_review = bool(
            (not d.rule_is_main_theme)
            and (not one_day_tour_flag)
            and (
                (heat_latest >= 55.0 or avg_heat_5d >= 52.0)
                or v2_borderline_alive
            )
            and (
                mainline_continuity_score >= 58.0
                or v2_borderline_alive
            )
            and (
                event_continuity_score >= 14.0
                or v2_borderline_alive
            )
            and (
                net_inflow_days_5d >= 1
                or mainline_continuity_score >= 80.0
                or (limit_up_count >= 3 and mainline_continuity_score >= 60.0)
                or v2_borderline_alive
            )
            and (limit_up_count >= 1 or board_boom_days_5d >= 1 or active_days_10d >= 2)
            and (not v2_fade_confirmed)
            and (not v2_final_mainline_alive or v2_final_cycle_state in {"divergence", "repair", "分歧", "修复"})
        )
        # 非预检通过且非边界样本，不调用LLM，直接否决。
        if not d.rule_is_main_theme and not borderline_llm_review:
            d.llm_applied = False
            d.llm_is_main_theme = False
            d.llm_confidence = 100
            d.llm_reasons = ["market_gate_failed_or_logic_precheck_failed"]
            d.llm_risk_flags = []
            d.llm_model = model_name
            d.is_main_theme = False
            d.identity_status = "observed"
            continue
        if borderline_llm_review and v2_borderline_alive:
            evidence["borderline_llm_review_by_v2_streak"] = True
            evidence["v2_alive_streak_support_hold"] = {
                "v2_alive_days_3d": v2_alive_days_3d,
                "v2_div_repair_alive_days_3d": v2_div_repair_alive_days_3d,
                "kline_support_hold": kline_support_hold,
            }
        try:
            prompt = _build_llm_prompt(trade_date, d)
            raw = await _call_llm_review(
                prompt=prompt,
                api_key=api_key,
                api_base=api_base,
                model_name=model_name,
                timeout_seconds=timeout_seconds,
            )
            d.llm_applied = True
            llm_final = raw.get("is_main_theme_core_llm", None)
            if llm_final is None:
                logic_llm = bool(raw.get("logic_dimension_ok_llm", False))
                market_llm = bool(raw.get("market_dimension_ok_llm", False))
                llm_final = bool(logic_llm and market_llm)
            d.llm_is_main_theme = bool(llm_final)
            d.llm_confidence = int(raw.get("confidence", 0))
            reasons = raw.get("reasons", [])
            risk_flags = raw.get("risk_flags", [])
            d.llm_reasons = [str(x).strip() for x in reasons] if isinstance(reasons, list) else []
            d.llm_risk_flags = [str(x).strip() for x in risk_flags] if isinstance(risk_flags, list) else []
            d.llm_model = model_name
            if borderline_llm_review and "borderline_llm_review" not in d.llm_reasons:
                d.llm_reasons.append("borderline_llm_review")
        except Exception as exc:
            if require_llm:
                raise RuntimeError(
                    f"mainline_identity_llm_required_call_failed:subject={d.subject_key}:error={str(exc)}"
                ) from exc
            d.llm_applied = False
            d.llm_is_main_theme = False
            d.llm_confidence = 0
            d.llm_reasons = [f"llm_error:{str(exc)}"]
            d.llm_risk_flags = ["llm_call_failed"]
            d.llm_model = model_name
        if d.rule_is_main_theme:
            d.is_main_theme = bool(d.llm_is_main_theme)
        else:
            # 边界纠偏只在“非一日游 + 连续性/热度/资金均达标”时允许升级主线。
            d.is_main_theme = bool(
                borderline_llm_review
                and d.llm_is_main_theme
                and (not one_day_tour_flag)
                and mainline_continuity_score >= 60.0
                and (net_inflow_days_5d >= 2 or (net_inflow_days_5d >= 1 and active_days_10d >= 2))
            )
        hard_gate_ok = bool(
            d.rule_is_main_theme
            and d.llm_applied
            and (d.llm_is_main_theme is True)
        )
        if not hard_gate_ok:
            d.is_main_theme = False
            if "hard_gate_rule_and_llm_required" not in d.llm_risk_flags:
                d.llm_risk_flags.append("hard_gate_rule_and_llm_required")
            evidence["hard_gate_blocked"] = True
        d.identity_status = "confirmed" if d.is_main_theme else "observed"
    if require_llm and rule_pass_decisions:
        applied_count = sum(1 for d in rule_pass_decisions if d.llm_applied)
        if applied_count == 0:
            raise RuntimeError("mainline_identity_llm_required_but_no_successful_reviews")


async def _upsert_decisions(
    conn: asyncpg.Connection,
    trade_date: date,
    decisions: List[IdentityDecision],
    *,
    allow_historical_overwrite: bool = False,
    allow_unsafe_demotion: bool = False,
) -> None:
    sql = """
    INSERT INTO theme_mainline_identity_registry (
        subject_key, theme_name, is_main_theme, identity_status,
        first_seen_date, first_confirmed_date, last_review_date, source_trade_date,
        logic_score, market_score, composite_score, evidence_json,
        rule_is_main_theme, llm_applied, llm_is_main_theme, llm_confidence,
        llm_reasons, llm_risk_flags, llm_model, llm_reviewed_at, rule_version
    ) VALUES (
        $1, $2, $3, $4,
        $5, $6, $7, $8,
        $9, $10, $11, $12::jsonb,
        $13, $14, $15, $16,
        $17::jsonb, $18::jsonb, $19, $20, $21
    )
    ON CONFLICT (subject_key) DO UPDATE SET
        theme_name = EXCLUDED.theme_name,
        is_main_theme = EXCLUDED.is_main_theme,
        identity_status = EXCLUDED.identity_status,
        first_confirmed_date = CASE
            WHEN theme_mainline_identity_registry.first_confirmed_date IS NULL AND EXCLUDED.is_main_theme
            THEN EXCLUDED.first_confirmed_date
            ELSE theme_mainline_identity_registry.first_confirmed_date
        END,
        last_review_date = EXCLUDED.last_review_date,
        source_trade_date = EXCLUDED.source_trade_date,
        logic_score = EXCLUDED.logic_score,
        market_score = EXCLUDED.market_score,
        composite_score = EXCLUDED.composite_score,
        evidence_json = EXCLUDED.evidence_json,
        rule_is_main_theme = EXCLUDED.rule_is_main_theme,
        llm_applied = EXCLUDED.llm_applied,
        llm_is_main_theme = EXCLUDED.llm_is_main_theme,
        llm_confidence = EXCLUDED.llm_confidence,
        llm_reasons = EXCLUDED.llm_reasons,
        llm_risk_flags = EXCLUDED.llm_risk_flags,
        llm_model = EXCLUDED.llm_model,
        llm_reviewed_at = EXCLUDED.llm_reviewed_at,
        rule_version = EXCLUDED.rule_version,
        updated_at = NOW()
    WHERE (
            EXCLUDED.last_review_date >= COALESCE(theme_mainline_identity_registry.last_review_date, DATE '1900-01-01')
            OR $22::boolean = TRUE
    )
      AND (
            $23::boolean = TRUE
            OR NOT (
                COALESCE(theme_mainline_identity_registry.is_main_theme, FALSE) = TRUE
                AND COALESCE(NULLIF(LOWER(theme_mainline_identity_registry.identity_status), ''), 'observed') = 'confirmed'
                AND COALESCE(EXCLUDED.is_main_theme, FALSE) = FALSE
                AND COALESCE(EXCLUDED.llm_applied, FALSE) = FALSE
            )
    )
    """
    payload = []
    for d in decisions:
        payload.append(
            (
                d.subject_key,
                d.theme_name,
                d.is_main_theme,
                d.identity_status,
                trade_date,
                d.source_trade_date if d.is_main_theme else None,
                trade_date,
                d.source_trade_date,
                d.logic_score,
                d.market_score,
                d.composite_score,
                json.dumps(d.evidence, ensure_ascii=False),
                d.rule_is_main_theme,
                d.llm_applied,
                d.llm_is_main_theme,
                d.llm_confidence,
                json.dumps(d.llm_reasons, ensure_ascii=False),
                json.dumps(d.llm_risk_flags, ensure_ascii=False),
                d.llm_model,
                datetime.now(),
                (
                    MANUAL_OVERRIDE_RULE_VERSION
                    if d.is_main_theme and bool(d.evidence.get("manual_override_mainline"))
                    else (
                        CLUSTER_BOOTSTRAP_RULE_VERSION
                        if d.is_main_theme and bool(d.evidence.get("cluster_bootstrap_direct_confirm"))
                        else (
                        CLUSTER_COMP_RULE_VERSION
                        if d.is_main_theme and bool(d.evidence.get("cluster_compensation_mainline"))
                        else (
                            UPGRADE_TRIGGER_RULE_VERSION
                            if bool(d.evidence.get("upgrade_trigger_review_pending"))
                            else (LLM_RULE_VERSION if d.llm_applied else RULE_VERSION)
                        )
                        )
                    )
                ),
                bool(allow_historical_overwrite),
                bool(allow_unsafe_demotion),
            )
        )
    if payload:
        await conn.executemany(sql, payload)


async def _apply_lifecycle_downgrade(
    conn: asyncpg.Connection,
    trade_date: date,
    deactivate_fade_days: int,
) -> int:
    window = max(int(deactivate_fade_days), 1)
    sql = """
    WITH latest AS (
        SELECT
            v2.subject_key,
            v2.fade_confirmed,
            ROW_NUMBER() OVER (
                PARTITION BY v2.subject_key
                ORDER BY v2.trade_date DESC
            ) AS rn
        FROM theme_cycle_judgement_v2 v2
        JOIN theme_mainline_identity_registry mr
          ON mr.subject_key = v2.subject_key
        WHERE v2.trade_date <= $1::date
          AND mr.identity_status = 'confirmed'
    ),
    agg AS (
        SELECT
            subject_key,
            COUNT(*) AS sampled_days,
            COUNT(*) FILTER (WHERE fade_confirmed) AS fade_days
        FROM latest
        WHERE rn <= $2::int
        GROUP BY subject_key
    ),
    to_deactivate AS (
        SELECT subject_key
        FROM agg
        WHERE sampled_days = $2::int
          AND fade_days = $2::int
    )
    UPDATE theme_mainline_identity_registry mr
    SET
        is_main_theme = FALSE,
        identity_status = 'inactive',
        last_review_date = $1::date,
        evidence_json = COALESCE(mr.evidence_json, '{}'::jsonb) || jsonb_build_object(
            'lifecycle',
            jsonb_build_object(
                'deactivated_on', $1::text,
                'reason', 'consecutive_fade_confirmed',
                'window_days', $2::int
            )
        ),
        updated_at = NOW()
    WHERE mr.subject_key IN (SELECT subject_key FROM to_deactivate)
      AND mr.identity_status = 'confirmed'
    """
    tag = await conn.execute(sql, trade_date, window)
    return int(tag.split()[-1])


async def main_async() -> int:
    args = parse_args()
    trade_date = _parse_date(args.trade_date)
    if args.cluster_bootstrap_direct_confirm and not str(args.subject_keys_file or "").strip():
        raise ValueError(
            "--cluster-bootstrap-direct-confirm 仅允许配合 --subject-keys-file 使用，"
            "禁止在全量热点宇宙任务中启用。"
        )
    require_llm = (not args.disable_llm) and (not args.allow_llm_fallback)
    conn = await _connect()
    try:
        await ensure_table(conn)
        subject_keys_override = _load_subject_keys_file(args.subject_keys_file)
        only_new = args.mode == "incremental" and not args.review_existing
        if subject_keys_override:
            hot_rows = [{"subject_key": key} for key in subject_keys_override]
            source_mode = "subject_keys_file"
        else:
            hot_rows = await _fetch_hot_subjects(
                conn,
                trade_date=trade_date,
                lookback_days=int(args.lookback_days),
                universe_size=int(args.universe_size),
                only_new=only_new,
            )
            cluster_subject_keys = await _fetch_cluster_subjects_for_review(
                conn,
                trade_date=trade_date,
                lookback_days=int(args.lookback_days),
            )
            if cluster_subject_keys:
                existing = {str(r["subject_key"]) for r in hot_rows}
                appended = 0
                for key in cluster_subject_keys:
                    if key in existing:
                        continue
                    hot_rows.append({"subject_key": key})
                    existing.add(key)
                    appended += 1
                if appended > 0:
                    print(f"[OK] cluster_subjects_appended={appended}")
            source_mode = "hot_universe"

        decisions: List[IdentityDecision] = []
        skipped = 0
        for hot in hot_rows:
            srow = await _fetch_latest_mainline_scores(conn, str(hot["subject_key"]), trade_date)
            if not srow:
                skipped += 1
                continue
            decisions.append(_decide_identity(srow))
        compensation_candidates = sum(1 for d in decisions if bool(d.evidence.get("jyhf_hot_mainline_flag")))
        cluster_comp_count = _apply_cluster_compensation(decisions)
        await _apply_llm_review(
            decisions,
            trade_date=trade_date,
            enable_llm=not args.disable_llm,
            require_llm=require_llm,
            timeout_seconds=int(args.llm_timeout_seconds),
        )
        manual_override_count = _apply_manual_mainline_overrides(decisions)
        cluster_bootstrap_count = _apply_cluster_bootstrap_direct_confirm(
            decisions,
            enabled=bool(args.cluster_bootstrap_direct_confirm),
        )
        upgrade_stats = await _apply_upgrade_trigger(conn, decisions, trade_date)
        review_queue_upserted = await _upsert_review_queue(conn, decisions, trade_date)

        await _upsert_decisions(
            conn,
            trade_date,
            decisions,
            allow_historical_overwrite=bool(args.allow_historical_overwrite),
            allow_unsafe_demotion=bool(args.allow_unsafe_demotion),
        )
        deactivated = await _apply_lifecycle_downgrade(
            conn,
            trade_date=trade_date,
            deactivate_fade_days=int(args.deactivate_fade_days),
        )

        confirmed = [x for x in decisions if x.is_main_theme]
        observed = [x for x in decisions if not x.is_main_theme]
        llm_applied_count = sum(1 for x in decisions if x.llm_applied)
        llm_yes_count = sum(1 for x in decisions if x.llm_is_main_theme is True)
        ranked = sorted(decisions, key=lambda x: (-x.composite_score, x.subject_key))

        print(f"[OK] trade_date={trade_date.isoformat()} mode={args.mode} source={source_mode}")
        print(
            "[OK] write_guards "
            f"allow_historical_overwrite={bool(args.allow_historical_overwrite)} "
            f"allow_unsafe_demotion={bool(args.allow_unsafe_demotion)}"
        )
        if subject_keys_override:
            print(f"[OK] subject_keys_file={Path(args.subject_keys_file).expanduser().resolve()} count={len(subject_keys_override)}")
        print(f"[OK] scanned={len(hot_rows)} decided={len(decisions)} skipped_no_scores={skipped}")
        print(
            f"[OK] llm_applied={llm_applied_count} llm_yes={llm_yes_count} "
            f"llm_enabled={not args.disable_llm} llm_required={require_llm}"
        )
        print(f"[OK] compensation_candidates_active10d_gte4={compensation_candidates}")
        print(f"[OK] manual_overrides={manual_override_count}")
        print(f"[OK] cluster_compensations={cluster_comp_count}")
        print(f"[OK] cluster_bootstrap_direct_confirms={cluster_bootstrap_count}")
        print(
            "[OK] upgrade_candidates={0} upgrade_review_pending={1}".format(
                int(upgrade_stats.get("candidate_count") or 0),
                int(upgrade_stats.get("review_pending_count") or 0),
            )
        )
        print(f"[OK] review_queue_upserted={review_queue_upserted}")
        print(f"[OK] confirmed={len(confirmed)} observed={len(observed)}")
        print(f"[OK] lifecycle_deactivated={deactivated}")
        for item in ranked[: int(args.top_k)]:
            print(
                f"[ROW] status={item.identity_status:<9} subject={item.subject_key} theme={item.theme_name[:24]:<24} "
                f"logic={item.logic_score:6.2f} market={item.market_score:6.2f} composite={item.composite_score:6.2f}"
            )
    finally:
        await conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main_async()))
