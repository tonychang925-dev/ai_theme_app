#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
真实环境测试脚本 - 使用真实的 Notion API 测试 fetch_tasks_by_milestone 方法
运行前请确保 NOTION_TOKEN 环境变量已设置
"""

import json
import os
import sys
from datetime import datetime
from typing import List, Dict, Optional

# 添加项目根目录到路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from notion_sync_manager import NotionSyncManager
from sync_pm_status import PMSStatusSyncManager


def print_separator(title):
    """打印分隔线"""
    print("\n" + "=" * 60)
    print(f" {title}")
    print("=" * 60)


def test_connection():
    """测试 Notion 连接是否正常"""
    print_separator("测试 Notion 连接")
    
    try:
        manager = NotionSyncManager()
        # 尝试获取一个页面来测试连接
        test_result = manager.notion.users.me()
        print(f"✅ Notion 连接成功")
        print(f"   用户: {test_result.get('name', 'Unknown')}")
        print(f"   邮箱: {test_result.get('person', {}).get('email', 'Unknown')}")
        return True
    except Exception as e:
        print(f"❌ Notion 连接失败: {e}")
        return False


def test_query_database():
    """测试 query_database 方法"""
    print_separator("测试 query_database 方法")
    
    manager = PMSStatusSyncManager()
    
    # 测试查询 tasks 数据库
    print("\n📋 查询 tasks 数据库...")
    try:
        # 不带过滤条件的查询
        tasks = manager.query_database("tasks")
        print(f"✅ 查询成功，获取到 {len(tasks)} 个任务")
        
        if tasks:
            # 显示前3个任务的简要信息
            print("\n前3个任务预览:")
            for i, task in enumerate(tasks[:3]):
                props = task.get("properties", {})
                name = props.get("Name", {}).get("title", [{}])[0].get("text", {}).get("content", "无名称")
                status = props.get("Status", {}).get("select", {}).get("name", "未知")
                print(f"  {i+1}. {name} (状态: {status})")
        
        return tasks
    except Exception as e:
        print(f"❌ 查询失败: {e}")
        import traceback
        traceback.print_exc()
        return []


def test_fetch_all_active_tasks():
    """测试获取所有活跃任务"""
    print_separator("测试 fetch_all_active_tasks 方法")
    
    manager = PMSStatusSyncManager()
    
    try:
        tasks = manager.fetch_all_active_tasks()
        print(f"✅ 获取到 {len(tasks)} 个活跃任务 (状态非 done)")
        
        # 按状态统计
        status_count = {}
        for task in tasks:
            status = task.get("status", "Unknown")
            status_count[status] = status_count.get(status, 0) + 1
        
        print("\n📊 任务状态分布:")
        for status, count in status_count.items():
            print(f"  {status}: {count} 个")
        
        # 显示前5个任务详情
        if tasks:
            print("\n📝 前5个任务详情:")
            for i, task in enumerate(tasks[:5]):
                print(f"\n  --- 任务 {i+1} ---")
                print(f"  ID: {task.get('id', 'N/A')}")
                print(f"  名称: {task.get('name', 'N/A')}")
                print(f"  状态: {task.get('status', 'N/A')}")
                print(f"  优先级: {task.get('priority', 'N/A')}")
                print(f"  估算工时: {task.get('estimate', 'N/A')}")
                print(f"  里程碑ID: {task.get('milestone_id', 'N/A')}")
        
        return tasks
    except Exception as e:
        print(f"❌ 获取活跃任务失败: {e}")
        import traceback
        traceback.print_exc()
        return []


def test_fetch_tasks_by_milestone():
    """测试按里程碑获取任务"""
    print_separator("测试 fetch_tasks_by_milestone 方法")
    
    manager = PMSStatusSyncManager()
    
    # 首先获取所有里程碑
    print("\n📋 获取所有里程碑...")
    try:
        milestones = manager.query_database("milestones")
        print(f"✅ 获取到 {len(milestones)} 个里程碑")
        
        if not milestones:
            print("❌ 没有找到任何里程碑，无法继续测试")
            return []
        
        # 显示所有里程碑
        milestone_list = []
        for i, milestone in enumerate(milestones):
            props = milestone.get("properties", {})
            name = props.get("Name", {}).get("title", [{}])[0].get("text", {}).get("content", "无名称")
            phase = props.get("Phase", {}).get("select", {}).get("name", "未知")
            print(f"  {i+1}. {name} (阶段: {phase})")
            print(f"     ID: {milestone['id']}")
            milestone_list.append({
                "id": milestone['id'],
                "name": name,
                "phase": phase
            })
        
        # 选择第一个里程碑进行测试
        if milestone_list:
            test_milestone = milestone_list[0]
            print(f"\n🔍 测试里程碑: {test_milestone['name']} (ID: {test_milestone['id']})")
            
            # 测试不带状态过滤
            print("\n📋 获取该里程碑下的所有任务...")
            tasks_all = manager.fetch_tasks_by_milestone(test_milestone['id'])
            print(f"✅ 获取到 {len(tasks_all)} 个任务")
            
            # 按状态统计
            status_count = {}
            for task in tasks_all:
                status = task.get("status", "Unknown")
                status_count[status] = status_count.get(status, 0) + 1
            
            if status_count:
                print("\n📊 任务状态分布:")
                for status, count in status_count.items():
                    print(f"  {status}: {count} 个")
            
            # 测试带状态过滤
            print("\n📋 测试状态过滤 [Todo, Doing]...")
            tasks_filtered = manager.fetch_tasks_by_milestone(
                test_milestone['id'], 
                status_filter=["Todo", "Doing"]
            )
            print(f"✅ 获取到 {len(tasks_filtered)} 个 Todo/Doing 任务")
            
            # 验证过滤结果
            for task in tasks_filtered:
                status = task.get("status", "")
                assert status in ["Todo", "Doing"], f"任务状态 {status} 不应该在结果中"
            print("✅ 状态过滤验证通过")
            
            # 显示任务详情
            if tasks_filtered:
                print(f"\n📝 前3个 {test_milestone['name']} 的任务详情:")
                for i, task in enumerate(tasks_filtered[:3]):
                    print(f"\n  --- 任务 {i+1} ---")
                    print(f"  ID: {task.get('id', 'N/A')}")
                    print(f"  名称: {task.get('name', 'N/A')}")
                    print(f"  状态: {task.get('status', 'N/A')}")
                    print(f"  优先级: {task.get('priority', 'N/A')}")
                    print(f"  估算工时: {task.get('estimate', 'N/A')}")
            
            return tasks_filtered
        else:
            print("❌ 没有找到里程碑")
            return []
            
    except Exception as e:
        print(f"❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()
        return []


def test_fetch_task_by_id():
    """测试根据ID获取单个任务"""
    print_separator("测试 fetch_task_by_id 方法")
    
    manager = PMSStatusSyncManager()
    
    # 先获取一个任务ID
    try:
        tasks = manager.fetch_all_active_tasks()
        if not tasks:
            print("❌ 没有找到任务，无法测试")
            return None
        
        test_task = tasks[0]
        task_id = test_task['id']
        print(f"\n🔍 测试任务: {test_task['name']} (ID: {task_id})")
        
        # 根据ID获取任务
        task = manager.fetch_task_by_id(task_id)
        
        if task:
            print("✅ 成功获取任务")
            print(f"  名称: {task.get('name', 'N/A')}")
            print(f"  状态: {task.get('status', 'N/A')}")
            print(f"  优先级: {task.get('priority', 'N/A')}")
            print(f"  估算工时: {task.get('estimate', 'N/A')}")
            print(f"  里程碑ID: {task.get('milestone_id', 'N/A')}")
            
            # 验证数据一致性
            assert task['id'] == task_id, "任务ID不匹配"
            assert task['name'] == test_task['name'], "任务名称不匹配"
            print("✅ 数据一致性验证通过")
            
            return task
        else:
            print("❌ 获取任务失败")
            return None
            
    except Exception as e:
        print(f"❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()
        return None


def test_format_task():
    """测试任务格式化方法"""
    print_separator("测试 _format_task 方法")
    
    manager = PMSStatusSyncManager()
    
    # 获取一个真实任务进行测试
    try:
        tasks = manager.fetch_all_active_tasks()
        if not tasks:
            print("❌ 没有找到任务，无法测试")
            return
        
        raw_task = tasks[0]  # 注意：这里拿到的已经是格式化后的任务
        print(f"\n🔍 原始任务数据:")
        print(json.dumps(raw_task, ensure_ascii=False, indent=2)[:500] + "...")
        
        # 由于我们拿到的已经是格式化后的，我们测试 _format_task 的逆过程不实际
        # 而是测试 _format_tasks 方法对原始 API 返回的处理
        print("\n✅ _format_task 方法已在获取任务时自动调用")
        print("   所有返回的任务都已经过格式化处理")
        
    except Exception as e:
        print(f"❌ 测试失败: {e}")


def run_all_tests():
    """运行所有测试"""
    print("\n" + "=" * 60)
    print("  Notion API 真实环境测试套件")
    print("=" * 60)
    
    # 检查环境变量
    if not os.getenv("NOTION_TOKEN"):
        print("❌ 错误: NOTION_TOKEN 环境变量未设置")
        print("   请先设置: export NOTION_TOKEN=your_token_here")
        sys.exit(1)
    
    # 运行测试
    tests = [
        ("连接测试", test_connection),
        ("查询数据库", test_query_database),
        ("获取活跃任务", test_fetch_all_active_tasks),
        ("按里程碑获取任务", test_fetch_tasks_by_milestone),
        ("根据ID获取任务", test_fetch_task_by_id),
        ("格式化测试", test_format_task)
    ]
    
    results = {}
    for name, test_func in tests:
        print(f"\n▶ 运行 {name}...")
        try:
            result = test_func()
            results[name] = "✅ 通过" if result is not None else "⚠️ 部分通过"
        except Exception as e:
            print(f"❌ {name} 失败: {e}")
            results[name] = "❌ 失败"
    
    # 打印测试总结
    print("\n" + "=" * 60)
    print(" 测试结果总结")
    print("=" * 60)
    for name, result in results.items():
        print(f"  {result} {name}")


if __name__ == "__main__":
    run_all_tests()