#!/usr/bin/env python3
"""
从JSONL文件分析神剑股份历史数据和弱转强条件
"""
import json
from datetime import date, datetime, timedelta
from typing import List, Dict, Any

def load_kline_data(file_path: str) -> List[Dict[str, Any]]:
    """加载JSONL格式的K线数据"""
    data = []
    with open(file_path, 'r', encoding='utf-8') as f:
        for line in f:
            try:
                record = json.loads(line.strip())
                # 转换trade_date为date对象
                if 'trade_date' in record and isinstance(record['trade_date'], str):
                    record['trade_date'] = datetime.strptime(record['trade_date'], '%Y-%m-%d').date()
                data.append(record)
            except json.JSONDecodeError as e:
                print(f"JSON解析错误: {e}, 行: {line[:100]}")
    return data

def analyze_limit_up_pattern(data: List[Dict[str, Any]], analysis_date: date, trading_days: int = 7) -> Dict[str, Any]:
    """分析涨停模式"""
    # 过滤在analysis_date之前的数据
    relevant_data = [d for d in data if d['trade_date'] <= analysis_date]
    relevant_data.sort(key=lambda x: x['trade_date'])
    
    # 取最近trading_days个交易日
    recent_data = relevant_data[-trading_days:] if len(relevant_data) >= trading_days else relevant_data
    
    # 统计涨停
    limit_up_dates = []
    limit_up_count = 0
    consecutive_count = 0
    max_consecutive = 0
    current_consecutive = 0
    prev_date = None
    
    for i, record in enumerate(recent_data):
        pct_chg = float(record.get('pct_chg', 0))
        is_limit_up = pct_chg >= 9.9
        
        if is_limit_up:
            limit_up_count += 1
            limit_up_dates.append(record['trade_date'])
            
            # 检查是否连续涨停
            if prev_date:
                # 检查是否是连续的交易日
                days_diff = (record['trade_date'] - prev_date).days
                if days_diff == 1:  # 自然日连续
                    current_consecutive += 1
                else:
                    current_consecutive = 1
            else:
                current_consecutive = 1
            
            max_consecutive = max(max_consecutive, current_consecutive)
            prev_date = record['trade_date']
    
    # 确定模式
    pattern_type = '无涨停'
    has_pattern = False
    strength_score = 0
    
    if max_consecutive >= 2:
        pattern_type = f'连续{max_consecutive}天涨停'
        has_pattern = True
        strength_score = 95
    elif limit_up_count >= 2:
        pattern_type = f'{limit_up_count}次非连续涨停'
        has_pattern = True
        strength_score = 85
    elif limit_up_count == 1:
        pattern_type = '单日涨停'
        strength_score = 70
    else:
        strength_score = 30
    
    return {
        'has_limit_up_pattern': has_pattern,
        'limit_up_count': limit_up_count,
        'max_consecutive_days': max_consecutive,
        'limit_up_dates': [d.strftime('%Y-%m-%d') for d in limit_up_dates],
        'analysis_period': f"{trading_days}个交易日",
        'pattern_type': pattern_type,
        'strength_score': strength_score,
        'recent_data_count': len(recent_data)
    }

