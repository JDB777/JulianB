/**
 * The server's connection to Supabase. Uses the SECRET key, which bypasses
 * row level security - it lives only in Vercel's environment and never
 * reaches the browser. The browser never talks to the database directly.
 */

import { createClient } from '@supabase/supabase-js';

let client = null;

export function db() {
  if (client) return client;
  const url = process.env.SUPABASE_URL;
  const key = process.env.SUPABASE_SECRET_KEY;
  if (!url || !key) throw new Error('The database is not configured on the server.');
  client = createClient(url, key, { auth: { persistSession: false } });
  return client;
}

/* Every route takes a campaign id from the browser; make sure it is one. */
export function campaignId(raw) {
  const n = Number(raw);
  return Number.isInteger(n) && n > 0 ? n : null;
}
