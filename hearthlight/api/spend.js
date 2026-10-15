/**
 * The spend meter, for the table to see and answer.
 *
 *   GET  /api/spend?campaign=ID&stage=play   -> { spent, nextCheckin }
 *   POST /api/spend { campaign, stage }      -> { nextCheckin }   a player said "keep going"
 */

import { campaignId } from './_lib/db.js';
import { status, approve } from './_lib/meter.js';

const STAGES = new Set(['setup', 'play']);

export default async function handler(req, res) {
  try {
    const src = req.method === 'GET' ? req.query : req.body;
    const id = campaignId(src?.campaign);
    const stage = String(src?.stage || 'play');
    if (!id) return res.status(400).json({ error: 'Which campaign?' });
    if (!STAGES.has(stage)) return res.status(400).json({ error: 'Unknown stage.' });

    if (req.method === 'GET') return res.status(200).json(await status(id, stage));
    if (req.method === 'POST') return res.status(200).json({ nextCheckin: await approve(id, stage) });
    return res.status(405).json({ error: 'Use GET or POST.' });
  } catch (err) {
    console.error('spend error', err?.message);
    return res.status(500).json({ error: 'Could not reach the spend meter.' });
  }
}
