#!/usr/bin/env python3
"""
P0-C1 subset validation: run 7 AR glasses role_guard miss cases
through the updated ThemeMatchEngine and check recovery.
"""

import asyncio
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from theme_service.services.theme_service import ThemeService

CASES = [
    ("pm_case_0003", "2025年1月3日，1月3日电，美国专利及商标局官网显示，英伟达公开了一项AR眼镜专利（US20250004275A1），名为\"无背光增强现实数字全息技术\"", "AR眼镜"),
    ("pm_case_0006", "24日讯，鸿海宣布，将携手Porotech进军AR眼镜市场", "AR眼镜"),
    ("pm_case_0010", "2024年11月20日，云天励飞战略投资闪极科技 后者将推国内首款量产AI拍摄眼镜", "AR眼镜"),
    ("pm_case_0017", "2024年9月18日，科技公司Snap在美国加利福尼亚州圣莫尼卡举办的2024Snap全球生态合作伙伴大会上，发布旗下第五代SpectaclesAR眼镜", "AR眼镜"),
    ("pm_case_0023", "2024年8月26日，小米已开发出一款AI眼镜，并将尽快推向市场", "AR眼镜"),
    ("pm_case_0024", "消息面上，据媒体报道，北京多屏未来科技有限公司已于近日完成数百万美元的A轮融资", "AR眼镜"),
    ("pm_case_0033", "2024年8月13日，**近日，扎克伯格在 SPC 黑客松活动上的一场对谈分享，不限于 AI 、AR、创业以及团队管理等经验", "AR眼镜"),
]


async def run_one(service: ThemeService, case_id: str, title: str, expected: str) -> dict:
    row = {
        "event_id": 1,
        "news_id": 1,
        "id": 1,
        "title": title,
        "content": title,
        "summary": title[:200],
        "event_type": "structured",
    }
    envelope = await service.match_event(row)
    decision = str(envelope.get("decision", "?"))
    subject_key = str(envelope.get("matched_subject_key", ""))
    subject_name = str(envelope.get("matched_theme_name", ""))
    confidence = float(envelope.get("confidence") or 0)
    reason = str(envelope.get("reason_code", ""))
    audit = envelope.get("audit") if isinstance(envelope.get("audit"), dict) else {}
    top_candidates = audit.get("top_candidates", [])[:3]

    # Check if gold is in top5
    gold_in_top5 = any(
        c.get("subject_name", "") == expected or expected in c.get("subject_name", "")
        for c in top_candidates
    )
    gold_is_primary = (decision == "MATCH" and subject_key == "9030409")

    # Check role_guard for AR glasses candidate
    ar_candidate = next((c for c in top_candidates if c.get("subject_key") == "9030409"), None)
    role_guard_blocked = ar_candidate.get("evidence", {}).get("role_guard_blocked", False) if ar_candidate else None
    valid_anchors = ar_candidate.get("evidence", {}).get("valid_anchor_terms", []) if ar_candidate else []

    return {
        "case_id": case_id,
        "title": title[:60],
        "decision": decision,
        "matched_subject_name": subject_name,
        "confidence": confidence,
        "reason_code": reason,
        "gold_match": subject_key == "9030409",
        "gold_in_top5": gold_in_top5,
        "ar_rank": next((i+1 for i, c in enumerate(top_candidates) if c.get("subject_key") == "9030409"), None),
        "ar_role_guard_blocked": role_guard_blocked,
        "ar_valid_anchors": valid_anchors[:8],
        "top3_names": [c.get("subject_name", "") for c in top_candidates],
        "top3_keys": [c.get("subject_key", "") for c in top_candidates],
        "top3_guard": [c.get("evidence", {}).get("role_guard_blocked", False) for c in top_candidates],
    }


async def main():
    os.environ.setdefault("DB_TYPE", "postgresql")
    os.environ.setdefault("PG_DATABASE", os.environ.get("PG_DATABASE", "stock_data"))
    from database_service.streams.gateway_integration import get_gateway
    gw = await get_gateway(enable_retry=True)
    service = ThemeService()
    service.set_database_gateway(gw)

    print("=" * 80)
    print("P0-C1 AR眼镜 Subset Validation")
    print("=" * 80)
    print()

    recovered = 0
    improved = 0
    unchanged = 0

    for case_id, title, expected in CASES:
        result = await run_one(service, case_id, title, expected)
        ar_blocked = result["ar_role_guard_blocked"]
        gold_hit = result["gold_match"]
        rank = result["ar_rank"]

        status = "---"
        if gold_hit:
            recovered += 1
            status = "RECOVERED"
        elif ar_blocked is False and rank == 1 and not gold_hit:
            # Gold is now unblocked and should match
            improved += 1
            status = "UNBLOCKED (decision pending)"
        elif ar_blocked is False:
            improved += 1
            status = "UNBLOCKED (not primary)"
        elif ar_blocked is True:
            unchanged += 1
            status = "STILL BLOCKED"
        else:
            unchanged += 1
            status = "NOT IN TOP5"

        print(f"[{status:30s}] {case_id} | AR rank={rank} | blocked={ar_blocked} | "
              f"valid_anchors={result['ar_valid_anchors'][:3]} | "
              f"match={result['matched_subject_name']} | {title[:50]}...")

    print()
    print("─" * 80)
    print(f"Recovered: {recovered}/7   Improved: {improved}/7   Unchanged: {unchanged}/7")
    print()

    await gw.close()


if __name__ == "__main__":
    asyncio.run(main())
