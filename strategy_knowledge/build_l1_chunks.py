"""ADR-032 L1 builder — Strategy Source Chunks.

L1 = "structured source chunks preserving chapter/section/page".

This script does NOT interpret. It preserves.
  - The chapter/section/page/concept structure is authored by hand (semantic work).
  - The chunk body text is taken VERBATIM from the PDF via `pdftotext(-layout)`,
    page by page, so no paraphrase can enter L1.

Output: strategy_knowledge/documents/<document_id>.chunks.json

Authority boundary (ADR-032):
  - L1 preserves the source. It is not interpretation, not a card, not a rule.
  - source_refs remain the ground truth: the PDF file itself.
"""

from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

CST = timezone(timedelta(hours=8))

KNOWLEDGE_DIR = Path(__file__).resolve().parent
REPO_ROOT = KNOWLEDGE_DIR.parent
REGISTRY_PATH = KNOWLEDGE_DIR / "documents" / "registry.json"
OUT_DIR = KNOWLEDGE_DIR / "documents"

SCHEMA_VERSION = "strategy-source-chunks.v1"


# ── Authored structure ──────────────────────────────────────────────────────
# chapter / section / page range / concepts / fidelity.
# `fidelity`:
#   clean          — text extracted cleanly
#   degraded_table — table content is fragmented by pdftotext
#   image_only     — page body is a chart/diagram; text extraction is unusable
#   partial_image  — mixed: prose plus image-only figures

