#!/usr/bin/env python3
"""
简化版测试运行器 - 运行28字段表结构的核心测试
"""
import subprocess
import sys
import os
import time
from pathlib import Path
from datetime import datetime

# 颜色输出
class Colors:
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    RED = '\033[91m'
    BLUE = '\033[94m'
    CYAN = '\033[96m'
    PURPLE = '\033[95m'
    BOLD = '\033[1m'
    UNDERLINE = '\033[4m'
    END = '\033[0m'

def print_header(title: str):
    """打印标题"""
    print(f"\n{Colors.CYAN}{'='*60}{Colors.END}")
    print(f"{Colors.BOLD}{Colors.CYAN}{title}{Colors.END}")
    print(f"{Colors.CYAN}{'='*60}{Colors.END}")

def run_simple_test(test_name: str, test_file: str, args: list = None):
    """运行单个测试"""
    print(f"\n{Colors.BLUE}▶️  运行测试: {test_name}{Colors.END}")
    
    test_path = Path(test_file)
    if not test_path.exists():
        print(f"{Colors.YELLOW}⚠️  测试文件不存在: {test_file}{Colors.END}")
        return {"status": "skipped", "reason": "文件不存在"}
    
    start_time = time.time()
    
    # 构建命令
    cmd = [sys.executable, str(test_path)]
    if args:
        cmd.extend(args)
    
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=300,
            cwd=Path(__file__).parent.parent  # 在项目根目录运行
        )
        
        execution_time = time.time() - start_time
        
        if result.returncode == 0:
            print(f"{Colors.GREEN}✅ 测试通过 ({execution_time:.2f}秒){Colors.END}")
            
            # 尝试解析测试输出
            if "✅ 所有" in result.stdout or "测试通过" in result.stdout:
                print(f"   输出: {result.stdout.strip().split('\\n')[-1]}")
            
            return {
                "status": "passed",
                "execution_time": execution_time,
                "returncode": result.returncode,
                "stdout": result.stdout[-500:],  # 只保留最后500字符
                "stderr": result.stderr[-500:]
            }
        else:
            print(f"{Colors.RED}❌ 测试失败 ({execution_time:.2f}秒){Colors.END}")
            
            # 提取错误信息
            error_lines = []
            for line in (result.stderr + result.stdout).split('\n'):
                if any(keyword in line.lower() for keyword in 
                      ['error', 'fail', 'exception', 'assertion']):
                    error_lines.append(line.strip())
            
            if error_lines:
                print(f"   错误信息:")
                for err in error_lines[:3]:  # 只显示前3个错误
                    print(f"     - {err}")
            
            return {
                "status": "failed",
                "execution_time": execution_time,
                "returncode": result.returncode,
                "stdout": result.stdout[-500:],
                "stderr": result.stderr[-500:],
                "errors": error_lines[:3]
            }
            
    except subprocess.TimeoutExpired:
        print(f"{Colors.RED}⏰ 测试超时 (超过300秒){Colors.END}")
        return {
            "status": "timeout",
            "execution_time": 300
        }
    except Exception as e:
        print(f"{Colors.RED}💥 执行错误: {e}{Colors.END}")
        return {
            "status": "error",
            "error": str(e)
        }

