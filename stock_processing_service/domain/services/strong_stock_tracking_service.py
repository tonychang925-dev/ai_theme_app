"""强势股持续跟踪观察池 — 旧链 StrongStockTrackingService 的新架构 Domain 实现。

1:1 复刻 stock_service/services/strong_stock_tracking_service.py 的业务逻辑。
只包含业务规则，不包含任何 I/O（无 SQL、无 HTTP、无文件系统）。
所有外部数据通过参数传入。
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import date
from typing import Any

from stock_processing_service.domain.services.kline_support_scorer import SupportScoreResult

# ── 周期状态常量（与 stock_service/domain/cycle_states.py 一致）──
CYCLE_STATE_START = "start"
CYCLE_STATE_FERMENTATION = "fermentation"
CYCLE_STATE_ACCELERATION = "acceleration"
CYCLE_STATE_DIVERGENCE = "divergence"
CYCLE_STATE_REPAIR = "repair"
CYCLE_STATE_FADE_WATCH = "fade_watch"
CYCLE_STATE_FADE_CONFIRMED = "fade_confirmed"

CYCLE_STATES = {
    CYCLE_STATE_START,
    CYCLE_STATE_FERMENTATION,
    CYCLE_STATE_ACCELERATION,
    CYCLE_STATE_DIVERGENCE,
    CYCLE_STATE_REPAIR,
    CYCLE_STATE_FADE_WATCH,
    CYCLE_STATE_FADE_CONFIRMED,
}

RULE_VERSION = "strong_stock_watch.v2"


def _normalize_stock_id(raw: str) -> str:
    """统一证券代码格式为 000001.SZ / 600000.SH / 430001.BJ。
    等价于 stock_service/utils/security_id.py::normalize_stock_id。
    """
    value = (raw or "").strip().upper()
    if not value:
        return ""

    if "." in value:
        code, suffix = value.split(".", 1)
        if len(code) == 6 and code.isdigit() and suffix in {"SZ", "SH", "BJ"}:
            return f"{code}.{suffix}"
        value = code

    if len(value) != 6 or not value.isdigit():
        return ""

    if value.startswith(("60", "68")):
        suffix = "SH"
    elif value.startswith(("43", "83", "87")):
        suffix = "BJ"
    else:
        suffix = "SZ"

    return f"{value}.{suffix}"


@dataclass
class WatchSeedRow:
    """种子行数据 — 等价于旧链 WatchSeedRow + labels_json 展开。"""
    stock_id: str
    stock_name: str
    subject_key: str
    theme_name: str
    source_tag: str
    relay_role: str
    # 从旧链 labels_json 展开的关键字段
    recent_limit_up_count: int = 0
    current_flag_today: int = 0
    is_dragon_head: bool = False
    is_front_row_core: bool = False
    board_effect_confirmed: bool = False
    mainline_identity_confirmed: bool = True
    subject_limit_up_count: int = 0
    subject_strong_count: int = 0
    cond_gene: int = 0
    cond_volume: int = 0
    cond_structure: int = 0
    hard_gate_pass_count: int = 0
    is_main_theme: bool = False
    identity_status: str = "observed"
    labels: dict[str, Any] = field(default_factory=dict)
    evidence: dict[str, Any] = field(default_factory=dict)


@dataclass
class WatchScoreResult:
    """评分结果 — 等价于旧链 WatchScoreResult。"""
    stock_id: str = ""
    stock_name: str = ""
    subject_key: str = ""
    theme_name: str = ""
    source_tag: str = ""
    relay_role: str = ""
    watch_score: float = 0.0
    watch_priority: float = 0.0
    watch_status: str = "pending_seed"
    pool_entry_type: str = "observe_only"
    cycle_state: str = ""
    mainline_strength_score: float = 0.0
    fade_watch: bool = False
    fade_confirmed: bool = False
    support_type: str | None = None
    support_level: float | None = None
    support_score: float = 0.0
    strong_grade: str = "REJECT"
    broken_board: bool = False
    removed_reason: str | None = None
    labels: dict[str, Any] = field(default_factory=dict)
    evidence: dict[str, Any] = field(default_factory=dict)


@dataclass
class CycleSnapshot:
    """周期/主线状态快照 — 等价于旧链 _score_watch_row 中 cycle 查询结果。"""
    final_cycle_state: str = ""
    effective_mainline_alive: bool = False
    fade_watch: bool = False
    fade_confirmed: bool = False
    mainline_strength_score: float = 0.0
    event_continuity_score: float = 0.0


@dataclass
class BoardSnapshot:
    """板块强度快照 — 等价于旧链 board 查询结果。"""
    subject_limit_up_count: int = 0
    subject_strong_count: int = 0


@dataclass
class PositionSnapshot:
    """个股位置/均线快照 — 等价于旧链 pos 查询结果。"""
    position_label: str = ""
    ma_alignment_status: str = ""
    trend_strength_score: float = 0.0


@dataclass
class PatternSnapshot:
    """个股形态/量价快照 — 等价于旧链 pattern 查询结果。"""
    pattern_labels: list[str] = field(default_factory=list)
    volume_pattern_status: str = ""
    breakout_status: str = ""
    pullback_status: str = ""
    risk_pattern_status: str = ""


class StrongStockTrackingService:
    """旧链 StrongStockTrackingService 的新架构 Domain 实现。

    所有数据通过参数传入，Domain 只做纯业务计算。
    评分体系、阈值、硬门禁与旧链完全一致。
    """

    RULE_VERSION = RULE_VERSION
    ACTIVE_MIN_SCORE = 72.0
    WEAKENING_MIN_SCORE = 62.0
    OBSERVE_MIN_SCORE = 62.0
    FORMAL_MIN_SCORE = 78.0
    FORMAL_MIN_MAINLINE = 65.0
    STRONG_GRADE_S_MIN = 80.0
    STRONG_GRADE_A_MIN = 65.0
    STRONG_GRADE_B_MIN = 50.0

    # ── 种子候选过滤 ──

    @staticmethod
    def _is_disallowed_watch_stock(stock_id: str, stock_name: str) -> bool:
        """ST/688 排除 — 等价于旧链 _is_disallowed_watch_stock。"""
        canonical = _normalize_stock_id(stock_id)
        code = canonical.split(".", 1)[0] if "." in canonical else canonical
        if code.startswith("688"):
            return True
        name = str(stock_name or "").strip().upper()
        if not name:
            return False
        if name.startswith("ST") or name.startswith("*ST"):
            return True
        return False

    @staticmethod
    def _coerce_json_object(raw: Any) -> dict[str, Any]:
        """JSON 安全解析 — 等价于旧链 _coerce_json_object。"""
        if isinstance(raw, dict):
            return dict(raw)
        if raw is None:
            return {}
        if isinstance(raw, str):
            try:
                parsed = json.loads(raw)
                if isinstance(parsed, dict):
                    return parsed
            except Exception:
                return {}
        return {}

    @staticmethod
    def _assign_source_tag(
        recent_limit_up_count: int,
        is_leader: bool,
    ) -> str:
        """source_tag 赋值 — 等价于旧链 _fetch_seed_rows 中 source_tag 逻辑。"""
        if recent_limit_up_count >= 4:
            return "4_limit_up"
        elif recent_limit_up_count >= 3:
            return "3_limit_up"
        elif recent_limit_up_count >= 2:
            return "2_limit_up"
        elif is_leader:
            return "leader_core"
        else:
            return "front_row_core"

    @staticmethod
    def _assign_relay_role(
        is_leader: bool,
        best_rank: int,
    ) -> str:
        """relay_role 赋值 — 等价于旧链 _fetch_seed_rows 中 relay_role 逻辑。"""
        if is_leader:
            return "dragon"
        elif best_rank <= 3:
            return "sub_dragon"
        else:
            return "unknown"

    def build_seed_candidates(
        self,
        seed_rows: list[dict[str, Any]],
    ) -> list[WatchSeedRow]:
        """从 Gateway 返回的种子行构建 WatchSeedRow 列表。

        等价于旧链 _fetch_seed_rows 返回后的 Python 处理逻辑：
        - ST/688 排除
        - 去重（按 stock_id）
        - source_tag / relay_role 赋值
        - labels 构建
        """
        dedup: dict[str, WatchSeedRow] = {}
        for row in seed_rows:
            stock_id = _normalize_stock_id(str(row.get("stock_id") or ""))
            if not stock_id:
                continue
            stock_name = str(row.get("stock_name") or stock_id)
            if self._is_disallowed_watch_stock(stock_id, stock_name):
                continue

            recent_limit_up_count = int(row.get("recent_limit_up_count") or 0)
            is_leader = bool(row.get("is_leader_flag") or 0)
            best_rank = int(row.get("best_rank") or 999)
            current_flag_today = int(row.get("current_flag_today") or 0)
            subject_limit_up = int(row.get("subject_limit_up_count") or 0)
            subject_strong = int(row.get("subject_strong_count") or 0)
            cond_gene = int(row.get("cond_gene") or 0)
            cond_volume = int(row.get("cond_volume") or 0)
            cond_structure = int(row.get("cond_structure") or 0)
            has_two_board = bool(row.get("has_two_board") or False)

            source_tag = self._assign_source_tag(recent_limit_up_count, is_leader)
            relay_role = self._assign_relay_role(is_leader, best_rank)

            labels = {
                "has_recent_limit_up": recent_limit_up_count > 0,
                "recent_limit_up_count": recent_limit_up_count,
                "has_two_board": has_two_board,
                "current_flag_today": current_flag_today,
                "is_dragon_head": is_leader,
                "is_front_row_core": best_rank <= 3,
                "watch_window_days": 7,
                "mainline_identity_confirmed": True,
                "board_effect_confirmed": (
                    subject_limit_up >= 2 or subject_strong >= 3
                ),
                "subject_limit_up_count": subject_limit_up,
                "subject_strong_count": subject_strong,
                "hard_gate_cond_gene": bool(cond_gene),
                "hard_gate_cond_volume": bool(cond_volume),
                "hard_gate_cond_structure": bool(cond_structure),
                "hard_gate_pass_count": cond_gene + cond_volume + cond_structure,
            }
            if has_two_board:
                labels.update({
                    "entry_path": "independent_leader",
                    "identity_scope": "independent_stock_signal",
                    "strong_gene_seed": True,
                })
                labels.pop("mainline_identity_confirmed", None)
            evidence = {
                "schema_version": "watch_evidence.v1",
                "rule_version": self.RULE_VERSION,
                "seed_reason": {
                    "recent_limit_up_count": recent_limit_up_count,
                    "is_leader": is_leader,
                    "best_rank": best_rank,
                    "has_two_board": has_two_board,
                    "subject_limit_up_count": subject_limit_up,
                    "subject_strong_count": subject_strong,
                },
                "source": {"table": "subject_stock_daily_snapshot", "lookback_days": 7},
            }

            candidate = WatchSeedRow(
                stock_id=stock_id,
                stock_name=stock_name,
                subject_key=str(row.get("subject_key") or ""),
                theme_name=str(row.get("theme_name") or row.get("subject_key") or ""),
                source_tag=source_tag,
                relay_role=relay_role,
                recent_limit_up_count=recent_limit_up_count,
                current_flag_today=current_flag_today,
                is_dragon_head=is_leader,
                is_front_row_core=best_rank <= 3,
                board_effect_confirmed=labels["board_effect_confirmed"],
                subject_limit_up_count=subject_limit_up,
                subject_strong_count=subject_strong,
                cond_gene=cond_gene,
                cond_volume=cond_volume,
                cond_structure=cond_structure,
                hard_gate_pass_count=labels["hard_gate_pass_count"],
                is_main_theme=bool(row.get("is_main_theme") or False),
                identity_status=str(row.get("identity_status") or "observed"),
                labels=labels,
                evidence=evidence,
            )
            dedup[stock_id] = candidate

        return list(dedup.values())

    # ── 硬门禁 ──

    @staticmethod
    def _evaluate_strong_pool_hard_gate(
        *,
        recent_limit_up_count: int,
        final_mainline_alive: bool,
        board_effect_confirmed: bool,
        current_flag_today: int,
        broken_board: bool,
        volume_pattern_status: str,
        pullback_status: str,
        ma_status: str,
        pattern_labels: list[str],
        breakout_status: str,
        position_label: str,
        trend_strength_score: float,
        has_two_board: bool = False,
    ) -> dict[str, Any]:
        """4选3 硬门禁 — 等价于旧链 _evaluate_strong_pool_hard_gate。"""
        # Rule A：涨停基因（必须成立）
        rule_a_gene = recent_limit_up_count >= 1
        # Rule B：题材承接（主线+板块合力）
        rule_b_theme = final_mainline_alive and board_effect_confirmed
        # Rule C：量价结构健康
        rule_c_volume = (
            current_flag_today >= 2
            or volume_pattern_status in {"放量上涨", "缩量整理"}
            or pullback_status == "缩量回踩"
            or (not broken_board)
        )
        # Rule D：K线结构健康
        rule_d_structure = (
            ma_status == "均线多头"
            or "高量不破" in pattern_labels
            or breakout_status == "放量突破"
            or position_label in {"突破前高", "接近前高"}
            or trend_strength_score >= 70.0
        )
        pass_count = int(rule_a_gene) + int(rule_b_theme) + int(rule_c_volume) + int(rule_d_structure)
        # 硬门禁判定：
        #   - 常规路径：4选3（pass_count >= 3）
        #   - 主线承接豁免：(rule_b_theme AND recent_limit_up_count >= 2)
        #   - 独立龙头豁免：has_two_board=True 直接放行入池，
        #     入池后再由支撑破位、7日到期等机制做生命周期剔除
        passed = bool(
            rule_a_gene
            and (
                pass_count >= 3
                or (rule_b_theme and recent_limit_up_count >= 2)
                or has_two_board
            )
        )
        return {
            "rule_a_gene": rule_a_gene,
            "rule_b_theme": rule_b_theme,
            "rule_c_volume": rule_c_volume,
            "rule_d_structure": rule_d_structure,
            "pass_count": pass_count,
            "passed": passed,
        }

    # ── 5维评分 ──

    def score_watch_row(
        self,
        row: WatchSeedRow,
        *,
        current_flag_today: int | None = None,
        close_price: float | None = None,
        cycle: CycleSnapshot | None = None,
        board: BoardSnapshot | None = None,
        support_result: SupportScoreResult | None = None,
        pos: PositionSnapshot | None = None,
        pattern: PatternSnapshot | None = None,
    ) -> WatchScoreResult:
        """5维评分 + watch_status + pool_entry_type 分类。

        等价于旧链 _score_watch_row（strong_stock_tracking_service.py:543-958）。
        所有外部数据通过参数传入，Domain 不做任何 I/O。

        close_price 用于支撑破位判定：当 broken_board + mainline_alive 时，
        若 close_price < support_level 则判定 support_broken 进而剔除。
        """
        stock_id = row.stock_id
        stock_name = row.stock_name

        # ── 禁用股票检查 ──
        if self._is_disallowed_watch_stock(stock_id, stock_name):
            labels = dict(row.labels)
            labels.update({
                "removed_by_filter": True,
                "removed_reason": "exclude_st_or_688",
            })
            return WatchScoreResult(
                stock_id=stock_id,
                stock_name=stock_name,
                subject_key=row.subject_key,
                theme_name=row.theme_name,
                source_tag=row.source_tag,
                relay_role=row.relay_role,
                watch_score=0.0,
                watch_priority=0.0,
                watch_status="removed",
                pool_entry_type="reject",
                cycle_state=row.labels.get("cycle_state", ""),
                mainline_strength_score=0.0,
                fade_watch=False,
                fade_confirmed=True,
                support_type=None,
                support_level=None,
                support_score=0.0,
                labels=labels,
                evidence={
                    "schema_version": "watch_evidence.v1",
                    "rule_version": self.RULE_VERSION,
                    "phase": "phase1_seed_refresh_history",
                    "removed_reason": "exclude_st_or_688",
                },
            )

        # ── 基础数据 ──
        flag_today = current_flag_today if current_flag_today is not None else row.current_flag_today
        broken_board = flag_today < 2
        cycle = cycle or CycleSnapshot()
        board = board or BoardSnapshot()
        pos = pos or PositionSnapshot()
        pattern = pattern or PatternSnapshot()

        # ── 从 row labels 提取关键字段 ──
        labels = dict(row.labels)
        recent_limit_up_count = int(labels.get("recent_limit_up_count", 0) or 0)
        is_dragon_head = bool(labels.get("is_dragon_head") or False)
        is_front_row_core = bool(labels.get("is_front_row_core") or False)
        board_effect_confirmed_raw = bool(labels.get("board_effect_confirmed") or False)

        mainline_strength_score = cycle.mainline_strength_score
        event_continuity_score = cycle.event_continuity_score
        final_mainline_alive = cycle.effective_mainline_alive
        subject_limit_up_count = board.subject_limit_up_count
        subject_strong_count = board.subject_strong_count
        board_effect_confirmed = (
            board_effect_confirmed_raw
            or subject_limit_up_count >= 2
            or subject_strong_count >= 3
        )

        # ── 1) 涨停/强势基因（0-20）──
        gene_score = 0.0
        if recent_limit_up_count >= 4:
            gene_score = 20.0
        elif recent_limit_up_count >= 3:
            gene_score = 16.0
        elif recent_limit_up_count >= 2:
            gene_score = 12.0
        elif recent_limit_up_count >= 1:
            gene_score = 8.0
        if flag_today >= 2:
            gene_score = min(20.0, gene_score + 2.0)

        # ── 2) 题材主线分（0-20）──
        theme_score = 0.0
        if final_mainline_alive:
            theme_score += 8.0
        if event_continuity_score >= 40.0:
            theme_score += 6.0
        elif event_continuity_score >= 25.0:
            theme_score += 3.0
        if board_effect_confirmed:
            theme_score += 6.0
        theme_score = min(20.0, theme_score)

        # ── 3) 龙头地位分（0-20）──
        relay_role = row.relay_role
        if relay_role == "dragon":
            dragon_score = 20.0
        elif relay_role == "sub_dragon":
            dragon_score = 15.0
        elif relay_role == "card_position_candidate":
            dragon_score = 12.0
        elif is_front_row_core:
            dragon_score = 10.0
        else:
            dragon_score = 4.0

        # ── 4) 量价结构分（0-20）──
        pattern_labels = list(pattern.pattern_labels or [])
        volume_pattern_status = pattern.volume_pattern_status
        pullback_status = pattern.pullback_status

        volume_price_score = 0.0
        if flag_today >= 2:
            volume_price_score += 6.0
        if volume_pattern_status in {"放量上涨", "缩量整理"}:
            volume_price_score += 6.0
        if pullback_status == "缩量回踩":
            volume_price_score += 4.0
        if not broken_board:
            volume_price_score += 4.0
        volume_price_score = min(20.0, volume_price_score)

        # ── 5) K线结构分（0-20）──
        position_label = pos.position_label
        ma_status = pos.ma_alignment_status
        trend_strength_score = pos.trend_strength_score
        breakout_status = pattern.breakout_status

        structure_score = 0.0
        if ma_status == "均线多头":
            structure_score += 4.0
        if "高量不破" in pattern_labels:
            structure_score += 4.0
        if breakout_status == "放量突破":
            structure_score += 4.0
        if position_label in {"突破前高", "接近前高"}:
            structure_score += 4.0
        if trend_strength_score >= 70.0:
            structure_score += 4.0
        structure_score = min(20.0, structure_score)

        # ── 硬门禁 ──
        hard_gate = self._evaluate_strong_pool_hard_gate(
            recent_limit_up_count=recent_limit_up_count,
            final_mainline_alive=final_mainline_alive,
            board_effect_confirmed=board_effect_confirmed,
            current_flag_today=flag_today,
            broken_board=broken_board,
            volume_pattern_status=volume_pattern_status,
            pullback_status=pullback_status,
            ma_status=ma_status,
            pattern_labels=pattern_labels,
            breakout_status=breakout_status,
            position_label=position_label,
            trend_strength_score=trend_strength_score,
            has_two_board=bool(row.labels.get("has_two_board") or False),
        )

        if not bool(hard_gate.get("passed")):
            labels.update({
                "hard_gate_rule_a_gene": bool(hard_gate.get("rule_a_gene")),
                "hard_gate_rule_b_theme": bool(hard_gate.get("rule_b_theme")),
                "hard_gate_rule_c_volume": bool(hard_gate.get("rule_c_volume")),
                "hard_gate_rule_d_structure": bool(hard_gate.get("rule_d_structure")),
                "hard_gate_pass_count": int(hard_gate.get("pass_count") or 0),
                "removed_by_hard_gate": True,
                "removed_reason": "strong_pool_hard_gate_failed",
            })
            return WatchScoreResult(
                stock_id=stock_id,
                stock_name=stock_name,
                subject_key=row.subject_key,
                theme_name=row.theme_name,
                source_tag=row.source_tag,
                relay_role=row.relay_role,
                watch_score=0.0,
                watch_priority=0.0,
                watch_status="removed",
                pool_entry_type="reject",
                cycle_state=cycle.final_cycle_state,
                mainline_strength_score=mainline_strength_score,
                fade_watch=cycle.fade_watch,
                fade_confirmed=True,
                support_type=None,
                support_level=None,
                support_score=0.0,
                labels=labels,
                evidence={
                    "schema_version": "watch_evidence.v1",
                    "rule_version": self.RULE_VERSION,
                    "phase": "phase1_seed_refresh_history",
                    "hard_gate": hard_gate,
                    "removed_reason": "strong_pool_hard_gate_failed",
                },
            )

        # ── 综合评分 ──
        watch_score = round(
            gene_score + theme_score + dragon_score + volume_price_score + structure_score,
            2,
        )
        has_two_board = bool(labels.get("has_two_board") or False)

        if broken_board and not final_mainline_alive and not has_two_board:
            watch_score = max(0.0, round(watch_score - 8.0, 2))

        watch_priority = round(
            watch_score
            + (5.0 if relay_role == "dragon" else 0.0)
            + (2.0 if board_effect_confirmed else 0.0),
            2,
        )

        # ── 周期状态 ──
        fade_watch = cycle.fade_watch
        fade_confirmed = cycle.fade_confirmed
        cycle_state = cycle.final_cycle_state
        if cycle_state not in CYCLE_STATES:
            cycle_state = ""

        # ── 支撑破位判定（设计文档 26.6：跌破支撑线方可剔除）──
        support_broken = False
        if support_result is not None and support_result.support_level is not None and close_price is not None:
            support_broken = float(close_price) < float(support_result.support_level)

        # ── watch_status 判定 ──
        if fade_confirmed or cycle_state == CYCLE_STATE_FADE_CONFIRMED:
            watch_status = "removed"
        elif has_two_board:
            if support_broken:
                watch_status = "removed"
            elif watch_score >= self.ACTIVE_MIN_SCORE:
                watch_status = "active"
            else:
                watch_status = "weakening"
        elif broken_board:
            # 独立龙头不因主线死亡被剔除，只受支撑破位/7日到期约束
            if not final_mainline_alive and not has_two_board:
                watch_status = "removed"
            elif support_broken:
                watch_status = "removed"
            else:
                watch_status = "weakening"
        elif watch_score >= self.ACTIVE_MIN_SCORE:
            watch_status = "active"
        elif watch_score >= self.WEAKENING_MIN_SCORE:
            watch_status = "weakening"
        else:
            watch_status = "removed"

        # ── strong_grade ──
        if watch_score >= self.STRONG_GRADE_S_MIN:
            strong_grade = "S"
        elif watch_score >= self.STRONG_GRADE_A_MIN:
            strong_grade = "A"
        elif watch_score >= self.STRONG_GRADE_B_MIN:
            strong_grade = "B"
        else:
            strong_grade = "REJECT"

        # ── pool_entry_type ──
        if fade_confirmed or cycle_state == CYCLE_STATE_FADE_CONFIRMED:
            pool_entry_type = "reject"
        elif has_two_board and not support_broken:
            pool_entry_type = "observe_only"
        elif broken_board and (final_mainline_alive or has_two_board) and not support_broken:
            pool_entry_type = "observe_only"
        elif (
            strong_grade in {"S", "A"}
            and watch_score >= self.FORMAL_MIN_SCORE
            and mainline_strength_score >= self.FORMAL_MIN_MAINLINE
        ):
            pool_entry_type = "formal"
        elif watch_status in {"active", "weakening"} and strong_grade in {"S", "A", "B"} and watch_score >= self.OBSERVE_MIN_SCORE:
            pool_entry_type = "observe_only"
        else:
            pool_entry_type = "reject"

        # ── removed_reason ──
        removed_reason: str | None = None
        if watch_status == "removed":
            if fade_confirmed or cycle_state == CYCLE_STATE_FADE_CONFIRMED:
                removed_reason = "fade_confirmed"
            elif broken_board and support_broken:
                removed_reason = "support_broken"
            elif broken_board and not final_mainline_alive and not has_two_board:
                removed_reason = "broken_board_non_mainline"
            elif watch_score < self.WEAKENING_MIN_SCORE:
                removed_reason = "watch_score_below_threshold"
            else:
                removed_reason = "removed_unclassified"

        # ── 分歧/修复/退潮观望状态下加分 ──
        if cycle_state in {CYCLE_STATE_DIVERGENCE, CYCLE_STATE_REPAIR, CYCLE_STATE_FADE_WATCH}:
            watch_priority = round(watch_priority + 2.0, 2)

        # ── 支撑位数据 ──
        support_type = support_result.support_type if support_result else None
        support_level = support_result.support_level if support_result else None
        support_score = float(support_result.support_score) if support_result else 0.0
        support_strength = float(support_result.combined_strength) if support_result else 0.0

        # ── labels 补全 ──
        labels.update({
            "cycle_state": cycle_state,
            "fade_watch": fade_watch,
            "fade_confirmed": fade_confirmed,
            "mainline_strength_score": mainline_strength_score,
            "current_flag_today": flag_today,
            "broken_board": broken_board,
            "final_mainline_alive": final_mainline_alive,
            "board_effect_confirmed": board_effect_confirmed,
            "subject_limit_up_count": subject_limit_up_count,
            "subject_strong_count": subject_strong_count,
            "hard_gate_rule_a_gene": bool(hard_gate.get("rule_a_gene")),
            "hard_gate_rule_b_theme": bool(hard_gate.get("rule_b_theme")),
            "hard_gate_rule_c_volume": bool(hard_gate.get("rule_c_volume")),
            "hard_gate_rule_d_structure": bool(hard_gate.get("rule_d_structure")),
            "hard_gate_pass_count": int(hard_gate.get("pass_count") or 0),
            "strong_grade": strong_grade,
            "mainline_identity_confirmed": True,
            "hot_theme": board_effect_confirmed,
            "theme_has_event_catalyst": event_continuity_score >= 25.0,
            "ma_bullish": ma_status == "均线多头",
            "high_volume_unbroken": "高量不破" in pattern_labels,
            "new_high_structure": position_label in {"突破前高", "接近前高"},
            "stable_seal_order": not broken_board,
            "volume_up_price_up": volume_pattern_status == "放量上涨",
            "shrink_on_pullback": pullback_status == "缩量回踩",
            "support_type": support_type,
            "support_level": support_level,
            "support_score": support_score,
            "support_strength": support_strength,
            "support_broken": support_broken,
        })
        if has_two_board:
            labels.update({
                "entry_path": "independent_leader",
                "identity_scope": "independent_stock_signal",
                "strong_gene_seed": True,
            })
            for key in (
                "mainline_identity_confirmed",
                "final_mainline_alive",
                "cycle_state",
                "fade_watch",
                "fade_confirmed",
                "mainline_strength_score",
            ):
                labels.pop(key, None)
        if removed_reason:
            labels["removed_reason"] = removed_reason

        # ── evidence 构建 ──
        evidence = {
            "schema_version": "watch_evidence.v1",
            "rule_version": self.RULE_VERSION,
            "watch_score_breakdown": {
                "gene_score": gene_score,
                "theme_score": theme_score,
                "dragon_score": dragon_score,
                "volume_price_score": volume_price_score,
                "structure_score": structure_score,
            },
            "hard_gate": hard_gate,
            "cycle_state": cycle_state,
            "mainline_strength_score": mainline_strength_score,
            "broken_board": broken_board,
            "current_flag_today": flag_today,
            "final_mainline_alive": final_mainline_alive,
            "event_continuity_score": event_continuity_score,
            "subject_limit_up_count": subject_limit_up_count,
            "subject_strong_count": subject_strong_count,
            "position_label": position_label,
            "ma_alignment_status": ma_status,
            "pattern_labels": pattern_labels,
            "strong_grade": strong_grade,
            "support": {
                "support_type": support_type,
                "support_level": support_level,
                "support_score": support_score,
                "support_strength": support_strength,
                "support_breakdown": [{
                    "support_type": st.support_type,
                    "support_level": str(st.support_level),
                    "strength": str(st.strength),
                } for st in (support_result.support_types or [])] if support_result else {},
                "evidence_refs": support_result.support_refs if support_result else [],
            },
            "phase": "phase1_seed_refresh_history",
        }
        if has_two_board:
            evidence.update({
                "entry_path": "independent_leader",
                "identity_scope": "independent_stock_signal",
                "strong_gene_seed": True,
            })
            for key in (
                "final_mainline_alive",
                "cycle_state",
                "mainline_strength_score",
            ):
                evidence.pop(key, None)
        if removed_reason:
            evidence["removed_reason"] = removed_reason

        return WatchScoreResult(
            stock_id=stock_id,
            stock_name=stock_name,
            subject_key=row.subject_key,
            theme_name=row.theme_name,
            source_tag=row.source_tag,
            relay_role=row.relay_role,
            watch_score=watch_score,
            watch_priority=watch_priority,
            watch_status=watch_status,
            pool_entry_type=pool_entry_type,
            cycle_state=cycle_state,
            mainline_strength_score=mainline_strength_score,
            fade_watch=fade_watch,
            fade_confirmed=fade_confirmed,
            support_type=support_type,
            support_level=support_level,
            support_score=support_score,
            strong_grade=strong_grade,
            broken_board=broken_board,
            removed_reason=removed_reason,
            labels=labels,
            evidence=evidence,
        )

    @staticmethod
    def is_candidate_eligible(
        *,
        watch_status: str,
        pool_entry_type: str,
        candidate_source: str = "strong_watch_pool",
    ) -> bool:
        """D1 候选资格判定 — 等价于旧链 WeakToStrongCandidateBuilder._quick_row_gate + source check。"""
        if str(candidate_source or "").strip().lower() != "strong_watch_pool":
            return False
        if str(watch_status or "").strip().lower() not in {"active", "weakening"}:
            return False
        if str(pool_entry_type or "").strip().lower() not in {"formal", "observe_only"}:
            return False
        return True


__all__ = [
    "StrongStockTrackingService",
    "WatchSeedRow",
    "WatchScoreResult",
    "CycleSnapshot",
    "BoardSnapshot",
    "PositionSnapshot",
    "PatternSnapshot",
]
