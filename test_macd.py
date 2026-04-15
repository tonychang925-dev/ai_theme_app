#!/usr/bin/env python3
import pandas as pd
import pandas_ta as ta

# 创建测试数据
data = pd.DataFrame({'close': [10,11,12,13,14,15,16,17,18,19,20,21,22,23,24,25,26,27,28,29,30,31,32,33,34,35,36,37,38,39,40]})

# 计算MACD - 指定参数
macd_result = ta.macd(data['close'], fast=12, slow=26, signal=9)

print('MACD结果类型:', type(macd_result))
if isinstance(macd_result, pd.DataFrame):
    print('列名:', list(macd_result.columns))
    print('\n前几行:')
    print(macd_result.head())
else:
    print('MACD结果:', macd_result)