"""P2.6.1 — Evidence Artifact Layer.

Links analyst charts/tables to Emotion/Cognition/Playbook modules
as traceable evidence. MVP: JSON file storage, no DB migration.
"""

from __future__ import annotations

import json
import uuid
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

ARTIFACT_ROOT = Path("tmp/evidence_artifacts")


class EvidenceArtifactService:
    """CRUD for evidence artifacts linked to emotion/cognition/playbook."""

    def __init__(self, root: Path | None = None) -> None:
        self.root = root or ARTIFACT_ROOT
        self.root.mkdir(parents=True, exist_ok=True)

    def list(self, trade_date: date, module: str | None = None) -> list[dict[str, Any]]:
        artifacts: list[dict[str, Any]] = []
        date_dir = self.root / trade_date.isoformat()
        if not date_dir.exists():
            # Seed defaults for known dates
            return self._seed(trade_date, module)
        for f in sorted(date_dir.glob("*.json")):
            a = json.loads(f.read_text(encoding="utf-8"))
            if module and a.get("related_module") != module:
                continue
            artifacts.append(a)
        if not artifacts:
            return self._seed(trade_date, module)
        return artifacts

    def add(self, artifact: dict[str, Any]) -> dict[str, Any]:
        td = artifact.get("trade_date", "")
        date_dir = self.root / td
        date_dir.mkdir(parents=True, exist_ok=True)
        if not artifact.get("artifact_id"):
            artifact["artifact_id"] = f"evid_{uuid.uuid4().hex[:12]}"
        if not artifact.get("created_at"):
            artifact["created_at"] = datetime.now(timezone.utc).isoformat()
        path = date_dir / f"{artifact['artifact_id']}.json"
        path.write_text(json.dumps(artifact, ensure_ascii=False, indent=2), encoding="utf-8")
        return artifact

    def _seed(self, trade_date: date, module: str | None = None) -> list[dict[str, Any]]:
        """Seed default artifacts from known analyst PDF pages."""
        # 7/7 PDF artifacts
        artifacts = [
            {
                "artifact_id": "evid_77_emotion_breadth",
                "trade_date": "2026-07-07",
                "artifact_type": "table",
                "title": "大盘势能与情绪动能",
                "source": "analyst_pdf",
                "related_module": "emotion",
                "page_no": 4,
                "extracted_metrics": {
                    "limit_up_trend": "151→93→105→64→33",
                    "chain_board_trend": "21→18→16→7→5",
                    "emotion_momentum_trend": "高位→下滑→-12",
                    "key_finding": "涨停家数创近期新低，连板高度压缩"
                },
                "summary": "7/7涨停降至33家，连板降至5家，情绪动能降至-12。大盘势能快速收缩，赚钱效应减弱，短线情绪进入冰点。",
            },
            {
                "artifact_id": "evid_77_emotion_capital",
                "trade_date": "2026-07-07",
                "artifact_type": "chart",
                "title": "活跃资金成交量趋势",
                "source": "analyst_pdf",
                "related_module": "emotion",
                "page_no": 5,
                "extracted_metrics": {
                    "active_limitup_amount": "897亿",
                    "trend": "下降",
                    "key_finding": "活跃资金参与度明显下降"
                },
                "summary": "活跃资金成交量降至897亿，短线资金参与度明显下降。资金从高位科技持续流出，未见明显回流。",
            },
            {
                "artifact_id": "evid_77_emotion_relay",
                "trade_date": "2026-07-07",
                "artifact_type": "table",
                "title": "核心板块节律与连板天梯",
                "source": "analyst_pdf",
                "related_module": "emotion",
                "page_no": 6,
                "extracted_metrics": {
                    "max_board_height": "下降",
                    "promotion_rates": "一进二/二进三/三进四晋级率全面下降",
                    "key_finding": "接力生态退潮，高度压制"
                },
                "summary": "最高板高度下降，一进二/二进三/三进四晋级率全面下滑。接力生态进入退潮期，新高度尚未打开。",
            },
            {
                "artifact_id": "evid_77_style_institution",
                "trade_date": "2026-07-07",
                "artifact_type": "table",
                "title": "机构资金审美方向",
                "source": "analyst_pdf",
                "related_module": "emotion",
                "page_no": 7,
                "extracted_metrics": {
                    "institution_trend_state": "多数仍在调整",
                    "key_finding": "机构趋势方向退潮，防御为主"
                },
                "summary": "机构资金审美方向多数仍在调整期。高位科技方向持续受压，机构转向防御。",
            },
            {
                "artifact_id": "evid_77_style_hotmoney",
                "trade_date": "2026-07-07",
                "artifact_type": "table",
                "title": "情绪资金/游资方向节奏",
                "source": "analyst_pdf",
                "related_module": "emotion",
                "page_no": 8,
                "extracted_metrics": {
                    "hot_money_state": "游资方向尚未全面恢复",
                    "key_finding": "游资试探性操作，未形成合力"
                },
                "summary": "游资方向尚未全面恢复，仅少数方向有试探性操作。未形成板块合力，需观察新题材出现。",
            },
            {
                "artifact_id": "evid_77_cognition_limitup",
                "trade_date": "2026-07-07",
                "artifact_type": "chart",
                "title": "7/7涨停复盘图",
                "source": "analyst_pdf",
                "related_module": "cognition",
                "page_no": 10,
                "extracted_metrics": {
                    "key_finding": "涨停分布集中在机器人/通信/上游材料等方向"
                },
                "summary": "涨停个股主要分布在机器人、通信/CPO、上游材料等方向。题材结构分散，无明确主线。",
            },
        ]

        if module:
            artifacts = [a for a in artifacts if a["related_module"] == module]

        # Only seed for the exact date that matches
        if trade_date.isoformat() == "2026-07-07":
            for a in artifacts:
                self.add(a)
            return artifacts

        return []
