from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Dict, List


@dataclass
class AlertMessage:
    signal_level: str
    stock_id: str
    stock_name: str
    title: str
    content: str


class WeakToStrongAlertService:
    """弱转强提示渲染服务（P3）。"""

    def render(self, record: Dict[str, object]) -> AlertMessage:
        level = str(record.get("signal_level") or "X")
        stock_id = str(record.get("stock_id") or "")
        stock_name = str(record.get("stock_name") or stock_id)
        decision = str(record.get("decision") or "--")
        score = float(record.get("confirmation_score") or 0.0)
        data_status = str(record.get("data_status") or "")
        evidence = record.get("signal_evidence") or {}
        breakdown = ((evidence if isinstance(evidence, dict) else {}).get("scores") or {}).get("breakdown") or {}

        tags = {
            "A": "强确认",
            "B": "观察确认",
            "C": "放弃",
            "X": "数据异常",
        }
        tag = tags.get(level, "未知")
        title = f"[{level}/{tag}] {stock_name}({stock_id})"

        bullet = [
            f"decision={decision}",
            f"score={score:.2f}",
            f"data_status={data_status or '--'}",
        ]
        if isinstance(breakdown, dict):
            for key in ("auction_open_pct", "last_minute_volume_ratio", "plate_red_ratio", "plate_leader_strength"):
                if key in breakdown:
                    bullet.append(f"{key}={breakdown[key]}")
        content = " | ".join(bullet)
        return AlertMessage(
            signal_level=level,
            stock_id=stock_id,
            stock_name=stock_name,
            title=title,
            content=content,
        )

    def render_batch(self, trade_date: date, rows: List[Dict[str, object]]) -> Dict[str, object]:
        level_count = {"A": 0, "B": 0, "C": 0, "X": 0}
        messages: List[AlertMessage] = []
        for row in rows:
            msg = self.render(row)
            messages.append(msg)
            level_count[msg.signal_level] = level_count.get(msg.signal_level, 0) + 1

        return {
            "trade_date": trade_date.isoformat(),
            "total": len(rows),
            "level_count": level_count,
            "messages": [
                {
                    "signal_level": m.signal_level,
                    "stock_id": m.stock_id,
                    "stock_name": m.stock_name,
                    "title": m.title,
                    "content": m.content,
                }
                for m in messages
            ],
        }