def main():
    """主函数"""
    print_header("🚀 Phase1: 核心数据网关测试 - 28字段表结构适配")
    print(f"开始时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    # 获取项目根目录
    project_root = Path(__file__).parent.parent
    os.chdir(project_root)
    print(f"工作目录: {project_root}")
    
    all_results = {}
    
    # 定义要运行的测试
    tests_to_run = [
        {
            "name": "基础冒烟测试",
            "file": "tests/smoke/test_basic_smoke.py",
            "args": None
        },
        {
            "name": "28字段结构验证",
            "file": "tests/smoke/test_schema_validation.py",
            "args": None
        },
        {
            "name": "内存数据库性能测试",
            "file": "tests/performance/test_memory_performance.py",
            "args": None
        },
        {
            "name": "缓存策略测试",
            "file": "tests/smoke/test_cache_smoke.py",
            "args": None
        }
    ]
    
    # 检查并运行测试
    for test_info in tests_to_run:
        test_file = project_root / test_info["file"]
        if test_file.exists():
            result = run_simple_test(
                test_info["name"],
                str(test_file),
                test_info["args"]
            )
            all_results[test_info["name"]] = result
        else:
            print(f"{Colors.YELLOW}⚠️  跳过测试 {test_info['name']}: 文件不存在{Colors.END}")
            all_results[test_info["name"]] = {
                "status": "skipped",
                "reason": "文件不存在"
            }
    
    # 汇总结果
    print_header("📊 测试结果汇总")
    
    total = len(all_results)
    passed = sum(1 for r in all_results.values() if r.get("status") == "passed")
    failed = sum(1 for r in all_results.values() if r.get("status") == "failed")
    skipped = sum(1 for r in all_results.values() if r.get("status") == "skipped")
    timeout = sum(1 for r in all_results.values() if r.get("status") == "timeout")
    
    print(f"总测试数: {total}")
    if passed > 0:
        print(f"{Colors.GREEN}✅ 通过: {passed}{Colors.END}")
    if failed > 0:
        print(f"{Colors.RED}❌ 失败: {failed}{Colors.END}")
    if skipped > 0:
        print(f"{Colors.YELLOW}⚠️  跳过: {skipped}{Colors.END}")
    if timeout > 0:
        print(f"{Colors.RED}⏰ 超时: {timeout}{Colors.END}")
    
    # 详细结果
    print(f"\n{Colors.BOLD}详细结果:{Colors.END}")
    for name, result in all_results.items():
        status = result.get("status", "unknown")
        if status == "passed":
            color = Colors.GREEN
            symbol = "✅"
            time_str = f"({result.get('execution_time', 0):.2f}秒)"
        elif status == "failed":
            color = Colors.RED
            symbol = "❌"
            time_str = f"(退出码: {result.get('returncode', -1)})"
        elif status == "skipped":
            color = Colors.YELLOW
            symbol = "⚠️"
            time_str = f"- {result.get('reason', '')}"
        elif status == "timeout":
            color = Colors.RED
            symbol = "⏰"
            time_str = ""
        else:
            color = Colors.YELLOW
            symbol = "❓"
            time_str = ""
        
        print(f"  {color}{symbol} {name:20} {status.upper():10} {time_str}{Colors.END}")
    
    # 保存结果
    results_file = project_root / "test_results" / f"simplified_results_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
    results_file.parent.mkdir(exist_ok=True)
    
    with open(results_file, 'w') as f:
        f.write(f"测试结果汇总 - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\\n")
        f.write(f"总测试数: {total}\\n")
        f.write(f"通过: {passed}\\n")
        f.write(f"失败: {failed}\\n")
        f.write(f"跳过: {skipped}\\n\\n")
        
        for name, result in all_results.items():
            f.write(f"{name}: {result.get('status', 'unknown')}\\n")
            if "errors" in result:
                f.write(f"错误: {', '.join(result['errors'])}\n")
            f.write("-" * 50 + "\\n")
    
    print(f"\n详细结果已保存到: {results_file}")
    
    # 确定退出码
    if failed > 0:
        print(f"\n{Colors.RED}{'❌'*20}{Colors.END}")
        print(f"{Colors.RED}❌ 测试失败: 有 {failed} 个测试失败{Colors.END}")
        print(f"{Colors.RED}{'❌'*20}{Colors.END}")
        sys.exit(1)
    elif passed == 0 and total > 0:
        print(f"\n{Colors.YELLOW}{'⚠️'*20}{Colors.END}")
        print(f"{Colors.YELLOW}⚠️  警告: 没有测试通过{Colors.END}")
        print(f"{Colors.YELLOW}{'⚠️'*20}{Colors.END}")
        sys.exit(1)
    else:
        print(f"\n{Colors.GREEN}{'✅'*20}{Colors.END}")
        print(f"{Colors.GREEN}✅ 所有测试通过！{Colors.END}")
        print(f"{Colors.GREEN}{'✅'*20}{Colors.END}")
        sys.exit(0)

if __name__ == "__main__":
    main()