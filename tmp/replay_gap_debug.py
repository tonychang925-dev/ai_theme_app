import asyncio
from datetime import date
from stock_processing_service.tests.replay._post_market_replay_runner import run_post_market_replay

async def main():
    for d, n, s in [
        (date(2026, 4, 7), 'shenjian', '002361.SZ'),
        (date(2026, 4, 15), 'liande', '605060.SH'),
    ]:
        r = await run_post_market_replay(trade_date=d, sample_name=n)
        diag = r.target_diagnostics.get(s, {})
        print('===', n, d)
        print({k: diag.get(k) for k in [
            'gap_hit', 'gap_source', 'gap_hit_mode', 'gap_level', 'gap_distance_pct',
            'support_type', 'candidate_level', 'candidate_score'
        ]})
        er = diag.get('evidence_rules') or []
        cands = [x for x in er if isinstance(x, str) and x.startswith('legacy_gap_candidate')]
        print('legacy_candidates', len(cands))
        for line in cands[:12]:
            print(line)

asyncio.run(main())
