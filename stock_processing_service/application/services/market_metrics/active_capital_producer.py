"""ActiveCapitalProducer v1.

Produces analyst-style short-term active capital from BoardPoolSnapshot only.
No analyst labels, no fixed multipliers, no theme/money-flow inference.
"""

from __future__ import annotations

from dataclasses import dataclass

from .board_pool_snapshot import BoardPoolSnapshot


@dataclass(frozen=True, slots=True)
class ActiveCapitalComponent:
    type: str
    amount_yi: float
    source: str


@dataclass(frozen=True, slots=True)
class ActiveCapitalSnapshot:
    value_yi: float | None
    method: str
    quality: str
    confidence: float
    components: tuple[ActiveCapitalComponent, ...]
    missing: tuple[str, ...]


class ActiveCapitalProducer:
    """Produce active capital from persisted board-pool amounts."""

    METHOD = "board_pool_zt_zb_v1"

    def produce(self, board_pool: BoardPoolSnapshot) -> ActiveCapitalSnapshot:
        components: list[ActiveCapitalComponent] = []
        missing = list(board_pool.diagnostics.get("missing") or ())

        if board_pool.zt.amount_yi is not None:
            components.append(
                ActiveCapitalComponent(
                    type="ZT",
                    amount_yi=board_pool.zt.amount_yi,
                    source=board_pool.zt.amount_source or board_pool.source,
                )
            )
        if board_pool.zb.amount_yi is not None:
            components.append(
                ActiveCapitalComponent(
                    type="ZB",
                    amount_yi=board_pool.zb.amount_yi,
                    source=board_pool.zb.amount_source or board_pool.source,
                )
            )

        has_zt = board_pool.zt.amount_yi is not None
        has_zb = board_pool.zb.amount_yi is not None
        has_yzt = board_pool.yzt.amount_yi is not None

        if has_zt and has_zb:
            value = round(board_pool.zt.amount_yi + board_pool.zb.amount_yi, 2)
            quality = "FULL" if has_yzt else "PARTIAL"
            confidence = 0.95 if has_yzt else 0.85
        elif has_zt:
            value = None
            quality = "DEGRADED"
            confidence = 0.60
            if "board_pool.zb.amount_yi" not in missing:
                missing.append("board_pool.zb.amount_yi")
        else:
            value = None
            quality = "MISSING"
            confidence = 0.0
            for field in ("board_pool.zt.amount_yi", "board_pool.zb.amount_yi"):
                if field not in missing:
                    missing.append(field)

        return ActiveCapitalSnapshot(
            value_yi=value,
            method=self.METHOD,
            quality=quality,
            confidence=confidence,
            components=tuple(components),
            missing=tuple(missing),
        )
