#!/usr/bin/env python3
"""调试enhanced_technical_analysis.py中的MACD问题"""

import sys
sys.path.append('.')  # 添加当前目录到路径

import enhanced_technical_analysis as ta

print("调试enhanced_technical_analysis.py...")

# 加载数据
df = ta.load_stock_history("000636", days=20)
print(f"数据加载成功，形状: {df.shape}")

# 计算技术指标
df_ta = ta.calculate_technical_indicators(df)
print(f"技术指标计算完成，形状: {df_ta.shape}")

# 检查MACD相关列
macd_cols = ['MACD', 'MACD_signal', 'MACD_hist', 'EMA_12', 'EMA_26']
for col in macd_cols:
    if col in df_ta.columns:
        print(f"{col}: 存在, 最后值: {df_ta[col].iloc[-1]}, 是否有NaN: {df_ta[col].isna().any()}")
    else:
        print(f"{col}: 不存在")

# 检查最新的值
latest = df_ta.iloc[-1]
print(f"\n最新交易日 ({df_ta.index[-1].date()}):")
for col in ['close', 'MACD', 'MACD_signal', 'EMA_12', 'EMA_26', 'RSI_14']:
    if col in df_ta.columns:
        print(f"  {col}: {latest[col]}")

# 运行技术评估
assessment = ta.assess_technical_condition(df_ta)
print(f"\n技术评估结果:")
if 'macd' in assessment:
    print(f"MACD评估: {assessment['macd']}")
else:
    print("MACD评估: 未包含在结果中")