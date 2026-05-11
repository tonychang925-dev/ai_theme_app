"""
test_stock_recommend_live.py — 精简版全链路验证（2次LLM调用）
"""
import asyncio, asyncpg, os, sys, json, re, time
from collections import defaultdict
import aiohttp

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

class DeepSeekClient:
    def __init__(self):
        self.api_key = os.getenv("DEEPSEEK_API_KEY")
        self.base_url = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
        if not self.api_key:
            raise RuntimeError("DEEPSEEK_API_KEY 未设置")

    async def chat_completion(self, messages, temperature=0.1, max_tokens=512):
        headers = {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}
        payload = {"model": "deepseek-chat", "messages": messages,
                   "temperature": temperature, "max_tokens": max_tokens, "stream": False}
        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{self.base_url}/v1/chat/completions", headers=headers,
                json=payload, timeout=aiohttp.ClientTimeout(total=60),
            ) as resp:
                if resp.status != 200:
                    raise RuntimeError(f"API error {resp.status}: {(await resp.text())[:300]}")
                data = await resp.json()
                return {"content": data["choices"][0]["message"]["content"],
                        "usage": data.get("usage", {})}

EXAMPLE = {
    "text": (
        "【研选】公司多项AI算力光纤光缆产品取得突破性进展，"
        "并已完成800G高速光模块批量出货；"
        "光纤行业进入量价齐升的历史大周期，"
        "公司一季度实现业绩与盈利能力显著改善"
    ),
}


async def main():
    print("=" * 70)
    print("  StockRecommendService — 精简全链路 (最多2次LLM)")
    print("=" * 70)

    db = await asyncpg.connect(
        user="postgres", password="postgres", host="localhost", port=5432,
        database="stock_data_test",
    )
    llm = DeepSeekClient()

    from theme_service.services.stock_recommend_service import StockRecommendService
    svc = StockRecommendService(llm_client=llm)

    # ──── Step 1 ────
    print(f"\n📋 Step 1/5: LLM 结构化提取 (1次调用)")
    t0 = time.time()
    extracted = await svc._extract_research(EXAMPLE["text"])
    print(f"   ⏱️ {time.time()-t0:.1f}s → themes={extracted.get('themes')}, "
          f"products={extracted.get('key_products')}")

    # ──── Step 2 ────
    print(f"\n🔍 Step 2/5: 匹配 theme_gate_profile")
    terms = extracted.get("themes", []) + extracted.get("key_products", [])
    matched = await svc._match_themes(terms)
    for t in matched:
        print(f"   [{t['subject_key']}] {t['concept']:22s} score={t['match_score']}")

    # ──── Step 3+4 ────
    print(f"\n📈 Step 3/5: 查表 theme_stock_map + 收集证据")
    stocks = await svc._fetch_and_enrich(matched)
    leaders = sum(1 for s in stocks.values() if s.get("relation_type") == "leader")
    cores = sum(1 for s in stocks.values() if s.get("relation_type") == "core")
    has_ls = sum(1 for s in stocks.values() if s.get("lightspots"))
    print(f"   {len(stocks)}只 (leader={leaders} core={cores}) | "
          f"有lightspots:{has_ls}")

    # ──── Step 5 ────
    print(f"\n⚖️  Step 4/5: Gate 评分")
    for s in stocks.values():
        s["gate_score"] = svc._gate_score(terms, extracted, s)
    sorted_stocks = sorted(stocks.values(), key=lambda s: s["gate_score"], reverse=True)
    top = sorted_stocks[:15]
    print(f"   Top 5 (纯规则):")
    for s in top[:5]:
        print(f"     {s['stock_id']} {s['stock_name']:8s} [{s['relation_type']}] "
              f"gate={s['gate_score']:.0f} remark={s.get('remark','')[:60]}")

    # ──── Step 6 (可选) ────
    print(f"\n🤖 Step 5/5: 1次 LLM 批量核查 top {min(len(stocks), 20)}")
    t0 = time.time()
    result = await svc.recommend_from_text(
        EXAMPLE["text"], max_candidates=7, use_llm_verify=True,
    )
    print(f"   ⏱️ 总耗时 {time.time()-t0:.1f}s (含LLM×{result.audit.get('llm_calls',2)})")

    # ──── 输出 ────
    print(f"\n{'='*70}")
    print(f"🎯 精选荐股 ({len(result.recommendations)}只)")
    print(f"{'='*70}")

    boards = defaultdict(int)
    for s in result.recommendations:
        sid = s["stock_id"]
        if sid.startswith("300") or sid.startswith("301"): b = "创业板"
        elif sid.startswith("688"): b = "科创板"
        else: b = "主板"
        boards[b] += 1
    print(f"   板块: {' + '.join(f'{v}{k}' for k,v in boards.items())}")
    print(f"   LLM调用: {result.audit['llm_calls']}次")
    print()

    for i, s in enumerate(result.recommendations, 1):
        sid = s["stock_id"]
        board = "创业板" if sid.startswith("30") else ("科创板" if sid.startswith("688") else "主板")
        print(f"   {i}. [{board}] {s['stock_id']} {s['stock_name']}")
        print(f"      {s.get('llm_verdict','')} gate={s.get('gate_score',0):.0f}")
        print(f"      {s.get('llm_reason','')}")
        if s.get("remark"):
            print(f"      📍 {s['remark'][:120]}")
        for ls in s.get("lightspots", [])[:2]:
            print(f"      💡 {ls[:100]}")
        print()

    await db.close()
    print("✅ 完成")


if __name__ == "__main__":
    asyncio.run(main())