def analyze_gap_support(data: List[Dict[str, Any]], analysis_date: date) -> Dict[str, Any]:
    """分析缺口支撑"""
    # 找到目标日及前一日数据
    target_record = None
    prev_record = None
    
    for i, record in enumerate(data):
        if record['trade_date'] == analysis_date:
            target_record = record
            # 找前一个交易日
            if i > 0:
                prev_record = data[i-1]
            break
    
    if not target_record or not prev_record:
        return {
            'has_gap': False,
            'is_gap_support': False,
            'gap_support_level': 0,
            'error': '数据不足'
        }
    
    # 提取价格
    prev_high = float(prev_record.get('high_price', 0))
    prev_low = float(prev_record.get('low_price', 0))
    prev_close = float(prev_record.get('close_price', 0))
    
    current_low = float(target_record.get('low_price', 0))
    current_high = float(target_record.get('high_price', 0))
    current_close = float(target_record.get('close_price', 0))
    
    result = {
        'has_gap': False,
        'gap_type': '',
        'gap_position': '',
        'gap_size': 0.0,
        'is_gap_support': False,
        'gap_support_level': 0.0,
        'technical_signals': []
    }
    
    # 检查向上缺口（当日最低价 > 前一日最高价）
    gap_threshold = 0.001  # 0.1%
    if current_low > prev_high * (1 + gap_threshold):
        result['has_gap'] = True
        result['gap_type'] = 'breakaway'
        result['gap_position'] = 'above'
        result['gap_size'] = (current_low - prev_high) / prev_high * 100
        result['gap_support_level'] = prev_high
        result['technical_signals'].append(f"向上突破缺口: {result['gap_size']:.2f}%")
        
        # 检查是否回补缺口（价格回到缺口下沿附近）
        if current_low <= prev_high * 1.01:  # 在缺口下沿1%范围内
            result['is_gap_support'] = True
            result['technical_signals'].append(f"缺口回补，支撑位: {prev_high:.2f}")
    
    # 检查向下缺口（当日最高价 < 前一日最低价）
    elif current_high < prev_low * (1 - gap_threshold):
        result['has_gap'] = True
        result['gap_type'] = 'breakaway'
        result['gap_position'] = 'below'
        result['gap_size'] = (prev_low - current_high) / prev_low * 100
        result['gap_support_level'] = prev_low
        result['technical_signals'].append(f"向下突破缺口: {result['gap_size']:.2f}%")
        
        # 检查是否回补缺口
        if current_high >= prev_low * 0.99:  # 在缺口上沿1%范围内
            result['is_gap_support'] = True
            result['technical_signals'].append(f"缺口回补，阻力位: {prev_low:.2f}")
    
    return result

