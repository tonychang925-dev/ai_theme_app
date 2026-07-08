"""P2.7 — PDF Parser for analyst recap documents.

Extracts key metrics and narratives from analyst PDFs using pdfplumber.
Supplements auto-generated chart data with analyst-verified numbers.
"""

from __future__ import annotations

import re
from datetime import date
from pathlib import Path
from typing import Any


class AnalystPdfParser:
    """Parse analyst recap PDF and extract structured metrics."""

    def parse(self, pdf_path: str | Path) -> dict[str, Any]:
        try:
            import pdfplumber
            return self._parse_with_pdfplumber(Path(pdf_path))
        except ImportError:
            return self._parse_with_pdftotext(Path(pdf_path))

    def _parse_with_pdfplumber(self, path: Path) -> dict[str, Any]:
        import pdfplumber

        result: dict[str, Any] = {
            "source": str(path),
            "pages_parsed": 0,
            "text_pages": [],
            "metrics": {},
            "narrative": "",
            "key_phrases": [],
        }

        try:
            with pdfplumber.open(path) as pdf:
                result["pages_parsed"] = len(pdf.pages)
                full_text = ""

                for i, page in enumerate(pdf.pages):
                    text = page.extract_text() or ""
                    if text.strip():
                        result["text_pages"].append(i + 1)
                        full_text += text + "\n"

                result["narrative"] = full_text[:2000]

                # ── Extract metrics ──
                # 涨停数量: try regex first, then nearest-number-before-"涨停家数"
                lu = None
                m = re.search(r'涨停[家数]*\s*(\d+)\s*家', full_text)
                if m: lu = int(m.group(1))
                if not lu:
                    m = re.search(r'(\d+)\s*家\s*涨停', full_text)
                    if m: lu = int(m.group(1))
                if not lu:
                    idx = full_text.find("涨停家数") if "涨停家数" in full_text else full_text.find("涨停")
                    if idx > 0:
                        before = full_text[max(0, idx-30):idx]
                        nums = re.findall(r'\b(\d+)\b', before)
                        for n in reversed(nums):
                            v = int(n)
                            if 10 <= v <= 500:
                                lu = v
                                break
                if lu and 10 <= lu <= 500:
                    result["metrics"]["limit_up_count"] = lu

                # 成交量 (万亿 or 亿)
                # Match "成交量 2.5W 亿" or "2.5W" near 成交量 — split across lines
                m = re.search(r'成交量?\s*(\d+\.?\d*)\s*[万亿W]', full_text)
                if not m:
                    m = re.search(r'(\d+\.?\d*)\s*W?\s*\n?\s*[今天]*成交量', full_text)
                if not m:
                    m = re.search(r'(\d+\.?\d*)W', full_text)
                if m:
                    val = float(m.group(1))
                    result["metrics"]["turnover_wan_yi"] = val  # 2.5 in "2.5W 亿" = 2.5万亿

                # 情绪节点
                for phrase in ["情绪冰点", "情绪修复", "情绪高潮", "情绪分歧", "情绪退潮", "情绪发酵"]:
                    if phrase in full_text:
                        result["metrics"]["emotion_node_text"] = phrase
                        break

                # 最高换手板
                m = re.search(r'最高换手板[：:]\s*(\S+)', full_text)
                if m:
                    result["metrics"]["max_turnover_board"] = m.group(1)

                # 减仓/风控信号
                if "减仓" in full_text:
                    result["metrics"]["risk_signal"] = "减仓"

                # ── Key phrases ──
                phrases = []
                for p in ["情绪冰点", "新题材", "如有必干", "最高换手板", "做情绪连扳",
                           "机构资金审美", "台风概念", "减仓", "等待修复"]:
                    if p in full_text:
                        phrases.append(p)
                result["key_phrases"] = phrases

        except Exception as e:
            result["error"] = str(e)

        return result

    def _parse_with_pdftotext(self, path: Path) -> dict[str, Any]:
        import subprocess
        import tempfile

        result: dict[str, Any] = {
            "source": str(path),
            "metrics": {},
            "narrative": "",
            "key_phrases": [],
        }

        try:
            text = subprocess.check_output(
                ["pdftotext", "-layout", str(path), "-"],
                timeout=30, text=True
            )
            result["narrative"] = text[:2000]

            # Same extraction patterns
            m = re.search(r'涨停[家数]*\s*(\d+)\s*家', text)
            if m:
                result["metrics"]["limit_up_count"] = int(m.group(1))

            m = re.search(r'成交量?\s*([\d.]+)\s*[万亿]', text)
            if m:
                result["metrics"]["turnover_wan_yi"] = float(m.group(1))

        except Exception as e:
            result["error"] = str(e)

        return result


def parse_analyst_pdf(pdf_path: str, trade_date: date | None = None) -> dict[str, Any]:
    """Quick parse an analyst PDF and return structured metrics."""
    parser = AnalystPdfParser()
    result = parser.parse(pdf_path)

    if trade_date:
        result["trade_date"] = trade_date.isoformat()

    return result
