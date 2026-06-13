-- ============================================================
-- Form 4 Insider Tracker — Supabase schema setup
-- Paste this entire file into the Supabase SQL Editor and run.
-- Dashboard → SQL Editor → New query → paste → Run
-- ============================================================

CREATE TABLE IF NOT EXISTS public.form4_filings (
  id               BIGSERIAL PRIMARY KEY,
  record_key       TEXT UNIQUE NOT NULL,   -- dedup hash: accession|security|action|shares
  filing_date      DATE NOT NULL,
  company_name     TEXT,
  ticker           TEXT,
  insider_name     TEXT,
  insider_role     TEXT,
  security         TEXT,
  action           TEXT,                   -- Bought / Sold / Acquired / Disposed
  transaction_type TEXT,                   -- Open Market Purchase / Grant / etc.
  shares           NUMERIC,
  price_per_share  NUMERIC,
  total_value      NUMERIC,
  shares_after     NUMERIC,
  is_derivative    BOOLEAN DEFAULT FALSE,
  exercise_price   NUMERIC,
  expiration_date  DATE,
  cik              TEXT,
  accession        TEXT,
  created_at       TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS form4_date_idx    ON public.form4_filings (filing_date DESC);
CREATE INDEX IF NOT EXISTS form4_ticker_idx  ON public.form4_filings (ticker);
CREATE INDEX IF NOT EXISTS form4_action_idx  ON public.form4_filings (action);
CREATE INDEX IF NOT EXISTS form4_company_idx ON public.form4_filings (company_name);

-- Row Level Security
ALTER TABLE public.form4_filings ENABLE ROW LEVEL SECURITY;

CREATE POLICY "anyone_can_read"   ON public.form4_filings FOR SELECT USING (true);
CREATE POLICY "anyone_can_insert" ON public.form4_filings FOR INSERT WITH CHECK (true);
CREATE POLICY "anyone_can_update" ON public.form4_filings FOR UPDATE USING (true);
