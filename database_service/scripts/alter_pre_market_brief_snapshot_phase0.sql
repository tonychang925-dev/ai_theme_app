ALTER TABLE pre_market_brief_snapshot
ADD COLUMN IF NOT EXISTS status varchar(20) NOT NULL DEFAULT 'draft',
ADD COLUMN IF NOT EXISTS generated_at timestamptz,
ADD COLUMN IF NOT EXISTS finalized_at timestamptz,
ADD COLUMN IF NOT EXISTS updated_at timestamptz NOT NULL DEFAULT now();

