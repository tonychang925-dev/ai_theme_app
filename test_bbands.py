#!/usr/bin/env python3
import pandas as pd
import pandas_ta as ta

# 创建测试数据
data = pd.DataFrame({'close': [10,11,12,13,14,15,16,17,18,19,20,21,22,23,24,25,26,27,28,29]})

# 计算布林带
bb = ta.bbands(data['close'], length=5)

print('BB结果类型:', type(bb))
if isinstance(bb, pd.DataFrame):
    print('列名:', list(bb.columns))
    print('\n前几行:')
    print(bb.head())
else:
    print('BB结果:', bb)