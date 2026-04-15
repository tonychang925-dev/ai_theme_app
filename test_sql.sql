WITH stock_base AS (
    SELECT DISTINCT ON (split_part(s.stock_id, '.', 1), s.subject_key)
        split_part(s.stock_id, '.', 1) AS stock_code,
        s.stock_id,
        s.stock_name,
        s.subject_key,
        COALESCE(NULLIF(m.theme_name, ''), NULLIF(c.theme_name, ''), s.subject_key) AS theme_name,
        s.rank_order,
        s.pct_chg,
        s.limit_up,
        s.is_leader,
        c.primary_cycle_stage,
        c.action_bias,
        c.is_divergence,
        c.is_rebound,
        c.is_fermentation,
        c.is_fade,
        m.is_main_theme
    FROM subject_stock_daily_snapshot s
    LEFT JOIN theme_mainline_judgement m
      ON m.trade_date = s.trade_date
     AND m.subject_key = s.subject_key
    LEFT JOIN theme_cycle_judgement c
      ON c.trade_date = s.trade_date
     AND c.subject_key = s.subject_key
    WHERE s.trade_date = '2026-04-07'::date
      AND (s.stock_id = '002361' OR s.stock_id = '002361.SZ')
)
SELECT
    b.*,
    (
        SELECT COUNT(*)
        FROM subject_stock_daily_snapshot h
        WHERE split_part(h.stock_id, '.', 1) = b.stock_code
          AND h.trade_date <= '2026-04-07'::date
          AND h.trade_date > ('2026-04-07'::date - INTERVAL '30 days')
          AND COALESCE(h.limit_up, FALSE) = TRUE
    ) AS recent_limit_up_count,
    (
        SELECT h.pct_chg
        FROM subject_stock_daily_snapshot h
        WHERE split_part(h.stock_id, '.', 1) = b.stock_code
          AND h.trade_date < '2026-04-07'::date
        ORDER BY h.trade_date DESC
        LIMIT 1
    ) AS prev_day_pct_chg,
    (
        SELECT h.limit_up
        FROM subject_stock_daily_snapshot h
        WHERE split_part(h.stock_id, '.', 1) = b.stock_code
          AND h.trade_date < '2026-04-07'::date
        ORDER BY h.trade_date DESC
        LIMIT 1
    ) AS prev_day_limit_up
FROM stock_base b;