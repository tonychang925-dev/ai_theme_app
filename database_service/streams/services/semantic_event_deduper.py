"""通用语义去重器 — batch 内跨源去重 + 跨周期 recent cache + Qwen 灰区判定。

从 AkShareRealtimeNewsCollector._cross_source_dedup() 抽出，改进：
  - 候选检索更宽（title[:15] bucketing + 实体/股票代码 + token overlap）
  - 人物/公司硬保护（不同人物或不同公司 → 强制 distinct）
  - Qwen 预算保护（每轮 ≤20 次调用）
  - Keeper 综合评分（优先级 + 正文长度 + URL + 时间）
  - Audit JSONL 持续输出
  - 跨周期 recent cache（内存，后续迁 Redis）

Phase 4E (2026-05-24).
"""
from __future__ import annotations

import asyncio
import difflib
import hashlib
import json as _json
import logging
import os
import re as _regex
import time as _time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import jieba

from database_service.streams.services.news_prefilter_adapter import NewsPreFilterAdapter

logger = logging.getLogger(__name__)

TZ_CN = timezone(timedelta(hours=8))

# ── 已知人物名单 ──────────────────────────────────────────────────

KNOWN_PERSONS: set[str] = {
    "习近平", "李强", "赵乐际", "王沪宁", "蔡奇", "丁薛祥",
    "李希", "韩正", "刘鹤", "孙春兰", "胡春华", "刘国中",
    "何立峰", "张国清", "吴政隆", "谌贻琴", "郭声琨", "黄坤明",
    "王毅", "秦刚", "陈吉宁", "李鸿忠", "魏凤和", "李作成",
    "苗华", "张又侠", "何卫东", "郑栅洁", "蓝佛安", "王文涛",
    "易纲", "潘功胜", "吴清", "易会满", "李云泽",
}

# ── Source priority ───────────────────────────────────────────────

DEFAULT_SOURCE_PRIORITY: dict[str, int] = {
    "cls": 100,
    "akshare_cls": 95,
    "akshare_em": 80,
    "akshare_futu": 70,
    "akshare_ths": 60,
    "akshare_sina": 50,
    "akshare_cctv": 40,
    "db_collector": 60,
}


# ── Helpers ────────────────────────────────────────────────────────

