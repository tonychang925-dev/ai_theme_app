"""
本地Qwen新闻预筛选服务

目标：在进入大模型事件提取前做轻量分流，减少不必要的LLM调用。
默认优先使用 Qwen2.5-1.5B (GGUF + llama_cpp) 的 prompt 判定。
"""
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
        self.prompt_max_tokens = int(cfg.get("triage_prompt_max_tokens", 2))

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
            "政策", "业绩", "预增", "预亏", "并购", "重组", "订单", "中标",
            "回购", "减持", "停牌", "复牌", "监管", "财政", "降息", "加息",
            "关税", "出口", "制裁", "突破技术", "新品", "扩产", "事故", "诉讼",
        }
        self._concrete_catalyst_keywords = {
            "公告", "中标", "签约", "订单", "业绩预告", "净利润", "收入", "回购计划",
            "减持计划", "并购", "重组", "监管函", "处罚", "停牌", "复牌", "增持",
            "分红", "问询函", "产能", "投产", "召回", "诉讼", "获批", "批文",
            "补贴", "关税", "出口管制", "降息", "加息", "财政刺激",
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

        # 硬过滤已关闭 — 全部交由 Qwen prompt 判定
        # if rule_features["strict_trivial_skip"]:
        #     return {"decision": "SKIP", ...}

        if not self.enabled:
            return self._rule_decision(rule_features, reason_prefix="local_triage_disabled")

        # 1) prompt判定优先
        if self.mode in {"prompt", "hybrid"} and self._ensure_prompt_ready():
            prompt_result = self._prompt_decision(text, rule_features)
            if prompt_result is not None:
                return prompt_result

        # 2) 仅prompt模式下直接回退规则
        if self.mode == "prompt":
            return self._rule_decision(rule_features, reason_prefix="prompt_unavailable")

        # 3) embedding 回退
        if not self._ensure_qwen_ready():
            return self._rule_decision(rule_features, reason_prefix="qwen_unavailable")

        try:
            vec = self._matcher._encode_single_direct(text)
            if vec is None:
                return self._rule_decision(rule_features, reason_prefix="qwen_encode_empty")

            pos = float(self._matcher._cosine_similarity(vec, self._positive_anchor))
            neg = float(self._matcher._cosine_similarity(vec, self._negative_anchor))
            score = pos - neg

            if score >= self.pass_threshold:
                return {
                    "decision": "PASS",
                    "reason": f"embedding_score={score:.4f} >= pass_threshold={self.pass_threshold:.4f}",
                    "score": score,
                    "mode": "local_qwen_embedding",
                }
            if score <= self.skip_threshold and not rule_features["strong_signal"]:
                return {
                    "decision": "SKIP",
                    "reason": f"embedding_score={score:.4f} <= skip_threshold={self.skip_threshold:.4f}",
                    "score": score,
                    "mode": "local_qwen_embedding",
                }
            return {
                "decision": "REVIEW",
                "reason": f"embedding_score={score:.4f}, between thresholds",
                "score": score,
                "mode": "local_qwen_embedding",
            }
        except Exception as e:
            logger.warning(f"本地Qwen预筛选异常，降级规则模式: {e}")
            return self._rule_decision(rule_features, reason_prefix="qwen_exception")

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
            raw = str(response["choices"][0]["text"]).strip().upper()

            if raw.startswith("SKIP"):
                return {"decision": "SKIP", "reason": "prompt:SKIP", "score": None, "mode": "qwen1.5b_prompt", "raw": raw}
            if raw.startswith("PASS"):
                return {"decision": "PASS", "reason": "prompt:PASS", "score": None, "mode": "qwen1.5b_prompt", "raw": raw}
            if raw.startswith("REVIEW"):
                return {"decision": "REVIEW", "reason": "prompt:REVIEW", "score": None, "mode": "qwen1.5b_prompt", "raw": raw}

            # 非法输出兜底
            if features.get("trivial_price_move") and not features.get("has_catalyst"):
                return {
                    "decision": "SKIP",
                    "reason": "prompt_invalid_but_rule_skip",
                    "score": None,
                    "mode": "qwen1.5b_prompt",
                    "raw": raw,
                }
            return {
                "decision": "REVIEW",
                "reason": "prompt_invalid_output",
                "score": None,
                "mode": "qwen1.5b_prompt",
                "raw": raw,
            }
        except Exception as e:
            logger.warning(f"Qwen1.5B prompt判定异常: {e}")
            return None

    @staticmethod
    def _build_prompt(text: str) -> str:
        short_text = text[:420]
        return (
            "你是A股实时新闻过滤器。目标：剔除无交易价值的小事件，保留可能影响题材/板块预期的事件。\n"
            "规则：\n"
            "1) 仅股价涨跌、突破、回调、震荡，且没有明确催化（政策/业绩/并购/订单/监管/行业供需变化）=> SKIP。\n"
            "2) 有明确催化并可能影响题材、板块或资金预期 => PASS。\n"
            "3) 信息不足或争议较大 => REVIEW。\n"
            "只输出一个词：PASS 或 REVIEW 或 SKIP。\n"
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

    def _rule_decision(self, feat: Dict[str, Any], reason_prefix: str) -> Dict[str, Any]:
        if feat["empty"] or feat["text_len"] < self.min_text_len:
            return {"decision": "SKIP", "reason": f"{reason_prefix}:short_or_empty", "score": None, "mode": "rule"}
        if feat["strong_signal"]:
            return {"decision": "PASS", "reason": f"{reason_prefix}:strong_signal", "score": None, "mode": "rule"}
        if feat["weak_signal"]:
            return {"decision": "REVIEW", "reason": f"{reason_prefix}:weak_signal", "score": None, "mode": "rule"}
        return {"decision": "SKIP", "reason": f"{reason_prefix}:no_signal", "score": None, "mode": "rule"}
