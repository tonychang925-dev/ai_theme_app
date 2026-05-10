"""Evaluate Qwen2.5 1.5B for stock fact extraction task."""
import json
import sys
import time
import re

# --- Load sample data ---
DETAIL_DIR = "/Users/admin/Desktop/ai_theme_app/theme_data_complete/stock_details"

def strip_html(html):
    html = re.sub(r'<br\s*/?>', '\n', html)
    html = re.sub(r'</p>', '\n', html)
    html = re.sub(r'<[^>]+>', '', html)
    html = re.sub(r'\n{3,}', '\n\n', html)
    return html.strip()

# Pick 3 diverse stocks
test_stocks = ["000021", "002230", "600519"]  # 深科技, 科大讯飞, 贵州茅台
samples = []
for sid in test_stocks:
    with open(f"{DETAIL_DIR}/{sid}_detail.json") as f:
        data = json.load(f)
    detail_text = strip_html(data.get("data", {}).get("detail", ""))
    remark = data.get("data", {}).get("remark", "")
    name = data.get("data", {}).get("name", "")
    lightspots = [s.get("content", "") for s in data.get("data", {}).get("stockLightspots", [])[:10]]
    samples.append({
        "stock_id": sid, "name": name, "remark": remark,
        "detail_text": detail_text[:3000],  # truncated for testing
        "lightspots": lightspots
    })

# --- Simplified prompt (shorter for 1.5B model) ---
SYSTEM_PROMPT = """你是一个股票事实抽取器。从公司详情文本中提取结构化事实。

允许的 fact_type：
- main_business: 主营业务板块（如：存储半导体、高端制造）
- industry_role: 产业链角色/行业定位（如：存储封测企业、EMS企业）
- product: 产品/服务/解决方案（如：智能电表、SSD）
- technology: 关键技术/工艺/能力（如：8层堆叠、FlipChip封装）
- customer: 客户/合作对象名称（如：金士顿科技）
- benefit_logic: 受益逻辑（如：存储国产化、国产替代）

规则：
1. fact_value 必须是短语，不要完整句子
2. evidence_span 是原文中的支撑片段，要简短
3. 并列项必须拆成多条
4. 不要编造，只提取原文明确表达的内容
5. 宁缺毋滥

输出纯 JSON，格式：
{"facts": [{"fact_type": "product", "fact_value": "DRAM封装测试", "evidence_span": "从事高端存储芯片封装与测试"}]}"""

def build_prompt(sample):
    lines = [f"股票代码：{sample['stock_id']}",
             f"股票名称：{sample['name']}",
             f"一句话定位：{sample['remark']}"]
    if sample['lightspots']:
        lines.append("亮点句：")
        for ls in sample['lightspots'][:5]:
            lines.append(f"- {ls}")
    lines.append(f"\n公司详情：\n{sample['detail_text']}")
    return "\n".join(lines)

# --- Load model ---
from llama_cpp import Llama

MODEL_PATH = "/Users/admin/Desktop/ai_theme_app/model_service/models/qwen2.5/qwen2.5-1.5b-instruct-q5_k_m.gguf"

print("=" * 60)
print("Loading Qwen2.5 1.5B (Q5_K_M) - CPU only, n_ctx=4096")
print("=" * 60)

t0 = time.time()
model = Llama(
    model_path=MODEL_PATH,
    n_ctx=4096,
    n_threads=8,
    n_batch=256,
    verbose=False,
)
print(f"Model loaded in {time.time()-t0:.1f}s")

# --- Test each stock ---
for i, sample in enumerate(samples):
    print(f"\n{'='*60}")
    print(f"Test {i+1}: {sample['stock_id']} {sample['name']}")
    print(f"Detail text length: {len(sample['detail_text'])} chars")
    print(f"{'='*60}")

    user_prompt = build_prompt(sample)
    prompt_tokens = len(user_prompt) // 2  # rough estimate for Chinese

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user_prompt},
    ]

    t0 = time.time()
    try:
        response = model.create_chat_completion(
            messages=messages,
            temperature=0.1,
            top_p=0.9,
            max_tokens=1024,
            stop=["</s>", "<|im_end|>"],
        )
        elapsed = time.time() - t0
        content = response["choices"][0]["message"]["content"]
        print(f"\nGeneration time: {elapsed:.1f}s")
        print(f"Prompt ~{prompt_tokens} tokens, Output ~{len(content)//2} tokens")
        print(f"\n--- Raw LLM Output ---")
        print(content)

        # Try to parse JSON
        try:
            # Extract JSON block
            json_match = re.search(r'\{[\s\S]*\}', content)
            if json_match:
                parsed = json.loads(json_match.group())
                facts = parsed.get("facts", [])
                print(f"\n--- Parsed: {len(facts)} facts ---")
                for f in facts:
                    print(f"  [{f.get('fact_type','?')}] {f.get('fact_value','?')}")
                    print(f"    evidence: {f.get('evidence_span','?')[:80]}")
            else:
                print("\nERROR: No JSON found in output")
        except json.JSONDecodeError as e:
            print(f"\nERROR: JSON parse failed: {e}")

    except Exception as e:
        print(f"\nERROR: {e}")

print("\n" + "=" * 60)
print("Evaluation complete")
