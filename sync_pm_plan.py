#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
sync_pm_plan.py - 同步项目管理计划到 Notion（里程碑 + 任务）

能力：
1) Payload schema 校验（含 depends_on 关系校验）
2) 幂等 upsert（同 milestone.key / task.id 重跑不重复创建）
3) dry-run 预演（仅校验与输出，不落库）
4) 同步结果对账输出（tmp/pm_plan_sync_verify.json）
5) 失败重试（指数退避 1s/2s/4s，最多 3 次）
"""

import argparse
import json
import os
import re
import sys
import time
import traceback
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from notion_sync_manager import NotionSyncManager


TASK_ID_RE = re.compile(r"^(P\d+\.phase\d+-T\d+)\b")
MILESTONE_KEY_RE = re.compile(r"^(P\d+\.phase\d+)\b")


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _retry_with_backoff(fn, *args, **kwargs):
    waits = [1, 2, 4]
    last_exc = None
    for i, wait_s in enumerate(waits, start=1):
        try:
            return fn(*args, **kwargs)
        except Exception as exc:
            last_exc = exc
            if i == len(waits):
                break
            print(f"⚠️ 第 {i} 次调用失败，{wait_s}s 后重试: {exc}")
            time.sleep(wait_s)
    raise last_exc


def _load_json(path: str) -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _dump_json(path: str, obj: Dict[str, Any]) -> None:
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)


def _extract_task_id(task_name: str) -> Optional[str]:
    if not isinstance(task_name, str):
        return None
    m = TASK_ID_RE.match(task_name.strip())
    return m.group(1) if m else None


def _extract_milestone_key(name: str) -> Optional[str]:
    if not isinstance(name, str):
        return None
    m = MILESTONE_KEY_RE.match(name.strip())
    return m.group(1) if m else None


def _normalize_payload(raw: Dict[str, Any]) -> Dict[str, Any]:
    payload = dict(raw)

    # 兼容旧格式: milestone -> milestones
    if "milestones" not in payload and "milestone" in payload:
        m = payload["milestone"]
        payload["milestones"] = [
            {
                "key": m.get("key") or _extract_milestone_key(m.get("name", "")) or "P0.phase0",
                "name": m.get("name", "未命名里程碑"),
                "phase": m.get("phase", "phase 1"),
                "summary": m.get("summary", ""),
            }
        ]

    payload.setdefault("scope", "system")
    payload.setdefault("run_id", datetime.now().strftime("%Y%m%d_%H%M%S"))
    payload.setdefault("version", "1.1")
    payload.setdefault("generated_at", _utc_now())
    payload.setdefault("source_docs", [])

    milestones = payload.get("milestones", [])
    tasks = payload.get("tasks", [])

    # 标准化 milestone
    norm_milestones: List[Dict[str, Any]] = []
    for m in milestones:
        key = m.get("key") or _extract_milestone_key(m.get("name", ""))
        norm_milestones.append(
            {
                "key": key,
                "name": m.get("name", ""),
                "phase": m.get("phase", ""),
                "summary": m.get("summary", ""),
            }
        )

    # 标准化 tasks：统一 depends_on，确保 id
    norm_tasks: List[Dict[str, Any]] = []
    for t in tasks:
        depends_on = t.get("depends_on")
        if depends_on is None:
            depends_on = t.get("dependencies", [])
        depends_on = depends_on or []

        task_id = t.get("id") or _extract_task_id(t.get("name", ""))
        task_name = t.get("name", "")
        if task_id and isinstance(task_name, str) and not task_name.startswith(task_id):
            task_name = f"{task_id} {task_name}".strip()

        norm_tasks.append(
            {
                "id": task_id,
                "name": task_name,
                "priority": t.get("priority", "P1"),
                "estimate": t.get("estimate"),
                "depends_on": depends_on,
                "dod_checklist": t.get("dod_checklist", []),
                "milestone_key": t.get("milestone_key"),
            }
        )

    # phase_code 默认取第一个 milestone key
    if "phase_code" not in payload or not payload.get("phase_code"):
        payload["phase_code"] = norm_milestones[0]["key"] if norm_milestones else "P0.phase0"

    payload["milestones"] = norm_milestones
    payload["tasks"] = norm_tasks
    return payload


def _validate_payload(payload: Dict[str, Any]) -> Tuple[List[str], List[str]]:
    errors: List[str] = []
    warnings: List[str] = []

    for k in ["run_id", "version", "generated_at", "phase_code", "scope", "milestones", "tasks"]:
        if k not in payload:
            errors.append(f"缺少顶层字段: {k}")

    milestones = payload.get("milestones", [])
    tasks = payload.get("tasks", [])

    if not isinstance(milestones, list) or not milestones:
        errors.append("milestones 必须是非空数组")
    if not isinstance(tasks, list) or not tasks:
        errors.append("tasks 必须是非空数组")

    milestone_keys = set()
    for i, m in enumerate(milestones):
        for k in ["key", "name", "phase"]:
            if not m.get(k):
                errors.append(f"milestones[{i}] 缺少字段: {k}")
        key = m.get("key")
        if key in milestone_keys:
            errors.append(f"milestone key 重复: {key}")
        milestone_keys.add(key)

    task_ids = set()
    allowed_priority = {"P0", "P1", "P2"}
    for i, t in enumerate(tasks):
        for k in ["id", "name", "priority", "depends_on", "dod_checklist"]:
            if k not in t:
                errors.append(f"tasks[{i}] 缺少字段: {k}")

        tid = t.get("id")
        if not tid:
            errors.append(f"tasks[{i}] 缺少 id")
        elif tid in task_ids:
            errors.append(f"task id 重复: {tid}")
        else:
            task_ids.add(tid)

        if isinstance(t.get("name"), str) and tid and not t["name"].startswith(tid):
            warnings.append(f"tasks[{i}] name 未以 task id 开头，已在归一化阶段自动补齐: {tid}")

        if t.get("priority") not in allowed_priority:
            errors.append(f"tasks[{i}] priority 非法: {t.get('priority')}（允许 P0/P1/P2）")

        if not isinstance(t.get("depends_on", []), list):
            errors.append(f"tasks[{i}] depends_on 必须是数组")
        if not isinstance(t.get("dod_checklist", []), list):
            errors.append(f"tasks[{i}] dod_checklist 必须是数组")

    for t in tasks:
        for dep in t.get("depends_on", []):
            if dep not in task_ids:
                errors.append(f"任务依赖不存在: {t.get('id')} -> {dep}")

    if len(milestones) > 12:
        warnings.append(f"里程碑数量较大: {len(milestones)}，建议分批输出")
    if len(tasks) > 200:
        warnings.append(f"任务数量较大: {len(tasks)}，建议分批输出")

    return errors, warnings


def _search_pages_in_data_source(manager: NotionSyncManager, ds_key: str) -> List[Dict[str, Any]]:
    ds_id = manager.DS[ds_key]
    response = _retry_with_backoff(
        manager.notion.search,
        filter={"property": "object", "value": "page"},
    )
    out = []
    for page in response.get("results", []):
        parent = page.get("parent", {})
        if parent.get("type") == "data_source_id" and parent.get("data_source_id") == ds_id:
            out.append(page)
    return out


def _extract_title(page: Dict[str, Any], prop: str = "Name") -> str:
    props = page.get("properties", {})
    title_parts = props.get(prop, {}).get("title", [])
    return "".join([x.get("plain_text", "") for x in title_parts]).strip()


def _prefetch_existing(manager: NotionSyncManager) -> Dict[str, Any]:
    milestones = _search_pages_in_data_source(manager, "milestones")
    tasks = _search_pages_in_data_source(manager, "tasks")

    milestone_by_key: Dict[str, str] = {}
    milestone_by_name: Dict[str, str] = {}
    for m in milestones:
        name = _extract_title(m)
        mid = m.get("id")
        if name:
            milestone_by_name[name] = mid
            key = _extract_milestone_key(name)
            if key:
                milestone_by_key[key] = mid

    task_by_id: Dict[str, str] = {}
    task_by_name: Dict[str, str] = {}
    task_milestone_by_id: Dict[str, str] = {}
    for t in tasks:
        name = _extract_title(t)
        tid_page = t.get("id")
        props = t.get("properties", {})
        milestone_rel = props.get("Milestone", {}).get("relation", [])
        milestone_id = milestone_rel[0].get("id") if milestone_rel else None
        if name:
            task_by_name[name] = tid_page
            logical_id = _extract_task_id(name)
            if logical_id:
                task_by_id[logical_id] = tid_page
                if milestone_id:
                    task_milestone_by_id[logical_id] = milestone_id

    return {
        "milestones_total": len(milestones),
        "tasks_total": len(tasks),
        "milestone_by_key": milestone_by_key,
        "milestone_by_name": milestone_by_name,
        "task_by_id": task_by_id,
        "task_by_name": task_by_name,
        "task_milestone_by_id": task_milestone_by_id,
    }


def _infer_milestone_id_from_existing_tasks(
    payload_tasks: List[Dict[str, Any]], existing: Dict[str, Any]
) -> Tuple[Optional[str], List[str], bool]:
    """
    从 payload 中已存在于 Notion 的任务反推出应复用的里程碑：
    - 若唯一命中一个 milestone_id，则返回该 id；
    - 若命中多个不同 milestone_id，则返回 None 并给 warning；
    - 若无命中，则返回 None。
    """
    warnings: List[str] = []
    candidates = set()
    mapping = existing.get("task_milestone_by_id", {})
    for t in payload_tasks:
        tid = t.get("id")
        if tid and tid in mapping:
            candidates.add(mapping[tid])

    if len(candidates) == 1:
        return next(iter(candidates)), warnings, False
    if len(candidates) > 1:
        warnings.append(
            f"通过既有任务反推里程碑出现多值冲突: {sorted(candidates)}，将不启用反推复用"
        )
        return None, warnings, True
    return None, warnings, False


def _upsert_milestones(
    manager: NotionSyncManager,
    milestones: List[Dict[str, Any]],
    existing: Dict[str, Any],
    dry_run: bool,
) -> Tuple[Dict[str, str], int, int]:
    mapping: Dict[str, str] = {}
    created = 0
    updated = 0

    for m in milestones:
        key = m["key"]
        name = m["name"]
        phase = m["phase"]
        summary = m.get("summary", "")

        page_id = existing["milestone_by_key"].get(key) or existing["milestone_by_name"].get(name)

        if dry_run:
            if page_id:
                print(f"🧪 dry-run: 将更新里程碑 {name} ({page_id})")
                updated += 1
                mapping[key] = page_id
            else:
                fake = f"dryrun_milestone_{key}"
                print(f"🧪 dry-run: 将创建里程碑 {name} ({fake})")
                created += 1
                mapping[key] = fake
            continue

        if page_id:
            _retry_with_backoff(
                manager.notion.pages.update,
                page_id=page_id,
                properties={
                    "Name": {"title": [{"text": {"content": name}}]},
                    "Phase": {"select": {"name": phase}},
                    "Summary": {"rich_text": [{"text": {"content": summary}}]},
                },
            )
            print(f"✅ 更新里程碑: {name} ({page_id})")
            updated += 1
            mapping[key] = page_id
        else:
            page = _retry_with_backoff(manager.create_milestone, name, phase, summary)
            new_id = page["id"]
            print(f"✅ 创建里程碑: {name} ({new_id})")
            created += 1
            mapping[key] = new_id

    return mapping, created, updated


def _upsert_tasks(
    manager: NotionSyncManager,
    tasks: List[Dict[str, Any]],
    milestone_mapping: Dict[str, str],
    default_milestone_key: str,
    existing: Dict[str, Any],
    dry_run: bool,
) -> Tuple[Dict[str, str], int, int, List[str]]:
    task_page_mapping: Dict[str, str] = {}
    created = 0
    updated = 0
    warnings: List[str] = []

    for t in tasks:
        tid = t["id"]
        name = t["name"]
        milestone_key = t.get("milestone_key") or default_milestone_key
        milestone_id = milestone_mapping.get(milestone_key)
        if not milestone_id:
            warnings.append(f"任务 {tid} 找不到 milestone_key={milestone_key}，将尝试使用默认里程碑")
            milestone_id = next(iter(milestone_mapping.values()), None)
        if not milestone_id:
            raise ValueError(f"任务 {tid} 无法确定 Milestone 关联 ID")

        dep_rel = []
        for dep in t.get("depends_on", []):
            dep_page_id = task_page_mapping.get(dep) or existing["task_by_id"].get(dep)
            if dep_page_id:
                dep_rel.append({"id": dep_page_id})
            else:
                warnings.append(f"任务 {tid} 的依赖 {dep} 暂不可解析，将忽略该依赖")

        dod_multi = [{"name": x} for x in t.get("dod_checklist", [])]
        page_id = existing["task_by_id"].get(tid) or existing["task_by_name"].get(name)

        if dry_run:
            if page_id:
                print(f"🧪 dry-run: 将更新任务 {name} ({page_id})")
                updated += 1
                task_page_mapping[tid] = page_id
            else:
                fake = f"dryrun_task_{tid}"
                print(f"🧪 dry-run: 将创建任务 {name} ({fake})")
                created += 1
                task_page_mapping[tid] = fake
            continue

        if page_id:
            _retry_with_backoff(
                manager.notion.pages.update,
                page_id=page_id,
                properties={
                    "Name": {"title": [{"text": {"content": name}}]},
                    "Priority": {"select": {"name": t.get("priority", "P1")}},
                    "Estimate": {"number": t.get("estimate")},
                    "Milestone": {"relation": [{"id": milestone_id}]},
                    "Dependencies": {"relation": dep_rel},
                    "DoD Checklist": {"multi_select": dod_multi},
                },
            )
            print(f"✅ 更新任务: {name} ({page_id})")
            updated += 1
            task_page_mapping[tid] = page_id
        else:
            page = _retry_with_backoff(
                manager.create_task,
                milestone_id=milestone_id,
                name=name,
                priority=t.get("priority", "P1"),
                estimate=t.get("estimate"),
                dependencies=dep_rel,
                dod_checklist=dod_multi,
            )
            new_id = page["id"]
            print(f"✅ 创建任务: {name} ({new_id})")
            created += 1
            task_page_mapping[tid] = new_id

    return task_page_mapping, created, updated, warnings


def _update_task_progress(payload: Dict[str, Any], dry_run: bool) -> None:
    manager = NotionSyncManager()
    for task_update in payload.get("task_updates", []):
        task_id = task_update["task_id"]
        progress = task_update["progress"]
        if dry_run:
            print(f"🧪 dry-run: 将更新任务进度 {task_id} -> {progress}%")
            continue
        _retry_with_backoff(manager.update_progress, page_id=task_id, progress=progress)
        print(f"✅ 更新任务进度: {task_id} -> {progress}%")


def _build_verify(
    payload: Dict[str, Any],
    dry_run: bool,
    milestones_created: int,
    milestones_updated: int,
    tasks_created: int,
    tasks_updated: int,
    existing: Dict[str, Any],
    milestone_mapping: Dict[str, str],
    task_mapping: Dict[str, str],
    warnings: List[str],
    errors: List[str],
) -> Dict[str, Any]:
    id_mapping = {}
    id_mapping.update(milestone_mapping)
    id_mapping.update(task_mapping)

    return {
        "run_id": payload.get("run_id"),
        "scope": payload.get("scope"),
        "phase_code": payload.get("phase_code"),
        "dry_run": dry_run,
        "generated_at": _utc_now(),
        "milestones": {
            "created": milestones_created,
            "updated": milestones_updated,
            "total_after_sync": existing.get("milestones_total", 0) + milestones_created,
        },
        "tasks": {
            "created": tasks_created,
            "updated": tasks_updated,
            "total_after_sync": existing.get("tasks_total", 0) + tasks_created,
        },
        "id_mapping": id_mapping,
        "warnings": warnings,
        "errors": errors,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="同步项目计划到 Notion（支持 dry-run、幂等 upsert、schema 校验）")
    parser.add_argument("input_file", help="计划 payload JSON 文件路径")
    parser.add_argument("--update-progress", action="store_true", help="更新任务进度模式")
    parser.add_argument("--dry-run", action="store_true", help="仅校验与预演，不写 Notion")
    parser.add_argument(
        "--verify-out",
        default="tmp/pm_plan_sync_verify.json",
        help="同步对账输出路径（默认: tmp/pm_plan_sync_verify.json）",
    )
    args = parser.parse_args()

    try:
        raw = _load_json(args.input_file)
        payload = _normalize_payload(raw)

        print(f"📋 开始同步项目管理计划: {args.input_file}")
        print(f"📅 同步时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"🧪 dry-run: {'是' if args.dry_run else '否'}")
        print("-" * 60)

        if args.update_progress:
            _update_task_progress(payload, args.dry_run)
            verify = {
                "run_id": payload.get("run_id"),
                "mode": "update-progress",
                "dry_run": args.dry_run,
                "generated_at": _utc_now(),
                "errors": [],
            }
            _dump_json(args.verify_out, verify)
            print(f"💾 已输出对账文件: {args.verify_out}")
            print("✅ Notion sync completed (pm-plan)")
            return

        errors, warnings = _validate_payload(payload)
        if warnings:
            for w in warnings:
                print(f"⚠️ {w}")
        if errors:
            for e in errors:
                print(f"❌ {e}")
            verify = _build_verify(
                payload,
                args.dry_run,
                0,
                0,
                0,
                0,
                {"milestones_total": 0, "tasks_total": 0},
                {},
                {},
                warnings,
                errors,
            )
            _dump_json(args.verify_out, verify)
            print(f"💾 已输出对账文件: {args.verify_out}")
            sys.exit(1)

        manager = NotionSyncManager()
        token = os.getenv("NOTION_TOKEN")
        if not token and not args.dry_run:
            print("❌ 未检测到 NOTION_TOKEN，无法执行在线同步")
            sys.exit(1)

        existing = {
            "milestones_total": 0,
            "tasks_total": 0,
            "milestone_by_key": {},
            "milestone_by_name": {},
            "task_by_id": {},
            "task_by_name": {},
            "task_milestone_by_id": {},
        }

        if token:
            try:
                existing = _prefetch_existing(manager)
            except Exception as exc:
                print(f"❌ 预取 Notion 现有数据失败: {exc}")
                if args.dry_run:
                    print("🧪 dry-run 模式：继续输出预演结果（无现网对账基线）")
                else:
                    raise
        else:
            print("🧪 dry-run 且无 NOTION_TOKEN：将跳过在线预取")

        # 更严格幂等：若 milestone key 未命中，优先用“已有任务关系”反推要复用的里程碑
        infer_warnings: List[str] = []
        inferred_mid, infer_warnings, infer_conflict = _infer_milestone_id_from_existing_tasks(payload["tasks"], existing)
        if inferred_mid:
            first_key = payload["milestones"][0]["key"] if payload.get("milestones") else None
            if first_key and first_key not in existing.get("milestone_by_key", {}):
                existing["milestone_by_key"][first_key] = inferred_mid
                print(f"🔁 幂等复用：通过既有任务反推里程碑 {first_key} -> {inferred_mid}")
        for w in infer_warnings:
            print(f"⚠️ {w}")
        if infer_conflict:
            raise ValueError(
                "检测到既有任务反推里程碑多值冲突，请人工确认目标里程碑后再重试同步"
            )

        milestone_mapping, m_created, m_updated = _upsert_milestones(
            manager=manager,
            milestones=payload["milestones"],
            existing=existing,
            dry_run=args.dry_run,
        )

        default_m_key = payload["milestones"][0]["key"]
        task_mapping, t_created, t_updated, task_warnings = _upsert_tasks(
            manager=manager,
            tasks=payload["tasks"],
            milestone_mapping=milestone_mapping,
            default_milestone_key=default_m_key,
            existing=existing,
            dry_run=args.dry_run,
        )

        all_warnings = warnings + infer_warnings + task_warnings
        for w in task_warnings:
            print(f"⚠️ {w}")

        verify = _build_verify(
            payload=payload,
            dry_run=args.dry_run,
            milestones_created=m_created,
            milestones_updated=m_updated,
            tasks_created=t_created,
            tasks_updated=t_updated,
            existing=existing,
            milestone_mapping=milestone_mapping,
            task_mapping=task_mapping,
            warnings=all_warnings,
            errors=[],
        )
        _dump_json(args.verify_out, verify)
        print(f"💾 已输出对账文件: {args.verify_out}")

        print("-" * 60)
        if args.dry_run:
            print("✅ Dry-run completed (pm-plan)")
        else:
            print("✅ Notion sync completed (pm-plan)")

    except FileNotFoundError:
        print(f"❌ 文件不存在: {args.input_file}")
        sys.exit(1)
    except json.JSONDecodeError:
        print(f"❌ 无效的JSON格式: {args.input_file}")
        sys.exit(1)
    except Exception as exc:
        print("❌ 同步失败，已中止")
        print(f"错误: {exc}")
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
