#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
sync_arch_review.py - 同步架构评审结果到 Notion

能力：
1) payload schema 校验
2) dry-run 预演
3) 同步重试（默认 2 次尝试）
4) 输出同步结果文件 tmp/arch_review_sync_verify.json
"""

import argparse
import json
import os
import time
import traceback
from datetime import datetime, timezone
from typing import Any, Dict, List, Tuple

from notion_sync_manager import NotionSyncManager


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _dump_json(path: str, data: Dict[str, Any]) -> None:
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def _load_payload(path: str) -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _normalize_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
    obj = dict(payload)
    obj.setdefault("run_id", datetime.now().strftime("%Y%m%d_%H%M%S"))
    obj.setdefault("scope", "system")
    obj.setdefault("generated_at", _utc_now())
    return obj


def _validate_payload(payload: Dict[str, Any]) -> Tuple[List[str], List[str]]:
    errors: List[str] = []
    warnings: List[str] = []

    for field in ["run_id", "scope", "generated_at", "milestone", "review", "adr_list"]:
        if field not in payload:
            errors.append(f"缺少顶层字段: {field}")

    milestone = payload.get("milestone", {})
    review = payload.get("review", {})
    adr_list = payload.get("adr_list", [])

    if not isinstance(milestone, dict):
        errors.append("milestone 必须是对象")
    else:
        for f in ["name", "phase", "summary"]:
            if not milestone.get(f):
                errors.append(f"milestone 缺少字段: {f}")

    if not isinstance(review, dict):
        errors.append("review 必须是对象")
    else:
        for f in ["name", "type"]:
            if not review.get(f):
                errors.append(f"review 缺少字段: {f}")

    if not isinstance(adr_list, list) or not adr_list:
        errors.append("adr_list 必须是非空数组")
    else:
        for i, adr in enumerate(adr_list):
            if not isinstance(adr, dict):
                errors.append(f"adr_list[{i}] 必须是对象")
                continue
            for f in ["name", "context", "decision"]:
                if not adr.get(f):
                    errors.append(f"adr_list[{i}] 缺少字段: {f}")

    if isinstance(adr_list, list) and len(adr_list) > 20:
        warnings.append(f"adr_list 数量较多: {len(adr_list)}，建议分批同步")

    return errors, warnings


def _retry_sync(fn, retries: int = 2, delay_s: int = 1):
    last_exc = None
    for attempt in range(1, retries + 1):
        try:
            return fn()
        except Exception as exc:
            last_exc = exc
            if attempt < retries:
                print(f"⚠️ 第 {attempt} 次同步失败，{delay_s}s 后重试: {exc}")
                time.sleep(delay_s)
    raise last_exc


def sync(payload: Dict[str, Any], dry_run: bool = False) -> Dict[str, Any]:
    milestone = payload["milestone"]
    review = payload["review"]
    adr_list = payload["adr_list"]

    if dry_run:
        print("🧪 dry-run: 将创建里程碑:", milestone["name"])
        print("🧪 dry-run: 将创建评审:", review["name"])
        for adr in adr_list:
            print("🧪 dry-run: 将创建 ADR:", adr["name"])
        return {
            "milestone_id": "dryrun_milestone_id",
            "review_id": "dryrun_review_id",
            "adr_ids": [f"dryrun_adr_{i+1}" for i in range(len(adr_list))],
        }

    manager = NotionSyncManager()

    created_milestone = manager.create_milestone(
        milestone["name"],
        milestone["phase"],
        milestone["summary"],
    )
    milestone_id = created_milestone["id"]

    created_review = manager.create_review(
        milestone_id,
        review["name"],
        review["type"],
    )
    review_id = created_review["id"]

    adr_ids: List[str] = []
    for adr in adr_list:
        created_adr = manager.create_adr(
            milestone_id,
            adr["name"],
            adr["context"],
            adr["decision"],
        )
        adr_ids.append(created_adr["id"])

    return {
        "milestone_id": milestone_id,
        "review_id": review_id,
        "adr_ids": adr_ids,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="同步架构评审结果到 Notion")
    parser.add_argument("input_file", help="架构评审 payload JSON 文件路径")
    parser.add_argument("--dry-run", action="store_true", help="仅预演，不写入 Notion")
    parser.add_argument(
        "--verify-out",
        default="tmp/arch_review_sync_verify.json",
        help="同步结果输出路径",
    )
    args = parser.parse_args()

    verify: Dict[str, Any] = {
        "run_id": None,
        "sync_status": "failed",
        "dry_run": args.dry_run,
        "generated_at": _utc_now(),
        "errors": [],
        "warnings": [],
        "id_mapping": {},
    }

    try:
        payload = _normalize_payload(_load_payload(args.input_file))
        verify["run_id"] = payload.get("run_id")
        verify["scope"] = payload.get("scope")

        errors, warnings = _validate_payload(payload)
        verify["warnings"] = warnings
        if warnings:
            for w in warnings:
                print(f"⚠️ {w}")

        if errors:
            verify["errors"] = errors
            for e in errors:
                print(f"❌ {e}")
            _dump_json(args.verify_out, verify)
            print(f"💾 已输出同步校验文件: {args.verify_out}")
            raise SystemExit(1)

        print(f"📋 开始同步架构评审: {args.input_file}")
        print(f"📅 同步时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"🧪 dry-run: {'是' if args.dry_run else '否'}")
        print("-" * 60)

        if not args.dry_run and not os.getenv("NOTION_TOKEN"):
            verify["errors"] = ["未检测到 NOTION_TOKEN，无法执行在线同步"]
            _dump_json(args.verify_out, verify)
            print(f"💾 已输出同步校验文件: {args.verify_out}")
            raise SystemExit(1)

        result = _retry_sync(lambda: sync(payload, dry_run=args.dry_run), retries=2, delay_s=1)

        verify["sync_status"] = "success"
        verify["id_mapping"] = result
        _dump_json(args.verify_out, verify)
        print(f"💾 已输出同步校验文件: {args.verify_out}")
        print("-" * 60)
        print("✅ Notion sync completed (arch-review)")

    except FileNotFoundError:
        verify["errors"] = [f"文件不存在: {args.input_file}"]
        _dump_json(args.verify_out, verify)
        print(f"❌ 文件不存在: {args.input_file}")
        raise SystemExit(1)
    except json.JSONDecodeError:
        verify["errors"] = [f"无效 JSON 格式: {args.input_file}"]
        _dump_json(args.verify_out, verify)
        print(f"❌ 无效 JSON 格式: {args.input_file}")
        raise SystemExit(1)
    except SystemExit:
        raise
    except Exception as exc:
        verify["errors"] = [str(exc), traceback.format_exc()]
        _dump_json(args.verify_out, verify)
        print("❌ 架构评审同步失败")
        print(str(exc))
        print(traceback.format_exc())
        raise SystemExit(1)


if __name__ == "__main__":
    main()
