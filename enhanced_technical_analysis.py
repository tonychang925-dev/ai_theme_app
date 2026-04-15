#!/usr/bin/env python3
"""
增强技术分析脚本 - 基于历史K线和开源技术分析框架
支持：移动平均线、MACD、RSI、布林带、成交量指标、K线模式识别
"""

import json
import pandas as pd
import numpy as np
from pathlib import Path
from datetime import datetime, timedelta
import warnings
warnings.filterwarnings('ignore')

# 尝试导入技术分析库
TECH_LIBS_AVAILABLE = {
    'pandas_ta': False,
    'talib': False,
    'ta': False
}

try:
    import pandas_ta as ta
    TECH_LIBS_AVAILABLE['pandas_ta'] = True
    print("✓ pandas-ta 已加载")
except ImportError:
    print("⚠ pandas-ta 未安装，使用 'pip install pandas-ta' 安装")

try:
    import talib
    TECH_LIBS_AVAILABLE['talib'] = True
    print("✓ TA-Lib 已加载")
except ImportError:
    print("⚠ TA-Lib 未安装，使用 'pip install TA-Lib' 安装")

try:
    import ta as ta_simple
    TECH_LIBS_AVAILABLE['ta'] = True
    print("✓ ta 已加载")
except ImportError:
    print("⚠ ta 未安装，使用 'pip install ta' 安装")

PROJECT_ROOT = Path(__file__).resolve().parent
STOCK_DAILY_DIR = PROJECT_ROOT / "theme_data_complete" / "stock_daily"
TUSHARE_KLINE_DIR = PROJECT_ROOT / "theme_data_complete" / "_stock_kline" / "tushare" / "daily_bar"

def load_tushare_kline_data(stock_code="000636", days=20, end_date="2026-04-08"):
    """
    从tushare K线数据加载股票历史数据

    Args:
        stock_code: 股票代码（如"000636"）
        days: 需要加载的交易天数
        end_date: 结束日期

    Returns:
        pandas DataFrame with columns: date, open, high, low, close, volume, amount, pct_chg
    """
    # 构建文件路径：股票代码需要转换为文件格式（如000636.SZ.jsonl）
    if stock_code.startswith('6'):
        suffix = '.SH'
    else:
        suffix = '.SZ'

    file_name = f"{stock_code}{suffix}.jsonl"
    file_path = TUSHARE_KLINE_DIR / file_name

    if not file_path.exists():
        print(f"⚠ tushare数据文件不存在: {file_path}")
        return pd.DataFrame()

    history = []
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue

                try:
                    data = json.loads(line)
                except json.JSONDecodeError:
                    continue

                trade_date = data.get('trade_date', '')

                # 如果指定了结束日期，跳过结束日期之后的数据
                if end_date and trade_date > end_date:
                    continue

                # tushare数据中amount单位为千元，转换为元以保持与stock_daily数据一致
                amount_in_yuan = float(data.get('amount', 0)) * 1000 if data.get('amount') is not None else 0
                history.append({
                    'date': trade_date,
                    'open': float(data.get('open_price', 0)) if data.get('open_price') is not None else 0,
                    'high': float(data.get('high_price', 0)) if data.get('high_price') is not None else 0,
                    'low': float(data.get('low_price', 0)) if data.get('low_price') is not None else 0,
                    'close': float(data.get('close_price', 0)) if data.get('close_price') is not None else 0,
                    'volume': float(data.get('volume', 0)) if data.get('volume') is not None else 0,
                    'amount': amount_in_yuan,  # 已转换为元
                    'pct_chg': float(data.get('pct_chg', 0)) if data.get('pct_chg') is not None else 0
                })
    except Exception as e:
        print(f"❌ 读取tushare数据失败: {e}")
        return pd.DataFrame()

    if not history:
        print(f"❌ tushare数据文件中未找到有效数据: {file_path}")
        return pd.DataFrame()

    # 转换为DataFrame并按日期排序
    df = pd.DataFrame(history)
    df['date'] = pd.to_datetime(df['date'])
    df = df.sort_values('date', ascending=False)  # 降序排列，最新的在前面

    # 取最近days天的数据
    if len(df) > days:
        df = df.head(days)

    df = df.sort_values('date')  # 升序排列，最旧的在前面
    df.set_index('date', inplace=True)

    print(f"✓ 从tushare加载 {len(df)} 个交易日数据 ({df.index[0].date()} 至 {df.index[-1].date()})")
    return df

