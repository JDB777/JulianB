/**
 * What every paid call costs, in US dollars. The ONLY place prices live.
 *
 * Claude prices are per million tokens, taken from Anthropic's published model
 * table on 2026-10-14 (claude-api reference, cached 2026-10-06). Cache writes
 * are the 5-minute TTL rate (1.25x input), which is what the DM's prompt uses.
 *
 * When a price changes, edit this file and nothing else.
 * Gemini image prices are added in Phase 3, looked up at the time.
 */

export const CLAUDE = {
  'claude-opus-5':   { input: 5.00, output: 25.00, cacheRead: 0.50, cacheWrite: 6.25 },
  'claude-opus-5-5': { input: 4.00, output: 20.00, cacheRead: 0.20, cacheWrite: 5.00 },
};

/* Turn a Claude usage block into dollars. An unknown model throws rather than
   guessing: a meter that silently reads zero is worse than one that stops. */
export function claudeCost(model, usage) {
  const p = CLAUDE[model];
  if (!p) throw new Error(`No price for ${model} in api/_lib/prices.js`);
  const u = {
    input:      usage?.input_tokens ?? 0,
    cacheRead:  usage?.cache_read_input_tokens ?? 0,
    cacheWrite: usage?.cache_creation_input_tokens ?? 0,
    output:     usage?.output_tokens ?? 0,
  };
  const usd = (u.input * p.input + u.cacheRead * p.cacheRead
             + u.cacheWrite * p.cacheWrite + u.output * p.output) / 1e6;
  return { usd, tokens: u };
}
