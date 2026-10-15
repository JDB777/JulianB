/**
 * The spend meter. Julian's rule, 2026-10-14:
 *
 *   setup (characters + images)   $3 per campaign
 *   play  (the DM)                $10 per campaign
 *
 * The game asks BEFORE the call that would cross the line, so it stops as
 * close under as one call allows - "$9.93 of $10". Any player may say yes;
 * each yes moves the line up $5.
 *
 * The check lives here, in the same function that holds the API key, so a
 * stale page, a refresh or a second tab cannot get round it.
 */

import { db } from './db.js';

/* No history yet: assume a DM turn costs this much. Deliberately on the high
   side, so the first check-in of a campaign comes early rather than late. */
const FIRST_GUESS_USD = 0.05;

export async function status(campaignId, stage) {
  const { data, error } = await db().rpc('spend_status',
    { p_campaign_id: campaignId, p_stage: stage });
  if (error) throw error;
  const row = Array.isArray(data) ? data[0] : data;
  if (!row) throw new Error(`No campaign ${campaignId}`);
  return { spent: Number(row.spent), nextCheckin: Number(row.next_checkin) };
}

/* What the next call will probably cost: the dearest of the last five, so the
   estimate tracks the campaign as the story log (and the prompt) grows. */
export async function estimate(campaignId, stage) {
  const { data, error } = await db().from('spend')
    .select('usd').eq('campaign_id', campaignId).eq('stage', stage)
    .order('id', { ascending: false }).limit(5);
  if (error) throw error;
  if (!data || !data.length) return FIRST_GUESS_USD;
  return Math.max(...data.map(r => Number(r.usd)));
}

/* Where the meter stands, and - if the next call would cross the line - the
   check-in to show the table instead of making the call. */
export async function checkBefore(campaignId, stage) {
  const [s, next] = await Promise.all([status(campaignId, stage), estimate(campaignId, stage)]);
  const checkin = s.spent + next <= s.nextCheckin ? null
    : { stage, spent: round2(s.spent), limit: s.nextCheckin, after: s.nextCheckin + 5 };
  return { ...s, checkin };
}

export async function record(campaignId, stage, row) {
  const { error } = await db().from('spend').insert({
    campaign_id: campaignId, stage,
    provider: row.provider, model: row.model,
    input_tokens: row.tokens?.input ?? 0,
    cache_read: row.tokens?.cacheRead ?? 0,
    cache_write: row.tokens?.cacheWrite ?? 0,
    output_tokens: row.tokens?.output ?? 0,
    images: row.images ?? 0,
    usd: row.usd,
    note: row.note ?? null,
  });
  /* The call already happened and was paid for. Losing the record would make
     the meter read low, so this is logged loudly rather than swallowed. */
  if (error) console.error('spend NOT recorded', campaignId, stage, row.usd, error.message);
}

export async function approve(campaignId, stage) {
  const { data, error } = await db().rpc('spend_approve',
    { p_campaign_id: campaignId, p_stage: stage });
  if (error) throw error;
  return Number(data);
}

const round2 = n => Math.round(n * 100) / 100;
