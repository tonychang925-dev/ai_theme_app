"""P1-F-0 P0 验证: one-stock-daily → normalize → DB 写入 最小闭环.

用法:
  PYTHONPATH=/Users/admin/Desktop/ai_theme_app \
  python scripts/check_jyhf_stock_daily_p0.py

验证 3 只股票: 确保 API 返回结构稳定, normalizer 正常, DB 幂等写入.
"""
from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

# 确保项目根在 sys.path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from stock_processing_service.integrations.jyhf_market.api_client import JyhfMarketApiClient
from stock_processing_service.integrations.jyhf_market.normalizers import normalize_stock_daily_bars
from stock_processing_service.sinks.jyhf_market_db_sink import JyhfMarketDbSink

# ── 测试股票 ──
TEST_STOCKS = [
    ("002795.SZ", "002795"),   # 永和智控
    ("605299.SH", "605299"),   # 舒华体育
    ("600000.SH", "600000"),   # 浦发银行
]

DSN = "postgresql://postgres:postgres@localhost:5432/stock_data_test"


async def main():
    # 直接从文件加载 token，跳过 SSL 校验（局域网环境可用）
    token_data = json.loads(Path("/tmp/jyhf_auth_token.json").read_text())
    direct_token = token_data["token"]

    # 用最小化 token provider（不做网络校验）
    class _DirectToken:
        def get_token(self) -> str: return direct_token
        def is_token_valid(self) -> bool: return True
        def force_refresh(self) -> bool: return True

    api = JyhfMarketApiClient(_DirectToken(), "https://app.txcfgl.com", timeout=15.0, max_retries=1)
    sink = JyhfMarketDbSink(DSN)

    all_ok = True
    for sys_id, api_id in TEST_STOCKS:
        print(f"\n── {sys_id} (api={api_id}) ──")
        try:
            raw = await api.get_stock_daily(api_id, days=5)
            bars = normalize_stock_daily_bars(raw, stock_id=sys_id, api_stock_id=api_id, days=5)
            if not bars:
                print(f"  ❌ 0 bars after normalize")
                all_ok = False
                continue

            # 打印最近 3 条
            for b in bars[-3:]:
                print(f"  {b.trade_date} | O={b.open} H={b.high} L={b.low} C={b.close} chg={b.pct_chg}% vol={b.vol}")

            written = await sink.write_stock_daily_bars(bars)
            print(f"  ✅ {len(bars)} bars normalized, {written} written to DB (upsert)")
        except Exception as exc:
            print(f"  ❌ FAILED: {exc}")
            all_ok = False

    # ── DB 验证 ──
    print("\n── DB 验证 ──")
    import asyncpg
    pool = await asyncpg.create_pool(DSN, min_size=1, max_size=1)
    row = await pool.fetchrow(
        "SELECT COUNT(*) AS cnt, MAX(trade_date) AS latest FROM jyhf_stock_daily_bar"
    )
    print(f"  total rows: {row['cnt']}, latest trade_date: {row['latest']}")
    for sys_id, _ in TEST_STOCKS:
        row2 = await pool.fetchrow(
            "SELECT COUNT(*) AS cnt, MAX(trade_date) AS latest FROM jyhf_stock_daily_bar WHERE stock_id=$1",
            sys_id,
        )
        print(f"  {sys_id}: {row2['cnt']} bars, latest={row2['latest']}")
    await pool.close()

    await sink.close()
    if all_ok:
        print("\n✅ P0 验证全部通过")
    else:
        print("\n❌ 存在失败项")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