def load_stock_history(stock_code="000636", days=20, end_date="2026-04-08"):
    """
    加载股票历史K线数据（优先使用tushare数据，如果不可用则回退到stock_daily数据）

    Args:
        stock_code: 股票代码
        days: 需要加载的交易天数
        end_date: 结束日期

    Returns:
        pandas DataFrame with columns: date, open, high, low, close, volume, amount
    """
    print("🔄 尝试加载股票历史数据...")

    # 优先尝试tushare数据
    tushare_df = load_tushare_kline_data(stock_code, days, end_date)
    if not tushare_df.empty:
        print("✅ 使用tushare数据")
        return tushare_df

    print("⚠ tushare数据不可用，尝试stock_daily数据...")

    # 回退到stock_daily数据
    history = []
    dates_loaded = set()

    # 查找所有可用的数据文件
    all_files = list(STOCK_DAILY_DIR.glob("*_stocks.jsonl"))

    if not all_files:
        print(f"❌ 未找到股票数据文件，请检查目录: {STOCK_DAILY_DIR}")
        return pd.DataFrame()

    print(f"📁 扫描 {len(all_files)} 个数据文件...")

    # 遍历所有文件，收集股票数据
    for file_path in all_files:
        try:
            # 从文件名解析日期
            filename = file_path.name
            parts = filename.split('_')
            if len(parts) < 2:
                continue

            file_date_str = parts[1]  # 文件日期

            # 跳过结束日期之后的日期
            if file_date_str > end_date:
                continue

            with open(file_path, 'r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue

                    try:
                        data = json.loads(line)
                    except json.JSONDecodeError:
                        continue

                    # 检查股票代码匹配
                    if isinstance(data, list) and len(data) > 2:
                        if data[2] == stock_code:  # 股票代码匹配
                            # 解析OHLCV数据
                            trade_date = data[0]
                            if isinstance(trade_date, str):
                                date_only = trade_date.split()[0]  # 提取日期部分
                            else:
                                date_only = str(trade_date)

                            # 确保日期与文件日期一致
                            if date_only != file_date_str:
                                # 如果不一致，使用文件日期（更可靠）
                                date_only = file_date_str

                            if date_only in dates_loaded:
                                continue  # 避免重复（同一天的数据）

                            history.append({
                                'date': date_only,
                                'open': float(data[4]) if data[4] is not None else 0,
                                'high': float(data[5]) if data[5] is not None else 0,
                                'low': float(data[6]) if data[6] is not None else 0,
                                'close': float(data[7]) if data[7] is not None else 0,
                                'volume': float(data[12]) if data[12] is not None else 0,
                                'amount': float(data[13]) if data[13] is not None else 0,
                                'pct_chg': float(data[10]) if len(data) > 10 and data[10] is not None else 0,
                                'turnover': float(data[15]) if len(data) > 15 and data[15] is not None else 0
                            })
                            dates_loaded.add(date_only)
                            break  # 找到股票后跳出当前文件循环
        except Exception as e:
            # 忽略单个文件错误，继续处理其他文件
            continue

    if not history:
        print(f"❌ 未找到股票 {stock_code} 的历史数据")
        return pd.DataFrame()

    # 转换为DataFrame并按日期排序
    df = pd.DataFrame(history)
    df['date'] = pd.to_datetime(df['date'])
    df = df.sort_values('date', ascending=False)  # 降序排列，最新的在前面

    # 取最近days天的数据
    if len(df) > days:
        df = df.head(days)

    df = df.sort_values('date')  # 升序排列，最旧的在前面
    df.set_index('date', inplace=True)

    print(f"✓ 从stock_daily加载 {len(df)} 个交易日数据 ({df.index[0].date()} 至 {df.index[-1].date()})")
    return df

def calculate_technical_indicators(df):
    """
    计算技术指标
    """
    if df.empty or len(df) < 5:
        print("⚠ 数据不足，至少需要5个交易日")
        return df

    df_ta = df.copy()

    # 1. 移动平均线 (使用基础计算如果库不可用)
    if TECH_LIBS_AVAILABLE['pandas_ta']:
        try:
            df_ta['SMA_5'] = ta.sma(df_ta['close'], length=5)
            df_ta['SMA_10'] = ta.sma(df_ta['close'], length=10)
            df_ta['SMA_20'] = ta.sma(df_ta['close'], length=20)
            df_ta['EMA_12'] = ta.ema(df_ta['close'], length=12)
            df_ta['EMA_26'] = ta.ema(df_ta['close'], length=26)

            # 检查EMA计算是否有效
            if df_ta['EMA_12'].isna().all() or df_ta['EMA_26'].isna().all():
                raise ValueError("EMA计算结果无效")
        except Exception as e:
            print(f"⚠ pandas-ta EMA计算失败，使用手动计算: {e}")
            # 回退到手动计算
            df_ta['SMA_5'] = df_ta['close'].rolling(window=5).mean()
            df_ta['SMA_10'] = df_ta['close'].rolling(window=10).mean()
            df_ta['SMA_20'] = df_ta['close'].rolling(window=20).mean()
            df_ta['EMA_12'] = df_ta['close'].ewm(span=12, adjust=False).mean()
            df_ta['EMA_26'] = df_ta['close'].ewm(span=26, adjust=False).mean()
    else:
        # 手动计算简单移动平均
        df_ta['SMA_5'] = df_ta['close'].rolling(window=5).mean()
        df_ta['SMA_10'] = df_ta['close'].rolling(window=10).mean()
        df_ta['SMA_20'] = df_ta['close'].rolling(window=20).mean()
        # 指数移动平均
        df_ta['EMA_12'] = df_ta['close'].ewm(span=12, adjust=False).mean()
        df_ta['EMA_26'] = df_ta['close'].ewm(span=26, adjust=False).mean()

    # 2. MACD指标
    if TECH_LIBS_AVAILABLE['pandas_ta']:
        try:
            macd_result = ta.macd(df_ta['close'], fast=12, slow=26, signal=9)
            if macd_result is not None and isinstance(macd_result, pd.DataFrame):
                # pandas-ta返回的列名格式为: MACD_12_26_9, MACDs_12_26_9, MACDh_12_26_9
                macd_col = f"MACD_12_26_9"
                signal_col = f"MACDs_12_26_9"
                hist_col = f"MACDh_12_26_9"
                if macd_col in macd_result.columns:
                    df_ta['MACD'] = macd_result[macd_col]
                    df_ta['MACD_signal'] = macd_result[signal_col]
                    df_ta['MACD_hist'] = macd_result[hist_col]
                else:
                    # 列名不匹配，回退到手动计算
                    raise ValueError("MACD列名不匹配")
            else:
                # 结果无效，回退到手动计算
                raise ValueError("MACD计算结果无效")
        except Exception as e:
            print(f"⚠ pandas-ta MACD计算失败，使用手动计算: {e}")
            # 手动计算MACD
            ema12 = df_ta['EMA_12']
            ema26 = df_ta['EMA_26']
            df_ta['MACD'] = ema12 - ema26
            df_ta['MACD_signal'] = df_ta['MACD'].ewm(span=9, adjust=False).mean()
            df_ta['MACD_hist'] = df_ta['MACD'] - df_ta['MACD_signal']
    else:
        # 手动计算MACD
        ema12 = df_ta['EMA_12']
        ema26 = df_ta['EMA_26']
        df_ta['MACD'] = ema12 - ema26
        df_ta['MACD_signal'] = df_ta['MACD'].ewm(span=9, adjust=False).mean()
        df_ta['MACD_hist'] = df_ta['MACD'] - df_ta['MACD_signal']

    # 3. RSI指标
    if TECH_LIBS_AVAILABLE['pandas_ta']:
        df_ta['RSI_14'] = ta.rsi(df_ta['close'], length=14)
    elif TECH_LIBS_AVAILABLE['ta']:
        df_ta['RSI_14'] = ta_simple.momentum.RSIIndicator(df_ta['close'], window=14).rsi()
    else:
        # 手动计算RSI
        delta = df_ta['close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
        rs = gain / loss
        df_ta['RSI_14'] = 100 - (100 / (1 + rs))

    # 4. 布林带
    if TECH_LIBS_AVAILABLE['pandas_ta']:
        bb_result = ta.bbands(df_ta['close'], length=20)
        if isinstance(bb_result, pd.DataFrame):
            # pandas-ta返回的列名格式为: BBU_20_2.0_2.0, BBM_20_2.0_2.0, BBL_20_2.0_2.0
            upper_col = f"BBU_20_2.0_2.0"
            middle_col = f"BBM_20_2.0_2.0"
            lower_col = f"BBL_20_2.0_2.0"
            if upper_col in bb_result.columns:
                df_ta['BB_upper'] = bb_result[upper_col]
                df_ta['BB_middle'] = bb_result[middle_col]
                df_ta['BB_lower'] = bb_result[lower_col]
            else:
                # 回退到手动计算
                sma20 = df_ta['close'].rolling(window=20).mean()
                std20 = df_ta['close'].rolling(window=20).std()
                df_ta['BB_middle'] = sma20
                df_ta['BB_upper'] = sma20 + 2 * std20
                df_ta['BB_lower'] = sma20 - 2 * std20
    else:
        # 手动计算布林带
        sma20 = df_ta['close'].rolling(window=20).mean()
        std20 = df_ta['close'].rolling(window=20).std()
        df_ta['BB_middle'] = sma20
        df_ta['BB_upper'] = sma20 + 2 * std20
        df_ta['BB_lower'] = sma20 - 2 * std20

    # 5. 成交量指标
    df_ta['volume_ma5'] = df_ta['volume'].rolling(window=5).mean()
    df_ta['volume_ratio'] = df_ta['volume'] / df_ta['volume_ma5']

    # 价格与成交量关系
    df_ta['price_volume_trend'] = np.where(
        (df_ta['close'] > df_ta['close'].shift(1)) & (df_ta['volume'] > df_ta['volume_ma5']),
        '价量齐升',
        np.where(
            (df_ta['close'] < df_ta['close'].shift(1)) & (df_ta['volume'] > df_ta['volume_ma5']),
            '放量下跌',
            '量价正常'
        )
    )

    return df_ta

def identify_candle_patterns(df):
    """
    识别K线蜡烛图模式
    """
    patterns = {}

    if TECH_LIBS_AVAILABLE['talib'] and len(df) >= 3:
        try:
            # 常见单日模式
            patterns['doji'] = talib.CDLDOJI(df['open'], df['high'], df['low'], df['close'])
            patterns['hammer'] = talib.CDLHAMMER(df['open'], df['high'], df['low'], df['close'])
            patterns['inverted_hammer'] = talib.CDLINVERTEDHAMMER(df['open'], df['high'], df['low'], df['close'])
            patterns['engulfing'] = talib.CDLENGULFING(df['open'], df['high'], df['low'], df['close'])
            patterns['harami'] = talib.CDLHARAMI(df['open'], df['high'], df['low'], df['close'])

            # 多日模式
            patterns['morning_star'] = talib.CDLMORNINGSTAR(df['open'], df['high'], df['low'], df['close'])
            patterns['evening_star'] = talib.CDLEVENINGSTAR(df['open'], df['high'], df['low'], df['close'])
        except Exception as e:
            print(f"⚠ K线模式识别出错: {e}")

    # 检查最近是否有模式出现
    recent_patterns = {}
    if patterns:
        for name, values in patterns.items():
            if not values.empty and values.iloc[-1] != 0:
                pattern_strength = abs(values.iloc[-1])
                recent_patterns[name] = {
                    'strength': pattern_strength,
                    'signal': '看涨' if values.iloc[-1] > 0 else '看跌',
                    'description': get_candle_pattern_description(name, values.iloc[-1])
                }

    return recent_patterns

def get_candle_pattern_description(pattern_name, value):
    """获取K线模式描述"""
    descriptions = {
        'doji': '十字星，表示市场犹豫不决',
        'hammer': '锤子线，底部反转信号',
        'inverted_hammer': '倒锤子线，潜在底部信号',
        'engulfing': '吞没形态，强烈反转信号',
        'harami': '孕线，趋势可能反转',
        'morning_star': '早晨之星，底部反转',
        'evening_star': '黄昏之星，顶部反转'
    }
    base_desc = descriptions.get(pattern_name, pattern_name)
    direction = "看涨" if value > 0 else "看跌"
    return f"{direction} - {base_desc}"

def assess_technical_condition(df):
    """
    综合技术形态评估
    """
    if df.empty or len(df) < 5:
        return {"error": "数据不足"}

    latest = df.iloc[-1]
    prev_day = df.iloc[-2] if len(df) >= 2 else latest

    assessment = {}

    # 1. 趋势判断
    if 'SMA_5' in df.columns and 'SMA_20' in df.columns:
        sma_5_today = latest['SMA_5']
        sma_20_today = latest['SMA_20']
        sma_5_yesterday = prev_day['SMA_5'] if len(df) >= 2 else sma_5_today

        price_position = ""
        if pd.notna(sma_5_today) and pd.notna(sma_20_today):
            if latest['close'] > sma_5_today > sma_20_today:
                price_position = "强势上涨"
            elif sma_5_today > latest['close'] > sma_20_today:
                price_position = "震荡整理"
            elif latest['close'] < sma_20_today:
                price_position = "弱势下跌"
            else:
                price_position = "横盘整理"

            # 均线排列
            if sma_5_today > sma_20_today:
                ma_alignment = "多头排列"
            elif sma_5_today < sma_20_today:
                ma_alignment = "空头排列"
            else:
                ma_alignment = "均线粘合"
        else:
            price_position = "数据不足"
            ma_alignment = "数据不足"

        assessment['trend'] = {
            'price_position': price_position,
            'ma_alignment': ma_alignment,
            'sma_5': round(sma_5_today, 2) if pd.notna(sma_5_today) else None,
            'sma_20': round(sma_20_today, 2) if pd.notna(sma_20_today) else None
        }

    # 2. MACD信号
    if 'MACD' in df.columns and 'MACD_signal' in df.columns:
        macd = latest['MACD']
        macd_signal = latest['MACD_signal']
        macd_hist = latest.get('MACD_hist', 0)

        if pd.notna(macd) and pd.notna(macd_signal):
            if macd > macd_signal:
                macd_signal_type = "金叉"
            else:
                macd_signal_type = "死叉"

            # 判断背离
            macd_divergence = "无"
            if len(df) >= 10:
                price_trend = df['close'].iloc[-5:].mean() > df['close'].iloc[-10:-5].mean()
                macd_trend = df['MACD'].iloc[-5:].mean() > df['MACD'].iloc[-10:-5].mean()
                if price_trend != macd_trend:
                    macd_divergence = "顶背离" if price_trend and not macd_trend else "底背离"

            assessment['macd'] = {
                'signal': macd_signal_type,
                'divergence': macd_divergence,
                'value': round(macd, 4),
                'signal_line': round(macd_signal, 4),
                'histogram': round(macd_hist, 4)
            }

    # 3. RSI状态
    if 'RSI_14' in df.columns:
        rsi = latest['RSI_14']
        if pd.notna(rsi):
            if rsi > 70:
                rsi_status = "超买"
            elif rsi < 30:
                rsi_status = "超卖"
            else:
                rsi_status = "正常"

            assessment['rsi'] = {
                'status': rsi_status,
                'value': round(rsi, 2),
                'overbought': rsi > 70,
                'oversold': rsi < 30
            }

    # 4. 布林带分析
    if all(col in df.columns for col in ['BB_upper', 'BB_middle', 'BB_lower']):
        bb_upper = latest['BB_upper']
        bb_middle = latest['BB_middle']
        bb_lower = latest['BB_lower']

        if pd.notna(bb_upper) and pd.notna(bb_lower):
            close_price = latest['close']
            bb_position = ""
            bb_width = bb_upper - bb_lower

            if close_price > bb_upper:
                bb_position = "突破上轨"
            elif close_price < bb_lower:
                bb_position = "跌破下轨"
            else:
                bb_position = "轨道内运行"

            # 布林带宽度（波动率）
            if len(df) >= 20:
                bb_width_ma = df['BB_upper'].iloc[-20:] - df['BB_lower'].iloc[-20:]
                avg_bb_width = bb_width_ma.mean()
                if bb_width > avg_bb_width * 1.2:
                    volatility = "高波动"
                elif bb_width < avg_bb_width * 0.8:
                    volatility = "低波动"
                else:
                    volatility = "正常波动"
            else:
                volatility = "数据不足"

            assessment['bollinger'] = {
                'position': bb_position,
                'volatility': volatility,
                'upper': round(bb_upper, 2),
                'middle': round(bb_middle, 2),
                'lower': round(bb_lower, 2),
                'width': round(bb_width, 2)
            }

    # 5. 成交量分析
    if 'volume_ratio' in df.columns:
        volume_ratio = latest['volume_ratio']
        price_volume_trend = latest.get('price_volume_trend', '未知')

        assessment['volume'] = {
            'volume_ratio': round(volume_ratio, 2) if pd.notna(volume_ratio) else None,
            'trend': price_volume_trend,
            'volume_ma5': round(latest.get('volume_ma5', 0)) if pd.notna(latest.get('volume_ma5')) else None
        }

    # 6. 关键价位
    if len(df) >= 10:
        recent_high = df['high'].iloc[-10:].max()
        recent_low = df['low'].iloc[-10:].min()
        current_close = latest['close']

        assessment['key_levels'] = {
            'resistance': round(recent_high * 1.02, 2),  # 近期高点+2%
            'support': round(recent_low * 0.98, 2),     # 近期低点-2%
            'pivot_point': round((latest['high'] + latest['low'] + latest['close']) / 3, 2),
            'current_close': round(current_close, 2)
        }

    # 7. K线模式识别
    candle_patterns = identify_candle_patterns(df)
    if candle_patterns:
        assessment['candle_patterns'] = candle_patterns

    return assessment

def generate_technical_report(stock_code, stock_name, assessment, df):
    """
    生成技术分析报告
    """
    if not assessment or 'error' in assessment:
        return "技术分析失败：数据不足或计算错误"

    report = []
    report.append("=" * 80)
    report.append(f"📈 {stock_name} ({stock_code}) 技术分析报告")
    report.append(f"分析周期: {len(df)}个交易日 ({df.index[0].date()} 至 {df.index[-1].date()})")
    report.append("=" * 80)

    # 趋势分析
    if 'trend' in assessment:
        trend = assessment['trend']
        report.append("\n🎯 趋势分析")
        report.append(f"   价格位置: {trend['price_position']}")
        report.append(f"   均线排列: {trend['ma_alignment']}")
        if trend['sma_5']:
            report.append(f"   5日均线: {trend['sma_5']}元")
        if trend['sma_20']:
            report.append(f"   20日均线: {trend['sma_20']}元")

    # MACD分析
    if 'macd' in assessment:
        macd = assessment['macd']
        report.append("\n📊 MACD指标")
        report.append(f"   信号: {macd['signal']}")
        report.append(f"   背离: {macd['divergence']}")
        report.append(f"   MACD值: {macd['value']}")
        report.append(f"   信号线: {macd['signal_line']}")

    # RSI分析
    if 'rsi' in assessment:
        rsi = assessment['rsi']
        report.append("\n📈 RSI指标")
        report.append(f"   状态: {rsi['status']} (值: {rsi['value']})")
        if rsi['overbought']:
            report.append("   ⚠️ 注意: RSI超买，短期可能有回调压力")
        elif rsi['oversold']:
            report.append("   💡 机会: RSI超卖，可能出现技术性反弹")

    # 布林带分析
    if 'bollinger' in assessment:
        bb = assessment['bollinger']
        report.append("\n🎪 布林带分析")
        report.append(f"   位置: {bb['position']}")
        report.append(f"   波动率: {bb['volatility']}")
        report.append(f"   上轨: {bb['upper']}元")
        report.append(f"   中轨: {bb['middle']}元")
        report.append(f"   下轨: {bb['lower']}元")

    # 成交量分析
    if 'volume' in assessment:
        volume = assessment['volume']
        report.append("\n📦 成交量分析")
        if volume['volume_ratio']:
            report.append(f"   量比: {volume['volume_ratio']}")
            if volume['volume_ratio'] > 1.5:
                report.append("   📈 放量明显，资金关注度高")
            elif volume['volume_ratio'] < 0.8:
                report.append("   📉 缩量明显，交投清淡")
        report.append(f"   量价关系: {volume['trend']}")

    # K线模式
    if 'candle_patterns' in assessment:
        report.append("\n🕯️ K线模式识别")
        for pattern_name, pattern_info in assessment['candle_patterns'].items():
            report.append(f"   • {pattern_name}: {pattern_info['signal']} - {pattern_info['description']}")

    # 关键价位
    if 'key_levels' in assessment:
        levels = assessment['key_levels']
        report.append("\n🔑 关键价位")
        report.append(f"   当前收盘: {levels['current_close']}元")
        report.append(f"   压力位: {levels['resistance']}元")
        report.append(f"   支撑位: {levels['support']}元")
        report.append(f"   枢轴点: {levels['pivot_point']}元")

    # 综合建议
    report.append("\n" + "=" * 80)
    report.append("💡 综合技术面建议")

    recommendations = []

    # 基于趋势判断
    if 'trend' in assessment:
        trend = assessment['trend']
        if "强势上涨" in trend['price_position']:
            recommendations.append("趋势向好，可考虑持股或逢低吸纳")
        elif "弱势下跌" in trend['price_position']:
            recommendations.append("趋势偏弱，建议谨慎观望")

    # 基于RSI判断
    if 'rsi' in assessment:
        rsi = assessment['rsi']
        if rsi['overbought']:
            recommendations.append("RSI超买，注意短期调整风险")
        elif rsi['oversold']:
            recommendations.append("RSI超卖，可能出现技术性反弹机会")

    # 基于布林带判断
    if 'bollinger' in assessment:
        bb = assessment['bollinger']
        if "突破上轨" in bb['position']:
            recommendations.append("突破布林带上轨，强势但需注意回调")
        elif "跌破下轨" in bb['position']:
            recommendations.append("跌破布林带下轨，超跌可能出现反弹")

    if recommendations:
        for i, rec in enumerate(recommendations, 1):
            report.append(f"   {i}. {rec}")
    else:
        report.append("   技术面中性，建议结合基本面和资金面综合判断")

    report.append("\n" + "=" * 80)
    report.append(f"📅 报告生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    return "\n".join(report)

def main():
    """主函数"""
    print("🔧 增强技术分析脚本启动...")
    print(f"技术分析库状态: {TECH_LIBS_AVAILABLE}")

    # 示例分析风华高科
    stock_code = "000636"
    stock_name = "风华高科"
    days = 20  # 分析20个交易日

    print(f"\n📊 分析股票: {stock_name} ({stock_code})")
    print(f"分析周期: 最近{days}个交易日")

    # 1. 加载历史数据
    print("\n1️⃣ 加载历史K线数据...")
    df = load_stock_history(stock_code, days=days)

    if df.empty:
        print("❌ 无法加载股票数据，请检查数据文件")
        return

    print(f"✓ 成功加载 {len(df)} 天数据")
    print(f"   最新收盘: {df['close'].iloc[-1]}元 (日期: {df.index[-1].date()})")
    print(f"   价格区间: {df['low'].min():.2f} - {df['high'].max():.2f}元")

    # 2. 计算技术指标
    print("\n2️⃣ 计算技术指标...")
    df_ta = calculate_technical_indicators(df)

    if df_ta.empty:
        print("❌ 技术指标计算失败")
        return

    # 3. 综合技术评估
    print("\n3️⃣ 综合技术评估...")
    assessment = assess_technical_condition(df_ta)

    # 4. 生成报告
    print("\n4️⃣ 生成技术分析报告...")
    report = generate_technical_report(stock_code, stock_name, assessment, df_ta)

    # 输出报告
    print("\n" + report)

    # 5. 保存报告到文件
    output_file = f"technical_report_{stock_code}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
    with open(output_file, 'w', encoding='utf-8') as f:
        f.write(report)

    print(f"\n💾 报告已保存至: {output_file}")

    # 显示数据摘要
    print("\n" + "=" * 80)
    print("📋 技术数据摘要")
    print("=" * 80)

    if len(df_ta) >= 5:
        latest_data = df_ta.iloc[-1]
        print(f"\n最新交易日 ({df_ta.index[-1].date()}):")
        print(f"   收盘价: {latest_data['close']:.2f}元")
        print(f"   涨跌幅: {latest_data.get('pct_chg', 'N/A'):.2f}%")
        print(f"   成交量: {latest_data['volume']:,.0f}手")
        print(f"   成交额: {latest_data['amount']/100000000:.2f}亿元")

        if 'SMA_5' in latest_data and pd.notna(latest_data['SMA_5']):
            print(f"\n技术指标:")
            print(f"   5日均线: {latest_data['SMA_5']:.2f}元")
            print(f"   20日均线: {latest_data.get('SMA_20', 'N/A')}")
            print(f"   RSI(14): {latest_data.get('RSI_14', 'N/A')}")
            if 'MACD' in latest_data:
                print(f"   MACD: {latest_data['MACD']:.4f}")

if __name__ == "__main__":
    main()