def main():
    file_path = "/Users/admin/Desktop/ai_theme_app/theme_data_complete/_stock_kline/tushare/daily_bar/002361.SZ.jsonl"
    
    print(f"从JSONL文件分析神剑股份数据")
    print(f"文件路径: {file_path}")
    print("=" * 70)
    
    # 加载数据
    data = load_kline_data(file_path)
    print(f"加载了 {len(data)} 条K线记录")
    
    # 显示最近20条记录
    recent_data = sorted(data, key=lambda x: x['trade_date'], reverse=True)[:20]
    print(f"\n最近20个交易日:")
    print("日期        开盘价  最高价  最低价  收盘价   涨跌幅%")
    print("-" * 70)
    for record in recent_data:
        td = record['trade_date']
        open_p = float(record.get('open_price', 0))
        high_p = float(record.get('high_price', 0))
        low_p = float(record.get('low_price', 0))
        close_p = float(record.get('close_price', 0))
        pct = float(record.get('pct_chg', 0))
        is_limit = pct >= 9.9
        
        print(f"{td}  {open_p:6.2f}  {high_p:6.2f}  {low_p:6.2f}  {close_p:6.2f}  {pct:7.2f}% {'✅涨停' if is_limit else ''}")
    
    # 分析4/7日的弱转强条件
    test_date = date(2026, 4, 7)
    print(f"\n{'='*70}")
    print(f"分析弱转强条件 - {test_date}")
    print("=" * 70)
    
    # 找到当日数据
    target_record = next((d for d in data if d['trade_date'] == test_date), None)
    if not target_record:
        print(f"未找到{test_date}的数据")
        return
    
    pct_chg = float(target_record.get('pct_chg', 0))
    print(f"当日数据:")
    print(f"  涨跌幅: {pct_chg:.2f}%")
    print(f"  开盘价: {target_record.get('open_price', 0)}")
    print(f"  最高价: {target_record.get('high_price', 0)}")
    print(f"  最低价: {target_record.get('low_price', 0)}")
    print(f"  收盘价: {target_record.get('close_price', 0)}")
    
    # 条件1: 当日弱势下跌
    condition1 = pct_chg < -2.0
    print(f"\n条件1 - 当日弱势下跌 (<-2%): {pct_chg:.2f}% → {'✅满足' if condition1 else '❌不满足'}")
    
    # 条件2: 前期强势（涨停模式分析）
    limit_up_pattern = analyze_limit_up_pattern(data, test_date, trading_days=7)
    print(f"\n条件2 - 前期强势（7个交易日内）:")
    print(f"  涨停模式: {limit_up_pattern['pattern_type']}")
    print(f"  涨停次数: {limit_up_pattern['limit_up_count']}")
    print(f"  最长连续涨停: {limit_up_pattern['max_consecutive_days']}天")
    print(f"  涨停日期: {limit_up_pattern['limit_up_dates']}")
    print(f"  是否有涨停模式: {'✅是' if limit_up_pattern['has_limit_up_pattern'] else '❌否'}")
    
    condition2 = limit_up_pattern['has_limit_up_pattern']
    print(f"  → {'✅满足' if condition2 else '❌不满足'}")
    
    # 检查更长时间范围（30天）的涨停情况
    limit_up_pattern_30 = analyze_limit_up_pattern(data, test_date, trading_days=30)
    print(f"\n补充分析（30个交易日内）:")
    print(f"  涨停次数: {limit_up_pattern_30['limit_up_count']}")
    print(f"  涨停日期: {limit_up_pattern_30['limit_up_dates']}")
    
    # 条件3: 缺口支撑分析
    gap_analysis = analyze_gap_support(data, test_date)
    print(f"\n条件3 - 缺口支撑分析:")
    print(f"  是否有缺口: {'✅是' if gap_analysis['has_gap'] else '❌否'}")
    print(f"  缺口类型: {gap_analysis.get('gap_type', 'N/A')}")
    print(f"  缺口支撑位: {gap_analysis.get('gap_support_level', 0):.2f}")
    print(f"  是否有缺口支撑: {'✅是' if gap_analysis.get('is_gap_support', False) else '❌否'}")
    
    if gap_analysis.get('technical_signals'):
        print(f"  技术信号:")
        for signal in gap_analysis['technical_signals']:
            print(f"    - {signal}")
    
    condition3 = gap_analysis.get('is_gap_support', False)
    print(f"  → {'✅满足' if condition3 else '❌不满足'}")
    
    # 综合判断
    print(f"\n{'='*70}")
    print(f"弱转强综合判断:")
    all_conditions = condition1 and condition2 and condition3
    if all_conditions:
        print(f"🎯 神剑股份在{test_date}完全满足弱转强所有条件！")
    else:
        print(f"❌ 神剑股份在{test_date}不满足弱转强条件")
        missing = []
        if not condition1: missing.append("当日弱势下跌")
        if not condition2: missing.append("前期强势")
        if not condition3: missing.append("到达支撑位")
        print(f"  缺失条件: {', '.join(missing)}")
    
    # 与数据库数据对比
    print(f"\n{'='*70}")
    print(f"与数据库数据对比:")
    print(f"JSONL文件数据（正确）:")
    print(f"  最高价: {target_record.get('high_price', 0)}")
    print(f"  最低价: {target_record.get('low_price', 0)}")
    print(f"  收盘价: {target_record.get('close_price', 0)}")
    
    # 数据库中的错误数据（根据之前测试）
    print(f"数据库数据（错误）:")
    print(f"  最高价: 15.25 (应16.47)")
    print(f"  最低价: 15.74 (应14.80)")
    print(f"  收盘价: 15.85 (应15.25)")
    print(f"  ⚠️ 数据库数据高低价颠倒且收盘价错误")
    
    # 生成修复SQL
    print(f"\n修复SQL建议:")
    print(f"UPDATE subject_stock_daily_snapshot SET")
    print(f"  high_price = 16.47,")
    print(f"  low_price = 14.80,")
    print(f"  close_price = 15.25")
    print(f"WHERE stock_id = '002361' AND trade_date = '2026-04-07';")

if __name__ == "__main__":
    main()
