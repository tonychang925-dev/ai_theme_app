-- Guard rail: market truth table must accept only tushare-derived rows.
-- Apply once in DB to enforce at storage layer.

CREATE OR REPLACE FUNCTION sps_guard_stock_daily_snapshot_truth()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    IF NEW.source_name IS NULL OR LOWER(NEW.source_name) NOT LIKE 'tushare%' THEN
        RAISE EXCEPTION
            'blocked: non-truth source_name=% is not allowed in stock_daily_snapshot (trade_date=%, stock_id=%)',
            NEW.source_name, NEW.trade_date, NEW.stock_id
            USING ERRCODE = 'check_violation';
    END IF;
    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS trg_guard_stock_daily_snapshot_truth ON stock_daily_snapshot;

CREATE TRIGGER trg_guard_stock_daily_snapshot_truth
BEFORE INSERT OR UPDATE ON stock_daily_snapshot
FOR EACH ROW
EXECUTE FUNCTION sps_guard_stock_daily_snapshot_truth();