L1_SPECS: dict[str, dict] = {
    "trading_system_v1": {
        "chunks": [
            {
                "chunk_id": "c01",
                "chapter": "1. 抓市场主线",
                "chapter_weight": "35%",
                "section": "主线的判定 / 题材的来源",
                "page_start": 1,
                "page_end": 1,
                "concepts": ["主线判定", "题材来源", "政策", "技术创新", "重大事件", "行业周期", "资产重组", "大热点大干"],
                "fidelity": "clean",
            },
            {
                "chunk_id": "c02",
                "chapter": "1. 抓市场主线",
                "chapter_weight": "35%",
                "section": "主线判定的两大维度：逻辑（新颖度/时机/影响广度）与市场（资金认可）",
                "page_start": 1,
                "page_end": 1,
                "concepts": ["新颖度", "时机", "影响广度", "资金认可", "主线门槛"],
                "fidelity": "clean",
            },
            {
                "chunk_id": "c03",
                "chapter": "2. 看市场情绪",
                "chapter_weight": "30%",
                "section": "找准切入周期 / 市场情绪轨迹七阶段",
                "page_start": 2,
                "page_end": 2,
                "concepts": ["情绪轨迹", "市场初期", "市场发酵", "市场加速", "市场高潮", "市场分歧", "市场退潮", "周期结束"],
                "fidelity": "clean",
            },
            {
                "chunk_id": "c04",
                "chapter": "2. 看市场情绪",
                "chapter_weight": "30%",
                "section": "相对确定性的行情判断依据（大环境/小环境/个股高胜算）",
                "page_start": 2,
                "page_end": 2,
                "concepts": ["大环境保护", "小环境安全", "个股高胜算", "盛极而衰", "突破买入", "低吸"],
                "fidelity": "clean",
            },
            {
                "chunk_id": "c05",
                "chapter": "2. 看市场情绪",
                "chapter_weight": "30%",
                "section": "阶段一 初期-试错 / 阶段二 发酵-进场",
                "page_start": 2,
                "page_end": 3,
                "concepts": ["初期试错", "发酵进场", "竞价分时图", "量比", "换手率", "二次领涨"],
                "fidelity": "clean",
            },
            {
                "chunk_id": "c06",
                "chapter": "2. 看市场情绪",
                "chapter_weight": "30%",
                "section": "阶段三 高潮-离场（警惕）",
                "page_start": 3,
                "page_end": 3,
                "concepts": ["高潮离场", "龙虎榜", "涨停家数"],
                "fidelity": "clean",
            },
            {
                "chunk_id": "c07",
                "chapter": "2. 看市场情绪",
                "chapter_weight": "30%",
                "section": "阶段四 分歧-关注（含买/不买判定规则）",
                "page_start": 3,
                "page_end": 3,
                "concepts": ["分歧关注", "首阴", "被动分歧", "买不买规则", "二波行情", "换手率<50%"],
                "fidelity": "clean",
            },
            {
                "chunk_id": "c08",
                "chapter": "2. 看市场情绪",
                "chapter_weight": "30%",
                "section": "阶段五 弱转强-再次切入",
                "page_start": 3,
                "page_end": 3,
                "concepts": ["弱转强切入", "反包", "分歧转一致"],
                "fidelity": "clean",
            },
            {
                "chunk_id": "c09",
                "chapter": "2. 看市场情绪",
                "chapter_weight": "30%",
                "section": "阶段六 再次高潮-离场 / 阶段七 分歧-补涨 / 阶段八 退潮-放弃",
                "page_start": 3,
                "page_end": 3,
                "concepts": ["再次高潮离场", "分歧补涨", "退潮放弃", "不参与跟风股二次分歧"],
                "fidelity": "clean",
            },
            {
                "chunk_id": "c10",
                "chapter": "3. 盯龙头核心",
                "chapter_weight": "20%",
                "section": "核心个股 / 龙头个股特征（硬逻辑、高辨识度、属性、抗下跌）",
                "page_start": 3,
                "page_end": 4,
                "concepts": ["龙头识别", "硬逻辑", "高辨识度", "首板换手率", "量比", "3低特征", "抗下跌"],
                "fidelity": "clean",
            },
            {
                "chunk_id": "c11",
                "chapter": "3. 盯龙头核心",
                "chapter_weight": "20%",
                "section": "龙头操作要领五条",
                "page_start": 4,
                "page_end": 4,
                "concepts": ["操作要领", "第一时间介入", "捂得住", "不做短线", "买龙二"],
                "fidelity": "clean",
            },
            {
                "chunk_id": "c12",
                "chapter": "3. 盯龙头核心",
                "chapter_weight": "20%",
                "section": "套利个股（创业板20cm）/ 补涨股",
                "page_start": 4,
                "page_end": 4,
                "concepts": ["套利个股", "20cm", "一字板定方向", "补涨股"],
                "fidelity": "clean",
            },
            {
                "chunk_id": "c13",
                "chapter": "4. 找准买点",
                "chapter_weight": "15%",
                "section": "交易前准备 / 临盘交易原则 / 三个买入时机",
                "page_start": 4,
                "page_end": 4,
                "concepts": ["交易前准备", "复盘推演", "临盘原则", "三个买入时机", "择时重于择股"],
                "fidelity": "clean",
            },
            {
                "chunk_id": "c14",
                "chapter": "4. 找准买点",
                "chapter_weight": "15%",
                "section": "分时盘口判定 / 分时买点1-4",
                "page_start": 4,
                "page_end": 6,
                "concepts": ["分时均线", "放量买入", "分时买点", "放量突破", "回踩均价线", "MACD"],
                "fidelity": "partial_image",
                "image_only_note": "分时买点1/2/3/4 为示意图，pdftotext 仅能取到图注文字。",
            },
            {
                "chunk_id": "c15",
                "chapter": "4. 找准买点",
                "chapter_weight": "15%",
                "section": "缩量拉升诱多识别",
                "page_start": 5,
                "page_end": 6,
                "concepts": ["缩量拉升", "诱多", "MACD顶背离", "红柱缩头死叉", "需观望"],
                "fidelity": "clean",
            },
            {
                "chunk_id": "c16",
                "chapter": "结论",
                "chapter_weight": None,
                "section": "不符合原则即空仓观望",
                "page_start": 6,
                "page_end": 8,
                "concepts": ["空仓观望", "宁愿错过"],
                "fidelity": "clean",
            },
        ]
    },
    "weak_to_strong_v1": {
        "chunks": [
            {
                "chunk_id": "c01",
                "chapter": "什么是弱转强",
                "chapter_weight": None,
                "section": "概念与核心逻辑",
                "page_start": 1,
                "page_end": 1,
                "concepts": ["弱转强定义", "主力洗盘震仓", "二波行情"],
                "fidelity": "clean",
            },
            {
                "chunk_id": "c02",
                "chapter": "常见的弱势三种",
                "chapter_weight": None,
                "section": "中到大阴线 / 冲高回落上影线 / 栏板涨停",
                "page_start": 1,
                "page_end": 1,
                "concepts": ["大阴线", "上影线", "栏板涨停", "弱势类型"],
                "fidelity": "clean",
            },
            {
                "chunk_id": "c03",
                "chapter": "弱转强的特征信号",
                "chapter_weight": None,
                "section": "前一日分歧 / 次日反包 / 板块联动",
                "page_start": 1,
                "page_end": 2,
                "concepts": ["前一日分歧", "首阴", "资金护盘", "关键支撑位", "5日线", "10日线", "次日反包", "封单果断", "板块联动", "补涨股助攻"],
                "fidelity": "clean",
            },
            {
                "chunk_id": "c04",
                "chapter": "“弱”的典型——烂板",
                "chapter_weight": None,
                "section": "烂板筹码 / 底部首板烂板 / 关键位置暴量 / 烂板五要素",
                "page_start": 2,
                "page_end": 2,
                "concepts": ["烂板", "充分换手", "箱体突破", "炸板", "破板不深跌", "回撤3%", "封单变小", "缩量", "烂而不弱"],
                "fidelity": "clean",
            },
            {
                "chunk_id": "c05",
                "chapter": "弱转强核心原则",
                "chapter_weight": None,
                "section": "该弱不弱则为强",
                "page_start": 2,
                "page_end": 2,
                "concepts": ["该弱不弱则为强"],
                "fidelity": "clean",
            },
            {
                "chunk_id": "c06",
                "chapter": "弱转强类型",
                "chapter_weight": None,
                "section": "盘前集合竞价弱转强 / 早盘分时弱转强 / 盘中弱转强",
                "page_start": 2,
                "page_end": 3,
                "concepts": ["集合竞价弱转强", "高开", "抢筹", "早盘分时弱转强", "分时均线", "盘中弱转强", "强于大盘", "突破分时平台"],
                "fidelity": "clean",
            },
            {
                "chunk_id": "c07",
                "chapter": "具体操作策略",
                "chapter_weight": None,
                "section": "关键位置观察",
                "page_start": 4,
                "page_end": 4,
                "concepts": ["前一日分时低点不破", "资金护盘", "5日线", "10日线", "成交量不能萎缩", "假反抽"],
                "fidelity": "clean",
            },
            {
                "chunk_id": "c08",
                "chapter": "具体操作策略",
                "chapter_weight": None,
                "section": "介入时机与最佳买点",
                "page_start": 4,
                "page_end": 4,
                "concepts": ["回踩承接", "打板", "半路跟进", "分时弱转强板", "反包板", "趋势转强买入", "分时均线放量上攻"],
                "fidelity": "clean",
            },
            {
                "chunk_id": "c09",
                "chapter": "仓位控制",
                "chapter_weight": None,
                "section": "首次轻仓 / 主线+绝对龙头 / 龙二次龙头 / 忌满仓",
                "page_start": 4,
                "page_end": 4,
                "concepts": ["仓位控制", "轻仓1-2成", "主线龙头5-8成", "龙二次龙头2-4成", "忌满仓梭哈"],
                "fidelity": "clean",
            },
            {
                "chunk_id": "c10",
                "chapter": "止盈止损",
                "chapter_weight": None,
                "section": "反包失败减仓 / 成功反包持股 / 跌破支撑清仓",
                "page_start": 4,
                "page_end": 4,
                "concepts": ["止盈止损", "反包失败", "重新站上关键价位", "持股待二波", "跌破10日线", "跌破前低", "清仓"],
                "fidelity": "clean",
            },
            {
                "chunk_id": "c11",
                "chapter": "注意事项",
                "chapter_weight": None,
                "section": "强势股前提 / 真假弱转强 / 跟风股陷阱 / 市场环境匹配 / 心态风险",
                "page_start": 4,
                "page_end": 5,
                "concepts": ["杂毛不配弱转强", "真假弱转强", "放量换手", "缩量拉升", "跟风股陷阱", "退潮成功率低", "分歧-修复阶段", "诱多"],
                "fidelity": "clean",
            },
            {
                "chunk_id": "c12",
                "chapter": "总结",
                "chapter_weight": None,
                "section": "口诀",
                "page_start": 5,
                "page_end": 5,
                "concepts": ["总结口诀"],
                "fidelity": "clean",
            },
        ]
    },
    "auction_v1": {
        "chunks": [
            {
                "chunk_id": "c01",
                "chapter": "集合竞价分时走势",
                "chapter_weight": None,
                "section": "9:20–9:25 稳定性要求",
                "page_start": 1,
                "page_end": 1,
                "concepts": ["真实集合竞价", "920-925", "走势稳定", "不能急跌"],
                "fidelity": "clean",
            },
            {
                "chunk_id": "c02",
                "chapter": "集合竞价的最佳走势",
                "chapter_weight": None,
                "section": "六种最佳图形（倒L+上坡 / 红盘区阶梯 / 锥形+U / 上翘一字 / 倒L+U / 一字上翘+阶梯）",
                "page_start": 2,
                "page_end": 4,
                "concepts": ["倒L型上坡型", "红盘区阶梯型", "锥形+U形", "上翘一字型", "倒L+U形", "一字上翘+阶梯向上", "量能逐步放大"],
                "fidelity": "partial_image",
                "image_only_note": "六种最佳走势均为竞价分时示意图，pdftotext 仅能取到图注文字。",
            },
            {
                "chunk_id": "c03",
                "chapter": "集合竞价分时明细",
                "chapter_weight": None,
                "section": "9:24–9:25 最后一分钟抢筹",
                "page_start": 5,
                "page_end": 5,
                "concepts": ["最后一分钟", "924-925", "竞价单放大", "抢筹"],
                "fidelity": "clean",
            },
            {
                "chunk_id": "c04",
                "chapter": "集合竞价重点关注",
                "chapter_weight": None,
                "section": "弱转强的板块和个股",
                "page_start": 6,
                "page_end": 6,
                "concepts": ["龙头符合预期", "龙二龙三溢价", "龙头不符合预期规避", "卡位龙", "量价抬升", "昨日栏板炸板弱转强"],
                "fidelity": "clean",
            },
            {
                "chunk_id": "c05",
                "chapter": "集合竞价与涨停的关系",
                "chapter_weight": None,
                "section": "承接力与量能标准",
                "page_start": 6,
                "page_end": 6,
                "concepts": ["承接力", "买盘力量", "量能达前日最大分时1/2", "高开3%-5%", "一进二"],
                "fidelity": "clean",
            },
        ]
    },
    "find_ox_v1": {
        "chunks": [
            {
                "chunk_id": "c01",
                "chapter": "牛股三绝",
                "chapter_weight": None,
                "section": "1. 高量不破，后市要火",
                "page_start": 1,
                "page_end": 1,
                "concepts": ["高量不破", "高量柱", "第1浪", "第3浪"],
                "fidelity": "partial_image",
            },
            {
                "chunk_id": "c02",
                "chapter": "牛股三绝",
                "chapter_weight": None,
                "section": "2. 倍量不穿，后市翻番",
                "page_start": 1,
                "page_end": 1,
                "concepts": ["倍量不穿", "倍量柱", "底部基柱", "5日均线回踩低吸"],
                "fidelity": "partial_image",
            },
            {
                "chunk_id": "c03",
                "chapter": "牛股三绝",
                "chapter_weight": None,
                "section": "3. 缺口不补，后市如虎",
                "page_start": 2,
                "page_end": 2,
                "concepts": ["缺口不补", "跳空缺口", "大主线题材"],
                "fidelity": "clean",
            },
            {
                "chunk_id": "c04",
                "chapter": "强势股的7大特征",
                "chapter_weight": None,
                "section": "均线多头排列 / 放量涨缩量跌 / 分时拉升有量 / 低位筹码峰 / 题材深广度 / 创新高 / 连贯性",
                "page_start": 2,
                "page_end": 2,
                "concepts": ["均线多头排列", "放量涨缩量跌", "分时图", "筹码峰", "题材深广度", "股价创新高", "连贯性"],
                "fidelity": "clean",
            },
            {
                "chunk_id": "c05",
                "chapter": "选股方法",
                "chapter_weight": None,
                "section": "6天涨停基因筛选 / 倍量阳线跟进 / 分批入场",
                "page_start": 2,
                "page_end": 3,
                "concepts": ["涨停基因", "6天涨停", "买入位置", "买入逻辑", "倍量阳线", "放量突破进场", "分批入场"],
                "fidelity": "clean",
            },
        ]
    },
    "limit_up_v1": {
        "chunks": [
            {
                "chunk_id": "c01",
                "chapter": "总纲",
                "chapter_weight": None,
                "section": "两个方向 + 9 个要点",
                "page_start": 1,
                "page_end": 1,
                "concepts": ["预判能否涨停", "涨停能否封住"],
                "fidelity": "clean",
            },
            {
                "chunk_id": "c02",
                "chapter": "1. 预判涨停潜力股",
                "chapter_weight": None,
                "section": "四要点：涨停基因 / 题材 / 量能 / 形态",
                "page_start": 1,
                "page_end": 2,
                "concepts": ["涨停基因", "热点题材", "C位板块", "量能放量", "60日均线", "倍量", "脉冲式涨停", "台阶式涨停", "斜推式涨停", "震荡式涨停"],
                "fidelity": "clean",
            },
            {
                "chunk_id": "c03",
                "chapter": "2. 预判涨停能否封住",
                "chapter_weight": None,
                "section": "五要点：地位 / 利好 / 量能 / 形态 / 价位",
                "page_start": 2,
                "page_end": 2,
                "concepts": ["行业地位", "利好刺激", "涨停前放量涨停后缩量", "封板概率", "炸板后8%-10%震荡", "洗盘", "相对低位"],
                "fidelity": "clean",
            },
            {
                "chunk_id": "c04",
                "chapter": "3. 二板定龙头",
                "chapter_weight": None,
                "section": "量价特征 / 题材逻辑 / 盘口气质 / 情绪位置 / 新手注意事项",
                "page_start": 2,
                "page_end": 3,
                "concepts": ["二板定龙头", "换手板", "换手率>15%", "一字板", "二板放量分歧转一致", "缩量封死", "题材唯一性", "市场热度", "封单质量", "辨识度", "情绪冰点后第一波反弹", "板块效应"],
                "fidelity": "clean",
            },
            {
                "chunk_id": "c05",
                "chapter": "3. 二板定龙头",
                "chapter_weight": None,
                "section": "维度对照表（题材属性/市场地位/板块反馈/换手率/封单力度/盘口分时/资金属性/市场情绪）",
                "page_start": 3,
                "page_end": 3,
                "concepts": ["维度表", "风险提示", "板块反馈", "封单力度", "资金属性"],
                "fidelity": "degraded_table",
            },
        ]
    },
    "theme_tracking_v1": {
        "chunks": [
            {
                "chunk_id": "c01",
                "chapter": "当前主要题材 — 商业航天",
                "chapter_weight": None,
                "section": "催化剂事件 1–14",
                "page_start": 1,
                "page_end": 1,
                "concepts": ["商业航天", "催化剂事件", "卫星物联网", "SpaceX IPO", "长征十二号甲", "华菱线缆"],
                "fidelity": "clean",
            },
            {
                "chunk_id": "c02",
                "chapter": "市场情绪判定",
                "chapter_weight": None,
                "section": "商业航天 —— 判定表（是否属于主线/启动/发酵/分歧/弱转强/高潮/退潮/当日涨停数 → 结论）",
                "page_start": 1,
                "page_end": 2,
                "concepts": ["市场情绪判定表", "是否属于主线", "启动阶段", "发酵阶段", "分歧阶段", "弱转强阶段", "高潮阶段", "退潮阶段", "当日涨停数", "结论"],
                "fidelity": "degraded_table",
                "template_note": "此表为逐题材复用的判定模板，是 theme_tracking 的可操作骨架。",
            },
            {
                "chunk_id": "c03",
                "chapter": "强势股跟踪",
                "chapter_weight": None,
                "section": "商业航天 —— 股票池表（股票名称/板块/是否领涨/涨停类型/资金性质/流通性质/涨停封单/技术形态/当日资金/是否次新/龙头属性）",
                "page_start": 2,
                "page_end": 18,
                "concepts": ["强势股跟踪表", "是否领涨", "涨停类型", "资金性质", "流通性质", "涨停封单", "技术形态", "当日资金情况", "是否次新股", "龙头属性"],
                "fidelity": "degraded_table",
                "template_note": "逐股票复用的跟踪模板。",
            },
            {
                "chunk_id": "c04",
                "chapter": "市场情绪判定",
                "chapter_weight": None,
                "section": "算力+芯片",
                "page_start": 19,
                "page_end": 19,
                "concepts": ["算力+芯片", "市场情绪判定表"],
                "fidelity": "degraded_table",
            },
            {
                "chunk_id": "c05",
                "chapter": "强势股跟踪",
                "chapter_weight": None,
                "section": "算力+芯片",
                "page_start": 19,
                "page_end": 23,
                "concepts": ["强势股跟踪表", "算力", "芯片"],
                "fidelity": "degraded_table",
            },
            {
                "chunk_id": "c06",
                "chapter": "市场情绪判定",
                "chapter_weight": None,
                "section": "无人驾驶",
                "page_start": 24,
                "page_end": 24,
                "concepts": ["无人驾驶", "市场情绪判定表"],
                "fidelity": "degraded_table",
            },
            {
                "chunk_id": "c07",
                "chapter": "强势股跟踪",
                "chapter_weight": None,
                "section": "无人驾驶",
                "page_start": 24,
                "page_end": 31,
                "concepts": ["强势股跟踪表", "无人驾驶"],
                "fidelity": "degraded_table",
            },
            {
                "chunk_id": "c08",
                "chapter": "操作纪律",
                "chapter_weight": None,
                "section": "盘前大盘情绪冰点切忌操作",
                "page_start": 31,
                "page_end": 33,
                "concepts": ["大盘情绪", "板块情绪", "冰点", "切忌操作"],
                "fidelity": "clean",
            },
        ]
    },
}


