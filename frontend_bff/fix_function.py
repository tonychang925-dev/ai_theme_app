import sys
import re

with open('app.py', 'r') as f:
    content = f.read()

# 找到函数定义
pattern = r'(async def _execute_weak_to_strong_two_stage\(payload: ScreenerExecutePayload, trade_date: date\) -> Dict\[str, Any\]:\s*\n\s*started = time\.perf_counter\(\))'
match = re.search(pattern, content, re.DOTALL)
if not match:
    print("未找到函数定义")
    sys.exit(1)

func_start = match.start()
func_header = match.group(1)

# 提取函数其余部分
remaining = content[func_start + len(func_header):]

# 新的函数开头
new_header = '''async def _execute_weak_to_strong_two_stage(payload: ScreenerExecutePayload, trade_date: date) -> Dict[str, Any]:
    
    started = time.perf_counter()
    # 获取策略信息
    strategy = await stock_screener_repo.get_strategy(payload.strategy_id)
    strategy_name = getattr(strategy, "strategy_name", "弱转强策略")

    # 读取执行阶段配置
    run_stage1 = bool(payload.run_stage1)
    run_stage2 = bool(payload.run_stage2)

    # 显式双日期协议：区分候选交易日和确认交易日
    candidate_trade_date: Optional[date] = None
    confirm_trade_date: Optional[date] = None

    if run_stage1 and not run_stage2:
        # 纯盘后选股：传进来的是候选交易日
        candidate_trade_date = trade_date
        confirm_trade_date = None
    elif run_stage2 and not run_stage1:
        # 纯盘前确认：传进来的是确认交易日
        confirm_trade_date = trade_date
        candidate_trade_date = await _resolve_prev_trade_date(confirm_trade_date)
    else:
        # 两阶段都执行：传进来的是候选交易日
        candidate_trade_date = trade_date
        confirm_trade_date = await _resolve_next_trade_date(candidate_trade_date)

    logger.info(f"弱转强日期协议: candidate_trade_date={candidate_trade_date}, confirm_trade_date={confirm_trade_date}, run_stage1={run_stage1}, run_stage2={run_stage2}")'''

# 替换函数开头
new_content = content[:func_start] + new_header + remaining

# 写入文件
with open('app.py', 'w') as f:
    f.write(new_content)

print("函数开头已更新")
