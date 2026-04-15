#!/usr/bin/env python3
"""测试MACD修复"""

import json
import pandas as pd
import numpy as np
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent
TUSHARE_KLINE_DIR = PROJECT_ROOT / "theme_data_complete" / "_stock_kline" / "tushare" / "daily_bar"

def load_data():
    """加载数据"""
    stock_code = "000636"
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

            amount_in_yuan = float(data.get('amount', 0)) * 1000 if data.get('amount') is not None else 0
            history.append({
                'date': data.get('trade_date', ''),
                'close': float(data.get('close_price', 0)) if data.get('close_price') is not None else 0
            })

    df = pd.DataFrame(history)
    df['date'] = pd.to_datetime(df['date'])
    df = df.sort_values('date', ascending=False)
    if len(df) > 20:
        df = df.head(20)
    df = df.sort_values('date')
    df.set_index('date', inplace=True)

    return df

def test_macd_manual(df):
    """测试手动MACD计算"""
    print(f"数据行数: {len(df)}")
    print(f"close数据:")
    print(df['close'].head())

    # 计算EMA
    df['EMA_12'] = df['close'].ewm(span=12, adjust=False).mean()
    df['EMA_26'] = df['close'].ewm(span=26, adjust=False).mean()

    print(f"\nEMA_12 (前5个值): {df['EMA_12'].head().tolist()}")
    print(f"EMA_12 (后5个值): {df['EMA_12'].tail().tolist()}")
    print(f"EMA_12是否有NaN: {df['EMA_12'].isna().any()}")

    print(f"\nEMA_26 (前5个值): {df['EMA_26'].head().tolist()}")
    print(f"EMA_26 (后5个值): {df['EMA_26'].tail().tolist()}")
    print(f"EMA_26是否有NaN: {df['EMA_26'].isna().any()}")

    # 计算MACD
    df['MACD'] = df['EMA_12'] - df['EMA_26']
    df['MACD_signal'] = df['MACD'].ewm(span=9, adjust=False).mean()
    df['MACD_hist'] = df['MACD'] - df['MACD_signal']

    print(f"\nMACD (后5个值): {df['MACD'].tail().tolist()}")
    print(f"MACD是否有NaN: {df['MACD'].isna().any()}")

    print(f"\nMACD_signal (后5个值): {df['MACD_signal'].tail().tolist()}")
    print(f"MACD_hist (后5个值): {df['MACD_hist'].tail().tolist()}")

    # 检查哪些是NaN
    macd_nan_count = df['MACD'].isna().sum()
    print(f"\nMACD列中NaN数量: {macd_nan_count}/{len(df)}")

    if macd_nan_count > 0:
        print("MACD NaN的位置:")
        print(df[df['MACD'].isna()][['close', 'EMA_12', 'EMA_26', 'MACD']].head())

def main():
    print("测试MACD手动计算...")
    df = load_data()
    print(f"数据日期范围: {df.index[0].date()} 至 {df.index[-1].date()}")

    test_macd_manual(df)

if __name__ == "__main__":
    main()