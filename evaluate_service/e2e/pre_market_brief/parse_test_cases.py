from __future__ import annotations

import argparse
import re
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

if __package__ in (None, ""):
    sys.path.append(str(Path(__file__).resolve().parents[3]))
    from evaluate_service.e2e.pre_market_brief.common import default_output_dir, ensure_dir, ensure_no_gold_leak, write_json, write_jsonl
else:
    from .common import default_output_dir, ensure_dir, ensure_no_gold_leak, write_json, write_jsonl

HEADER_RE = re.compile(r"^测试集\d+\s*:\s*题材名称\s*:\s*(.+?)\s*$")


def _make_title(content: str, max_len: int = 80) -> str:
    text = content.strip().strip("*")
    for sep in ("。", "！", "？", "\n"):
        if sep in text:
            candidate = text.split(sep, 1)[0].strip()
            if candidate:
                text = candidate
                break
    return text[:max_len] or "盘前必读回放新闻"


def parse_test_cases_file(
    path: Path,
    *,
    run_id: str,
    trade_date: str,
    limit: int | None = None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    input_rows: list[dict[str, Any]] = []
    gold_rows: list[dict[str, Any]] = []
    current_theme: str | None = None
    base_time = datetime.strptime(f"{trade_date}T07:00:00", "%Y-%m-%dT%H:%M:%S")

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line:
            continue
        header = HEADER_RE.match(line)
        if header:
            current_theme = header.group(1).strip()
            continue
        if not line.startswith("-"):
            continue
        if not current_theme:
            raise ValueError(f"新闻行缺少测试集题材标题: {line[:80]}")
        content = line.lstrip("-").strip()
        if not content:
            continue
        case_no = len(input_rows) + 1
        case_id = f"pm_case_{case_no:04d}"
        external_id = f"{run_id}:{case_id}"
        publish_time = base_time + timedelta(seconds=case_no)
        input_payload = {
            "external_id": external_id,
            "news_id": external_id,
            "title": _make_title(content),
            "content": content,
            "source": "akshare_replay",
            "source_channel": "akshare_replay",
            "publish_date": trade_date,
            "publish_time": publish_time.isoformat(),
            "collected_at": publish_time.isoformat(),
            "url": f"e2e://{run_id}/{case_id}",
            "run_id": run_id,
            "case_id": case_id,
            "type": "raw_news",
        }
        ensure_no_gold_leak(input_payload, context=case_id)
        input_rows.append(input_payload)
        gold_rows.append(
            {
                "case_id": case_id,
                "external_id": external_id,
                "gold_theme_name": current_theme,
            }
        )
        if limit and len(input_rows) >= limit:
            break

    return input_rows, gold_rows


def main() -> None:
    parser = argparse.ArgumentParser(description="解析盘前必读 E2E 测试集，分离程序输入与 gold label。")
    parser.add_argument("--test-cases", default="evaluate_service/data/raw/test_cases.txt")
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--trade-date", required=True)
    parser.add_argument("--limit", type=int)
    parser.add_argument("--out-dir")
    args = parser.parse_args()

    out_dir = ensure_dir(Path(args.out_dir) if args.out_dir else default_output_dir(args.run_id))
    input_rows, gold_rows = parse_test_cases_file(
        Path(args.test_cases),
        run_id=args.run_id,
        trade_date=args.trade_date,
        limit=args.limit,
    )
    input_path = out_dir / "input_news.jsonl"
    gold_path = out_dir / "gold_labels.jsonl"
    write_jsonl(input_path, input_rows)
    write_jsonl(gold_path, gold_rows)
    write_json(
        out_dir / "parse_result.json",
        {
            "run_id": args.run_id,
            "trade_date": args.trade_date,
            "input_count": len(input_rows),
            "gold_count": len(gold_rows),
            "input_path": str(input_path),
            "gold_path": str(gold_path),
        },
    )
    print(f"parsed input_count={len(input_rows)} gold_count={len(gold_rows)} out_dir={out_dir}")


if __name__ == "__main__":
    main()
