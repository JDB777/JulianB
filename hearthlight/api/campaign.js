/**
 * Campaigns: list the ones you can resume, or start a new one.
 *
 *   GET  /api/campaign            -> { campaigns: [{ id, name, status, last_played }] }
 *   POST /api/campaign { name }   -> { id, name }
 */

import { db } from './_lib/db.js';

const today = () => new Date().toISOString().slice(0, 10);

export default async function handler(req, res) {
  try {
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
        .insert({ name, status: 'ongoing', started_on: today() })
        .select('id, name').single();
      if (error) throw error;
      return res.status(200).json(data);
    }

    return res.status(405).json({ error: 'Use GET or POST.' });
  } catch (err) {
    console.error('campaign error', err?.message);
    return res.status(500).json({ error: 'Could not reach the campaign records.' });
  }
}
