/**
 * What every paid call costs, in US dollars. The ONLY place prices live.
 *
 * Claude prices are per million tokens, from Anthropic's published model
 * table (claude-api reference, cached 2026-10-06), checked 2026-10-15.
 * Cache writes: 5-minute TTL is 1.25x input, 1-hour TTL is 2x input. The DM's
 * prompt uses the 1-hour TTL since Phase 2, because a table that stops to talk
 * for ten minutes would otherwise pay to rewrite the rulebook every time.
 *
 * claude-opus-5 and claude-opus-4-8 are here because they are where a refused
 * DM turn can be re-run (server-side fallbacks, api/dm.js).
 *
 * When a price changes, edit this file and nothing else.
 * Gemini image prices are added in Phase 3, looked up at the time.
 */

export const CLAUDE = {
  'claude-opus-5-5': { input: 4.00, output: 20.00, cacheRead: 0.20, cacheWrite: 5.00, cacheWrite1h: 8.00 },
  'claude-opus-5':   { input: 5.00, output: 25.00, cacheRead: 0.50, cacheWrite: 6.25, cacheWrite1h: 10.00 },
  'claude-opus-4-8': { input: 5.00, output: 25.00, cacheRead: 0.50, cacheWrite: 6.25, cacheWrite1h: 10.00 },
};

/* Turn a Claude usage block into dollars. An unknown model throws rather than
   guessing: a meter that silently reads zero is worse than one that stops.
   `served` is the model that actually answered, when a fallback ran. The
   dearer of the two prices is used, so a fallback can only make the meter
   read high, never low. */
export function claudeCost(model, usage, served) {
  const p = CLAUDE[model];
  if (!p) throw new Error(`No price for ${model} in api/_lib/prices.js`);
  const q = served && served !== model && CLAUDE[served] ? CLAUDE[served] : p;
  const price = k => Math.max(p[k], q[k]);

  const write = usage?.cache_creation_input_tokens ?? 0;
  const write1h = usage?.cache_creation?.ephemeral_1h_input_tokens ?? 0;
  const u = {
    input:      usage?.input_tokens ?? 0,
    cacheRead:  usage?.cache_read_input_tokens ?? 0,
    cacheWrite: write,
    output:     usage?.output_tokens ?? 0,
  };
  const usd = (u.input * price('input') + u.cacheRead * price('cacheRead')
             + (write - write1h) * price('cacheWrite') + write1h * price('cacheWrite1h')
             + u.output * price('output')) / 1e6;
  return { usd, tokens: u };
}
