"""M5a: Eastmoney research report client (via akshare)."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import date
from typing import Any

import akshare as ak

SOURCE_NAME = "eastmoney"
ENDPOINT_KEY = "research_report"


@dataclass(frozen=True)
class ResearchReportResult:
    stock_code: str
    stock_name: str
    title: str
    organization: str | None
    publish_date: date | None
    rating: str | None
    eps_2026: float | None
    eps_2027: float | None
    eps_2028: float | None
    pe_2026: float | None
    pe_2027: float | None
    pe_2028: float | None
    industry: str | None
    pdf_url: str | None
    source_trace_id: str


class ResearchReportClient:
    """Eastmoney research report metadata client (akshare wrapper)."""

    def __init__(self) -> None:
        pass

    async def fetch_reports(
        self, stock_code: str, trade_date: date, stock_name: str = "",
    ) -> list[ResearchReportResult]:
        td_str = trade_date.isoformat()
        try:
            df = await asyncio.to_thread(
                ak.stock_research_report_em, symbol=stock_code,
            )
        except Exception:
            return []

        if df is None or df.empty:
            return []

        results: list[ResearchReportResult] = []
        for _, row in df.iterrows():
            try:
                pub_str = str(row.get("日期") or "")
                pub_date = None
                try:
                    pub_date = date.fromisoformat(pub_str)
                except ValueError:
                    continue

                # Include reports within 90 days
                if (trade_date - pub_date).days > 90:
                    continue

                results.append(ResearchReportResult(
                    stock_code=stock_code,
                    stock_name=stock_name or str(row.get("股票简称", stock_code)),
                    title=str(row.get("报告名称") or ""),
                    organization=str(row.get("机构") or ""),
                    publish_date=pub_date,
                    rating=str(row.get("东财评级") or ""),
                    eps_2026=_safe_float(row.get("2026-盈利预测-收益")),
                    eps_2027=_safe_float(row.get("2027-盈利预测-收益")),
                    eps_2028=_safe_float(row.get("2028-盈利预测-收益")),
                    pe_2026=_safe_float(row.get("2026-盈利预测-市盈率")),
                    pe_2027=_safe_float(row.get("2027-盈利预测-市盈率")),
                    pe_2028=_safe_float(row.get("2028-盈利预测-市盈率")),
                    industry=str(row.get("行业") or ""),
                    pdf_url=str(row.get("报告PDF链接") or ""),
                    source_trace_id=f"em_report:{stock_code}:{pub_str}:{row.get('报告名称','')[:40]}",
                ))
            except (ValueError, TypeError, KeyError):
                continue
        return results


def _safe_float(val: Any) -> float | None:
    try:
        return float(val)
    except (ValueError, TypeError):
        return None
