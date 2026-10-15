/**
 * The save file. The page keeps the game in memory while you play and writes
 * it here after every turn, so closing the browser loses nothing.
 *
 *   GET  /api/save?campaign=ID                  -> { scene, state } or { state: null }
 *   POST /api/save { campaign, scene, state }   -> { ok: true }
 *
 * Phase 1 keeps one open encounter row per campaign: the whole table as it
 * stands, fight or no fight. Closing fights into history comes later.
 */

import { db, campaignId } from './_lib/db.js';

const MAX_STATE_BYTES = 1_000_000;   // a whole fight is ~50 KB; this is a sanity bound
const today = () => new Date().toISOString().slice(0, 10);

export default async function handler(req, res) {
  try {
    if (req.method === 'GET') {
      const id = campaignId(req.query?.campaign);
      if (!id) return res.status(400).json({ error: 'Which campaign?' });
      const { data, error } = await db().from('encounters')
        .select('scene, state, updated_at')
        .eq('campaign_id', id).eq('is_open', true).maybeSingle();
      if (error) throw error;
      return res.status(200).json(data || { state: null });
    }

    if (req.method === 'POST') {
      const id = campaignId(req.body?.campaign);
      const state = req.body?.state;
      if (!id) return res.status(400).json({ error: 'Which campaign?' });
      if (!state || typeof state !== 'object') return res.status(400).json({ error: 'Nothing to save.' });
      if (JSON.stringify(state).length > MAX_STATE_BYTES) return res.status(413).json({ error: 'Save too large.' });
      const scene = req.body?.scene ? String(req.body.scene).slice(0, 120) : null;

      const { data: updated, error: e1 } = await db().from('encounters')
        .update({ scene, state })
        .eq('campaign_id', id).eq('is_open', true)
        .select('id');
      if (e1) throw e1;
      if (!updated.length) {
        const { error: e2 } = await db().from('encounters')
          .insert({ campaign_id: id, scene, state });
        if (e2) throw e2;
      }
      await db().from('campaigns').update({ last_played: today() }).eq('id', id);
      return res.status(200).json({ ok: true });
    }

    return res.status(405).json({ error: 'Use GET or POST.' });
  } catch (err) {
    console.error('save error', err?.message);
    return res.status(500).json({ error: 'Could not reach the save file.' });
  }
}