# ── Builder ─────────────────────────────────────────────────────────────────

def _tool_version() -> str:
    try:
        out = subprocess.run(["pdftotext", "-v"], capture_output=True, text=True)
        return (out.stderr or out.stdout).splitlines()[0].strip()
    except Exception as exc:  # pragma: no cover
        return f"pdftotext (version unknown: {exc})"


def _page_text(pdf_path: Path, page: int) -> str:
    """Verbatim text of a single PDF page via pdftotext -layout."""
    result = subprocess.run(
        ["pdftotext", "-layout", "-f", str(page), "-l", str(page), str(pdf_path), "-"],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(f"pdftotext failed for {pdf_path} page {page}: {result.stderr}")
    return result.stdout


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def build_document(document_id: str, entry: dict, spec: dict) -> dict:
    pdf_path = REPO_ROOT / entry["file_path"]
    if not pdf_path.is_file():
        raise FileNotFoundError(f"source PDF missing: {pdf_path}")

    actual_sha = _sha256(pdf_path)
    if actual_sha != entry["sha256"]:
        raise ValueError(
            f"sha256 mismatch for {document_id}: registry={entry['sha256']} actual={actual_sha}"
        )

    page_cache: dict[int, str] = {}
    chunks = []
    for raw in spec["chunks"]:
        start, end = raw["page_start"], raw["page_end"]
        texts = []
        for page in range(start, end + 1):
            if page not in page_cache:
                page_cache[page] = _page_text(pdf_path, page)
            texts.append(page_cache[page])
        chunk = {
            "chunk_id": f"{document_id}.{raw['chunk_id']}",
            "chapter": raw["chapter"],
            "chapter_weight": raw.get("chapter_weight"),
            "section": raw["section"],
            "page_start": start,
            "page_end": end,
            "concepts": raw["concepts"],
            "fidelity": raw["fidelity"],
            "text": "\n".join(texts).strip(),
        }
        if raw.get("image_only_note"):
            chunk["image_only_note"] = raw["image_only_note"]
        if raw.get("template_note"):
            chunk["template_note"] = raw["template_note"]
        chunks.append(chunk)

    concepts_index: dict[str, list[str]] = {}
    for chunk in chunks:
        for concept in chunk["concepts"]:
            concepts_index.setdefault(concept, []).append(chunk["chunk_id"])

    covered = sorted({p for c in chunks for p in range(c["page_start"], c["page_end"] + 1)})
    all_pages = list(range(1, entry["pages"] + 1))
    uncovered = [p for p in all_pages if p not in covered]

    return {
        "schema_version": SCHEMA_VERSION,
        "layer": "L1",
        "authority": "source_preservation_only",
        "boundary_flags": {
            "not_interpretation": True,
            "not_prompt_material": True,
            "not_strategy_card": True,
            "source_of_truth": "the PDF file itself",
        },
        "document_id": document_id,
        "title": entry["title"],
        "short_name": entry["short_name"],
        "source_file_path": entry["file_path"],
        "source_sha256": entry["sha256"],
        "source_version": entry["version"],
        "total_pages": entry["pages"],
        "extraction": {
            "tool": "pdftotext",
            "tool_version": _tool_version(),
            "options": "-layout",
            "granularity": "per-page, reassembled per chunk",
            "extracted_at": datetime.now(CST).isoformat(),
            "llm_used": False,
        },
        "chunks": chunks,
        "concepts_index": concepts_index,
        "page_coverage": {
            "covered_pages": covered,
            "uncovered_pages": uncovered,
        },
    }


def main(argv: list[str]) -> int:
    registry = json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))
    entries = {d["document_id"]: d for d in registry["documents"]}

    targets = argv[1:] or list(L1_SPECS.keys())
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    for document_id in targets:
        if document_id not in L1_SPECS:
            print(f"SKIP {document_id}: no L1 spec authored")
            continue
        if document_id not in entries:
            print(f"SKIP {document_id}: not in registry")
            continue
        payload = build_document(document_id, entries[document_id], L1_SPECS[document_id])
        out_path = OUT_DIR / f"{document_id}.chunks.json"
        out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        cov = payload["page_coverage"]
        print(
            f"OK {document_id}: {len(payload['chunks'])} chunks, "
            f"{len(payload['concepts_index'])} concepts, "
            f"pages {len(cov['covered_pages'])}/{payload['total_pages']}"
            + (f", UNCOVERED={cov['uncovered_pages']}" if cov["uncovered_pages"] else "")
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
