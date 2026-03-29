#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
sync_pm_status.py - Notion项目管理状态同步脚本
功能：
1. 获取任务列表（从Notion里程碑关联任务）
2. 更新任务状态
3. 更新测试证据
4. 计算并更新里程碑进度
5. 创建和更新阶段报告
6. 记录验收决策
7. 批量离线同步

版本: 2.0.0
最后更新: 2026-02-13
"""

import json
import sys
import os
import argparse
import subprocess
from datetime import datetime
from typing import List, Dict, Any, Optional
from pathlib import Path

# 添加项目根目录到路径
sys.path.insert(0, str(Path(__file__).parent))

from notion_sync_manager import NotionSyncManager


class PMSStatusSyncManager(NotionSyncManager):
    """扩展的状态同步管理器"""
    
    def __init__(self):
        """初始化同步管理器"""
        super().__init__()
        self.offline_mode = False
        self.flow_check_mode = False
        self.last_fetch_error: Optional[str] = None
        self.offline_payload = {
            "task_updates": [],
            "milestone_updates": [],
            "reports": [],
            "decisions": []
        }
        
    # ============================
    # 1. 任务获取功能
    # ============================

    def _query_data_source_pages(self, data_source_id: str) -> List[Dict]:
        """通过 data_sources.query 全量拉取数据源页面（分页）"""
        pages: List[Dict] = []
        start_cursor: Optional[str] = None
        while True:
            kwargs: Dict[str, Any] = {
                "data_source_id": data_source_id,
                "page_size": 100,
            }
            if start_cursor:
                kwargs["start_cursor"] = start_cursor
            response = self.notion.data_sources.query(**kwargs)
            pages.extend(response.get("results", []))
            if not response.get("has_more"):
                break
            start_cursor = response.get("next_cursor")
            if not start_cursor:
                break
        return pages

    def query_database(self, db_key: str, filter_params: Optional[Dict] = None) -> List[Dict]:
        """查询数据源中的页面"""
        if db_key not in self.DS:
            raise ValueError(f"Unknown database key: {db_key}. Valid keys: {list(self.DS.keys())}")

        # 离线模式：直接返回空列表，不调用 API
        if self.offline_mode:
            print(f"📴 离线模式：跳过数据库查询 ({db_key})")
            return []

        try:
            data_source_id = self.DS[db_key]
            filtered_pages = self._query_data_source_pages(data_source_id)
            
            # 如果有过滤条件，应用过滤
            if filter_params and "filter" in filter_params:
                filter_cond = filter_params["filter"]
                
                # 处理里程碑过滤
                if filter_cond.get("property") == "Milestone":
                    milestone_id = filter_cond.get("relation", {}).get("contains")
                    if milestone_id:
                        milestone_filtered = []
                        for page in filtered_pages:
                            props = page.get("properties", {})
                            milestone_rel = props.get("Milestone", {}).get("relation", [])
                            if any(rel.get("id") == milestone_id for rel in milestone_rel):
                                milestone_filtered.append(page)
                        filtered_pages = milestone_filtered
                
                # 处理状态过滤
                elif filter_cond.get("property") == "Status":
                    status_cond = filter_cond.get("select", {})
                    if "does_not_equal" in status_cond:
                        exclude_status = status_cond["does_not_equal"]
                        status_filtered = []
                        for page in filtered_pages:
                            props = page.get("properties", {})
                            status = props.get("Status", {}).get("select", {}).get("name")
                            if status != exclude_status:
                                status_filtered.append(page)
                        filtered_pages = status_filtered
            
            return filtered_pages

        except Exception as e:
            print(f"❌ 查询数据源失败 ({db_key}): {e}")
            if not self.offline_mode:
                import traceback
                traceback.print_exc()
            return []
    
    def fetch_tasks_by_milestone(self, milestone_id: str, status_filter: Optional[List[str]] = None) -> List[Dict]:
        """获取指定里程碑下的所有任务"""
        self.last_fetch_error = None
        # 离线模式直接返回空列表或从本地文件读取
        if self.offline_mode:
            print("📴 离线模式：从本地缓存读取任务")
            cache_file = f"tmp/milestone_{milestone_id}_tasks.json"
            if os.path.exists(cache_file):
                try:
                    with open(cache_file, 'r', encoding='utf-8') as f:
                        cached_data = json.load(f)
                        tasks = cached_data.get("tasks", [])
                        print(f"📴 从缓存读取到 {len(tasks)} 个任务")
                        return tasks
                except Exception as e:
                    print(f"📴 读取缓存失败: {e}")
            return []
        
        try:
            # 正常模式：调用 Notion API（data source query + 分页）
            task_pages = self._query_data_source_pages(self.DS["tasks"])
            
            # 过滤出关联指定里程碑的任务
            milestone_tasks = []
            for task in task_pages:
                props = task.get("properties", {})
                milestone_rel = props.get("Milestone", {}).get("relation", [])
                if any(rel.get("id") == milestone_id for rel in milestone_rel):
                    milestone_tasks.append(task)
            
            # 应用状态过滤（如果有）
            if status_filter:
                filtered_tasks = []
                for task in milestone_tasks:
                    props = task.get("properties", {})
                    status = props.get("Status", {}).get("select", {}).get("name")
                    if status in status_filter:
                        filtered_tasks.append(task)
                milestone_tasks = filtered_tasks
            
            formatted_tasks = self._format_tasks(milestone_tasks)
            
            # 缓存到本地文件
            cache_file = f"tmp/milestone_{milestone_id}_tasks.json"
            os.makedirs("tmp", exist_ok=True)
            with open(cache_file, 'w', encoding='utf-8') as f:
                json.dump({"tasks": formatted_tasks}, f, ensure_ascii=False, indent=2)
            
            return formatted_tasks
            
        except Exception as e:
            print(f"❌ 查询任务时发生错误: {e}")
            self.last_fetch_error = str(e)
            return []

    def fetch_all_active_tasks(self) -> List[Dict]:
        """获取所有活跃任务（状态非 done）"""
        self.last_fetch_error = None
        # 离线模式直接返回空列表或从本地文件读取
        if self.offline_mode:
            print("📴 离线模式：从本地缓存读取任务")
            cache_file = "tmp/task_cache.json"
            if os.path.exists(cache_file):
                try:
                    with open(cache_file, 'r', encoding='utf-8') as f:
                        cached_data = json.load(f)
                        tasks = cached_data.get("tasks", [])
                        print(f"📴 从缓存读取到 {len(tasks)} 个任务")
                        return tasks
                except Exception as e:
                    print(f"📴 读取缓存失败: {e}")
            return []
        
        # 正常模式：调用 Notion API（data source query + 分页）
        try:
            task_pages = self._query_data_source_pages(self.DS["tasks"])
            
            active_tasks = []
            for task in task_pages:
                props = task.get("properties", {})
                status = props.get("Status", {}).get("select", {}).get("name")
                if status != "done":
                    active_tasks.append(task)
            
            formatted_tasks = self._format_tasks(active_tasks)
            self._cache_tasks(formatted_tasks)
            return formatted_tasks
            
        except Exception as e:
            print(f"❌ 获取活跃任务失败: {e}")
            self.last_fetch_error = str(e)
            return []

    def fetch_all_tasks(self) -> List[Dict]:
        """获取 tasks 数据源中的所有任务（包含 done）"""
        self.last_fetch_error = None
        if self.offline_mode:
            print("📴 离线模式：从本地缓存读取任务")
            cache_file = "tmp/task_cache.json"
            if os.path.exists(cache_file):
                try:
                    with open(cache_file, 'r', encoding='utf-8') as f:
                        cached_data = json.load(f)
                        tasks = cached_data.get("tasks", [])
                        print(f"📴 从缓存读取到 {len(tasks)} 个任务")
                        return tasks
                except Exception as e:
                    print(f"📴 读取缓存失败: {e}")
            return []

        try:
            task_pages = self._query_data_source_pages(self.DS["tasks"])
            formatted_tasks = self._format_tasks(task_pages)
            self._cache_tasks(formatted_tasks)
            return formatted_tasks

        except Exception as e:
            print(f"❌ 获取任务失败: {e}")
            self.last_fetch_error = str(e)
            return []
    
    def _cache_tasks(self, tasks: List[Dict]) -> None:
        """缓存任务到本地文件"""
        if self.offline_mode:
            return
        
        try:
            os.makedirs("tmp", exist_ok=True)
            cache_file = "tmp/task_cache.json"
            with open(cache_file, 'w', encoding='utf-8') as f:
                json.dump({"tasks": tasks, "timestamp": datetime.now().isoformat()}, 
                        f, ensure_ascii=False, indent=2)
            print(f"📦 任务已缓存到: {cache_file}")
        except Exception as e:
            print(f"⚠️ 缓存任务失败: {e}")
    
    def fetch_task_by_id(self, task_id: str) -> Optional[Dict]:
        """根据ID获取单个任务"""
        try:
            page = self.notion.pages.retrieve(page_id=task_id)
            return self._format_task(page)
        except Exception as e:
            print(f"❌ 获取任务失败: {e}")
            return None
    
    def _format_tasks(self, raw_tasks: List[Dict]) -> List[Dict]:
        """格式化原始任务数据"""
        formatted = []
        for task in raw_tasks:
            formatted.append(self._format_task(task))
        return formatted
    
    def _format_task(self, task: Dict) -> Dict:
        """格式化单个任务，增加里程碑名称和阶段信息"""
        props = task.get("properties", {})
        
        # 原有的字段获取逻辑...
        name = ""
        name_field = props.get("Name", {}).get("title", [])
        if name_field:
            name = name_field[0].get("text", {}).get("content", "")
        
        status = props.get("Status", {}).get("select", {}).get("name", "Unknown")
        priority = props.get("Priority", {}).get("select", {}).get("name", "P2")
        estimate = props.get("Estimate", {}).get("number")
        
        # 获取DoD清单
        dod = props.get("DoD Checklist", {}).get("multi_select", [])
        dod_list = [item.get("name") for item in dod]
        
        # 获取测试证据
        test_evidence = props.get("Test Evidence", {}).get("rich_text", [])
        evidence_text = ""
        if test_evidence:
            evidence_text = test_evidence[0].get("text", {}).get("content", "")
        
        # 获取依赖
        dependencies = props.get("Dependencies", {}).get("relation", [])
        dep_ids = [dep.get("id") for dep in dependencies]
        
        # 获取里程碑ID
        milestone = props.get("Milestone", {}).get("relation", [])
        milestone_id = milestone[0].get("id") if milestone else None
        
        # 获取里程碑名称和阶段
        milestone_name = None
        phase = None
        if milestone_id:
            try:
                milestone_page = self.notion.pages.retrieve(page_id=milestone_id)
                milestone_props = milestone_page.get("properties", {})
                
                # 获取里程碑名称
                name_field = milestone_props.get("Name", {}).get("title", [])
                if name_field:
                    milestone_name = name_field[0].get("text", {}).get("content", "")
                
                # 获取阶段
                phase_select = milestone_props.get("Phase", {}).get("select", {})
                phase = phase_select.get("name") if phase_select else None
                
            except Exception as e:
                print(f"⚠️ 获取里程碑信息失败: {e}")
        
        return {
            "id": task["id"],
            "name": name,
            "status": status,
            "priority": priority,
            "estimate": estimate,
            "dod_checklist": dod_list,
            "test_evidence": evidence_text,
            "dependencies": dep_ids,
            "milestone_id": milestone_id,
            "milestone_name": milestone_name,  # 新增
            "phase": phase,                    # 新增
            "url": task.get("url", ""),
            "last_edited": task.get("last_edited_time", "")
        }
    
    # ============================
    # 2. 任务状态更新
    # ============================

    def _collect_changed_files(self) -> List[str]:
        """收集工作区变更文件（暂存/未暂存/未跟踪）"""
        try:
            inside_repo = subprocess.run(
                ["git", "rev-parse", "--is-inside-work-tree"],
                capture_output=True,
                text=True,
                check=True
            )
            if inside_repo.stdout.strip() != "true":
                return []
        except Exception:
            return []

        changed_files: List[str] = []
        commands = [
            ["git", "diff", "--name-only"],
            ["git", "diff", "--cached", "--name-only"],
            ["git", "ls-files", "--others", "--exclude-standard"],
        ]
        for cmd in commands:
            try:
                result = subprocess.run(cmd, capture_output=True, text=True, check=True)
                lines = [line.strip() for line in result.stdout.splitlines() if line.strip()]
                changed_files.extend(lines)
            except Exception:
                continue
        return changed_files

    def _is_test_path(self, path: str) -> bool:
        normalized = path.replace("\\", "/")
        filename = normalized.split("/")[-1]
        if normalized.startswith("tests/") or "/tests/" in normalized:
            return True
        if filename.startswith("test_") and filename.endswith(".py"):
            return True
        if filename.endswith("_test.py"):
            return True
        return False

    def _has_test_script_changes(self) -> bool:
        """检测工作区是否存在测试脚本变更（暂存/未暂存/未跟踪）"""
        changed_files = self._collect_changed_files()
        return any(self._is_test_path(path) for path in changed_files)
    
    def update_task_status(
        self,
        task_id: str,
        status: Optional[str] = None,
        test_evidence: Optional[str] = None,
        test_files: Optional[List[str]] = None
    ) -> Dict:
        """更新任务状态和测试证据
        
        Args:
            task_id: 任务页面ID
            status: 新状态 (Todo/Doing/Blocked/In review/done)，可选
            test_evidence: 测试证据文本，可选
            test_files: 当前任务对应测试文件列表，可选
        
        Returns:
            更新后的页面对象
        """
        # 至少需要更新一项内容
        if status is None and test_evidence is None:
            raise ValueError("至少需要指定 status 或 test_evidence 中的一个")
        
        properties = {}
        resolved_task: Optional[Dict[str, Any]] = None
        
        # 添加状态更新（如果有）
        if status is not None:
            valid_statuses = ["Todo", "Doing", "Blocked", "In review", "done"]
            if status not in valid_statuses:
                raise ValueError(f"无效的状态值: {status}，有效值: {valid_statuses}")

            # flow-check 模式默认不改真实任务状态
            if self.flow_check_mode:
                print(f"🧪 flow-check: 跳过真实状态更新 ({task_id} -> {status})")
                status = None
            else:
                # P0/P1 任务在进入 In review/done 前必须检测到测试脚本变更
                if status in ["In review", "done"]:
                    resolved_task = self.fetch_task_by_id(task_id)
                    priority = (resolved_task or {}).get("priority")
                    if priority in ["P0", "P1"] and not self._has_test_script_changes():
                        raise ValueError(
                            "门禁失败：P0/P1 任务进入 In review/done 前未检测到测试脚本变更。"
                            "请先新增/更新 tests 下自动化测试，或在 flow-check 模式下执行演练。"
                        )
                    if priority in ["P0", "P1"]:
                        if not test_files:
                            raise ValueError(
                                "门禁失败：P0/P1 任务进入 In review/done 前必须显式提供 --test-files。"
                            )
                        normalized_changed = {p.replace("\\", "/") for p in self._collect_changed_files()}
                        normalized_expected = [p.strip().replace("\\", "/") for p in test_files if p.strip()]
                        if not normalized_expected:
                            raise ValueError(
                                "门禁失败：--test-files 为空。请提供至少一个测试文件路径。"
                            )
                        invalid_non_test = [p for p in normalized_expected if not self._is_test_path(p)]
                        if invalid_non_test:
                            raise ValueError(
                                f"门禁失败：以下 --test-files 不是测试脚本路径: {invalid_non_test}"
                            )
                        missing = [p for p in normalized_expected if p not in normalized_changed]
                        if missing:
                            raise ValueError(
                                f"门禁失败：以下 --test-files 未出现在当前 diff 中: {missing}"
                            )
                    if priority in ["P0", "P1"]:
                        existing_evidence = str((resolved_task or {}).get("test_evidence", "")).strip()
                        incoming_evidence = str(test_evidence or "").strip()
                        if not existing_evidence and not incoming_evidence:
                            raise ValueError(
                                "门禁失败：P0/P1 任务进入 In review/done 前必须具备 Test Evidence。"
                            )
            
            if status is not None:
                properties["Status"] = {
                    "select": {"name": status}
                }
            
            # 注意：移除 Completed Date 字段的自动写入
            # 如果确实需要记录完成时间，可以在 Notion 中添加该字段后再启用
        
        # 添加测试证据更新（如果有）
        if test_evidence:
            properties["Test Evidence"] = {
                "rich_text": [{"text": {"content": test_evidence}}]
            }
        
        # 离线模式：只记录到 payload，不调用 API
        if self.offline_mode:
            print(f"📴 离线模式：记录任务更新 (task_id={task_id})")
            update_record = {"task_id": task_id, "timestamp": datetime.now().isoformat()}
            if status:
                update_record["status"] = status
            if test_evidence:
                update_record["test_evidence"] = test_evidence
            if test_files:
                update_record["test_files"] = test_files
            self.offline_payload["task_updates"].append(update_record)
            return {"offline": True, "task_id": task_id, "updated": True}
        
        # 正常模式：调用 Notion API
        # flow-check 且无实际属性更新时，直接返回 dry-run
        if self.flow_check_mode and not properties:
            return {"flow_check": True, "task_id": task_id, "updated": False}

        try:
            result = self.notion.pages.update(
                page_id=task_id,
                properties=properties
            )
            
            # 如果更新了状态，自动更新所属里程碑进度
            if status is not None:
                task = resolved_task or self.fetch_task_by_id(task_id)
                if task and task.get("milestone_id"):
                    self.update_milestone_progress(task["milestone_id"])
            
            return result
        except Exception as e:
            if self.offline_mode:
                self.offline_payload["task_updates"].append({
                    "task_id": task_id,
                    "status": status,
                    "test_evidence": test_evidence,
                    "error": str(e),
                    "timestamp": datetime.now().isoformat()
                })
                return {"offline": True, "task_id": task_id, "error": str(e)}
            else:
                raise e
    
    def batch_update_tasks(self, task_updates: List[Dict]) -> List[Dict]:
        """批量更新任务
        
        Args:
            task_updates: [{"task_id": "xxx", "status": "Doing", "test_evidence": "..."}, ...]
        """
        results = []
        for update in task_updates:
            try:
                result = self.update_task_status(
                    update["task_id"],
                    update["status"],
                    update.get("test_evidence"),
                    update.get("test_files")
                )
                results.append({
                    "task_id": update["task_id"],
                    "success": True,
                    "result": result
                })
                print(f"  ✅ 更新任务: {update['task_id']} -> {update['status']}")
            except Exception as e:
                results.append({
                    "task_id": update["task_id"],
                    "success": False,
                    "error": str(e)
                })
                print(f"  ❌ 更新失败: {update['task_id']} - {e}")
        
        return results
    
    # ============================
    # 3. 里程碑进度计算与更新
    # ============================
    
    def get_milestone_tasks(self, milestone_id: str) -> List[Dict]:
        """获取里程碑下的所有任务"""
        return self.fetch_tasks_by_milestone(milestone_id)
    
    def calculate_milestone_progress(self, milestone_id: str, phase_filter: Optional[str] = None) -> float:
        """计算里程碑完成百分比
        
        计算逻辑: 
        - 基础版: (已完成任务数 / 总任务数) * 100
        - 加权版: (各任务进度之和 / (任务数 * 100)) * 100 (如果有任务级进度)
        
        Args:
            milestone_id: 里程碑ID
            
        Returns:
            完成百分比 (0-100)
        """
        tasks = self.get_milestone_tasks(milestone_id)
        if phase_filter:
            phase_key = phase_filter.strip().lower()
            tasks = [t for t in tasks if str(t.get("phase", "")).strip().lower() == phase_key]
        
        if not tasks:
            return 0.0
        
        total_tasks = len(tasks)
        
        # 检查是否有任务级进度字段
        has_task_progress = any(task.get("progress") is not None for task in tasks)
        
        if has_task_progress:
            # 加权计算
            total_progress = sum(task.get("progress", 0) for task in tasks)
            progress = total_progress / total_tasks
        else:
            # 基于状态计算
            status_weights = {
                "done": 100,
                "In review": 80,
                "Doing": 30,
                "Blocked": 10,
                "Todo": 0
            }
            
            total_progress = 0
            for task in tasks:
                status = task.get("status", "Todo")
                weight = status_weights.get(status, 0)
                total_progress += weight
            
            progress = total_progress / total_tasks / 100
        
        return round(progress, 2)
    
    def update_milestone_progress(
        self,
        milestone_id: str,
        progress: Optional[float] = None,
        phase_filter: Optional[str] = None
    ) -> Dict:
        """更新里程碑进度"""
        # 离线模式：只记录到 payload，不调用 API
        if self.offline_mode:
            print(f"📴 离线模式：记录里程碑进度更新 (milestone_id={milestone_id}, progress={progress})")
            self.offline_payload["milestone_updates"].append({
                "milestone_id": milestone_id,
                "progress": progress,
                "phase_filter": phase_filter,
                "timestamp": datetime.now().isoformat()
            })
            return {"offline": True, "milestone_id": milestone_id}
        
        # 正常模式：调用 Notion API
        if progress is None:
            progress = self.calculate_milestone_progress(milestone_id, phase_filter=phase_filter)
        
        properties = {
            "Progress": {"number": progress}
        }
        
        try:
            result = self.notion.pages.update(
                page_id=milestone_id,
                properties=properties
            )
            return result
        except Exception as e:
            raise e
    
    def _cache_tasks(self, tasks: List[Dict]) -> None:
        """缓存任务到本地文件"""
        try:
            os.makedirs("tmp", exist_ok=True)
            cache_file = "tmp/task_cache.json"
            with open(cache_file, 'w', encoding='utf-8') as f:
                json.dump({"tasks": tasks, "timestamp": datetime.now().isoformat()}, 
                        f, ensure_ascii=False, indent=2)
            print(f"📦 任务已缓存到: {cache_file}")
        except Exception as e:
            print(f"⚠️ 缓存任务失败: {e}")
    
    def update_all_milestones_progress(self) -> List[Dict]:
        """更新所有里程碑的进度"""
        results = []
        
        # 离线模式：只记录操作意图，不查询 API
        if self.offline_mode:
            print("📴 离线模式：记录更新所有里程碑进度的意图")
            self.offline_payload.setdefault("bulk_operations", []).append({
                "operation": "update_all_milestones_progress",
                "timestamp": datetime.now().isoformat()
            })
            return [{"offline": True, "message": "记录批量更新操作"}]
        
        # 正常模式：查询里程碑并更新
        try:
            milestones = self.query_database("milestones")
        except Exception as e:
            print(f"❌ 查询里程碑失败: {e}")
            return []
        
        for milestone in milestones:
            milestone_id = milestone["id"]
            try:
                progress = self.calculate_milestone_progress(milestone_id)
                result = self.update_milestone_progress(milestone_id, progress)
                
                # 获取里程碑名称
                props = milestone.get("properties", {})
                title_list = props.get("Name", {}).get("title", [])
                if title_list and len(title_list) > 0:
                    name = title_list[0].get("text", {}).get("content", "Unknown")
                else:
                    name = "Unknown"
                
                results.append({
                    "milestone_id": milestone_id,
                    "name": name,
                    "progress": progress,
                    "success": True
                })
                print(f"  ✅ 更新里程碑: {name} -> {progress}%")
            except Exception as e:
                results.append({
                    "milestone_id": milestone_id,
                    "success": False,
                    "error": str(e)
                })
                print(f"  ❌ 更新失败: {milestone_id} - {e}")
        
        return results
    
    # ============================
    # 4. 阶段报告管理
    # ============================
    
    def create_phase_report(self, milestone_id: str, report_data: Dict) -> Dict:
        """创建阶段报告"""
        # 离线模式：只记录到 payload，不调用 API
        if self.offline_mode:
            print(f"📴 离线模式：记录创建报告 (milestone_id={milestone_id})")
            self.offline_payload.setdefault("reports", []).append({
                "milestone_id": milestone_id,
                "report_data": report_data,
                "timestamp": datetime.now().isoformat()
            })
            return {"offline": True, "milestone_id": milestone_id}
        
        # 正常模式：调用 Notion API
        properties = {
            "Name": {
                "title": [{"text": {"content": report_data.get("name", "Phase Report")}}]
            },
            "Milestone": {
                "relation": [{"id": milestone_id}]
            }
        }
        
        # 映射字段名
        field_mapping = {
            "scope": "Scope",
            "deliverables": "Deliverables",
            "test_results": "Test Results",
            "risks": "Risks & Follow-ups",
            "commands_run": "Commands Run",
            "diff_summary": "Diff Summary",
            "links": "Links",
            "status": "Status"
        }
        
        for key, notion_field in field_mapping.items():
            if key in report_data and report_data[key]:
                if key == "links":
                    properties[notion_field] = {"url": report_data[key]}
                elif key == "status":
                    properties[notion_field] = {"select": {"name": report_data[key]}}
                else:
                    properties[notion_field] = {
                        "rich_text": [{"text": {"content": str(report_data[key])}}]
                    }
        
        try:
            result = self.notion.pages.create(
                parent={"data_source_id": self.DS["reports"]},
                properties=properties
            )
            return result
        except Exception as e:
            if self.offline_mode:
                self.offline_payload.setdefault("reports", []).append({
                    "milestone_id": milestone_id,
                    "report_data": report_data,
                    "error": str(e),
                    "timestamp": datetime.now().isoformat()
                })
                return {"offline": True, "milestone_id": milestone_id}
            else:
                raise e
    
    def update_report_status(self, report_id: str, status: str) -> Dict:
        """更新报告状态"""
        valid_statuses = ["Draft", "Submitted", "Reviewed", "Approved", "Rework"]
        if status not in valid_statuses:
            raise ValueError(f"无效的状态值: {status}")
        
        # 离线模式：只记录到 payload
        if self.offline_mode:
            print(f"📴 离线模式：记录更新报告状态 (report_id={report_id}, status={status})")
            self.offline_payload.setdefault("report_updates", []).append({
                "report_id": report_id,
                "status": status,
                "timestamp": datetime.now().isoformat()
            })
            return {"offline": True, "report_id": report_id, "status": status}
        
        # 正常模式：调用 Notion API
        try:
            result = self.notion.pages.update(
                page_id=report_id,
                properties={
                    "Status": {"select": {"name": status}}
                }
            )
            return result
        except Exception as e:
            if self.offline_mode:
                self.offline_payload.setdefault("report_updates", []).append({
                    "report_id": report_id,
                    "status": status,
                    "error": str(e),
                    "timestamp": datetime.now().isoformat()
                })
                return {"offline": True, "report_id": report_id, "status": status}
            else:
                raise e
    
    def generate_report_from_file(self, milestone_id: str, report_file: str) -> Dict:
        """从Markdown文件生成报告"""
        if not os.path.exists(report_file):
            raise FileNotFoundError(f"报告文件不存在: {report_file}")
        
        with open(report_file, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # 解析Markdown内容
        report_data = {
            "name": os.path.basename(report_file),
            "scope": self._extract_section(content, "目标与范围"),
            "deliverables": self._extract_section(content, "变更文件清单"),
            "test_results": self._extract_section(content, "验证命令与结果"),
            "risks": self._extract_section(content, "风险与限制"),
            "commands_run": "",
            "diff_summary": "",
            "links": "",
            "status": "Draft"
        }
        
        # 离线模式：只记录到 payload
        if self.offline_mode:
            print(f"📴 离线模式：记录从文件生成报告 (milestone_id={milestone_id}, file={report_file})")
            self.offline_payload.setdefault("reports", []).append({
                "milestone_id": milestone_id,
                "report_data": report_data,
                "source_file": report_file,
                "timestamp": datetime.now().isoformat()
            })
            return {"offline": True, "milestone_id": milestone_id}
        
        # 正常模式：调用 create_phase_report
        return self.create_phase_report(milestone_id, report_data)
    
    def _extract_section(self, content: str, section_name: str) -> str:
        """从Markdown中提取章节内容（简化版）"""
        import re
        pattern = rf"##\s+\d+\.\s+{section_name}\s*(.*?)(?=##|\Z)"
        match = re.search(pattern, content, re.DOTALL)
        if match:
            return match.group(1).strip()
        return ""
    
    def link_report_to_review(self, report_id: str, review_id: str) -> Dict:
        """关联报告到评审"""
        if not report_id or not review_id:
            raise ValueError("report_id 和 review_id 都不能为空")
        
        # 离线模式：只记录到 payload，不调用 API
        if self.offline_mode:
            print(f"📴 离线模式：记录报告关联 (report_id={report_id}, review_id={review_id})")
            self.offline_payload.setdefault("report_links", []).append({
                "report_id": report_id,
                "review_id": review_id,
                "timestamp": datetime.now().isoformat()
            })
            return {"offline": True, "report_id": report_id, "review_id": review_id}
        
        # 正常模式：调用 Notion API
        try:
            result = self.notion.pages.update(
                page_id=review_id,
                properties={
                    "Report": {
                        "relation": [{"id": report_id}]
                    }
                }
            )
            return result
        except Exception as e:
            if self.offline_mode:
                self.offline_payload.setdefault("report_links", []).append({
                    "report_id": report_id,
                    "review_id": review_id,
                    "error": str(e),
                    "timestamp": datetime.now().isoformat()
                })
                return {"offline": True, "report_id": report_id, "review_id": review_id}
            else:
                raise e
    
    # ============================
    # 5. 决策记录
    # ============================
    
    def record_decision(self, milestone_id: str, decision: str, notes: str = "") -> Dict:
        """记录验收决策
        
        Args:
            milestone_id: 里程碑ID
            decision: 决策 (ACCEPT/REWORK/REQUEST_CHANGES/APPROVED_WITH_NOTES)
            notes: 备注
        """
        # 离线模式：只记录到 payload，不调用 API
        if self.offline_mode:
            print(f"📴 离线模式：记录决策 (milestone_id={milestone_id}, decision={decision})")
            self.offline_payload.setdefault("decisions", []).append({
                "milestone_id": milestone_id,
                "decision": decision,
                "notes": notes,
                "timestamp": datetime.now().isoformat()
            })
            return {"offline": True, "milestone_id": milestone_id, "decision": decision}
        
        # 正常模式：调用 Notion API
        try:
            # 获取里程碑当前状态
            milestone = self.notion.pages.retrieve(page_id=milestone_id)
            current_summary = milestone.get("properties", {}).get("Summary", {}).get("rich_text", [])
            
            decision_text = f"\n\n**验收决策** ({datetime.now().strftime('%Y-%m-%d %H:%M')}): {decision}"
            if notes:
                decision_text += f"\n**备注**: {notes}"
            
            new_summary = current_summary.copy() if current_summary else []
            if new_summary:
                new_summary[0]["text"]["content"] += decision_text
            else:
                new_summary = [{"text": {"content": decision_text}}]
            
            result = self.notion.pages.update(
                page_id=milestone_id,
                properties={
                    "Summary": {
                        "rich_text": new_summary
                    }
                }
            )
            return result
        except Exception as e:
            if self.offline_mode:
                self.offline_payload.setdefault("decisions", []).append({
                    "milestone_id": milestone_id,
                    "decision": decision,
                    "notes": notes,
                    "error": str(e),
                    "timestamp": datetime.now().isoformat()
                })
                return {"offline": True, "milestone_id": milestone_id, "decision": decision}
            else:
                raise e

    def accept_closeout_atomic(
        self,
        milestone_id: str,
        decision: str,
        notes: str,
        post_fetch_output: str,
    ) -> Dict:
        """原子执行 ACCEPT 收尾在线步骤（A/C）"""
        summary: Dict[str, Any] = {
            "milestone_id": milestone_id,
            "decision": decision,
            "record_decision_rc": 1,
            "record_decision_error": None,
            "fetch_rc": 1,
            "fetch_error": None,
            "post_fetch_output": post_fetch_output,
        }

        try:
            self.record_decision(milestone_id, decision, notes)
            summary["record_decision_rc"] = 0
        except Exception as e:
            summary["record_decision_error"] = str(e)

        try:
            tasks = self.fetch_tasks_by_milestone(milestone_id)
            out_path = Path(post_fetch_output)
            out_path.parent.mkdir(parents=True, exist_ok=True)
            out_path.write_text(json.dumps({"tasks": tasks}, ensure_ascii=False, indent=2), encoding="utf-8")
            summary["fetch_rc"] = 0
        except Exception as e:
            summary["fetch_error"] = str(e)

        return summary
    
    # ============================
    # 6. 离线同步支持
    # ============================
    
    def enable_offline_mode(self):
        """启用离线模式"""
        self.offline_mode = True
        print("📴 已启用离线模式，所有变更将记录到本地")

    def enable_flow_check_mode(self):
        """启用 flow-check 模式（默认不改真实任务状态）"""
        self.flow_check_mode = True
        print("🧪 已启用 flow-check 模式：任务状态更新将以 dry-run 方式执行")
    
    def save_offline_payload(self, filepath: str = "tmp/offline_payload.json"):
        """保存离线payload到文件"""
        os.makedirs(os.path.dirname(filepath), exist_ok=True)
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(self.offline_payload, f, ensure_ascii=False, indent=2)
        print(f"💾 离线数据已保存到: {filepath}")
    
    def batch_sync_offline(self, filepath: str) -> Dict:
        """批量同步离线数据"""
        with open(filepath, 'r', encoding='utf-8') as f:
            payload = json.load(f)
        
        results = {
            "task_updates": [],
            "milestone_updates": [],
            "reports": [],
            "report_updates": [],
            "report_links": [],
            "decisions": [],
            "errors": []
        }
        
        # 临时禁用离线模式
        original_offline_mode = self.offline_mode
        self.offline_mode = False
        
        try:
            # 同步任务更新
            for update in payload.get("task_updates", []):
                try:
                    result = self.update_task_status(
                        update["task_id"],
                        update["status"],
                        update.get("test_evidence"),
                        update.get("test_files")
                    )
                    results["task_updates"].append({"success": True, "data": update})
                except Exception as e:
                    results["task_updates"].append({"success": False, "data": update, "error": str(e)})
                    results["errors"].append({"type": "task_update", "error": str(e), "data": update})
            
            # 同步里程碑更新
            for update in payload.get("milestone_updates", []):
                try:
                    result = self.update_milestone_progress(
                        update["milestone_id"],
                        update.get("progress")
                    )
                    results["milestone_updates"].append({"success": True, "data": update})
                except Exception as e:
                    results["milestone_updates"].append({"success": False, "data": update, "error": str(e)})
                    results["errors"].append({"type": "milestone_update", "error": str(e), "data": update})
            
            # 同步报告创建
            for report in payload.get("reports", []):
                try:
                    result = self.create_phase_report(
                        report["milestone_id"],
                        report["report_data"]
                    )
                    results["reports"].append({"success": True, "data": report})
                except Exception as e:
                    results["reports"].append({"success": False, "data": report, "error": str(e)})
                    results["errors"].append({"type": "report", "error": str(e), "data": report})
            
            # 同步报告状态更新
            for update in payload.get("report_updates", []):
                try:
                    result = self.update_report_status(
                        update["report_id"],
                        update["status"]
                    )
                    results["report_updates"].append({"success": True, "data": update})
                except Exception as e:
                    results["report_updates"].append({"success": False, "data": update, "error": str(e)})
                    results["errors"].append({"type": "report_update", "error": str(e), "data": update})
            
            # 同步报告关联
            for link in payload.get("report_links", []):
                try:
                    result = self.link_report_to_review(
                        link["report_id"],
                        link["review_id"]
                    )
                    results["report_links"].append({"success": True, "data": link})
                except Exception as e:
                    results["report_links"].append({"success": False, "data": link, "error": str(e)})
                    results["errors"].append({"type": "report_link", "error": str(e), "data": link})
            
            # 同步决策记录
            for decision in payload.get("decisions", []):
                try:
                    result = self.record_decision(
                        decision["milestone_id"],
                        decision["decision"],
                        decision.get("notes", "")
                    )
                    results["decisions"].append({"success": True, "data": decision})
                except Exception as e:
                    results["decisions"].append({"success": False, "data": decision, "error": str(e)})
                    results["errors"].append({"type": "decision", "error": str(e), "data": decision})
            
        finally:
            # 恢复离线模式
            self.offline_mode = original_offline_mode
        
        return results
    
    def fetch_tasks_by_criteria(self, milestone_name: str = None, phase: str = None, 
                           task_prefix: str = None, status_filter: List[str] = None) -> List[Dict]:
        """按多种条件过滤任务"""
        self.last_fetch_error = None
        
        # 获取全量任务（包含 done），由 status_filter 决定是否筛选
        all_tasks = self.fetch_all_tasks()
        filtered_tasks = []
        
        for task in all_tasks:
            match = True
            
            # 按里程碑名称过滤
            if milestone_name and task.get("milestone_name"):
                if milestone_name.lower() not in task["milestone_name"].lower():
                    match = False
            
            # 按阶段过滤
            if phase and task.get("phase"):
                if phase.lower() != task["phase"].lower():
                    match = False
            
            # 按任务前缀过滤（如 P1.phase0）
            if task_prefix and task.get("name"):
                if not task["name"].startswith(task_prefix):
                    match = False
            
            # 按状态过滤
            if status_filter and task.get("status") not in status_filter:
                match = False
            
            if match:
                filtered_tasks.append(task)
        
        return filtered_tasks

    def fetch_tasks_by_prefix(self, prefix: str, status_filter: List[str] = None) -> List[Dict]:
        """按任务名称前缀过滤任务，如 'P1.phase0'"""
        self.last_fetch_error = None
        # 获取全量任务（包含 done），由 status_filter 决定是否筛选
        all_tasks = self.fetch_all_tasks()
        
        filtered = []
        for task in all_tasks:
            if task.get("name", "").startswith(prefix):
                if status_filter is None or task.get("status") in status_filter:
                    filtered.append(task)
        
        return filtered

# ============================
# 命令行接口
# ============================

def main():
    parser = argparse.ArgumentParser(description="Notion项目管理状态同步工具")
    parser.add_argument("--verify-token", action="store_true", help="预检 NOTION_TOKEN 是否可用")
    parser.add_argument("--fetch-tasks", action="store_true", help="获取任务列表")
    parser.add_argument("--milestone-id", help="里程碑ID")
    parser.add_argument("--milestone-name", help="按里程碑名称过滤（支持模糊匹配）")  # 新增
    parser.add_argument("--phase", help="按阶段过滤，如 'phase 0', 'phase 1'")        # 新增
    parser.add_argument("--task-prefix", help="按任务前缀过滤，如 'P1.phase0'")       # 新增
    parser.add_argument("--status", help="状态过滤器，多个状态用逗号分隔")
    parser.add_argument("--output", help="输出文件路径")
    
    parser.add_argument("--update-task", help="更新任务状态，参数为任务ID")
    parser.add_argument("--status-value", help="新状态值")
    parser.add_argument("--test-evidence", help="测试证据文本")
    parser.add_argument("--test-files", help="逗号分隔的测试文件路径列表（P0/P1 进入 In review/done 必填）")
    parser.add_argument("--flow-check", action="store_true", help="流程演练模式（默认不改真实任务状态）")
    
    parser.add_argument("--update-milestone-progress", help="更新里程碑进度，参数为里程碑ID")
    parser.add_argument("--phase-filter", help="仅按指定 phase 计算里程碑进度，如 'phase 0'")
    parser.add_argument("--update-all-milestones", action="store_true", help="更新所有里程碑进度")
    
    parser.add_argument("--create-report", action="store_true", help="创建阶段报告")
    parser.add_argument("--report-file", help="报告文件路径")
    parser.add_argument("--update-report", help="更新报告状态，参数为报告ID")
    parser.add_argument("--report-status", help="报告新状态")

    parser.add_argument("--report-id", help="报告ID，用于关联评审")

    parser.add_argument("--link-report-to-review", action="store_true", help="关联报告到评审")
    parser.add_argument("--review-id", help="评审ID")
    
    parser.add_argument("--record-decision", action="store_true", help="记录验收决策")
    parser.add_argument("--accept-closeout", action="store_true", help="原子执行 ACCEPT 收尾（record-decision + post-fetch）")
    parser.add_argument("--decision", help="决策内容")
    parser.add_argument("--notes", help="备注")
    parser.add_argument("--summary-output", help="原子收尾摘要输出路径")
    
    parser.add_argument("--offline", action="store_true", help="启用离线模式")
    parser.add_argument("--batch-sync", help="批量同步离线文件")
    
    parser.add_argument("--version", action="version", version="sync_pm_status.py 2.1.1")
    
    args = parser.parse_args()
    
    # 如果没有参数，显示帮助
    if len(sys.argv) == 1:
        parser.print_help()
        sys.exit(1)
    
    try:
        manager = PMSStatusSyncManager()
    except Exception as e:
        if args.verify_token:
            print("🔐 Token 预检结果:")
            print(json.dumps({"ok": False, "error": str(e)}, ensure_ascii=False, indent=2))
            sys.exit(1)
        print(f"❌ 初始化失败: {e}")
        sys.exit(1)

    # Token 预检（用于 autopilot preflight）
    if args.verify_token:
        result = manager.verify_token()
        print("🔐 Token 预检结果:")
        print(json.dumps(result, ensure_ascii=False, indent=2))
        if not result.get("ok"):
            sys.exit(1)
        return
    
    # 离线模式
    if args.offline:
        manager.enable_offline_mode()
    if args.flow_check:
        manager.enable_flow_check_mode()
    
    # 批量同步
    if args.batch_sync:
        print(f"📋 开始批量同步离线文件: {args.batch_sync}")
        results = manager.batch_sync_offline(args.batch_sync)
        print(json.dumps(results, ensure_ascii=False, indent=2))
        return
    
    # 获取任务列表
    if args.fetch_tasks:
        print("📋 获取任务列表...")
        status_filter = args.status.split(",") if args.status else None
        
        if args.task_prefix:
            # 按任务前缀过滤
            tasks = manager.fetch_tasks_by_prefix(args.task_prefix, status_filter)
            print(f"✅ 按前缀 '{args.task_prefix}' 获取到 {len(tasks)} 个任务")
        elif args.milestone_name:
            # 按里程碑名称过滤
            tasks = manager.fetch_tasks_by_criteria(
                milestone_name=args.milestone_name,
                status_filter=status_filter
            )
            print(f"✅ 按里程碑名称 '{args.milestone_name}' 获取到 {len(tasks)} 个任务")
        elif args.phase:
            # 按阶段过滤
            tasks = manager.fetch_tasks_by_criteria(
                phase=args.phase,
                status_filter=status_filter
            )
            print(f"✅ 按阶段 '{args.phase}' 获取到 {len(tasks)} 个任务")
        elif args.milestone_id:
            # 原有的按里程碑ID过滤
            tasks = manager.fetch_tasks_by_milestone(args.milestone_id, status_filter)
            print(f"✅ 按里程碑ID获取到 {len(tasks)} 个任务")
        else:
            # 获取所有活跃任务
            tasks = manager.fetch_all_active_tasks()
            print(f"✅ 获取到 {len(tasks)} 个活跃任务")
        
        if args.output:
            with open(args.output, 'w', encoding='utf-8') as f:
                json.dump({"tasks": tasks}, f, ensure_ascii=False, indent=2)
            print(f"💾 已保存到: {args.output}")
        else:
            print(json.dumps(tasks, ensure_ascii=False, indent=2))
        
        # 关键修复：任务查询失败时必须返回非0，避免把网络/权限错误误判为“成功且0条”
        if manager.last_fetch_error:
            print(f"❌ 获取任务失败（退出码非0）: {manager.last_fetch_error}")
            sys.exit(1)
    
    # 更新任务状态/测试证据
    elif args.update_task:
        # 检查是否提供了状态值或测试证据
        has_status = args.status_value is not None
        has_evidence = args.test_evidence is not None
        
        if not has_status and not has_evidence:
            print("❌ 请至少指定一项更新内容：--status-value 或 --test-evidence")
            sys.exit(1)
        
        print(f"🔄 更新任务: {args.update_task}")
        if has_status:
            print(f"   状态: {args.status_value}")
        if has_evidence:
            evidence_preview = args.test_evidence[:50] + "..." if len(args.test_evidence) > 50 else args.test_evidence
            print(f"   测试证据: {evidence_preview}")
        parsed_test_files = None
        if args.test_files:
            parsed_test_files = [item.strip() for item in args.test_files.split(",") if item.strip()]
            print(f"   测试文件: {parsed_test_files}")
        
        try:
            result = manager.update_task_status(
                args.update_task,
                args.status_value,  # 可以是 None
                args.test_evidence,  # 可以是 None
                parsed_test_files
            )
            print(f"✅ 更新完成")
            if not args.offline and result:
                print(json.dumps(result, ensure_ascii=False, indent=2))
        except Exception as e:
            print(f"❌ 更新失败: {e}")
            sys.exit(1)
    
    # 更新里程碑进度
    elif args.update_milestone_progress:
        if args.phase_filter:
            print(f"🔄 更新里程碑进度: {args.update_milestone_progress} (phase={args.phase_filter})")
        else:
            print(f"🔄 更新里程碑进度: {args.update_milestone_progress}")
        try:
            result = manager.update_milestone_progress(
                args.update_milestone_progress,
                phase_filter=args.phase_filter
            )
            print(f"✅ 更新完成")
            if not args.offline:
                print(json.dumps(result, ensure_ascii=False, indent=2))
        except Exception as e:
            print(f"❌ 更新失败: {e}")
            sys.exit(1)
    
    elif args.update_all_milestones:
        print("🔄 更新所有里程碑进度...")
        try:
            results = manager.update_all_milestones_progress()
            print(f"✅ 完成，共处理 {len(results)} 个里程碑")
        except Exception as e:
            print(f"❌ 更新失败: {e}")
            sys.exit(1)
    
    # 创建报告
    elif args.create_report:
        if not args.milestone_id:
            print("❌ 请指定 --milestone-id")
            sys.exit(1)
        
        try:
            if args.report_file:
                print(f"📄 从文件生成报告: {args.report_file}")
                result = manager.generate_report_from_file(args.milestone_id, args.report_file)
            else:
                # 交互式创建
                report_data = {
                    "name": input("报告名称: ").strip(),
                    "scope": input("范围: ").strip(),
                    "deliverables": input("可交付成果: ").strip(),
                    "test_results": input("测试结果: ").strip(),
                    "risks": input("风险: ").strip(),
                    "status": "Draft"
                }
                result = manager.create_phase_report(args.milestone_id, report_data)
            
            print(f"✅ 报告创建完成")
            if not args.offline:
                print(json.dumps(result, ensure_ascii=False, indent=2))
        except Exception as e:
            print(f"❌ 创建报告失败: {e}")
            sys.exit(1)
    
    # 更新报告状态
    elif args.update_report:
        if not args.report_status:
            print("❌ 请指定 --report-status")
            sys.exit(1)
        
        print(f"🔄 更新报告状态: {args.update_report} -> {args.report_status}")
        try:
            result = manager.update_report_status(args.update_report, args.report_status)
            print(f"✅ 更新完成")
        except Exception as e:
            print(f"❌ 更新失败: {e}")
            sys.exit(1)
    
    # 关联报告到评审
    elif args.link_report_to_review:
        if not args.report_id or not args.review_id:
            print("❌ 请指定 --report-id 和 --review-id")
            sys.exit(1)
        
        print(f"🔄 关联报告 {args.report_id} 到评审 {args.review_id}")
        try:
            result = manager.link_report_to_review(args.report_id, args.review_id)
            print(f"✅ 关联完成")
        except Exception as e:
            print(f"❌ 关联失败: {e}")
            sys.exit(1)

    # 原子 ACCEPT 收尾（在线 A/C）
    elif args.accept_closeout:
        if not args.milestone_id:
            print("❌ 请指定 --milestone-id")
            sys.exit(1)
        decision = args.decision or "ACCEPT"
        notes = args.notes or ""
        post_fetch_output = args.output or "tmp/post_accept_fetch.json"
        print(f"🔄 原子收尾: decision={decision}, milestone={args.milestone_id}")
        try:
            summary = manager.accept_closeout_atomic(
                milestone_id=args.milestone_id,
                decision=decision,
                notes=notes,
                post_fetch_output=post_fetch_output,
            )
            if args.summary_output:
                out = Path(args.summary_output)
                out.parent.mkdir(parents=True, exist_ok=True)
                out.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
            print(json.dumps(summary, ensure_ascii=False, indent=2))
            if summary.get("record_decision_rc") != 0:
                print("❌ 原子收尾失败: record_decision")
                sys.exit(1)
            if summary.get("fetch_rc") != 0:
                print("❌ 原子收尾失败: post_fetch")
                sys.exit(1)
            print("✅ 原子收尾完成")
        except Exception as e:
            print(f"❌ 原子收尾异常: {e}")
            sys.exit(1)
    
    # 记录决策
    elif args.record_decision:
        if not args.milestone_id or not args.decision:
            print("❌ 请指定 --milestone-id 和 --decision")
            sys.exit(1)
        
        print(f"🔄 记录决策: {args.decision} 到里程碑 {args.milestone_id}")
        if args.notes:
            print(f"   备注: {args.notes}")
        
        try:
            result = manager.record_decision(args.milestone_id, args.decision, args.notes)
            print(f"✅ 决策已记录")
        except Exception as e:
            print(f"❌ 记录决策失败: {e}")
            sys.exit(1)
    
    # 保存离线数据
    if manager.offline_mode and manager.offline_payload:
        manager.save_offline_payload()


if __name__ == "__main__":
    main()
