"""F10 资金动向本地采集脚本.

用途:
  - 在独立 Python 解释器中直接连接通达信行情链路
  - 拉取个股 F10 的「资金动向」正文
  - 将原始文本输出为 JSON，供主项目 runner 解析并落库

注意:
  - 不启动 HTTP 服务
  - 不依赖 stock_processing_service
"""
from __future__ import annotations

import argparse
import json
import logging
import re
import sys
from dataclasses import asdict, dataclass
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from tools.tdx_market_agent.tdx_client import TdxClient, parse_stock_id  # noqa: E402

TZ_CN = timezone(timedelta(hours=8))
logger = logging.getLogger("tdx_f10_collect")


def _now() -> str:
    return datetime.now(TZ_CN).isoformat()


def _strip_text(text: str) -> str:
    return text.replace("\r\n", "\n").replace("\r", "\n").strip()


def _extract_raw_text_from_dict(content: dict, *, requested_section: str = "") -> str:
    """mootdx F10(name=X) returns {section_name: text, ...}.

    Extract actual text content from the dict. Prioritize:
    1. Exact section name match
    2. Partial section name match (e.g. "资金" in key)
    3. Any value that looks like F10 content (>200 chars with ◇ marker)
    4. First non-empty value
    """
    if not content:
        return ""

    requested = str(requested_section or "").strip()

    # Exact match
    if requested and requested in content:
        return str(content[requested] or "")

    # Partial match on requested section
    if requested:
        for key, value in content.items():
            if requested in str(key):
                return str(value or "")

    # Any value that looks like F10 content
    for value in content.values():
        text = str(value or "").strip()
        if len(text) > 200 and "◇" in text:
            return text

    # Fallback: longest non-empty value
    best = ""
    for value in content.values():
        text = str(value or "").strip()
        if len(text) > len(best):
            best = text
    return best


def _extract_updated_date(content: dict) -> str | None:
    """Extract update date from F10 content dict."""
    # Check all values for 更新日期 pattern
    for value in content.values():
        text = str(value or "")
        match = re.search(r"更新日期[：:]\s*(\d{4}-\d{2}-\d{2})", text)
        if match:
            return match.group(1)
    return None


def _extract_stock_name(text: str) -> str | None:
    if not text:
        return None
    first_line = _strip_text(text).splitlines()[0] if _strip_text(text) else ""
    match = re.search(r"◇\d{6}\s+(.+?)\s+更新日期", first_line)
    if match:
        return match.group(1).strip()
    return None


@dataclass
class CollectRecord:
    stock_id: str
    system_stock_id: str
    stock_name: str | None
    source: str
    section: str
    source_updated_date: str | None
    raw_text: str
    connected_server: str
    ts: str


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="本地采集通达信 F10 资金动向正文")
    parser.add_argument("--symbols", required=True, help="逗号分隔股票代码，如 000001,600000")
    parser.add_argument("--trade-date", required=False, default="", help="交易日，仅用于回传元数据")
    parser.add_argument("--section", default="资金动向", help="F10 章节名，默认资金动向")
    parser.add_argument("--timeout", type=float, default=10.0, help="TDX 连接超时秒数")
    parser.add_argument("--log-level", default="INFO", choices=("DEBUG", "INFO", "WARNING", "ERROR"))
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format="%(asctime)s [%(levelname)s] %(message)s",
    )

    symbols = [item.strip() for item in str(args.symbols).split(",") if item.strip()]
    if not symbols:
        parser.error("至少提供一个股票代码")

    client = TdxClient(timeout=args.timeout)
    try:
        client.connect()
    except Exception as exc:
        logger.error("TDX 连接失败: %s", exc)
        return 2

    records: list[CollectRecord] = []
    errors: list[dict[str, Any]] = []
    total = len(symbols)
    for raw_symbol in symbols:
        numeric_symbol, system_symbol = parse_stock_id(raw_symbol)
        try:
            logger.info("progress %s/%s %s", len(records) + len(errors) + 1, total, numeric_symbol)
            content = client.get_f10_content(numeric_symbol, name=args.section)
            raw_text = ""
            source_updated_date = None
            if isinstance(content, dict):
                # mootdx F10(name=X) 返回 {section_name: text_content, ...}
                # section name 不一定是请求的 name，需要从 dict values 中提取正文
                raw_text = _extract_raw_text_from_dict(content, requested_section=args.section)
                source_updated_date = _extract_updated_date(content)
            elif isinstance(content, str):
                raw_text = content
            else:
                raw_text = str(content or "")
            raw_text = _strip_text(raw_text)
            records.append(
                CollectRecord(
                    stock_id=numeric_symbol,
                    system_stock_id=system_symbol,
                    stock_name=_extract_stock_name(raw_text),
                    source="tdx_mootdx",
                    section=args.section,
                    source_updated_date=str(source_updated_date).strip() if source_updated_date else None,
                    raw_text=raw_text,
                    connected_server=client.server_info,
                    ts=_now(),
                )
            )
        except Exception as exc:
            errors.append(
                {
                    "stock_id": numeric_symbol,
                    "system_stock_id": system_symbol,
                    "error": f"{type(exc).__name__}: {exc}",
                }
            )
            logger.warning("progress %s/%s %s failed: %s", len(records) + len(errors), total, numeric_symbol, exc)

    payload = {
        "ts": _now(),
        "trade_date": args.trade_date or None,
        "section": args.section,
        "connected_server": client.server_info,
        "record_count": len(records),
        "error_count": len(errors),
        "records": [asdict(item) for item in records],
        "errors": errors,
    }
    json.dump(payload, sys.stdout, ensure_ascii=False)
    sys.stdout.write("\n")
    client.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
