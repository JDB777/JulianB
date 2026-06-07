-- ============================================================
-- WordFall — Supabase schema setup
-- Paste this entire file into the Supabase SQL Editor and run.
-- Dashboard → SQL Editor → New query → paste → Run
-- ============================================================

-- Scores / leaderboard table
CREATE TABLE IF NOT EXISTS public.scores (
  id            UUID        DEFAULT gen_random_uuid() PRIMARY KEY,
  player_name   TEXT        NOT NULL,
  score         INTEGER     NOT NULL DEFAULT 0,
  longest_word  TEXT,
  words_spelled INTEGER     NOT NULL DEFAULT 0,
  created_at    TIMESTAMPTZ DEFAULT NOW()
);

-- Fast leaderboard queries (top scores)
CREATE INDEX IF NOT EXISTS scores_by_score ON public.scores (score DESC);

-- Row Level Security — anyone can read and submit; nobody can edit or delete
ALTER TABLE public.scores ENABLE ROW LEVEL SECURITY;

CREATE POLICY "anyone_can_read" ON public.scores
  FOR SELECT USING (true);

CREATE POLICY "anyone_can_insert" ON public.scores
  FOR INSERT WITH CHECK (
    length(player_name) BETWEEN 1 AND 12
    AND score >= 0
    AND words_spelled >= 0
  );

-- Optional: keep only top 500 scores to avoid unbounded growth
-- (run manually or add as a scheduled function later)
-- DELETE FROM public.scores
--   WHERE id NOT IN (
--     SELECT id FROM public.scores ORDER BY score DESC LIMIT 500
--   );
