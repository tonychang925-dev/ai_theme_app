from __future__ import annotations

import json
from dataclasses import asdict, is_dataclass
from datetime import date
from pathlib import Path
from typing import Any

from stock_processing_service.application.replay.replay_runner import ReplayRunReport


class ReplayReportWriter:
    def __init__(self, root: str | Path = "reports/replay") -> None:
        self._root = Path(root)

    def write_matrix(
        self,
        *,
        trade_date: date,
        reports: list[ReplayRunReport | dict[str, Any]],
    ) -> dict[str, str]:
        day_dir = self._root / trade_date.strftime("%Y%m%d")
        day_dir.mkdir(parents=True, exist_ok=True)
        payload = [self._to_dict(report) for report in reports]
        json_path = day_dir / "replay_matrix.json"
        md_path = day_dir / "replay_matrix.md"
        json_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2, default=str),
            encoding="utf-8",
        )
        md_path.write_text(self._to_markdown(payload), encoding="utf-8")
        return {"json": str(json_path), "md": str(md_path)}

    @classmethod
    def _to_dict(cls, value: ReplayRunReport | dict[str, Any]) -> dict[str, Any]:
        if isinstance(value, dict):
            return dict(value)
        if is_dataclass(value):
            payload = asdict(value)
        else:
            payload = dict(value)
        payload["trade_date"] = str(payload.get("trade_date") or "")
        payload["mode"] = str(payload.get("mode") or "")
        payload["ok"] = bool(getattr(value, "ok", payload.get("ok", False)))
        return payload

    @staticmethod
    def _to_markdown(payload: list[dict[str, Any]]) -> str:
        lines = [
            "# Replay Matrix",
            "",
            "| case_name | trade_date | stock_id | mode | ok | layers | assertions |",
            "|---|---|---|---|---:|---|---|",
        ]
        for row in payload:
            layers = row.get("layer_results") or []
            layer_text = ", ".join(
                f"{r.get('layer_name')}:{r.get('status')}" if isinstance(r, dict) else str(r)
                for r in layers
            )
            assertions = row.get("assertions") or {}
            diagnostics = assertions.get("diagnostics") if isinstance(assertions.get("diagnostics"), dict) else {}
            candidate_miss = diagnostics.get("candidate_miss") if isinstance(diagnostics.get("candidate_miss"), dict) else {}
            selection = candidate_miss.get("selection") if isinstance(candidate_miss.get("selection"), dict) else {}
            ranking = candidate_miss.get("ranking") if isinstance(candidate_miss.get("ranking"), dict) else {}
            assertion_text = "passed=" + str(assertions.get("passed", ""))
            reason = selection.get("not_selected_reason", "")
            rank_text = "observe_rank={}/{}".format(
                ranking.get("observe_rank"),
                ranking.get("observe_total"),
            )
            lines.append(
                "| {case} | {date} | {stock} | {mode} | {ok} | {layers} | {assertions}; {reason}; {rank} |".format(
                    case=row.get("case_name", ""),
                    date=row.get("trade_date", ""),
                    stock=row.get("stock_id", ""),
                    mode=row.get("mode", ""),
                    ok=str(bool(row.get("ok"))).lower(),
                    layers=layer_text.replace("|", "\\|"),
                    assertions=assertion_text.replace("|", "\\|"),
                    reason=str(reason).replace("|", "\\|"),
                    rank=rank_text.replace("|", "\\|"),
                )
            )
            failed = [
                (key, detail)
                for key, detail in ((assertions.get("layer_results") or {}).items())
                if isinstance(detail, dict) and detail.get("passed") is not True
            ]
            if failed:
                lines.extend(["", f"## {row.get('case_name', '')} Failed Assertions", ""])
                for key, detail in failed:
                    lines.append(
                        "- `{key}` expected `{expected}` actual `{actual}`".format(
                            key=key,
                            expected=detail.get("expected"),
                            actual=detail.get("actual"),
                        )
                    )
        return "\n".join(lines) + "\n"
