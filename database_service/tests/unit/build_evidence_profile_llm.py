#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
题材证据画像生成工具 - 0.5B Transformers 改进版
"""

import json
import time
import re
from pathlib import Path
import torch
from transformers import AutoModelForCausalLM, AutoTokenizer

# 配置
MODEL_PATH = "/Users/admin/Desktop/ai_theme_app/.qwen_cache/models--Qwen--Qwen2.5-0.5B-Instruct/snapshots/7ae557604adf67be50417f59c2c2f167def9a775"
DATA_DIR = Path("/Users/admin/Desktop/ai_theme_app/theme_data_complete")
MAX_HISTORY = 5          # 增加历史事件数量
MAX_CHARS = 500          # 增加字符数

# 加载模型
print("📦 加载模型...")
tokenizer = AutoTokenizer.from_pretrained(MODEL_PATH, trust_remote_code=True)
tokenizer.pad_token = tokenizer.eos_token
model = AutoModelForCausalLM.from_pretrained(MODEL_PATH, trust_remote_code=True)
device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
model.to(device)
model.eval()
print("✅ 模型加载完成，设备：", device)

def load_theme_data(theme_id):
    """加载历史事件和详情"""
    history_file = DATA_DIR / "history" / f"{theme_id}_history.jsonl"
    detail_file = DATA_DIR / "details" / f"{theme_id}_details.jsonl"

    history_texts = []
    if history_file.exists():
        with open(history_file, 'r', encoding='utf-8') as f:
            for i, line in enumerate(f):
                if i >= MAX_HISTORY:
                    break
                item = json.loads(line)
                desc = item.get('description', '')
                if desc:
                    if len(desc) > MAX_CHARS:
                        desc = desc[:MAX_CHARS] + "..."
                    history_texts.append(desc)

    detail_text = ""
    if detail_file.exists():
        with open(detail_file, 'r', encoding='utf-8') as f:
            for line in f:
                item = json.loads(line)
                detail = item.get('detail', '')
                if detail:
                    detail = re.sub(r'<[^>]+>', ' ', detail)
                    detail = re.sub(r'\s+', ' ', detail).strip()
                    if len(detail) > MAX_CHARS * 2:
                        detail = detail[:MAX_CHARS*2] + "..."
                    detail_text = detail
                break

    return "\n\n".join(history_texts), detail_text

def extract_last_json(text):
    """提取最后一个 JSON 对象"""
    start = text.rfind('{')
    end = text.rfind('}') + 1
    if start != -1 and end > start:
        json_str = text[start:end]
        try:
            return json.loads(json_str)
        except:
            # 尝试修复单引号
            try:
                return json.loads(json_str.replace("'", '"'))
            except:
                pass
    return None

def generate_evidence(theme_id, theme_name):
    """生成证据画像，改进提示词"""
    history, detail = load_theme_data(theme_id)
    
    # 改进提示词：加入示例，明确要求输出多个关键词
    prompt = f"""你是一个专业的题材分析师。请从以下文本中提取该题材的核心关键词，输出JSON格式，包含must_have和should_have字段。

题材：{theme_name}

历史事件：
{history}

详细描述：
{detail}

要求：
- must_have：该题材最核心、最具区分度的关键词（例如核心技术、核心公司、核心政策等），至少输出5个。
- should_have：经常出现但不是绝对必要的相关词汇，至少输出3个。
- 只从文本中提取已有词汇，不要捏造。

示例输出：
{{"must_have": ["台积电", "ASML", "光刻机", "刻蚀机", "沉积设备"], "should_have": ["SIA", "资本开支", "国产替代"], "must_not": []}}

现在请输出JSON："""

    inputs = tokenizer(prompt, return_tensors="pt", truncation=True, max_length=1024).to(device)
    with torch.no_grad():
        outputs = model.generate(
            **inputs,
            max_new_tokens=512,
            do_sample=False,
            pad_token_id=tokenizer.pad_token_id,
        )
    result = tokenizer.decode(outputs[0][inputs["input_ids"].shape[1]:], skip_special_tokens=True).strip()

    data = extract_last_json(result)
    if data:
        return {
            "must_have": data.get("must_have", []),
            "should_have": data.get("should_have", []),
            "must_not": data.get("must_not", [])
        }
    else:
        print("警告：未找到有效JSON，原始输出：", result[:200])
        return None

def main():
    theme_id = "9011398"
    theme_name = "半导体设备"
    print(f"处理 {theme_id} {theme_name}")
    evidence = generate_evidence(theme_id, theme_name)
    if evidence:
        print("生成成功：", evidence)
        # 保存结果
        out_file = DATA_DIR / f"{theme_id}_evidence_profile_improved.json"
        with open(out_file, 'w', encoding='utf-8') as f:
            json.dump({
                "theme_id": theme_id,
                "theme_name": theme_name,
                "must_have": evidence["must_have"],
                "should_have": evidence["should_have"],
                "must_not": evidence["must_not"],
                "meta": {"generated_at": time.time()}
            }, f, ensure_ascii=False, indent=2)
        print(f"已保存至 {out_file}")
    else:
        print("生成失败")

if __name__ == "__main__":
    main()