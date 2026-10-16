/**
 * Campaigns: list the ones you can resume, open one, or start a new one.
 *
 *   GET  /api/campaign            -> { campaigns: [{ id, name, status, last_played }] }
 *   GET  /api/campaign?id=N       -> { id, name, roll }
 *   POST /api/campaign { name }   -> { id, name, roll }
 *
 * Every campaign carries its own copy of the roll (the job, the lie, the
 * truth, the places...). A campaign made before the roll existed is given the
 * current one the first time it is opened.
 */

import { db, campaignId } from './_lib/db.js';
import { DEFAULT_ROLL } from './_lib/roll.js';

const today = () => new Date().toISOString().slice(0, 10);

export default async function handler(req, res) {
  try {
    if (req.method === 'GET' && req.query?.id !== undefined) {
      const id = campaignId(req.query.id);
      if (!id) return res.status(400).json({ error: 'Which campaign?' });
      const { data, error } = await db().from('campaigns')
        .select('id, name, roll').eq('id', id).maybeSingle();
      if (error) throw error;
      if (!data) return res.status(404).json({ error: 'No such campaign.' });
      if (!data.roll) {
        const { error: e2 } = await db().from('campaigns')
          .update({ roll: DEFAULT_ROLL }).eq('id', id);
        if (e2) throw e2;
        data.roll = DEFAULT_ROLL;
      }
      return res.status(200).json(data);
    }

    if (req.method === 'GET') {
      const { data, error } = await db().from('campaigns')
        .select('id, name, status, last_played, updated_at')
        .neq('status', 'ended')
        .order('updated_at', { ascending: false })
        .limit(20);
      if (error) throw error;
      return res.status(200).json({ campaigns: data });
    }

    if (req.method === 'POST') {
      const name = String(req.body?.name || '').trim().slice(0, 80);
      if (!name) return res.status(400).json({ error: 'Give the campaign a name.' });
      const { data, error } = await db().from('campaigns')
        .insert({ name, status: 'ongoing', started_on: today(), roll: DEFAULT_ROLL })
        .select('id, name, roll').single();
      if (error) throw error;
      return res.status(200).json(data);
    }

    return res.status(405).json({ error: 'Use GET or POST.' });
  } catch (err) {
    console.error('campaign error', err?.message);
    return res.status(500).json({ error: 'Could not reach the campaign records.' });
  }
}
