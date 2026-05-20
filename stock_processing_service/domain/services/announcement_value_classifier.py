"""P1-D2: 公告价值分类器。

按标题+公告类型将 raw_intel_document 分为 A/B/C/D 四级，
控制 PDF 解析和 LLM 抽取的优先级。
"""
from __future__ import annotations

from typing import Any, Dict

# A 类：最高优先级 — 公司经营/业绩/风险/资本动作
A_CLASS_KEYWORDS = [
    "重大合同", "中标", "订单", "项目投资", "产能建设",
    "业绩预告", "业绩快报", "年报", "季报", "半年报",
    "回购", "增持", "减持", "并购", "重组", "资产收购", "资产出售",
    "控制权变更", "实际控制人变更",
    "立案调查", "行政处罚", "风险提示", "退市风险", "ST",
    "诉讼", "仲裁", "债务违约", "资产减值", "商誉减值",
    "重大资产重组", "要约收购", "吸收合并",
]

# B 类：中等优先级 — 公司治理/常规披露
B_CLASS_KEYWORDS = [
    "分红", "权益分派", "股权激励", "员工持股计划",
    "关联交易", "担保", "质押",
    "高管变更", "董事会决议", "监事会决议", "股东大会决议",
    "非公开发行", "可转债", "配股",
]

# C 类：低优先级 — 程序性/例行公告
C_CLASS_KEYWORDS = [
    "独立董事意见", "监事会意见", "董事会公告",
    "股东大会通知", "更正公告", "补充公告", "提示性公告",
    "制度修订", "章程修订", "公司章程",
]

# D 类：强过滤 — 中介机构材料
D_CLASS_KEYWORDS = [
    "保荐", "保荐机构", "保荐人", "持续督导", "督导报告",
    "核查意见", "专项核查", "核查报告",
    "法律意见书", "法律意见", "律师事务所",
    "会计师事务所", "审计报告", "鉴证报告",
    "独立财务顾问", "财务顾问报告", "财务顾问",
    "券商", "证券承销", "上市保荐书", "募集说明书",
    "承销保荐", "问询函回复", "问询函",
    "受托管理事务报告", "跟踪报告", "培训情况报告",
    "保荐总结报告书", "保荐工作报告",
    "督导跟踪报告", "年度持续督导", "保荐总结",
]


class AnnouncementValueClassifier:
    """按标题关键词分层公告价值。"""

    @staticmethod
    def classify(title: str, announcement_type: str = "") -> Dict[str, Any]:
        title_lower = title.lower() if title else ""
        ann_type_lower = (announcement_type or "").lower()

        # D 类优先检查（中介材料最高误判风险）
        d_matches = [kw for kw in D_CLASS_KEYWORDS if kw in title]
        if d_matches:
            return {
                "doc_value_level": "D",
                "doc_value_reason": f"中介机构材料: {', '.join(d_matches[:3])}",
                "should_parse_pdf": False,
                "should_llm_extract": False,
                "matched_keywords": d_matches,
            }

        # A 类：经营/业绩/风险/资本动作
        a_matches = [kw for kw in A_CLASS_KEYWORDS if kw in title]
        if a_matches:
            return {
                "doc_value_level": "A",
                "doc_value_reason": f"高价值经营公告: {', '.join(a_matches[:3])}",
                "should_parse_pdf": True,
                "should_llm_extract": True,
                "matched_keywords": a_matches,
            }

        # B 类：公司治理/常规披露
        b_matches = [kw for kw in B_CLASS_KEYWORDS if kw in title]
        if b_matches:
            return {
                "doc_value_level": "B",
                "doc_value_reason": f"常规披露: {', '.join(b_matches[:3])}",
                "should_parse_pdf": False,
                "should_llm_extract": True,
                "matched_keywords": b_matches,
            }

        # C 类：程序性/例行
        c_matches = [kw for kw in C_CLASS_KEYWORDS if kw in title]
        if c_matches:
            return {
                "doc_value_level": "C",
                "doc_value_reason": f"程序性公告: {', '.join(c_matches[:3])}",
                "should_parse_pdf": False,
                "should_llm_extract": True,
                "matched_keywords": c_matches,
            }

        # 默认 C 类（未能分类）
        return {
            "doc_value_level": "C",
            "doc_value_reason": "未命中已知分类关键词",
            "should_parse_pdf": False,
            "should_llm_extract": True,
            "matched_keywords": [],
        }
