"""M4b: CNInfo announcement normalizer.

Converts CNInfo raw response to evidence rows for stock_theme_reason_evidence.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date
from typing import Any


@dataclass(frozen=True)
class AnnouncementEvidence:
    trade_date: date
    stock_code: str
    stock_name: str
    announcement_id: str
    title: str
    announcement_type: str  # e.g. "业绩预告", "重大合同", "资产重组"
    pdf_url: str = ""
    source_name: str = "cninfo"
    endpoint_key: str = "cninfo_announcements"
    source_trace_id: str = ""


# Keywords that indicate event-driven announcements (not routine ones)
EVENT_KEYWORDS = re.compile(
    r"业绩预告|业绩快报|重大合同|中标|资产重组|收购|出售资产"
    r"|对外投资|战略合作|框架协议|政府补助|获得认证"
    r"|定增|配股|可转债|股权激励|回购|分红"
    r"|停产|复产|限售解禁|股东减持|股东增持"
    r"|董事长|总经理|变更|处罚|立案|诉讼"
    r"|新产品|新产线|技术突破|研发进展|临床试验"
    r"|退市风险|撤销.*风险|ST|\\*ST"
)

# Routine/low-value announcement patterns to skip
SKIP_PATTERNS = re.compile(
    r"独立董事|监事会|股东大会|年度报告|季度报告|半年度报告"
    r"|审计报告|内部控制|法律意见书|保荐机构|核查意见"
    r"|权益分派实施|变更登记|营业执照|公司章程"
    r"|投资者关系|调研活动|路演|说明会"
    r"|关于.*的补充公告|更正|提示性公告|临时受托管理"
    r"|债券.*付息|债券.*兑付|债券.*回售"
)


class CninfoAnnouncementNormalizer:
    """Normalizes CNInfo announcement responses into evidence rows."""

    def normalize(
        self,
        payload: dict[str, Any],
        trade_date: date,
    ) -> list[AnnouncementEvidence]:
        classified = payload.get("classifiedAnnouncements") or []
        results: list[AnnouncementEvidence] = []
        seen: set[str] = set()

        for group in classified:
            if not isinstance(group, list):
                continue
            for item in group:
                if not isinstance(item, dict):
                    continue
                stock_code = str(item.get("secCode") or "")
                stock_name = str(item.get("secName") or "")
                title = str(item.get("announcementTitle") or "")
                ann_id = str(item.get("announcementId") or "")
                ann_type = str(item.get("announcementTypeName") or "")
                pdf = str(item.get("adjunctUrl") or "")

                if not stock_code or not title:
                    continue
                if ann_id in seen:
                    continue
                seen.add(ann_id)

                # Filter: skip routine/non-event announcements
                if SKIP_PATTERNS.search(title):
                    continue

                results.append(AnnouncementEvidence(
                    trade_date=trade_date,
                    stock_code=stock_code,
                    stock_name=stock_name,
                    announcement_id=ann_id,
                    title=title.strip(),
                    announcement_type=ann_type,
                    pdf_url=f"http://static.cninfo.com.cn/{pdf}" if pdf else "",
                    source_trace_id=f"cninfo:{ann_id}",
                ))
        return results
