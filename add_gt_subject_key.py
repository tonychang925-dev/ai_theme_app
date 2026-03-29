#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import json

# ✅ 你已经整理好的映射（核心）
mapping = {
    "ai/ar眼镜": "9030409",
    "可控核聚变": "9017950",
    "对日制裁": "9059919",
    "稀土永磁": "9010367",
    "海洋经济": "9043698",
    "光刻胶": "9018411",
    "卫星互联": "9019807",
    "液冷数据中心": "9024880",
    "ai智能体manus": "9043089",
    "spacex": "9060949"
}

INPUT_FILE = "structured_events.jsonl"
OUTPUT_FILE = "structured_events_with_gt.jsonl"


def normalize(s):
    """统一小写 + 去空格"""
    if not s:
        return ""
    return s.strip().lower().replace(" ", "")


def main():
    total = 0
    hit = 0

    with open(INPUT_FILE, "r", encoding="utf-8") as fin, \
         open(OUTPUT_FILE, "w", encoding="utf-8") as fout:

        for line in fin:
            line = line.strip()
            if not line:
                continue

            obj = json.loads(line)

            theme_name_raw = obj.get("theme_name", "")
            theme_name = normalize(theme_name_raw)

            gt_subject_key = mapping.get(theme_name)

            if gt_subject_key:
                hit += 1

            obj["gt_subject_key"] = gt_subject_key  # 即使 None 也写进去（方便排查）

            fout.write(json.dumps(obj, ensure_ascii=False) + "\n")
            total += 1

    print("=" * 60)
    print(f"[DONE] 总事件数: {total}")
    print(f"[MATCH] 成功映射: {hit}")
    print(f"[MISS ] 未映射: {total - hit}")
    print(f"[OUT  ] 输出文件: {OUTPUT_FILE}")
    print("=" * 60)


if __name__ == "__main__":
    main()