from __future__ import annotations

from dataclasses import dataclass

from stock_service.models import ThemeLeaderCandidate


def _clip(value: float, upper: float = 100.0) -> float:
    return max(0.0, min(upper, round(value, 2)))


@dataclass(frozen=True)
class ThemeLeaderInput:
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
    is_new_stock: bool
    close_price: float
    position_label: str = ""
    trend_strength_score: float = 0.0
    pattern_labels: tuple[str, ...] = ()


class LeaderCandidateService:
    """
    P3.phase2 模块 3：
    在主线题材内部生成龙头候选评分与角色标签。
    """

    def compute_purity_score(self, row: ThemeLeaderInput) -> float:
        score = 0.0
        if row.is_leader:
            score += 45.0
        elif row.rank_order <= 3:
            score += 35.0
        elif row.rank_order <= 5:
            score += 25.0
        else:
            score += 10.0
        if row.is_new_stock:
            score += 5.0
        return _clip(score)

    def compute_leading_score(self, row: ThemeLeaderInput) -> float:
        score = 0.0
        if row.is_limit_up:
            score += 40.0
        score += min(max(row.pct_chg, 0.0), 20.0) * 2.0
        if row.is_leader:
            score += 15.0
        if row.rank_order <= 3:
            score += 10.0
        return _clip(score)

    def compute_capital_score(self, row: ThemeLeaderInput) -> float:
        score = 0.0
        score += min(max(row.turnover_rate, 0.0), 25.0) * 2.0
        score += min(max(row.volume_ratio, 0.0), 10.0) * 3.0
        score += min(max(row.main_net_inflow, 0.0) / 1e8, 10.0) * 2.0
        return _clip(score)

    def compute_structure_score(self, row: ThemeLeaderInput) -> float:
        score = 0.0
        if row.is_limit_up:
            score += 25.0
        if row.rank_order <= 3:
            score += 15.0
        if row.close_price and row.close_price <= 50:
            score += 10.0
        if row.is_new_stock:
            score += 10.0
        if row.position_label == "低位启动":
            score += 15.0
        elif row.position_label == "平台整理":
            score += 8.0
        elif row.position_label == "高位分歧":
            score -= 10.0
        if "放量突破" in row.pattern_labels:
            score += 12.0
        if "缩量回踩" in row.pattern_labels:
            score += 8.0
        if "高量不破" in row.pattern_labels:
            score += 10.0
        return _clip(score)

    def compute_resilience_score(self, row: ThemeLeaderInput) -> float:
        score = 0.0
        if row.is_limit_up:
            score += 25.0
        if row.pct_chg >= 8:
            score += 20.0
        elif row.pct_chg >= 5:
            score += 12.0
        elif row.pct_chg >= 0:
            score += 6.0
        if row.is_leader:
            score += 10.0
        score += min(max(row.trend_strength_score, 0.0), 100.0) * 0.15
        return _clip(score)

    def compute_composite_score(self, purity: float, leading: float, capital: float, structure: float, resilience: float) -> float:
        return _clip(
            purity * 0.25
            + leading * 0.25
            + capital * 0.20
            + structure * 0.15
            + resilience * 0.15
        )

    def derive_limit_up_type(self, row: ThemeLeaderInput) -> str:
        if row.is_limit_up and row.is_leader:
            return "leader_limit_up"
        if row.is_limit_up:
            return "limit_up"
        if row.pct_chg >= 5:
            return "strong_up"
        return "normal"

    def assign_role_label(self, rows: list[ThemeLeaderCandidate], index: int) -> str:
        candidate = rows[index]
        if index == 0:
            return "龙头"
        if index == 1:
            return "龙二" if candidate.is_limit_up else "卡位"
        if index == 2:
            if candidate.is_limit_up:
                return "补涨"
            if candidate.composite_score >= 60:
                return "强趋势"
            return "套利"
        return "淘汰"

    def build_evidence(self, row: ThemeLeaderInput, candidate: ThemeLeaderCandidate) -> list[str]:
        evidence = [
            f"题材内排序 {row.rank_order}",
            f"涨跌幅 {row.pct_chg:.2f}%",
            f"换手率 {row.turnover_rate:.2f}",
            f"量比 {row.volume_ratio:.2f}",
            f"涨停类型 {candidate.limit_up_type}",
        ]
        if row.position_label:
            evidence.append(f"K线位置 {row.position_label}")
        if row.pattern_labels:
            evidence.append(f"K线形态 {'/'.join(row.pattern_labels)}")
        return evidence

    def build_theme_candidates(self, rows: list[ThemeLeaderInput]) -> list[ThemeLeaderCandidate]:
        if not rows:
            return []
        scored: list[ThemeLeaderCandidate] = []
        for row in rows:
            purity = self.compute_purity_score(row)
            leading = self.compute_leading_score(row)
            capital = self.compute_capital_score(row)
            structure = self.compute_structure_score(row)
            resilience = self.compute_resilience_score(row)
            composite = self.compute_composite_score(purity, leading, capital, structure, resilience)
            scored.append(
                ThemeLeaderCandidate(
                    trade_date=row.trade_date,
                    subject_key=row.subject_key,
                    theme_name=row.theme_name,
                    stock_id=row.stock_id,
                    stock_name=row.stock_name,
                    purity_score=purity,
                    leading_score=leading,
                    capital_score=capital,
                    structure_score=structure,
                    resilience_score=resilience,
                    composite_score=composite,
                    is_limit_up=row.is_limit_up,
                    limit_up_type=self.derive_limit_up_type(row),
                    turnover_rate=row.turnover_rate,
                    volume_ratio=row.volume_ratio,
                    main_net_inflow=row.main_net_inflow,
                    is_new_stock=row.is_new_stock,
                    candidate_rank=0,
                    role_label="",
                    evidence=[],
                )
            )

        scored.sort(key=lambda item: (-item.composite_score, -item.leading_score, item.stock_id))
        if len(scored) <= 4:
            selected = list(scored)
        else:
            selected = [scored[0], scored[1], scored[2], scored[-1]]

        results: list[ThemeLeaderCandidate] = []
        row_map = {row.stock_id: row for row in rows}
        for idx, candidate in enumerate(selected, start=1):
            updated = ThemeLeaderCandidate(
                **{
                    **candidate.__dict__,
                    "candidate_rank": idx,
                    "role_label": self.assign_role_label(selected, idx - 1),
                    "evidence": self.build_evidence(row_map[candidate.stock_id], candidate),
                }
            )
            results.append(updated)
        return results
