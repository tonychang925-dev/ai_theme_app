#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
题材证据画像构建工具 - 改进版
使用 jieba 分词，优化证据词选择逻辑
"""

import json
import math
import re
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Set, Tuple, Optional
import argparse
import time
import sys

# 尝试导入 jieba，若未安装则提示并退出
try:
    import jieba
    import jieba.posseg as pseg
except ImportError:
    print("❌ 请先安装 jieba：pip install jieba")
    sys.exit(1)

# ====== 配置参数 ======
TOP_MUST = 25                      # must_have 最大数量
TOP_SHOULD = 25                    # should_have 最大数量
MIN_MUST_SCORE = 2.0                # must_have 最低分数
MIN_SHOULD_SCORE = 1.2              # should_have 最低分数
MIN_DOC_FREQ_RATIO = 0.2            # 词必须出现在至少 20% 的文档中才考虑为 must_have
MIN_TOKEN_LEN = 2                    # 最小词长度
MAX_TOKEN_LEN = 30                   # 最大词长度

# ====== 技术词库（用于 bonus，非必须）======
TECH_TERMS = {
    # 设备类型
    "光刻机", "刻蚀机", "沉积设备", "离子注入机", "清洗设备", "CMP设备",
    "涂胶显影", "量测设备", "检测设备", "探针台", "划片机", "键合机",
    "PVD", "CVD", "ALD", "MOCVD", "RTP",
    
    # 工艺/技术
    "EUV", "DUV", "ArF", "KrF", "High-NA",
    "7nm", "5nm", "3nm", "2nm", "14nm", "28nm",
    "FinFET", "GAA", "CFET", "3D NAND", "DRAM",
    "先进制程", "成熟制程", "特色工艺",
    
    # 公司/机构
    "ASML", "AMAT", "LAM", "TEL", "KLA", "NXE",
    "SMIC", "TSMC", "UMC", "Intel", "Samsung",
    "SIA", "SEMI", "BIS", "ITC", "EAR", "VEU", "ICRD",
    "北方华创", "中微公司", "拓荆科技", "华海清科", "芯源微", "盛美上海",
    
    # 产品/组件
    "GPU", "CPU", "FPGA", "ASIC", "SoC", "Chiplet", "IP核", "EDA",
    "DRAM", "NAND", "SRAM", "HBM",
    "逻辑芯片", "存储芯片", "模拟芯片", "功率芯片",
    
    # 中文完整词
    "半导体设备", "半导体材料", "半导体制造", "晶圆厂", "晶圆代工",
    "封装测试", "前道工艺", "后道工艺", "薄膜沉积", "等离子体刻蚀",
    "化学机械抛光", "离子注入", "光刻工艺", "刻蚀工艺", "清洗工艺",
}

# ====== 停用词（大幅扩充）======
STOPWORDS = {
    # 原有停用词
    "驱动事件", "新闻来源", "表示", "预计", "同比", "环比", "近日",
    "公司", "市场", "行业", "方面", "提升", "增长", "支持", "推进", 
    "相关", "我国", "中国", "美国", "日本", "荷兰",
    "2020", "2021", "2022", "2023", "2024", "2025", "2026", "2027",
    "亿元", "亿美元", "万元", "同比增长", "环比增长",
    "日讯", "日电", "上午", "下午", "昨日", "今日", "明日",
    "其中", "超过", "低于", "左右", "约", "近", "余",
    "根据", "按照", "通过", "对于", "由于", "因此",
    "报道", "表示", "指出", "强调", "透露", "宣布", "据悉",
    # 不完整词
    "半导体设", "导体设备", "体设备", "设备市", "场报告",
    "年第三季", "国际半导", "全球半导", "体产业协", "会近日在",
    "度全球半", "体设备市", "台积电预", "其中提到",
    
    # 新增泛词（从之前输出中提取）
    "发布", "上海", "期间", "新高", "政策", "机制", "国家",
    "来源", "走高", "等跟涨", "拉升涨停", "涨超", "午后直线",
    "此前封板", "发展的重", "装市场规", "的主要功", "史上最严",
    "利润总额", "期间复合", "装等类别", "入占比达", "大的细分",
    "界面新闻", "国务院国", "市公司质", "升中央企", "业控股上",
    "资委", "年持续提", "强做优做", "资本和国", "推动国有",
    "有企业做", "企改革", "举行", "家中央企", "改革冲刺",
    "有及国有", "推动跨集", "本投向重", "长三角地", "中国信科",
    "上海市生", "宁省国资", "制度安排", "培育壮大",
    # 常见动词/介词
    "举行", "建立", "提供", "应对", "开发", "研究", "发布日",
    "布企业出", "个国家", "款游戏获", "案提供依", "为上海游",
    "一国通", "将首次召", "研究中心", "风险预警", "政策法规",
    "海指引", "游戏出海", "建立海外", "开中国国", "今年首批",
}

# ====== 工具函数 ======
def now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")

def clean_html(text: str) -> str:
    """清理HTML标签"""
    if not text:
        return ""
    text = re.sub(r'<[^>]+>', ' ', text)
    text = re.sub(r'\s+', ' ', text)
    return text.strip()

def is_valid_file(filename: str) -> bool:
    """检查是否是有效文件（不是临时文件）"""
    if filename.startswith('.~'):
        return False
    if filename.endswith('.tmp') or filename.endswith('.temp'):
        return False
    return True

def read_jsonl_safe(file_path: Path) -> List[Dict]:
    """安全读取JSONL文件"""
    if not file_path.exists() or not is_valid_file(file_path.name):
        return []
    
    data = []
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        data.append(json.loads(line))
                    except json.JSONDecodeError:
                        continue
    except Exception:
        return []
    
    return data

def is_tech_term(token: str) -> bool:
    """判断是否是技术术语（用于加成）"""
    if token in TECH_TERMS:
        return True
    if re.match(r'^[A-Z][A-Z0-9\+\.\-]{2,}$', token):
        return True
    if re.match(r'^\d+\s*(nm|um|mm|GHz|MHz)$', token):
        return True
    return False

def is_complete_token(token: str) -> bool:
    """判断是否是完整的词（过滤分词错误）"""
    if not token or len(token) < 2:
        return False
    
    # 英文缩写保留
    if re.match(r'^[A-Z][A-Z0-9\+\.\-]{2,}$', token):
        return True
    
    # 数字+单位保留
    if re.match(r'^\d+nm$', token):
        return True
    
    # 中文词：长度至少2，不在停用词中
    if re.search(r'[\u4e00-\u9fff]', token):
        if len(token) == 1:
            return False
        if token in STOPWORDS:
            return False
        # 检查是否包含明显的切分错误（如以“的”结尾、单字等）
        if re.search(r'[的么了在于而]$', token):
            return False
        return True
    
    return False

# ====== 构建自定义词典 ======
def build_custom_dict(data_dir: Path):
    """从所有历史事件和详情中构建自定义词典，用于 jieba 分词"""
    print("🔧 正在构建自定义词典...")
    word_freq = Counter()
    
    # 遍历所有 history 文件
    for f in data_dir.glob("**/*_history.jsonl"):
        if not is_valid_file(f.name):
            continue
        for item in read_jsonl_safe(f):
            desc = item.get('description', '')
            if desc:
                # 用正则简单抽取候选词（中文2-5字，英文2+字母）
                words = re.findall(r'[\u4e00-\u9fff]{2,5}|[A-Za-z][A-Za-z0-9\+\.\-]{2,}', desc)
                word_freq.update(words)
    
    # 遍历所有 details 文件
    for f in data_dir.glob("**/*_details.jsonl"):
        if not is_valid_file(f.name):
            continue
        for item in read_jsonl_safe(f):
            detail = item.get('detail', '')
            if detail:
                detail_clean = clean_html(detail)
                words = re.findall(r'[\u4e00-\u9fff]{2,5}|[A-Za-z][A-Za-z0-9\+\.\-]{2,}', detail_clean)
                word_freq.update(words)
    
    # 将高频词（出现次数>=3）加入 jieba 词典
    added = 0
    for word, freq in word_freq.items():
        if freq >= 3 and len(word) >= 2 and word not in STOPWORDS:
            jieba.add_word(word, freq=freq)
            added += 1
    print(f"✅ 自定义词典构建完成，新增 {added} 个词")

# ====== 分词函数 ======
def smart_tokenize(text: str) -> List[str]:
    """使用 jieba 分词，返回词列表"""
    if not text:
        return []
    
    tokens = []
    # 使用 jieba 分词
    words = jieba.lcut(text)
    for w in words:
        w = w.strip()
        if not w or len(w) < MIN_TOKEN_LEN or len(w) > MAX_TOKEN_LEN:
            continue
        if w in STOPWORDS:
            continue
        tokens.append(w)
    
    return tokens

# ====== 数据加载 ======
def load_theme_data(data_dir: Path, theme_id: str) -> Tuple[List[Dict], str, str]:
    """加载题材数据"""
    history_dir = data_dir / "history"
    details_dir = data_dir / "details"
    
    # 加载历史事件
    history_events = []
    history_file = history_dir / f"{theme_id}_history.jsonl"
    if history_file.exists():
        data = read_jsonl_safe(history_file)
        for item in data:
            if item.get('description'):
                history_events.append(item)
    
    # 加载详情
    detail_text = ""
    reason_text = ""
    detail_file = details_dir / f"{theme_id}_details.jsonl"
    if detail_file.exists():
        data = read_jsonl_safe(detail_file)
        for item in data:
            if item.get('detail'):
                detail_text = clean_html(item['detail'])
            if item.get('reason'):
                reason_text = item['reason']
    
    return history_events, detail_text, reason_text

def scan_themes(data_dir: Path) -> Dict[str, str]:
    """扫描所有题材"""
    themes = {}
    
    history_dir = data_dir / "history"
    if history_dir.exists():
        for f in history_dir.glob("*_history.jsonl"):
            if is_valid_file(f.name):
                theme_id = f.stem.replace("_history", "")
                themes[theme_id] = f"题材{theme_id}"
    
    details_dir = data_dir / "details"
    if details_dir.exists():
        for f in details_dir.glob("*_details.jsonl"):
            if is_valid_file(f.name):
                theme_id = f.stem.replace("_details", "")
                if theme_id not in themes:
                    themes[theme_id] = f"题材{theme_id}"
    
    return themes

# ====== 构建画像 ======
def build_profile(theme_id: str, theme_name: str, history_events: List[Dict], 
                  detail_text: str, reason_text: str) -> Dict:
    """构建证据画像"""
    print(f"\n📊 文档统计:")
    
    docs = []
    
    # 历史事件
    for event in history_events:
        desc = event.get('description', '')
        if desc and len(desc) > 20:
            docs.append({
                "text": desc,
                "type": "history",
                "weight": 2.0
            })
    print(f"  history: {len([d for d in docs if d['type']=='history'])} 篇")
    
    # 详情
    if detail_text and len(detail_text) > 100:
        docs.append({
            "text": detail_text,
            "type": "detail",
            "weight": 1.5
        })
        print(f"  detail: 1 篇")
    
    # 理由
    if reason_text and len(reason_text) > 20:
        docs.append({
            "text": reason_text,
            "type": "reason",
            "weight": 1.0
        })
        print(f"  reason: 1 篇")
    
    if not docs:
        print("❌ 没有文档")
        return {}
    
    # 分词统计
    token_docs = []
    all_tokens = []
    
    for doc in docs:
        toks = smart_tokenize(doc["text"])
        if toks:
            token_docs.append({
                "tokens": toks,
                "weight": doc["weight"]
            })
            all_tokens.extend(toks)
    
    # 计算TF-IDF
    tf = Counter()
    df = Counter()
    
    for doc in token_docs:
        unique_tokens = set(doc["tokens"])
        for tok in unique_tokens:
            tf[tok] += doc["weight"]
            df[tok] += 1
    
    N = len(token_docs)
    
    # 计算分数
    scores = {}
    provenance = defaultdict(list)
    
    for doc in docs:
        toks = smart_tokenize(doc["text"])
        for tok in set(toks):
            idf = math.log((N + 1) / (df.get(tok, 1) + 1)) + 1.0
            bonus = 1.5 if is_tech_term(tok) else 1.0
            scores[tok] = tf.get(tok, 0) * idf * bonus
            
            if len(provenance[tok]) < 2:
                provenance[tok].append({
                    "type": doc["type"],
                    "snippet": doc["text"][:100].replace("\n", " ")
                })
    
    # 排序
    ranked = sorted(scores.items(), key=lambda x: x[1], reverse=True)
    
    print(f"\n📊 候选词统计: {len(ranked)} 个")
    print("\nTop 20 候选词:")
    for tok, score in ranked[:20]:
        tech_flag = "🔧" if is_tech_term(tok) else "📄"
        print(f"  {tech_flag} {tok}: {score:.2f}")
    
    # 分类
    must = []
    should = []
    
    # 计算 must_have 最低文档数
    min_doc_freq = max(2, int(N * MIN_DOC_FREQ_RATIO))
    
    for tok, score in ranked:
        if len(must) >= TOP_MUST:
            break
        if score < MIN_MUST_SCORE:
            continue
        # 要求出现在足够多的文档中
        if df.get(tok, 0) < min_doc_freq:
            continue
        # 排除明显不完整的词
        if not is_complete_token(tok):
            continue
        must.append(tok)
    
    for tok, score in ranked:
        if tok in must:
            continue
        if len(should) >= TOP_SHOULD:
            break
        if score < MIN_SHOULD_SCORE:
            continue
        if is_complete_token(tok):
            should.append(tok)
    
    # 构建结果
    profile = {
        "theme_id": theme_id,
        "theme_name": theme_name,
        "must_have": must,
        "should_have": should,
        "must_not": [],
        "meta": {
            "version": "evidence_profile_v2_improved",
            "generated_at": now_iso(),
            "history_count": len([d for d in docs if d['type']=='history']),
            "detail_count": 1 if detail_text else 0,
            "reason_count": 1 if reason_text else 0,
            "total_docs": len(docs),
            "must_count": len(must),
            "should_count": len(should)
        },
        "provenance": {tok: provenance[tok] for tok in must[:10] if tok in provenance}
    }
    
    return profile

# ====== 主函数 ======
def main():
    parser = argparse.ArgumentParser(description="题材证据画像构建工具 (改进版)")
    parser.add_argument("--data-dir", "-d", default="theme_data_complete",
                       help="数据目录路径")
    
    # 处理模式选择
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--theme", "-t", help="指定单个题材ID")
    group.add_argument("--batch", "-b", action="store_true", 
                       help="批量处理模式（处理所有题材）")
    group.add_argument("--ids", nargs='+', type=str, help="指定多个题材ID，用空格分隔")
    group.add_argument("--id-file", type=str, help="从文件读取题材ID列表，每行一个ID")
    
    parser.add_argument("--limit", "-l", type=int, default=0,
                       help="批量处理时限制处理数量（仅对 --batch 有效）")
    parser.add_argument("--batch-size", type=int, default=50,
                       help="分批处理时每批的大小（默认50），仅对批量模式有效")
    parser.add_argument("--pause", type=int, default=5,
                       help="批次间暂停秒数（默认5）")
    
    args = parser.parse_args()
    
    data_dir = Path(args.data_dir)
    if not data_dir.exists():
        print(f"❌ 目录不存在: {data_dir}")
        return
    
    print(f"\n📁 数据目录: {data_dir.absolute()}")
    
    # 构建自定义词典（仅第一次运行时需要，耗时但值得）
    build_custom_dict(data_dir)
    
    # 扫描题材
    print("\n🔍 扫描题材...")
    themes = scan_themes(data_dir)
    print(f"📋 找到 {len(themes)} 个题材")
    
    # 确定要处理的题材列表
    theme_ids_to_process = []
    if args.theme:
        theme_ids_to_process = [args.theme]
    elif args.batch:
        all_ids = list(themes.keys())
        if args.limit > 0:
            all_ids = all_ids[:args.limit]
        theme_ids_to_process = all_ids
        print(f"📦 批量模式：将处理 {len(theme_ids_to_process)} 个题材")
    elif args.ids:
        theme_ids_to_process = args.ids
        print(f"📦 指定ID模式：将处理 {len(theme_ids_to_process)} 个题材")
    elif args.id_file:
        id_file = Path(args.id_file)
        if not id_file.exists():
            print(f"❌ ID文件不存在: {id_file}")
            return
        with open(id_file, 'r', encoding='utf-8') as f:
            theme_ids_to_process = [line.strip() for line in f if line.strip()]
        print(f"📦 从文件读取了 {len(theme_ids_to_process)} 个题材ID")
    else:
        # 交互模式
        print("\n可用题材前20个:")
        for i, (tid, name) in enumerate(sorted(themes.items())[:20], 1):
            print(f"  {i:2d}. {tid} - {name}")
        theme_id = input("\n🎯 请输入题材ID: ").strip()
        if theme_id not in themes:
            print(f"❌ 题材不存在")
            return
        theme_ids_to_process = [theme_id]
    
    total = len(theme_ids_to_process)
    print(f"\n开始处理 {total} 个题材...")
    
    start_time = time.time()
    success_count = 0
    
    # 分批处理
    batch_size = args.batch_size
    for i in range(0, total, batch_size):
        batch = theme_ids_to_process[i:i+batch_size]
        print(f"\n{'='*60}")
        print(f"处理批次 {i//batch_size + 1}/{(total+batch_size-1)//batch_size}，本批 {len(batch)} 个题材")
        print(f"{'='*60}")
        
        for j, theme_id in enumerate(batch, 1):
            global_idx = i + j
            print(f"\n[{global_idx}/{total}] 处理 {theme_id}")
            
            theme_name = themes.get(theme_id, f"题材{theme_id}")
            history, detail, reason = load_theme_data(data_dir, theme_id)
            profile = build_profile(theme_id, theme_name, history, detail, reason)
            
            if profile:
                out_file = data_dir / f"{theme_id}_evidence_profile_improved.json"
                with open(out_file, 'w', encoding='utf-8') as f:
                    json.dump(profile, f, ensure_ascii=False, indent=2)
                print(f"  ✅ 已保存到 {out_file.name}")
                success_count += 1
            else:
                print(f"  ⚠️ 处理失败，跳过")
        
        # 批次间暂停
        if i + batch_size < total:
            print(f"\n⏸️ 批次完成，暂停 {args.pause} 秒...")
            time.sleep(args.pause)
    
    elapsed = time.time() - start_time
    print(f"\n{'='*60}")
    print(f"处理完成！成功: {success_count}/{total}，总用时: {elapsed:.1f}秒")

if __name__ == "__main__":
    main()