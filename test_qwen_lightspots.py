"""Test Qwen2.5 1.5B on lightspots (SHORT text) for fact extraction."""
import json, sys, time, re
import asyncpg
import asyncio

# Simplified system prompt - much shorter than the DeepSeek one
SYSTEM_PROMPT = """从股票亮点句中提取结构化事实。只输出 JSON，不要解释。

fact_type 定义：
- product: 产品/服务名称（如：牛磺酸、智能电表、SSD）
- technology: 技术/工艺/能力（如：8层堆叠、3D制版、FlipChip封装）
- customer: 客户/合作方名称（如：金士顿、京东、华为）
- main_business: 主营业务（如：存储半导体、高端制造）
- industry_role: 行业定位（如：存储封测企业、EMS企业）
- benefit_logic: 受益逻辑（如：存储国产化、国产替代）

要求：fact_value 必须简短（2-25字），必须是原文提到的具体内容，不要输出比喻或空泛表述。每个亮点句最多提取2-3条事实。宁缺毋滥。"""


def build_prompt(name, remark, lightspots):
    lines = [f"股票：{name}", f"定位：{remark or '无'}"]
    lines.append("亮点句：")
    for i, ls in enumerate(lightspots[:12], 1):
        lines.append(f"{i}. {ls}")
    return "\n".join(lines)


async def main():
    # Connect to DB
    pool = await asyncpg.create_pool(
        user="postgres", password="postgres",
        host="localhost", port=5432, database="stock_data_test",
        min_size=1, max_size=2
    )

    # Load model
    from llama_cpp import Llama
    MODEL = "/Users/admin/Desktop/ai_theme_app/model_service/models/qwen2.5/qwen2.5-1.5b-instruct-q5_k_m.gguf"
    print("Loading model (n_ctx=2048, CPU)...")
    t0 = time.time()
    model = Llama(model_path=MODEL, n_ctx=2048, n_threads=8, n_batch=256, verbose=False)
    print(f"Loaded in {time.time()-t0:.1f}s")

    # Test stocks
    test_stocks = [
        ("000021", "深科技"),
        ("002230", "科大讯飞"),
        ("600519", "贵州茅台"),
        ("002365", "永安药业"),
    ]

    for stock_id, name in test_stocks:
        # Get lightspots
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT content FROM stock_lightspots WHERE stock_id = $1 LIMIT 15", stock_id)
            lightspots = [r['content'] for r in rows]

            # Get name + remark from stocks table
            row = await conn.fetchrow(
                "SELECT name, remark FROM stocks WHERE stock_id = $1", stock_id)
            actual_name = row['name'] if row else name
            remark = ""

        # Also get remark from detail JSON
        import os
        detail_path = f"/Users/admin/Desktop/ai_theme_app/theme_data_complete/stock_details/{stock_id}_detail.json"
        if os.path.exists(detail_path):
            with open(detail_path) as f:
                data = json.load(f)
            remark = data.get("data", {}).get("remark", "")

        prompt = build_prompt(actual_name, remark, lightspots)
        prompt_chars = len(prompt)

        print(f"\n{'='*60}")
        print(f"Stock: {stock_id} {actual_name}")
        print(f"Lightspots: {len(lightspots)}, Prompt chars: {prompt_chars}")

        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
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

            print(f"Time: {elapsed:.1f}s, Output chars: {len(content)}")
            print(f"\n--- Output ---")
            print(content[:1500])

            # Try parsing JSON
            try:
                json_match = re.search(r'\{[\s\S]*\}', content)
                if json_match:
                    parsed = json.loads(json_match.group())
                    facts = parsed.get("facts", [])
                    print(f"\nParsed {len(facts)} facts:")
                    for f in facts:
                        print(f"  [{f.get('fact_type','?')}] {f.get('fact_value','?')}")
                else:
                    print("\nNo JSON found")
            except json.JSONDecodeError as e:
                print(f"\nJSON error: {e}")

        except Exception as e:
            print(f"Error: {e}")

    await pool.close()

asyncio.run(main())
