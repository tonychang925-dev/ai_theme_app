"""P2-B-4: JYHF 竞价时间线采集器。

专用于 9:15-9:26 竞价窗口，以 2-3s 频率采集 D1 候选股票行情，
生成时间线数据供 AuctionTimelineExtractor 做形态识别。

使用方式:
  python -m stock_processing_service.collectors.jyhf_auction_collector \
    --trade-date 2026-05-25 --candidate-date 2026-05-22 \
    --interval 3.0 --dsn postgresql://...
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import sys
import time as _time
from datetime import date, datetime, timezone, timedelta
from pathlib import Path
from typing import Any

import httpx

logger = logging.getLogger("jyhf_auction_collector")

TZ_CN = timezone(timedelta(hours=8))

_AUCTION_START = "09:15"
_AUCTION_END = "09:26"
_DEFAULT_INTERVAL = 3.0  # 秒


class JyhfAuctionCollector:
    """9:15-9:26 竞价窗口专用采集器，高频率采集候选股票。"""

    def __init__(
        self,
        dsn: str,
        token_path: str = "/tmp/jyhf_auth_token.json",
        api_base: str = "https://app.txcfgl.com",
        interval: float = _DEFAULT_INTERVAL,
        max_concurrency: int = 15,
    ):
        self._dsn = dsn
        self._token_path = token_path
        self._api_base = api_base.rstrip("/")
        self._interval = interval
        self._max_concurrency = max_concurrency
        self._pool = None

        self.stats = {
            "started_at": None, "finished_at": None,
            "candidates": 0, "points_collected": 0,
            "stocks_ok": 0, "stocks_fail": 0,
            "rounds": 0,
        }

    async def _get_pool(self):
        if self._pool is None:
            import asyncpg
            self._pool = await asyncpg.create_pool(self._dsn, min_size=1, max_size=3)
        return self._pool

    def _load_token(self) -> str:
        data = json.loads(Path(self._token_path).read_text())
        return data["token"]

    def _headers(self) -> dict:
        return {"Authorization": f"Bearer {self._load_token()}"}

    def _now_cst(self) -> datetime:
        return datetime.now(TZ_CN)

    def _in_auction_window(self) -> bool:
        """是否在竞价窗口内。"""
        now = self._now_cst()
        t = now.strftime("%H:%M")
        return _AUCTION_START <= t < _AUCTION_END

    # ── 候选加载 ──

    async def load_candidates(self, candidate_date: date) -> list[dict[str, Any]]:
        pool = await self._get_pool()
        rows = await pool.fetch(
            """SELECT stock_id, stock_name, subject_key, theme_name, candidate_type, weak_type
               FROM weak_to_strong_candidate_pool
               WHERE trade_date = $1
               ORDER BY candidate_score DESC""",
            candidate_date,
        )
        candidates = [{
            "stock_id": r["stock_id"],
            "stock_name": r["stock_name"],
            "subject_key": r["subject_key"],
            "theme_name": r["theme_name"],
            "candidate_type": r["candidate_type"],
            "weak_type": r["weak_type"],
        } for r in rows]
        self.stats["candidates"] = len(candidates)
        logger.info("Loaded %d D1 candidates from %s", len(candidates), candidate_date)
        return candidates

    # ── 采集 ──

    async def run(self, trade_date: date, candidate_date: date) -> dict:
        """主流程：等到竞价窗口 → 循环采集 → 写入 DB。"""
        self.stats["started_at"] = self._now_cst().isoformat()
        logger.info("Auction collector starting (trade=%s candidates=%s interval=%.1fs)",
                     trade_date, candidate_date, self._interval)

        # 加载候选
        candidates = await self.load_candidates(candidate_date)
        if not candidates:
            logger.warning("No candidates for %s", candidate_date)
            return self.stats

        # 等待竞价窗口
        if not self._in_auction_window():
            logger.info("Waiting for auction window (%s-%s)...", _AUCTION_START, _AUCTION_END)
            while not self._in_auction_window():
                await asyncio.sleep(5)
                # 超时保护：超过 9:30 退出
                now = self._now_cst()
                if now.hour >= 10 or (now.hour == 9 and now.minute >= 30):
                    logger.warning("Auction window passed (%s), exiting", now.strftime("%H:%M"))
                    return self.stats

        # 采集循环
        pool = await self._get_pool()
        sem = asyncio.Semaphore(self._max_concurrency)

        async def _fetch_one(c: dict) -> dict | None:
            sid = c["stock_id"].replace(".SZ", "").replace(".SH", "")
            async with sem:
                try:
                    async with httpx.AsyncClient(timeout=5.0, trust_env=False) as client:
                        r = await client.get(
                            f"{self._api_base}/api/app/stock/realtime/{sid}",
                            headers=self._headers(),
                        )
                    data = r.json().get("data", {})
                    if data and data.get("current"):
                        return {
                            "stock_id": c["stock_id"],
                            "current": float(data["current"]),
                            "pctChg": float(data.get("pctChg", 0)),
                            "amount": float(data.get("amount", 0)),
                            "vol": float(data.get("vol", 0)),
                            "open": float(data.get("open", 0)),
                            "time": str(data.get("time", "")),
                        }
                except Exception as exc:
                    logger.debug("Fetch %s failed: %s", sid, exc)
                return None

        logger.info("Starting auction loop (interval=%.1fs, concurrency=%d, candidates=%d)",
                     self._interval, self._max_concurrency, len(candidates))

        while self._in_auction_window():
            round_start = _time.time()
            tasks = [_fetch_one(c) for c in candidates]
            results = await asyncio.gather(*tasks)

            # 批量写入
            rows_to_insert = []
            now = self._now_cst()
            ok = 0
            for r in results:
                if r:
                    rows_to_insert.append((
                        trade_date, now,
                        r["stock_id"], r["current"], r["pctChg"],
                        r["amount"], r["vol"], r["open"], r["time"],
                    ))
                    ok += 1
                else:
                    self.stats["stocks_fail"] += 1

            if rows_to_insert:
                await pool.executemany(
                    """INSERT INTO jyhf_stock_quote_snapshot
                       (trade_date, ts, stock_id, current, pct_chg, amount, vol, open, source_endpoint)
                       VALUES ($1, $2, $3, $4, $5, $6, $7, $8, 'jyhf_auction')""",
                    [(td, ts, sid, curr, pct, amt, vol, op) for td, ts, sid, curr, pct, amt, vol, op in rows_to_insert],
                )

            self.stats["points_collected"] += len(rows_to_insert)
            self.stats["stocks_ok"] += ok - self.stats.get("_total_fail", 0)
            self.stats["rounds"] += 1

            elapsed = _time.time() - round_start
            sleep_for = max(0.1, self._interval - elapsed)
            logger.debug("Round %d: %d points in %.1fs, sleep %.1fs",
                         self.stats["rounds"], len(rows_to_insert), elapsed, sleep_for)
            await asyncio.sleep(sleep_for)

        self.stats["finished_at"] = self._now_cst().isoformat()
        logger.info("Auction collector finished: %d rounds, %d points",
                     self.stats["rounds"], self.stats["points_collected"])

        # ── P2-B-4: 盘后自动构建 timeline-enhanced snapshots 并入库 ──
        await self._build_and_persist_snapshots(trade_date, candidates)

        return self.stats

    async def _build_and_persist_snapshots(
        self, trade_date: date, candidates: list[dict[str, Any]],
    ) -> None:
        """用时间线数据构建 timeline-enhanced snapshot，写入 pre_market_auction_snapshot。"""
        try:
            from stock_processing_service.integrations.jyhf_market.auction_timeline import (
                JyhfAuctionTimelineExtractor,
            )
            extractor = JyhfAuctionTimelineExtractor(self._dsn)
            snapshots = await extractor.build_timeline_snapshots(
                trade_date=trade_date,
                candidate_trade_date=trade_date,
                candidates=candidates,
            )
            if not snapshots:
                logger.warning("No timeline snapshots produced")
                return

            pool = await self._get_pool()
            written = 0
            for snap in snapshots:
                await pool.execute(
                    """INSERT INTO pre_market_auction_snapshot
                       (trade_date, stock_id, stock_name, subject_key, theme_name, role_label,
                        window_start_time, window_end_time, last_minute_start_time, last_30s_start_time,
                        auction_open_price, pre_close, auction_open_pct, auction_volume, auction_amount,
                        last_minute_amount, last_minute_ratio, prev_day_max_intraday_amount, carry_ratio,
                        price_path_stability_score, is_red_zone, has_end_spike, has_end_drop,
                        shape_features, source_type, source_trace_id, source_trace,
                        source_version, rule_version)
                       VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15,$16,$17,$18,$19,
                               $20,$21,$22,$23,$24::jsonb,$25,$26,$27::jsonb,$28,$29)
                       ON CONFLICT (trade_date, stock_id) DO UPDATE SET
                        auction_open_price=EXCLUDED.auction_open_price,
                        auction_open_pct=EXCLUDED.auction_open_pct,
                        auction_amount=EXCLUDED.auction_amount,
                        carry_ratio=EXCLUDED.carry_ratio,
                        price_path_stability_score=EXCLUDED.price_path_stability_score,
                        shape_features=EXCLUDED.shape_features,
                        last_minute_ratio=EXCLUDED.last_minute_ratio,
                        has_end_drop=EXCLUDED.has_end_drop,
                        has_end_spike=EXCLUDED.has_end_spike,
                        source_version=EXCLUDED.source_version,
                        rule_version=EXCLUDED.rule_version,
                        updated_at=NOW()""",
                    snap["trade_date"], snap["stock_id"], snap["stock_name"],
                    snap["subject_key"], snap["theme_name"], snap["role_label"],
                    snap["window_start_time"], snap["window_end_time"],
                    snap["last_minute_start_time"], snap["last_30s_start_time"],
                    snap["auction_open_price"], snap["pre_close"],
                    snap["auction_open_pct"], snap["auction_volume"], snap["auction_amount"],
                    snap["last_minute_amount"], snap["last_minute_ratio"],
                    snap["prev_day_max_intraday_amount"], snap["carry_ratio"],
                    snap["price_path_stability_score"], snap["is_red_zone"],
                    snap["has_end_spike"], snap["has_end_drop"],
                    json.dumps(snap["shape_features"]),
                    snap["source_type"], snap["source_trace_id"],
                    json.dumps(snap["source_trace"]),
                    snap["source_version"], snap["rule_version"],
                )
                written += 1

            self.stats["snapshots_written"] = written
            logger.info("Timeline snapshots persisted: %d/%d", written, len(snapshots))
            await extractor.close()
        except Exception as exc:
            logger.exception("Timeline snapshot build failed: %s", exc)
            self.stats["last_error"] = str(exc)

    async def close(self):
        if self._pool:
            await self._pool.close()
            self._pool = None


# ── CLI ──

async def _main():
    import argparse
    p = argparse.ArgumentParser(description="JYHF Auction Timeline Collector")
    p.add_argument("--trade-date", required=True, help="竞价日期 YYYY-MM-DD")
    p.add_argument("--candidate-date", required=True, help="D1候选日期 YYYY-MM-DD")
    p.add_argument("--interval", type=float, default=_DEFAULT_INTERVAL, help="采集间隔(秒)")
    p.add_argument("--concurrency", type=int, default=15)
    p.add_argument("--dsn", default=os.getenv("DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/stock_data_test"))
    p.add_argument("--token-path", default=os.getenv("JYHF_AUTH_TOKEN_PATH", "/tmp/jyhf_auth_token.json"))
    args = p.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s", stream=sys.stderr)

    collector = JyhfAuctionCollector(
        dsn=args.dsn, token_path=args.token_path,
        interval=args.interval, max_concurrency=args.concurrency,
    )
    try:
        stats = await collector.run(
            trade_date=date.fromisoformat(args.trade_date),
            candidate_date=date.fromisoformat(args.candidate_date),
        )
        print(json.dumps(stats, ensure_ascii=False, indent=2))
    finally:
        await collector.close()


if __name__ == "__main__":
    asyncio.run(_main())
