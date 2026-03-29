#!/usr/bin/env python3
"""Interactive gguf benchmark (single model load, multi-turn judging).

Uses llama-cli in interactive mode to avoid repeated cold starts.
Evaluates mismatch samples with the same yes/no style as test_llm_theme_judge_batch.py.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path
from typing import Dict, List


REPO_ROOT = Path("/Users/admin/Desktop/ai_theme_app")
DEFAULT_MODEL = REPO_ROOT / "model_service/models/qwen2.5/qwen2.5-1.5b-instruct-q5_k_m.gguf"
DEFAULT_AB = REPO_ROOT / "tmp/phase3_semantic_vs_llm_mismatch13_ab_clean.json"
DEFAULT_EVENTS = REPO_ROOT / "evaluate_service/data/raw/ai_processed_events.json"
DEFAULT_OUT = REPO_ROOT / "tmp/phase3_llm_gguf_1p5b_mismatch_report.json"


def _load_json(path: Path):
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def _build_cases(ab_report: Dict) -> List[Dict]:
    sem = ab_report.get("semantic_only") or {}
    mappings = {r.get("event_id"): r.get("matched_theme_name") for r in sem.get("update_theme_mappings") or []}
    out = []
    for row in sem.get("ground_truth_comparison") or []:
        if row.get("ground_truth_passed"):
            continue
        eid = row.get("event_id")
        gt_themes = row.get("ground_truth_themes") or []
        gt = gt_themes[0] if gt_themes else row.get("ground_truth_theme_group")
        wrong = mappings.get(eid)
        if eid and gt and wrong:
            out.append({"event_id": eid, "gt_theme": gt, "wrong_theme": wrong, "event_title": row.get("event_title", "")})
    return out


def _events_map(events_json) -> Dict[str, Dict]:
    items = events_json if isinstance(events_json, list) else events_json.get("events", [])
    return {str(e.get("event_id")): e for e in items if isinstance(e, dict) and e.get("event_id")}


def _event_text(e: Dict) -> str:
    ai = e.get("ai_analysis") or {}
    return " ".join(
        [
            str(e.get("title") or ""),
            str(ai.get("core_concept") or ""),
            str(e.get("content") or ""),
        ]
    ).strip()


def _build_prompt(event_text: str, themes: List[str]) -> str:
    lines = "\n".join([f"{i+1}. {t}" for i, t in enumerate(themes)])
    return (
        "你是一个严格的金融题材裁判。\n\n"
        "给定一个【事件】和【多个候选题材】，\n"
        "请判断该事件是否“属于”每一个题材。\n\n"
        "判断标准：\n"
        "- 是否处于同一产业链 / 技术体系\n"
        "- 是否存在直接业务或技术关联\n"
        "- 仅凭“都是高科技”不能算\n\n"
        "输出要求：\n"
        "- 每一行一个题材\n"
        "- 格式固定：题材名=是 或 题材名=否\n"
        "- 不要任何解释\n\n"
        f"事件：\n{event_text}\n\n候选题材：\n{lines}\n"
    )


def _parse_yesno(text: str) -> Dict[str, bool]:
    parsed: Dict[str, bool] = {}
    for line in text.splitlines():
        if "=" not in line:
            continue
        k, v = line.split("=", 1)
        vv = v.strip()
        parsed[k.strip()] = ("是" in vv and "否" not in vv)
    return parsed


def _wait_for_prompt(proc: subprocess.Popen, timeout_sec: int) -> str:
    start = time.time()
    buf = []
    while time.time() - start < timeout_sec:
        ch = proc.stdout.read(1)
        if not ch:
            break
        buf.append(ch)
        if "".join(buf[-3:]).endswith("\n> "):
            break
    return "".join(buf)


def run_benchmark(model: Path, ab_file: Path, events_file: Path, out_file: Path, max_cases: int = 3) -> Dict:
    ab = _load_json(ab_file)
    cases = _build_cases(ab)[:max_cases]
    events = _events_map(_load_json(events_file))
    if not cases:
        raise RuntimeError("No mismatch cases found.")

    cmd = [
        "llama-cli",
        "-m",
        str(model),
        "--ctx-size",
        "2048",
        "-t",
        "8",
        "--temp",
        "0",
        "--top-p",
        "0.1",
        "--repeat-penalty",
        "1.2",
    ]
    proc = subprocess.Popen(
        cmd,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
    )

    start = time.time()
    boot = _wait_for_prompt(proc, timeout_sec=120)
    if "> " not in boot:
        proc.kill()
        raise RuntimeError("llama-cli boot failed or prompt not found")

    rows = []
    gt_yes = 0
    wrong_no = 0
    pair = 0
    for idx, case in enumerate(cases, 1):
        e = events.get(case["event_id"], {})
        text = _event_text(e)
        cands = list(dict.fromkeys([case["gt_theme"], case["wrong_theme"], "核聚变", "卫星制造"]))
        prompt = _build_prompt(text, cands)
        proc.stdin.write(prompt + "\n")
        proc.stdin.flush()
        out = _wait_for_prompt(proc, timeout_sec=120)
        parsed = _parse_yesno(out)

        g_yes = bool(parsed.get(case["gt_theme"], False))
        w_no = not bool(parsed.get(case["wrong_theme"], False))
        gt_yes += int(g_yes)
        wrong_no += int(w_no)
        pair += int(g_yes and w_no)
        rows.append(
            {
                "index": idx,
                "event_id": case["event_id"],
                "gt_theme": case["gt_theme"],
                "wrong_theme": case["wrong_theme"],
                "gt_yes": g_yes,
                "wrong_no": w_no,
                "pair_pass": bool(g_yes and w_no),
                "parsed": parsed,
                "raw_head": out[:500],
            }
        )
        print(f"progress {idx}/{len(cases)} gt_yes={g_yes} wrong_no={w_no}")

    proc.stdin.write("/exit\n")
    proc.stdin.flush()
    try:
        proc.wait(timeout=5)
    except Exception:
        proc.kill()

    n = len(cases)
    report = {
        "model": str(model),
        "method": "interactive_single_load_llama_cli",
        "sample_size": n,
        "gt_yes_rate": round(gt_yes / n, 4),
        "wrong_no_rate": round(wrong_no / n, 4),
        "pairwise_accuracy": round(pair / n, 4),
        "elapsed_sec": round(time.time() - start, 2),
        "rows": rows,
    }
    out_file.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return report


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", default=str(DEFAULT_MODEL))
    parser.add_argument("--ab", default=str(DEFAULT_AB))
    parser.add_argument("--events", default=str(DEFAULT_EVENTS))
    parser.add_argument("--out", default=str(DEFAULT_OUT))
    parser.add_argument("--max-cases", type=int, default=3)
    args = parser.parse_args()

    report = run_benchmark(
        model=Path(args.model),
        ab_file=Path(args.ab),
        events_file=Path(args.events),
        out_file=Path(args.out),
        max_cases=args.max_cases,
    )
    print(
        json.dumps(
            {
                "sample_size": report["sample_size"],
                "gt_yes_rate": report["gt_yes_rate"],
                "wrong_no_rate": report["wrong_no_rate"],
                "pairwise_accuracy": report["pairwise_accuracy"],
                "elapsed_sec": report["elapsed_sec"],
            },
            ensure_ascii=False,
        )
    )
    print(f"report: {args.out}")


if __name__ == "__main__":
    main()
