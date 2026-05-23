"""
本地Qwen新闻预筛选服务

目标：在进入大模型事件提取前做轻量分流，减少不必要的LLM调用。
默认优先使用 Qwen2.5-1.5B (GGUF + llama_cpp) 的 prompt 判定。
"""
import hashlib
import json
import logging
import os
import re
from pathlib import Path
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


class LocalQwenNewsTriageService:
    """本地Qwen预筛选（失败自动降级到规则模式）。"""

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        cfg = config or {}
        self.enabled = bool(cfg.get("enable_local_triage", False))
        self.mode = str(cfg.get("triage_mode", "prompt")).strip().lower()  # prompt|embedding|hybrid
        self.pass_threshold = float(cfg.get("triage_pass_threshold", 0.06))
        self.skip_threshold = float(cfg.get("triage_skip_threshold", -0.02))
        self.min_text_len = int(cfg.get("triage_min_text_len", 40))
        self.model_path = str(cfg.get("local_qwen_model_path") or "").strip()
        self.prompt_max_tokens = int(cfg.get("triage_prompt_max_tokens", 420))

        # prompt judge (Qwen1.5B gguf)
        self._prompt_llm = None
        self._prompt_ready = False
        self._prompt_init_attempted = False

        # embedding fallback
        self._matcher = None
        self._ready = False
        self._init_attempted = False
        self._positive_anchor = None
        self._negative_anchor = None

        self._catalyst_keywords = {
            "政策", "预增", "预亏", "并购", "重组", "订单", "中标",
            "财政", "降息", "加息", "关税", "出口", "制裁", "突破技术",
            "新品", "扩产", "投产", "供给短缺", "价格上涨", "技术突破",
        }
        self._concrete_catalyst_keywords = {
            "中标", "签约", "订单", "业绩预告", "并购", "重组", "停牌",
            "复牌", "产能", "投产", "召回", "获批", "批文", "补贴",
            "关税", "出口管制", "降息", "加息", "财政刺激", "重大合同",
        }
        self._generic_move_phrases = {
            "市场分析认为与政策面变化有关",
            "机构分析认为与政策面变化有关",
            "市场分析认为与资金流向有关",
            "机构分析认为与资金流向有关",
            "但后市可期",
            "股价今日上涨",
            "股价回调",
            "股价震荡",
        }

    def evaluate(self, news_data: Dict[str, Any]) -> Dict[str, Any]:
        text = self._build_text(news_data)
        rule_features = self._rule_features(text)

        forced_result = self._rule_prefilter(news_data, text, rule_features)
        if forced_result is not None:
            return forced_result

        if not self.enabled:
            return self._rule_decision(news_data, rule_features, reason_prefix="local_triage_disabled")

        # 1) prompt判定优先
        if self.mode in {"prompt", "hybrid"} and self._ensure_prompt_ready():
            prompt_result = self._prompt_decision(text, rule_features)
            if prompt_result is not None:
                return prompt_result

        # 2) 仅prompt模式下直接回退规则
        if self.mode == "prompt":
            return self._rule_decision(news_data, rule_features, reason_prefix="prompt_unavailable")

        # 3) embedding 回退
        if not self._ensure_qwen_ready():
            return self._rule_decision(news_data, rule_features, reason_prefix="qwen_unavailable")

        try:
            vec = self._matcher._encode_single_direct(text)
            if vec is None:
                return self._rule_decision(news_data, rule_features, reason_prefix="qwen_encode_empty")

            pos = float(self._matcher._cosine_similarity(vec, self._positive_anchor))
            neg = float(self._matcher._cosine_similarity(vec, self._negative_anchor))
            score = pos - neg

            if score >= self.pass_threshold:
                return self._build_result(
                    news_data,
                    decision="PASS",
                    importance_level="B",
                    event_value_type="theme_catalyst",
                    reason_code="embedding_importance_pass",
                    reason=f"embedding_score={score:.4f} >= pass_threshold={self.pass_threshold:.4f}",
                    confidence=min(1.0, max(0.0, score + 0.5)),
                    score=score,
                    mode="local_qwen_embedding",
                    evidence=["embedding_score"],
                )
            if score <= self.skip_threshold and not rule_features["strong_signal"]:
                return self._build_result(
                    news_data,
                    decision="SKIP",
                    importance_level="D",
                    event_value_type="market_noise",
                    reason_code="embedding_importance_skip",
                    reason=f"embedding_score={score:.4f} <= skip_threshold={self.skip_threshold:.4f}",
                    confidence=min(1.0, max(0.0, 0.5 - score)),
                    score=score,
                    mode="local_qwen_embedding",
                    evidence=["embedding_score"],
                )
            return self._build_result(
                news_data,
                decision="REVIEW",
                importance_level="C",
                event_value_type="market_noise",
                reason_code="embedding_importance_review",
                reason=f"embedding_score={score:.4f}, between thresholds",
                confidence=0.5,
                score=score,
                mode="local_qwen_embedding",
                evidence=["embedding_score"],
            )
        except Exception as e:
            logger.warning(f"本地Qwen预筛选异常，降级规则模式: {e}")
            return self._rule_decision(news_data, rule_features, reason_prefix="qwen_exception")

    def _ensure_prompt_ready(self) -> bool:
        if self._prompt_ready:
            return True
        if self._prompt_init_attempted:
            return False
        self._prompt_init_attempted = True

        try:
            from llama_cpp import Llama

            model_path = self._resolve_model_path(prefer_gguf=True)
            if not model_path:
                logger.warning("未找到Qwen1.5B GGUF模型，prompt预筛选不可用")
                return False

            n_gpu_layers = int(os.getenv("LOCAL_QWEN_TRIAGE_GPU_LAYERS", "0"))
            n_threads = int(os.getenv("LOCAL_QWEN_TRIAGE_THREADS", "8"))
            self._prompt_llm = Llama(
                model_path=model_path,
                n_ctx=2048,
                n_threads=n_threads,
                n_gpu_layers=n_gpu_layers,
                verbose=False,
            )
            self._prompt_ready = True
            logger.info(f"✅ 本地Qwen1.5B prompt预筛选已启用: model={model_path}")
            return True
        except Exception as e:
            logger.warning(f"初始化Qwen1.5B prompt预筛选失败: {e}")
            return False

    def _prompt_decision(self, text: str, features: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        try:
            prompt = self._build_prompt(text)
            response = self._prompt_llm(
                prompt,
                max_tokens=self.prompt_max_tokens,
                stop=["\n"],
                echo=False,
                temperature=0.0,
                top_p=0.9,
                top_k=40,
            )
            raw = str(response["choices"][0]["text"]).strip()
            parsed = self._parse_prompt_json(raw)
            if parsed is not None:
                parsed["mode"] = "qwen1.5b_prompt"
                parsed["raw"] = raw
                return self._normalize_result(parsed, fallback_text=text)

            # 非法输出兜底 → 回退规则判定，不阻塞事件
            return None  # 让外层 _rule_decision 接管
        except Exception as e:
            logger.warning(f"Qwen1.5B prompt判定异常: {e}")
            return None

    @staticmethod
    def _build_prompt(text: str) -> str:
        short_text = text[:420]
        return (
            "你是A股盘前新闻重要性预筛选器，只输出严格JSON。\n"
            "目标：只有重要产业/公司/宏观催化进入LLM结构化和题材匹配。\n"
            "默认SKIP：普通财报、回购、减持、澄清、风险提示、连板公告、行政监管措施、监管函、警示函、责令改正、天气灾害、列车停运、普通人事任命、普通IPO。\n"
            "地域词、监管机构所在地、公司行业属性不能构成PASS。重复事件输出DUPLICATE。\n"
            "PASS仅用于明确题材催化、公司重大订单/中标/并购重组、产业政策、技术突破、行业供需价格变化、海外产业链催化。\n"
            "信息有交易价值但证据不足输出REVIEW。\n"
            "C/D级REVIEW不得进入人工复核，只有S/A/B且有明确催化证据的REVIEW才可should_enter_review=true。\n"
            'JSON schema: {"decision":"PASS|REVIEW|SKIP|DUPLICATE","importance_level":"S|A|B|C|D","event_value_type":"theme_catalyst|company_catalyst|macro_policy|sector_supply_demand|major_risk_alert|low_value_disclosure|market_noise|duplicate","should_structurize":true,"should_publish_structured_stream":true,"should_enter_theme_match":true,"should_enter_review":false,"should_enter_premarket_major_events":true,"reason_code":"string","confidence":0.0,"evidence":["最多3条"],"dedupe_key":"规范化事件key"}\n'
            f"新闻：{short_text}\n"
            "输出："
        )

    def _ensure_qwen_ready(self) -> bool:
        if self._ready:
            return True
        if self._init_attempted:
            return False
        self._init_attempted = True

        try:
            from theme_service.matchers.local_qwen_matcher import LocalQwenEmbeddingMatcher

            model_path = self._resolve_model_path(prefer_gguf=False)
            if not model_path:
                logger.warning("未找到本地Qwen embedding模型路径，预筛选降级规则模式")
                return False

            matcher = LocalQwenEmbeddingMatcher(
                {
                    "model_name": model_path,
                    "use_cache": False,
                    "batch_size": 1,
                }
            )
            matcher.initialize([], [])

            self._matcher = matcher
            self._positive_anchor = matcher._encode_single_direct(
                "该新闻与A股交易相关，涉及题材、板块、政策、业绩、资金、涨跌停、个股异动。"
            )
            self._negative_anchor = matcher._encode_single_direct(
                "该内容与证券交易无关，属于泛资讯或噪声，不需要进入题材匹配。"
            )
            if self._positive_anchor is None or self._negative_anchor is None:
                logger.warning("本地Qwen embedding锚点编码失败，预筛选降级规则模式")
                return False

            self._ready = True
            logger.info(f"✅ 本地Qwen embedding预筛选已启用: model={model_path}")
            return True
        except Exception as e:
            logger.warning(f"初始化本地Qwen embedding预筛选失败，降级规则模式: {e}")
            return False

    def _resolve_model_path(self, prefer_gguf: bool) -> Optional[str]:
        candidates = []
        if self.model_path:
            candidates.append(self.model_path)
        env_path = os.getenv("LOCAL_QWEN_TRIAGE_MODEL_PATH", "").strip()
        if env_path:
            candidates.append(env_path)
        candidates.extend(
            [
                "/Users/admin/Desktop/ai_theme_app/model_service/models/qwen2.5/qwen2.5-1.5b-instruct-q5_k_m.gguf",
                "/Users/admin/Desktop/ai_theme_app/models/Qwen2.5-1.5B-Instruct",
                "/Users/admin/Desktop/ai_theme_app/models/Qwen2.5-0.5B-Instruct",
                "/Users/admin/Desktop/ai_theme_app/.qwen_cache/models--Qwen--Qwen2.5-0.5B-Instruct/snapshots/7ae557604adf67be50417f59c2c2f167def9a775",
            ]
        )

        for path_str in candidates:
            path = Path(path_str)
            if not path.exists():
                continue
            if prefer_gguf and not str(path).endswith(".gguf"):
                continue
            if (not prefer_gguf) and str(path).endswith(".gguf"):
                continue
            return str(path)
        return None

    def _build_text(self, news_data: Dict[str, Any]) -> str:
        title = str(news_data.get("title") or "").strip()
        content = str(news_data.get("content") or "").strip()
        return f"{title}\n{content}"[:1200]

    @staticmethod
    def _dedupe_key_from_text(text: str) -> str:
        normalized = re.sub(r"[\W_【】（）()]", "", text.lower())[:240]
        return hashlib.sha1(normalized.encode("utf-8")).hexdigest()[:24] if normalized else ""

    @staticmethod
    def _routing_flags(decision: str, importance_level: str = "C", event_value_type: str = "market_noise") -> Dict[str, bool]:
        should_continue = decision == "PASS"
        should_enter_review = (
            decision == "REVIEW"
            and importance_level in {"S", "A", "B"}
            and event_value_type in {
                "theme_catalyst",
                "company_catalyst",
                "macro_policy",
                "sector_supply_demand",
                "major_risk_alert",
            }
        )
        return {
            "should_structurize": should_continue,
            "should_publish_structured_stream": should_continue,
            "should_enter_theme_match": should_continue,
            "should_enter_review": should_enter_review,
            "should_enter_premarket_major_events": should_continue,
        }

    def _build_result(
        self,
        news_data: Dict[str, Any],
        *,
        decision: str,
        importance_level: str,
        event_value_type: str,
        reason_code: str,
        reason: str,
        confidence: float,
        score: float | None = None,
        mode: str = "rule",
        evidence: list[str] | None = None,
        raw: str | None = None,
    ) -> Dict[str, Any]:
        return self._build_result_from_text(
            self._build_text(news_data),
            decision=decision,
            importance_level=importance_level,
            event_value_type=event_value_type,
            reason_code=reason_code,
            reason=reason,
            confidence=confidence,
            score=score,
            mode=mode,
            evidence=evidence,
            raw=raw,
        )

    def _build_result_from_text(
        self,
        text: str,
        *,
        decision: str,
        importance_level: str,
        event_value_type: str,
        reason_code: str,
        reason: str,
        confidence: float,
        score: float | None = None,
        mode: str = "rule",
        evidence: list[str] | None = None,
        raw: str | None = None,
    ) -> Dict[str, Any]:
        normalized_decision = decision if decision in {"PASS", "REVIEW", "SKIP", "DUPLICATE"} else "REVIEW"
        normalized_importance = importance_level if importance_level in {"S", "A", "B", "C", "D"} else "C"
        result = {
            "decision": normalized_decision,
            "importance_level": normalized_importance,
            "event_value_type": event_value_type,
            **self._routing_flags(normalized_decision, normalized_importance, event_value_type),
            "reason_code": reason_code,
            "reason": reason,
            "confidence": min(1.0, max(0.0, float(confidence))),
            "evidence": list(evidence or [])[:3],
            "dedupe_key": self._dedupe_key_from_text(text),
            "score": score,
            "mode": mode,
        }
        if raw is not None:
            result["raw"] = raw
        return result

    def _normalize_result(self, raw: Dict[str, Any], *, fallback_text: str) -> Dict[str, Any]:
        decision = str(raw.get("decision") or "REVIEW").strip().upper()
        event_value_type = str(raw.get("event_value_type") or "market_noise").strip()
        evidence = raw.get("evidence") if isinstance(raw.get("evidence"), list) else []
        result = self._build_result_from_text(
            fallback_text,
            decision=decision,
            importance_level=str(raw.get("importance_level") or "C").strip().upper(),
            event_value_type=event_value_type,
            reason_code=str(raw.get("reason_code") or f"prompt_{decision.lower()}"),
            reason=str(raw.get("reason") or raw.get("reason_code") or f"prompt:{decision}"),
            confidence=float(raw.get("confidence") or 0.5),
            score=raw.get("score"),
            mode=str(raw.get("mode") or "qwen1.5b_prompt"),
            evidence=[str(item) for item in evidence],
            raw=str(raw.get("raw")) if raw.get("raw") is not None else None,
        )
        result["dedupe_key"] = str(raw.get("dedupe_key") or result["dedupe_key"])
        for key in (
            "should_structurize",
            "should_publish_structured_stream",
            "should_enter_theme_match",
            "should_enter_review",
            "should_enter_premarket_major_events",
        ):
            if key in raw and isinstance(raw.get(key), bool):
                result[key] = bool(raw[key])
        if result["decision"] in {"SKIP", "DUPLICATE"}:
            result["should_enter_review"] = False
        if result["decision"] == "REVIEW" and result["importance_level"] in {"C", "D"}:
            result["should_enter_review"] = False
        return result

    @staticmethod
    def _parse_prompt_json(raw: str) -> Dict[str, Any] | None:
        match = re.search(r"\{.*\}", raw, flags=re.DOTALL)
        if not match:
            return None
        try:
            parsed = json.loads(match.group(0))
        except Exception:
            return None
        return parsed if isinstance(parsed, dict) else None

    def _rule_prefilter(self, news_data: Dict[str, Any], text: str, features: Dict[str, Any]) -> Dict[str, Any] | None:
        strong_catalysts = {
            "重大订单", "中标", "签署合同", "重大合同", "重大并购", "重大资产重组",
            "并购重组", "产业政策", "技术突破", "首次突破", "供给短缺", "价格上涨",
            "价格大涨", "需求激增", "出口管制", "获批上市", "投产", "扩产",
        }
        low_value_groups = {
            "rule_low_value_regulatory": (
                "行政监管措施", "行政监管", "监管函", "警示函", "责令改正",
                "问询函", "关注函", "审核问询函",
            ),
            "rule_low_value_clarification": (
                "澄清", "风险提示", "交易异动", "连续涨停", "连板",
                "无注入", "不涉及", "无算力计划", "不存在", "未开展",
            ),
            "rule_low_value_disaster": ("天气预警", "山洪", "暴雨", "地震", "列车停运"),
            "rule_low_value_earnings": ("第一季度", "一季度", "Q1", "财报", "营收", "净利润"),
            "rule_low_value_disclosure": ("回购", "减持"),
            "rule_low_value_rights_change": ("权益变动", "触及1%整数倍"),
            "rule_low_value_investor_event": ("投资者接待日", "集体接待日", "业绩说明会"),
            "rule_low_value_ordinary_personnel": ("任命", "辞任", "选举"),
            "rule_low_value_ordinary_ipo": ("IPO", "上市聆讯", "递表", "招股书"),
        }
        for reason_code, terms in low_value_groups.items():
            hits = [term for term in terms if term in text]
            if hits:
                return self._build_result(
                    news_data,
                    decision="SKIP",
                    importance_level="D",
                    event_value_type="low_value_disclosure",
                    reason_code=reason_code,
                    reason=f"{reason_code}:{','.join(hits[:3])}",
                    confidence=0.98,
                    mode="rule_prefilter",
                    evidence=hits,
                )

        catalyst_hits = [term for term in strong_catalysts if term in text]
        if catalyst_hits:
            return self._build_result(
                news_data,
                decision="PASS",
                importance_level="B",
                event_value_type="theme_catalyst",
                reason_code="rule_strong_catalyst_pass",
                reason=f"rule_strong_catalyst:{','.join(catalyst_hits[:3])}",
                confidence=0.9,
                mode="rule_prefilter",
                evidence=catalyst_hits,
            )

        if features.get("strict_trivial_skip"):
            return self._build_result(
                news_data,
                decision="SKIP",
                importance_level="D",
                event_value_type="market_noise",
                reason_code="rule_trivial_market_noise",
                reason="rule:strict_trivial_skip",
                confidence=0.9,
                mode="rule_prefilter",
                evidence=["price_move_without_catalyst"],
            )
        return None

    def _rule_features(self, text: str) -> Dict[str, Any]:
        lower = text.lower()
        keyword_hits = sum(
            1
            for k in (
                "涨停",
                "跌停",
                "题材",
                "板块",
                "主力",
                "资金",
                "业绩",
                "预增",
                "并购",
                "重组",
                "政策",
                "公告",
                "龙虎榜",
                "北向",
                "回购",
                "减持",
            )
            if k in text
        )
        has_catalyst = any(k in text for k in self._catalyst_keywords)
        has_concrete_catalyst = any(k in text for k in self._concrete_catalyst_keywords)
        trivial_price_move = bool(
            re.search(r"(股价|收盘|盘中|涨|跌|突破|回调|震荡).{0,20}(\d+(\.\d+)?%)", text)
        )
        generic_move_phrase_hit = any(p in text for p in self._generic_move_phrases)
        strict_trivial_skip = bool(
            trivial_price_move and (generic_move_phrase_hit or (not has_concrete_catalyst))
        )
        stock_code_hit = bool(re.search(r"\b[036]\d{5}\b", text))
        strong_signal = keyword_hits >= 2 or stock_code_hit
        weak_signal = keyword_hits == 1
        return {
            "text_len": len(text),
            "keyword_hits": keyword_hits,
            "has_catalyst": has_catalyst,
            "has_concrete_catalyst": has_concrete_catalyst,
            "trivial_price_move": trivial_price_move,
            "generic_move_phrase_hit": generic_move_phrase_hit,
            "strict_trivial_skip": strict_trivial_skip,
            "stock_code_hit": stock_code_hit,
            "strong_signal": strong_signal,
            "weak_signal": weak_signal,
            "empty": len(lower.strip()) == 0,
        }

    def _rule_decision(self, news_data: Dict[str, Any], feat: Dict[str, Any], reason_prefix: str) -> Dict[str, Any]:
        if feat["empty"] or feat["text_len"] < self.min_text_len:
            return self._build_result(
                news_data,
                decision="SKIP",
                importance_level="D",
                event_value_type="market_noise",
                reason_code="rule_short_or_empty",
                reason=f"{reason_prefix}:short_or_empty",
                confidence=0.9,
            )
        if feat["strong_signal"]:
            return self._build_result(
                news_data,
                decision="PASS",
                importance_level="B",
                event_value_type="theme_catalyst",
                reason_code="rule_strong_signal",
                reason=f"{reason_prefix}:strong_signal",
                confidence=0.7,
                evidence=["strong_signal"],
            )
        if feat["weak_signal"]:
            return self._build_result(
                news_data,
                decision="REVIEW",
                importance_level="C",
                event_value_type="market_noise",
                reason_code="rule_weak_signal_review",
                reason=f"{reason_prefix}:weak_signal",
                confidence=0.5,
                evidence=["weak_signal"],
            )
        return self._build_result(
            news_data,
            decision="SKIP",
            importance_level="D",
            event_value_type="market_noise",
            reason_code="rule_no_signal_skip",
            reason=f"{reason_prefix}:no_signal",
            confidence=0.8,
        )
