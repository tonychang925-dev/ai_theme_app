#!/usr/bin/env python3
"""
调试MACD计算问题
"""

import json
import pandas as pd
import pandas_ta as ta
import numpy as np
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent
TUSHARE_KLINE_DIR = PROJECT_ROOT / "theme_data_complete" / "_stock_kline" / "tushare" / "daily_bar"

def load_tushare_data(stock_code="000636", days=20):
    """加载tushare数据"""
    if stock_code.startswith('6'):
        suffix = '.SH'
    else:
        suffix = '.SZ'

    file_name = f"{stock_code}{suffix}.jsonl"
    file_path = TUSHARE_KLINE_DIR / file_name

    history = []
    with open(file_path, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                data = json.loads(line)
            except json.JSONDecodeError:
                continue

            # tushare数据中amount单位为千元，转换为元
            amount_in_yuan = float(data.get('amount', 0)) * 1000 if data.get('amount') is not None else 0
            history.append({
                'date': data.get('trade_date', ''),
                'open': float(data.get('open_price', 0)) if data.get('open_price') is not None else 0,
                'high': float(data.get('high_price', 0)) if data.get('high_price') is not None else 0,
                'low': float(data.get('low_price', 0)) if data.get('low_price') is not None else 0,
                'close': float(data.get('close_price', 0)) if data.get('close_price') is not None else 0,
                'volume': float(data.get('volume', 0)) if data.get('volume') is not None else 0,
                'amount': amount_in_yuan,
                'pct_chg': float(data.get('pct_chg', 0)) if data.get('pct_chg') is not None else 0
            })

    df = pd.DataFrame(history)
    df['date'] = pd.to_datetime(df['date'])
    df = df.sort_values('date', ascending=False)
    if len(df) > days:
        df = df.head(days)
    df = df.sort_values('date')
    df.set_index('date', inplace=True)

    return df

def test_macd_calculation(df):
    """测试MACD计算"""
    print(f"数据形状: {df.shape}")
    print(f"数据预览:")
    print(df[['close']].head())
    print(f"\nclose列数据类型: {df['close'].dtype}")
    print(f"close列是否有NaN: {df['close'].isna().any()}")

    # 1. 尝试使用pandas-ta的macd函数
    print("\n1. 使用pandas-ta的macd函数:")
    try:
        macd_result = ta.macd(df['close'], fast=12, slow=26, signal=9)
        print(f"macd_result类型: {type(macd_result)}")
        if isinstance(macd_result, pd.DataFrame):
            print(f"列名: {list(macd_result.columns)}")
            print(f"形状: {macd_result.shape}")
            print(f"前5行:")
            print(macd_result.head())
            # 检查是否有NaN
            for col in macd_result.columns:
                if macd_result[col].isna().all():
                    print(f"警告: 列 {col} 全部为NaN")
        elif macd_result is None:
            print("macd_result为None")
        else:
            print(f"macd_result: {macd_result}")
    except Exception as e:
        print(f"pandas-ta macd函数出错: {e}")

    # 2. 手动计算MACD
    print("\n2. 手动计算MACD:")
    try:
        ema12 = df['close'].ewm(span=12, adjust=False).mean()
        ema26 = df['close'].ewm(span=26, adjust=False).mean()
        macd_line = ema12 - ema26
        signal_line = macd_line.ewm(span=9, adjust=False).mean()
        macd_hist = macd_line - signal_line

        print(f"EMA12最后5个值: {ema12.iloc[-5:].tolist()}")
        print(f"EMA26最后5个值: {ema26.iloc[-5:].tolist()}")
        print(f"MACD线最后5个值: {macd_line.iloc[-5:].tolist()}")
        print(f"信号线最后5个值: {signal_line.iloc[-5:].tolist()}")
        print(f"MACD直方图最后5个值: {macd_hist.iloc[-5:].tolist()}")
    except Exception as e:
        print(f"手动计算MACD出错: {e}")

    # 3. 检查数据长度
    print(f"\n3. 数据长度检查:")
    print(f"数据行数: {len(df)}")
    if len(df) < 26:
        print(f"警告: 数据只有{len(df)}行，少于MACD需要的26行")

def main():
    print("调试MACD计算...")

    # 加载数据
    df = load_tushare_data("000636", days=30)  # 加载30天数据
    print(f"加载了 {len(df)} 天数据 ({df.index[0].date()} 至 {df.index[-1].date()})")

    # 测试MACD计算
    test_macd_calculation(df)

    # 检查pandas-ta版本
    print(f"\npandas-ta版本: {ta.__version__ if hasattr(ta, '__version__') else '未知'}")

if __name__ == "__main__":
    main()