def _pick(row: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        value = row.get(key)
        if value is not None and str(value).strip() != "":
            return value
    return None


def _norm_title(title: str, keep: int = 15) -> str:
    """宽松标准化，取前 keep 个非标点字符。"""
    return _regex.sub(r'[^\w]', '', str(title)[:30]).lower()[:keep]


def _extract_stock_codes(title: str) -> set[str]:
    """提取 A 股 6 位股票代码。"""
    return set(_regex.findall(r'[036]\d{5}', str(title)))


def _extract_persons(title: str) -> set[str]:
    """从标题中提取已知人物名。"""
    return {p for p in KNOWN_PERSONS if p in str(title)}


def _extract_company_alias(title: str) -> set[str]:
    """从标题抽取公司简称（无股票代码时的 fallback）。

    规则：
      XXX： / 【XXX： / 【XXX】 / XXX公告 / XXX称
      XXX发布/宣布/表示/披露/回应/拟/将
      排除过短（<2）和过长（>10），排除纯数字，排除常见停用词。
    """
    _STOP_ALIAS: frozenset[str] = frozenset({
        "发布", "宣布", "公告", "表示", "披露", "回应", "最新", "拟将",
        "市场", "公司", "集团", "股份", "有限", "今日", "昨日", "本周",
    })
    found: set[str] = set()
    for pat in (
        r'【?([^】\s：:]+)[】：:]',
        r'([^\s]+)公告',
        r'([^\s]+)称',
        r'([^\s]{2,8}?)(?:发布|宣布|表示|披露|回应|拟将|拟|将)',
    ):
        for m in _regex.finditer(pat, str(title)):
            name = m.group(1).strip().rstrip('】').rstrip('【')
            if (
                2 <= len(name) <= 10
                and not _regex.search(r'\d{4}', name)
                and name not in _STOP_ALIAS
            ):
                found.add(name)
    return found


# ── jieba entity token extraction (Phase 4E fix) ────────────────────

# Tokens to exclude from entity buckets
_JIEBA_STOP_TOKENS: frozenset[str] = frozenset({
    "发布", "宣布", "公告", "表示", "披露", "回应", "最新", "拟将",
    "市场", "公司", "集团", "股份", "有限", "今日", "昨日", "本周",
    "近日", "显示", "企查查", "法定", "代表人", "经营范围", "包括",
    "成立", "销售", "服务", "相关", "数据", "消息", "新闻",
    "投资", "亿元", "万元", "APP", "简称",
})


def _extract_entity_tokens(title: str) -> set[str]:
    """使用 jieba 分词从标题中提取潜在实体关键词（2-6字）。

    作为 _extract_company_alias 的兜底，解决实体名嵌入长句时 regex 无法提取的问题。
    例如："企查查APP显示，近日，许昌市胖东来乐予文化娱乐有限公司成立..."
     →  jieba 可提取出 {"胖东来", "许昌市", "于龙飞"} 等实体词。
    """
    tokens: set[str] = set()
    try:
        words = jieba.lcut(str(title))
    except Exception:
        return tokens
    for w in words:
        w = w.strip()
        if (
            2 <= len(w) <= 6
            and not _regex.search(r'\d', w)
            and w not in _JIEBA_STOP_TOKENS
            and not w.startswith(("APP", ">", "<", "http"))
        ):
            tokens.add(w)
    return tokens


def _token_overlap(title_a: str, title_b: str) -> int:
    """字符 bigram 交集计数。"""
    if not title_a or not title_b:
        return 0
    bigrams_a = {title_a[i:i+2] for i in range(len(title_a) - 1)}
    bigrams_b = {title_b[i:i+2] for i in range(len(title_b) - 1)}
    return len(bigrams_a & bigrams_b)


# ── Audit ──────────────────────────────────────────────────────────

def _write_audit_line(audit_path: Path, record: dict[str, Any]) -> None:
    """追加一行 JSONL 到 audit 文件。"""
    try:
        audit_path.parent.mkdir(parents=True, exist_ok=True)
        with open(audit_path, "a", encoding="utf-8") as f:
            f.write(_json.dumps(record, ensure_ascii=False) + "\n")
    except Exception:
        pass  # audit 不可用不影响主链路


# ═══════════════════════════════════════════════════════════════════
# 主类
# ═══════════════════════════════════════════════════════════════════

class SemanticEventDeduper:
    """通用语义去重器。

    用法:
        deduper = SemanticEventDeduper(
            prefilter=prefilter_adapter,
            audit_dir="tmp/...",
        )
        await deduper.warmup()
        rows = await deduper.dedup_batch(rows)
        rows = await deduper.dedup_against_recent(rows)
        # ... publish ...
        for row in published:
            deduper.add_to_recent(row)
    """

    def __init__(
        self,
        *,
        prefilter: NewsPreFilterAdapter,
        recent_max_size: int = 500,
        recent_max_age_hours: int = 6,
        qwen_max_per_round: int = 20,
        qwen_max_candidates_per_news: int = 5,
        qwen_max_recent_comparisons: int = 50,
        audit_dir: str | Path | None = None,
        source_priority: dict[str, int] | None = None,
    ):
        self._prefilter = prefilter
        self._recent_max_size = max(1, int(recent_max_size))
        self._recent_max_age = timedelta(hours=max(1, int(recent_max_age_hours)))
        self._qwen_max_per_round = max(1, int(qwen_max_per_round))
        self._qwen_max_candidates = max(1, int(qwen_max_candidates_per_news))
        self._qwen_max_recent = max(1, int(qwen_max_recent_comparisons))
        self._source_priority = source_priority or DEFAULT_SOURCE_PRIORITY

        # batch 内 Qwen 预算（每轮 reset）
        self._qwen_this_round = 0

        # 跨周期内存 cache
        self._recent_titles: list[dict[str, Any]] = []

        # audit
        self._audit_path: Path | None = None
        if audit_dir:
            self._audit_path = Path(audit_dir) / "semantic_dedupe_audit.jsonl"

        # stats
        self.stats: dict[str, Any] = {
            "semantic_dedup_batch_count": 0,
            "semantic_dedup_recent_count": 0,
            "qwen_dedup_call_count": 0,
            "qwen_dedup_ready": False,
            "qwen_dedup_unavailable_count": 0,
            "qwen_dedup_budget_exhausted": 0,
            "hard_protect_count": 0,
            "hard_protect_by": {},
        }

    # ── 公开方法 ─────────────────────────────────────────────────

    async def warmup(self) -> bool:
        """异步预热 Qwen 模型，不阻塞 event loop。"""
        try:
            ready = await asyncio.to_thread(self._prefilter.preload_model)
            self.stats["qwen_dedup_ready"] = ready
            logger.info("qwen_dedup_ready=%s", ready)
            return ready
        except Exception as exc:
            self.stats["qwen_dedup_ready"] = False
            logger.warning("qwen_dedup_ready=false error=%s", exc)
            return False

    def new_round(self) -> None:
        """每轮采集前调用，重置 Qwen 预算。"""
        self._qwen_this_round = 0

    async def dedup_batch(self, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """batch 内跨源语义去重。

        改进版候选检索 + 硬保护 + 3-tier 判定 + keeper 综合评分。
        """
        if len(rows) <= 1:
            return rows

        # 1. 分桶 (loose + entity)
        buckets: dict[str, list[int]] = {}

        for i, row in enumerate(rows):
            title = str(_pick(row, "title", "新闻标题", "标题") or "")
            # loose bucket: first 15 normalized chars
            loose = _norm_title(title, keep=15)
            buckets.setdefault(f"L:{loose}", []).append(i)
            # entity buckets: stock codes
            for code in _extract_stock_codes(title):
                buckets.setdefault(f"S:{code}", []).append(i)
            # entity buckets: company aliases (Phase 4E fix — broad entity catch)
            for comp in _extract_company_alias(title):
                buckets.setdefault(f"C:{comp}", []).append(i)
            # entity buckets: jieba token fallback (Phase 4E fix — embedded entity catch)
            for token in _extract_entity_tokens(title):
                buckets.setdefault(f"E:{token}", []).append(i)

        # 2. 收集所有候选对 + 判定
        dup_pairs: list[tuple[int, int]] = []  # (keeper_idx, dropped_idx)
        seen_pairs: set[tuple[int, int]] = set()

        for indices in buckets.values():
            if len(indices) < 2:
                continue
            for a in range(len(indices)):
                ia = indices[a]
                title_a = str(_pick(rows[ia], "title", "新闻标题", "标题") or "")
                for b in range(a + 1, len(indices)):
                    ib = indices[b]
                    pair = (min(ia, ib), max(ia, ib))
                    if pair in seen_pairs:
                        continue
                    seen_pairs.add(pair)

                    title_b = str(_pick(rows[ib], "title", "新闻标题", "标题") or "")
                    if not title_a or not title_b:
                        continue

                    dup_result = await self._judge_pair(title_a, title_b, rows[ia], rows[ib])
                    if dup_result["is_dup"]:
                        if dup_result["keeper_idx"] == ia:
                            dup_pairs.append((ia, ib))
                        else:
                            dup_pairs.append((ib, ia))

        # 3. 去重
        if dup_pairs:
            dropped = {d for _, d in dup_pairs}
            self.stats["semantic_dedup_batch_count"] += len(dropped)
            logger.info(
                "SemanticDeduper: batch dedup — %d pairs merged, dropping %d rows (%.0f%%)",
                len(dup_pairs), len(dropped),
                len(dropped) / max(len(rows), 1) * 100,
            )
            rows = [r for i, r in enumerate(rows) if i not in dropped]

        return rows

    async def dedup_against_recent(self, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """跨周期去重 — 与 recent cache 比较。

        最多检查 qwen_max_recent_comparisons 条 recent。
        """
        if not rows or not self._recent_titles:
            return rows

        self._evict_stale_recent()
        recent_snapshot = self._recent_titles[:self._qwen_max_recent]

        kept: list[dict[str, Any]] = []
        for row in rows:
            title = str(_pick(row, "title", "新闻标题", "标题") or "")
            if not title:
                kept.append(row)
                continue

            is_dup = False
            # 每条新闻最多与 top N 条 recent 比较
            checked = 0
            for rc in recent_snapshot:
                if checked >= self._qwen_max_candidates:
                    break
                rc_title = str(rc.get("title", ""))
                if not rc_title:
                    continue

                # 快速 ratio 预筛
                ratio = difflib.SequenceMatcher(None, title, rc_title).ratio()
                if ratio < 0.45:
                    continue
                checked += 1

                dup_result = await self._judge_pair(
                    title, rc_title,
                    row, rc,
                    action="recent",
                )
                if dup_result["is_dup"]:
                    is_dup = True
                    break

            if is_dup:
                self.stats["semantic_dedup_recent_count"] += 1
                logger.debug("SemanticDeduper: recent dedup suppressed — title=%s...", title[:40])
            else:
                kept.append(row)

        return kept

    def add_to_recent(self, row: dict[str, Any]) -> None:
        """发布成功后写入 recent cache。"""
        title = str(_pick(row, "title", "新闻标题", "标题") or "")
        if not title:
            return

        self._recent_titles.insert(0, {
            "title": title,
            "source": str(row.get("source", "")),
            "source_channel": str(row.get("source_channel", "")),
            "news_id": str(row.get("news_id", "")),
            "seen_at": _time.time(),
        })

        # 超量裁剪
        if len(self._recent_titles) > self._recent_max_size:
            self._recent_titles = self._recent_titles[:self._recent_max_size]

    def get_stats(self) -> dict[str, Any]:
        s = dict(self.stats)
        s["recent_cache_size"] = len(self._recent_titles)
        return s

    # ── 内部方法 ─────────────────────────────────────────────────

    async def _judge_pair(
        self,
        title_a: str,
        title_b: str,
        row_a: dict[str, Any] | None = None,
        row_b: dict[str, Any] | None = None,
        *,
        action: str = "batch",
    ) -> dict[str, Any]:
        """判定一对新闻是否重复。

        Returns:
            dict with is_dup, keeper_idx, method, hard_protect_reason, ratio
        """
        row_a = row_a or {}
        row_b = row_b or {}
        result: dict[str, Any] = {
            "is_dup": False,
            "keeper_idx": 0,
            "method": "",
            "hard_protect_reason": "",
            "ratio": 0.0,
        }

        # ── 硬保护：人物 / 公司冲突 ──
        hp_reason = self._hard_protect(title_a, title_b)
        if hp_reason:
            result["hard_protect_reason"] = hp_reason
            result["method"] = "hard_protect"
            result["is_dup"] = False
            self.stats["hard_protect_count"] += 1
            self.stats["hard_protect_by"][hp_reason] = self.stats["hard_protect_by"].get(hp_reason, 0) + 1
            self._write_audit(title_a, title_b, 0.0, "hard_protect", "distinct", action, row_a, row_b, hp_reason)
            return result

        # ── ratio 计算 ──
        ratio = difflib.SequenceMatcher(None, title_a, title_b).ratio()
        result["ratio"] = ratio

        # ── candidate filter ──
        if not self._is_candidate(title_a, title_b, row_a, row_b, ratio):
            return result

        # ── ratio > 0.85 → 自动判重 ──
        if ratio > 0.85:
            result["is_dup"] = True
            result["method"] = "ratio"
            result["keeper_idx"] = self._select_keeper(row_a, row_b, 0, 1)
            self._write_audit(title_a, title_b, ratio, "ratio", "dup", action, row_a, row_b)
            return result

        # ── Qwen warmup 未完成保护 ──
        if not self.stats.get("qwen_dedup_ready"):
            # warmup 未完成时不调 Qwen，避免首次调用触发同步模型加载
            if ratio > 0.75:
                result["is_dup"] = True
                result["method"] = "conservative_warmup"
                result["keeper_idx"] = self._select_keeper(row_a, row_b, 0, 1)
                self._write_audit(title_a, title_b, ratio, "conservative_warmup", "dup", action, row_a, row_b)
            else:
                self._write_audit(title_a, title_b, ratio, "warmup_not_ready", "distinct", action, row_a, row_b)
            return result

        # ── Qwen 预算检查 ──
        if self._qwen_this_round >= self._qwen_max_per_round:
            self.stats["qwen_dedup_budget_exhausted"] += 1
            result["method"] = "budget_exhausted"
            # 超预算后只做 ratio > 0.85 自动去重，其余保留
            self._write_audit(title_a, title_b, ratio, "budget_exhausted", "distinct", action, row_a, row_b)
            return result

        # ── 灰区：0.5 < ratio <= 0.85 → Qwen ──
        if 0.5 < ratio <= 0.85:
            try:
                qwen_result = await asyncio.to_thread(
                    self._prefilter.check_semantic_duplicate, title_a, title_b
                )
                self._qwen_this_round += 1
                self.stats["qwen_dedup_call_count"] += 1

                if qwen_result is True:
                    result["is_dup"] = True
                    result["method"] = "qwen"
                    result["keeper_idx"] = self._select_keeper(row_a, row_b, 0, 1)
                    self._write_audit(title_a, title_b, ratio, "qwen", "dup", action, row_a, row_b)
                    return result
                elif qwen_result is None:
                    # Qwen 不可用
                    self.stats["qwen_dedup_unavailable_count"] += 1
                    if ratio > 0.75:
                        result["is_dup"] = True
                        result["method"] = "conservative"
                        result["keeper_idx"] = self._select_keeper(row_a, row_b, 0, 1)
                        self._write_audit(title_a, title_b, ratio, "conservative", "dup", action, row_a, row_b)
                        return result

                # Qwen said False → distinct
                self._write_audit(title_a, title_b, ratio, "qwen", "distinct", action, row_a, row_b)
                return result

            except Exception:
                self.stats["qwen_dedup_unavailable_count"] += 1
                self._qwen_this_round += 1
                if ratio > 0.75:
                    result["is_dup"] = True
                    result["method"] = "conservative"
                    result["keeper_idx"] = self._select_keeper(row_a, row_b, 0, 1)
                    self._write_audit(title_a, title_b, ratio, "conservative", "dup", action, row_a, row_b)
                return result

        # ratio <= 0.5 → distinct
        return result

    def _is_candidate(
        self,
        title_a: str,
        title_b: str,
        row_a: dict[str, Any],
        row_b: dict[str, Any],
        ratio: float,
    ) -> bool:
        """三条件候选：实体重合 OR token overlap>=2 OR ratio>0.45"""
        if ratio > 0.45:
            return True
        if _token_overlap(title_a, title_b) >= 2:
            return True
        stocks_a = _extract_stock_codes(title_a)
        stocks_b = _extract_stock_codes(title_b)
        if stocks_a and stocks_b and stocks_a & stocks_b:
            return True
        comps_a = _extract_company_alias(title_a)
        comps_b = _extract_company_alias(title_b)
        if comps_a and comps_b and comps_a & comps_b:
            return True
        return False

    def _hard_protect(self, title_a: str, title_b: str) -> str | None:
        """人物/公司冲突硬保护。

        返回 distinct 原因，或 None 表示需要继续判定。
        """
        persons_a = _extract_persons(title_a)
        persons_b = _extract_persons(title_b)
        stocks_a = _extract_stock_codes(title_a)
        stocks_b = _extract_stock_codes(title_b)
        companies_a = _extract_company_alias(title_a)
        companies_b = _extract_company_alias(title_b)

        # 不同人物 + 无共同股票 + 无共同公司 → distinct
        if persons_a and persons_b and persons_a != persons_b:
            if not (stocks_a & stocks_b) and not (companies_a & companies_b):
                return "hard_protect:different_persons"

        # 不同公司 + 无共同股票 + 无共同人物 → distinct
        if companies_a and companies_b and companies_a != companies_b:
            if not (stocks_a & stocks_b) and not (persons_a & persons_b):
                return "hard_protect:different_companies"

        return None

    def _select_keeper(
        self,
        row_a: dict[str, Any],
        row_b: dict[str, Any],
        idx_a: int,
        idx_b: int,
    ) -> int:
        """选 Keeper：综合评分高的保留。"""
        score_a = self._keeper_score(row_a)
        score_b = self._keeper_score(row_b)
        return idx_a if score_a >= score_b else idx_b

    def _keeper_score(self, row: dict[str, Any]) -> float:
        """Keeper 综合评分。"""
        ch = str(row.get("source_channel", ""))
        score = float(self._source_priority.get(ch, 0)) * 10
        content_len = len(str(row.get("content", "") or row.get("title", "")))
        score += min(content_len / 200.0, 3.0)
        if row.get("url"):
            score += 1.0
        if row.get("publish_time"):
            score += 1.0
        return score

    def _write_audit(
        self,
        title_a: str,
        title_b: str,
        ratio: float,
        method: str,
        result: str,
        action: str,
        row_a: dict[str, Any],
        row_b: dict[str, Any],
        hard_protect_reason: str = "",
    ) -> None:
        if not self._audit_path:
            return
        record: dict[str, Any] = {
            "ts": datetime.now(TZ_CN).isoformat(),
            "action": action,
            "title_a": str(title_a)[:120],
            "title_b": str(title_b)[:120],
            "ratio": round(ratio, 4),
            "method": method,
            "result": result,
            "keeper_score_a": round(self._keeper_score(row_a), 2) if row_a else 0,
            "keeper_score_b": round(self._keeper_score(row_b), 2) if row_b else 0,
            "source_a": str(row_a.get("source_channel", "") if row_a else ""),
            "source_b": str(row_b.get("source_channel", "") if row_b else ""),
        }
        if hard_protect_reason:
            record["hard_protect_reason"] = hard_protect_reason
        _write_audit_line(self._audit_path, record)

    def _evict_stale_recent(self) -> None:
        """清理过期 recent cache。"""
        cutoff = _time.time() - self._recent_max_age.total_seconds()
        self._recent_titles = [
            r for r in self._recent_titles
            if float(r.get("seen_at", 0)) > cutoff
        ]
