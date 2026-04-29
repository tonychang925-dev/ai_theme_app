#!/usr/bin/env bash
set -euo pipefail

DB_URL="${DB_URL:-postgresql://postgres:zxbzj~925@localhost/stock_data_test}"
TRADE_DATES=(2026-04-22 2026-04-23)
OUT_DIR="${OUT_DIR:-tmp/regression_vikay_20260422_20260423}"
mkdir -p "$OUT_DIR"

run_py() {
  POSTGRES_DATABASE=stock_data_test .venv/bin/python "$@"
}

echo "[STEP] Build Layer B v2 judgements"
for d in "${TRADE_DATES[@]}"; do
  run_py stock_service/scripts/build_theme_cycle_judgement_v2.py --trade-date "$d" --top-k 0 > "$OUT_DIR/build_v2_${d}.log" 2>&1
  echo "  - built v2 $d"
done

echo "[STEP] Build Layer C weak_to_strong candidates"
for d in "${TRADE_DATES[@]}"; do
  run_py scripts/build_weak_to_strong_candidate_pool.py --trade-date "$d" --max-candidates 10 --skip-legacy-entrypoint-gate > "$OUT_DIR/build_c_${d}.log" 2>&1
  echo "  - built C $d"
done

echo "[STEP] Export A/B/C snapshots"
psql "$DB_URL" -v ON_ERROR_STOP=1 -f - > "$OUT_DIR/abc_snapshot.tsv" <<'SQL'
WITH d AS (
  SELECT d::date trade_date
  FROM (VALUES ('2026-04-22'),('2026-04-23')) x(d)
),
sk AS (
  SELECT unnest(ARRAY[9014701,9027590,9035101,9051960]::bigint[]) AS subject_key
),
a AS (
  SELECT source_trade_date AS trade_date, subject_key::bigint subject_key, identity_status, is_main_theme
  FROM theme_mainline_identity_registry
  WHERE source_trade_date IN ('2026-04-22','2026-04-23')
),
b AS (
  SELECT trade_date, subject_key::bigint subject_key, final_cycle_state, fade_confirmed, final_mainline_alive, mainline_strength_score
  FROM theme_cycle_judgement_v2
  WHERE trade_date IN ('2026-04-22','2026-04-23')
),
c AS (
  SELECT trade_date, stock_id, subject_key::bigint subject_key, pool_entry_type, candidate_score
  FROM weak_to_strong_candidate_pool
  WHERE trade_date IN ('2026-04-22','2026-04-23')
    AND stock_id='600152.SH'
)
SELECT d.trade_date, sk.subject_key,
       COALESCE(a.identity_status,'') AS a_identity_status,
       COALESCE(a.is_main_theme::text,'') AS a_is_main,
       COALESCE(b.final_cycle_state,'') AS b_cycle_state,
       COALESCE(b.fade_confirmed::text,'') AS b_fade_confirmed,
       COALESCE(b.final_mainline_alive::text,'') AS b_alive,
       COALESCE(b.mainline_strength_score::text,'') AS b_strength,
       COALESCE(c.stock_id,'') AS c_stock_id,
       COALESCE(c.pool_entry_type,'') AS c_pool_entry_type,
       COALESCE(c.candidate_score::text,'') AS c_candidate_score
FROM d
CROSS JOIN sk
LEFT JOIN a ON a.trade_date=d.trade_date AND a.subject_key=sk.subject_key
LEFT JOIN b ON b.trade_date=d.trade_date AND b.subject_key=sk.subject_key
LEFT JOIN c ON c.trade_date=d.trade_date AND c.subject_key=sk.subject_key
ORDER BY d.trade_date, sk.subject_key;
SQL

echo "[STEP] Export candidate detail for 600152.SH"
psql "$DB_URL" -v ON_ERROR_STOP=1 -f - > "$OUT_DIR/candidate_600152.tsv" <<'SQL'
SELECT trade_date, stock_id, stock_name, subject_key, theme_name,
       pool_entry_type, candidate_score, candidate_type, weak_type,
       weak_intensity, cycle_state, mainline_strength_score,
       support_type, support_level, support_strength,
       fade_watch, fade_confirmed
FROM weak_to_strong_candidate_pool
WHERE stock_id='600152.SH'
  AND trade_date IN ('2026-04-22','2026-04-23')
ORDER BY trade_date;
SQL

echo "[DONE] Outputs in $OUT_DIR"
