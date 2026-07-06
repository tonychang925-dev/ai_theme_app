from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date
from typing import Any


_CAPITAL_TARGET_SECTION = "资金动向"
_SECTION_MARKER_PATTERN = re.compile(r"(?m)^【([^】]+)】")
_DATE_PATTERN = re.compile(r"(?P<date>\d{4}-\d{2}-\d{2})")
_MONEY_PATTERN = re.compile(r"(?P<sign>[+-]?)(?P<value>\d+(?:\.\d+)?)(?P<unit>亿|万|元)")


def _normalize_stock_id(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    upper = text.upper()
    if "." in upper:
        head, tail = upper.rsplit(".", 1)
        if tail in {"SZ", "SH", "BJ"}:
            text = head
    digits = re.sub(r"\D", "", text)
    if len(digits) == 6:
        return digits
    return text


def _format_money(value: float | None) -> str:
    if value is None:
        return "--"
    sign = "-" if value < 0 else ""
    amount = abs(float(value))
    if amount >= 100000000:
        return f"{sign}{amount / 100000000:.2f}亿"
    if amount >= 10000:
        return f"{sign}{amount / 10000:.2f}万"
    return f"{sign}{amount:.0f}元"


def _parse_money(value: str | None) -> float | None:
    text = str(value or "").strip()
    if not text:
        return None
    match = _MONEY_PATTERN.search(text.replace(",", ""))
    if not match:
        return None
    amount = float(match.group("value"))
    if match.group("sign") == "-":
        amount = -amount
    unit = match.group("unit")
    if unit == "亿":
        return amount * 100000000
    if unit == "万":
        return amount * 10000
    return amount


def _split_rows(text: str) -> list[str]:
    return [line.strip() for line in text.replace("\r\n", "\n").replace("\r", "\n").splitlines() if line.strip()]


@dataclass(frozen=True)
class F10CapitalSection:
    title: str
    body: str


class F10CapitalParser:
    """Parse TongDaXin F10 资金动向正文 into cacheable evidence rows."""

    section_name = _CAPITAL_TARGET_SECTION

    def split_sections(self, text: str) -> list[F10CapitalSection]:
        if not text:
            return []
        markers = list(_SECTION_MARKER_PATTERN.finditer(text))
        if not markers:
            return [F10CapitalSection(title=self.section_name, body=text.strip())]

        sections: list[F10CapitalSection] = []
        header = text[: markers[0].start()].strip()
        if header:
            sections.append(F10CapitalSection(title="header", body=header))
        for idx, match in enumerate(markers):
            title = match.group(1).strip()
            start = match.end()
            end = markers[idx + 1].start() if idx + 1 < len(markers) else len(text)
            body = text[start:end].strip()
            sections.append(F10CapitalSection(title=title, body=body))
        return sections

    def parse(
        self,
        *,
        stock_id: str,
        stock_name: str | None = None,
        trade_date: date | str | None = None,
        source_updated_date: date | str | None = None,
        raw_text: str,
        source: str = "tdx_f10",
        section: str = _CAPITAL_TARGET_SECTION,
    ) -> dict[str, Any]:
        normalized_stock_id = _normalize_stock_id(stock_id)
        text = str(raw_text or "").strip()
        split_sections = self.split_sections(text)
        sections = {section.title: section.body for section in split_sections if section.title}

        dragon_tiger = self._parse_dragon_tiger(sections.get("1.交易龙虎榜", ""))
        block_trade = self._parse_block_trade(sections.get("2.大宗交易", ""))
        margin_trading = self._parse_margin_trading(sections.get("3.融资融券", ""))
        capital_flow = self._parse_capital_flow(sections.get("4.资金流向", ""))
        strategic_lending = self._parse_strategic_lending(sections.get("5.战略配售可出借", ""))

        section_hits = [
            name for name, body in (
                ("1.交易龙虎榜", dragon_tiger.get("summary")),
                ("2.大宗交易", block_trade.get("summary")),
                ("3.融资融券", margin_trading.get("summary")),
                ("4.资金流向", capital_flow.get("summary")),
                ("5.战略配售可出借", strategic_lending.get("summary")),
            )
            if body
        ]

        parse_status = "ok"
        if not text:
            parse_status = "empty"
        elif not section_hits:
            parse_status = "partial"

        return {
            "trade_date": trade_date.isoformat() if isinstance(trade_date, date) else (str(trade_date).strip() if trade_date else None),
            "stock_id": normalized_stock_id,
            "stock_name": str(stock_name or "").strip() or None,
            "source": source,
            "section": section,
            "source_updated_date": (
                source_updated_date.isoformat() if isinstance(source_updated_date, date)
                else (str(source_updated_date).strip() if source_updated_date else None)
            ),
            "dragon_tiger_json": dragon_tiger,
            "block_trade_json": block_trade,
            "margin_trading_json": margin_trading,
            "capital_flow_json": capital_flow,
            "strategic_lending_json": strategic_lending,
            "raw_text": text or None,
            "parse_status": parse_status,
            "diagnostics": {
                "section_count": max(0, len(split_sections) - (1 if split_sections and split_sections[0].title == "header" else 0)),
                "section_hits": section_hits,
                "has_raw_text": bool(text),
                "normalized_stock_id": normalized_stock_id,
            },
        }

    @staticmethod
    def _parse_dragon_tiger(body: str) -> dict[str, Any]:
        text = body.strip()
        if not text:
            return {"has_lhb": False, "summary": "暂无数据", "details": []}
        has_lhb = "未能登上龙虎榜" not in text and "暂无数据" not in text
        summary = text.splitlines()[0].strip() if text.splitlines() else text
        latest_date = None
        date_match = _DATE_PATTERN.search(text)
        if date_match:
            latest_date = date_match.group("date")
        return {"has_lhb": has_lhb, "latest_date": latest_date, "summary": summary, "details": _split_rows(text)}

    @staticmethod
    def _parse_block_trade(body: str) -> dict[str, Any]:
        text = body.strip()
        if not text:
            return {"summary": "暂无数据", "details": []}
        return {"summary": text.splitlines()[0].strip() if text.splitlines() else text, "details": _split_rows(text)}

    def _parse_margin_trading(self, body: str) -> dict[str, Any]:
        text = body.strip()
        if not text:
            return {"summary": "暂无数据", "details": []}
        rows = _split_rows(text)
        latest_date = None
        latest_line = ""
        for line in rows:
            match = _DATE_PATTERN.search(line)
            if match and "融资融券信息" in line:
                latest_date = match.group("date")
                latest_line = line
                break
        if not latest_line:
            latest_line = rows[0] if rows else text
        summary = latest_line
        if latest_date:
            summary = latest_line.replace(f"{latest_date}融资融券信息：", "").replace(f"{latest_date}融资融券信息:", "").strip() or latest_line
        return {
            "latest_date": latest_date,
            "summary": summary,
            "details": rows,
        }

    def _parse_capital_flow(self, body: str) -> dict[str, Any]:
        text = body.strip()
        if not text:
            return {"summary": "暂无数据", "details": []}

        rows = _split_rows(text)
        data_row = ""
        for line in rows:
            if _DATE_PATTERN.match(line) and ("│" in line or "|" in line):
                data_row = line
                break

        if not data_row:
            return {"summary": rows[0] if rows else "暂无数据", "details": rows}

        parts = [part.strip() for part in re.split(r"[│|]", data_row) if part.strip()]
        latest_date = parts[0] if parts else None
        main_net_inflow = _parse_money(parts[1] if len(parts) > 1 else None)
        super_large_net_inflow = _parse_money(parts[3] if len(parts) > 3 else None)
        large_net_inflow = _parse_money(parts[5] if len(parts) > 5 else None)
        main_buy_net = _parse_money(parts[7] if len(parts) > 7 else None)

        def format_flow(prefix: str, value: float | None) -> str:
            if value is None:
                return ""
            direction = "净流出" if value < 0 else "净流入"
            return f"{prefix}{direction}{_format_money(abs(value))}"

        summary_parts = []
        for prefix, value in (
            ("主力", main_net_inflow),
            ("超大单", super_large_net_inflow),
            ("大单", large_net_inflow),
        ):
            text_part = format_flow(prefix, value)
            if text_part:
                summary_parts.append(text_part)
        if main_buy_net is not None:
            summary_parts.append(f"主买净额{_format_money(main_buy_net)}")

        summary = "，".join(summary_parts) if summary_parts else rows[0]
        return {
            "latest_date": latest_date,
            "main_net_inflow": main_net_inflow,
            "super_large_net_inflow": super_large_net_inflow,
            "large_net_inflow": large_net_inflow,
            "main_buy_net": main_buy_net,
            "summary": summary,
            "details": rows,
        }

    @staticmethod
    def _parse_strategic_lending(body: str) -> dict[str, Any]:
        text = body.strip()
        if not text:
            return {"summary": "暂无数据", "details": []}
        return {"summary": text.splitlines()[0].strip() if text.splitlines() else text, "details": _split_rows(text)}
