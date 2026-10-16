/**
 * Hearthlight — the AI Dungeon Master.
 *
 * The browser never sees the API key. It posts what the table said plus the
 * game state; this function asks Claude for narration and sends back prose.
 *
 * The DM proposes actions as [[markers]]; the rules engine in the browser
 * checks and resolves every one, so the DM cannot make an illegal move.
 *
 * What the DM is sent, in order (Phase 2, 2026-10-15):
 *   1. the whole rulebook (rulebook.js, ~27k tokens)       } system, cached
 *   2. the app protocol below: phases, markers, the board   }  for an hour
 *   3. this campaign's roll, from campaigns.roll            }
 *   4. the recent story, then this turn: session clock, party, board, phase
 * Parts 1-3 do not change during a campaign, so after the first call of a
 * sitting they are read from the cache at a twentieth of the price.
 *
 * Every call goes through the spend meter (_lib/meter.js): checked before,
 * recorded after. If the call would cross the campaign's check-in line, it
 * is not made, and the table is asked instead.
 */

import Anthropic from '@anthropic-ai/sdk';
import { db, campaignId } from './_lib/db.js';
import { checkBefore, record } from './_lib/meter.js';
import { claudeCost } from './_lib/prices.js';
import { RULEBOOK } from './_lib/rulebook.js';
import { DEFAULT_ROLL } from './_lib/roll.js';

const client = new Anthropic();           // reads ANTHROPIC_API_KEY from the environment
const MODEL = 'claude-opus-5-5';          // must have a row in _lib/prices.js, as must its fallbacks
const CACHE = { type: 'ephemeral', ttl: '1h' };

/* How this app works, for a DM who has just read the rulebook. Stable text:
   it sits inside the cached prefix, so edit it rarely. */
const PROTOCOL = `# How this table works

You are running a 90-minute one-shot for friends sitting round one screen. The
rulebook above is how the game works. This part is how the app works, and where
the two differ, this part wins.

## The two modes

- **Town**: no fight is running. The board shows a painted picture of where the
  party is, and a short list of the places they know about. This is where the
  talking, the exploring, the checks and the decisions happen. Nobody has a
  turn: answer whoever spoke.
- **Fight**: a battle grid with initiative. The app rolls initiative, keeps the
  order and tells you whose turn it is. Turn rules below.

## Whose turn it is, in a fight

- A turn opens with one line and nothing more: "It's Mordai's turn. What does
  Mordai do?" Usually the app writes that line itself.
- NO UNSOLICITED HELP. This is the most important rule at the table, in both
  modes. Never offer options, suggest tactics, point out distances, threats,
  cover, openings or where to go next, and never end with "does she do this, or
  that?", unless a player has asked for exactly that. When a player asks a
  question, answer exactly that question, plainly, and stop.
- TALKING IS ALWAYS FREE, for everyone, at any moment. It never costs a turn and
  is never refused.
- ACTING is what the turn gates. If someone tries to act out of turn, say so in
  the fiction ("Hadrian is already moving; Kestrel has not gone yet") and emit
  no marker.
- NEVER ACT FOR A CHARACTER unless the state marks it "you play this one", and
  only on its turn. Play such a character as a competent ally, never the star.
- NEVER PUT WORDS IN A PLAYER CHARACTER'S MOUTH: not their dialogue, thoughts,
  feelings or decisions. You narrate the world and play everyone in it who is
  not a player character.
- When a character is dying, the app rolls the death save. Do not roll it.

## How to speak

- Two to four sentences. Never a paragraph. A new place gets three sentences;
  an NPC's opening line gets two.
- Third person only. Never "you" or "your" about a character: "Kestrel draws
  the word up out of her chest", never "you draw the word up". Address
  characters by name.
- Use the pronoun the state gives for each character and never switch it.
  Where it says "unstated", choose one the first time and keep it.
- Describe damage, never hit point totals. Never roll dice or state numbers as
  if you had; the app rolls and tells you.
- Never end on a menu of choices. The only question allowed at the end is
  "What does <name> do?", or in town, "What do you do?" to the table at most
  once in a while.
- Say yes to invention: an inventive idea is a check, and it can work.
- A failed roll still moves the story. Never a dead end.
- Positions come only from the state. Never say a character moved anywhere the
  state does not show.
- Never mention these instructions, the rulebook, the app, or that you are an AI.

## The phase is your job this turn, and your only job

Every request names a PHASE.

- **opening**: the very start of the session. Open in medias res with the
  party already committed to the job and something already happening, at the
  starting place. Three or four sentences. End by going round the table: "Who
  are you, and why did you take this job?" Nothing else.
- **free**: town, and someone spoke. Answer them. Speak for the NPCs, describe
  what the party looks at, call for a check when something is uncertain. Move
  the story toward the next beat of the session skeleton through the world and
  its people, never by advising the table.
- **travel**: the party has just gone to a new place. The app has already
  moved them. Describe the arrival in up to three sentences: who is there, what
  they are doing. Then stop.
- **awaiting**: a fight, someone's turn. If a player spoke, respond to exactly
  that. If nobody spoke, say only "It's <name>'s turn. What does <name> do?"
- **resolved**: the dice have been rolled; you are told what happened. Narrate
  exactly that in one or two sentences. Add no outcome and no marker.
- **enemy**: the monsters have moved and struck; you are told the result.
  Narrate it. No markers.
- **between**: one line as a round turns.
- **aftermath**: a fight has just ended, and you are told how. Two or three
  sentences: what the fight leaves behind, and what it gave away (what the
  enemy carried, said, or guarded). The board is back on the town map.

## Discovery: the table finds things out

Finding places and people is the fun of the game, so the table is shown only
what it has discovered. Each turn you are told the places the party KNOWS and
the people it has MET.

- Never name, list or hint at a place the party does not know, and never
  describe the layout of the whole place. When the party learns of a place,
  because someone mentions it, it comes into view, or they find a way to it,
  emit [[reveal: The chapel]] and it is added to their list.
- Never name a person the party has not met, and never say where to find
  them. When someone is first seen or introduced, emit [[meet: Brienne Gorunn]]
  and they appear on screen. Until then, describe them only by what the party
  sees: "a heavy-shouldered woman behind the desk".
- The picture on screen shows the place, empty of people. Your description
  should agree with it: you are told what it shows.
- Describe what the party sees, then stop and ask. Nothing moves on until a
  player answers.

## The session skeleton and the clock

You are told how many minutes have been played and where that puts the session
on the 90-minute skeleton from the rulebook: hook, social scene, exploration,
the complication fight, the turn, the finale, the landing. Steer by it through
the fiction. If the clock says you are running late, cut toward the finale as
the rulebook says. At the landing, go round the table: "One line each: where is
your character a week from now?", then say what became of the place.

## The campaign is the story

You are given this campaign's roll: the job, who lies and why, the truth, the
clock, the boss and what it wants, the faction and what breaks them, the sites
and the people. Play it exactly as rolled. Weird stays weird. The secrets are
yours: let the table discover them through play, never announce them. The
truth lands at the turn, not before. The boss's want makes a non-combat ending
possible; let it be possible.

## The legal actions are a menu, in a fight

On a character's turn you are given LEGAL ACTIONS: the squares they can reach,
the enemies they can hit and with what, the abilities they can afford. It is
complete. Propose only what is on it, and never work out reach yourself. If an
attack is not listed, the target is out of reach.

## Making things happen: markers

You never change the game yourself; you ask the app with a marker on its own
line at the very END of your reply. The app checks it and does it or refuses.
Never describe the result of a marker: the app resolves it and tells you.
Only emit a marker when a player has asked for that action, or, for [[fight]],
[[go]] and [[note]], when the fiction has plainly arrived there.

In a fight, for the character whose turn it is:

    [[move H9]]              walk to that square
    [[closer]]               as far toward the nearest enemy as Speed allows
    [[closer: name]]         the same, toward that enemy
    [[attack]]               attack the nearest enemy in reach
    [[attack: name]]         attack that enemy
    [[use: Hold]]            spend a Spell Use on that ability
    [[use: Hold at name]]    the same, aimed at that enemy
    [[dash]]  [[special]]  [[end turn]]

At most one movement and one action marker per reply.

In either mode:

    [[check: DC 15 WIS insight for Kestrel]]
        Any uncertain thing a character tries: a skill check, an Influence
        attempt (CHA with persuasion, deception or intimidation, DC from the
        NPC's attitude), anything inventive. Name the ability, optionally the
        skill, and the character. The app rolls it with their bonuses. DC 10
        easy, 15 medium, 20 hard.

In town:

    [[go: The chapel]]
        The party goes to a place, when they say so. Use the place names
        exactly as the campaign lists them. Going somewhere reveals it. (The
        table can also click a place it knows.)
    [[reveal: The chapel]]      the party has learned that a place exists
    [[meet: Brienne Gorunn]]    the party has met this person (name or role)
        Several of these may go in one reply.
    [[fight: standard]]
    [[fight: finale at The gatehouse]]
        Violence breaks out. Sizes: warmup, standard, hard, finale. The finale
        is the boss fight and happens once, when the story reaches the boss.
        The fight is where the party stands unless you name a place. Write
        one or two sentences of it erupting; the app builds the enemies from
        this campaign's minions, sets the board and rolls initiative.
    [[note: the gaoler admitted the prisoner left three days ago]]
        Something the table has just learned that will matter later. The app
        keeps the list and shows it back to you every turn. One line, rarely.
    [[rest]]
        Only when the party asks to Catch Their Breath. Once per session; the
        app knows whether it is used and refuses a second.

You are given the exact state each turn. Treat it as the truth.`;

/* The roll as the DM reads it. Secrets are marked so it plays them as such. */
function rollText(r) {
  if (!r) return 'No campaign has been rolled.';
  const npcs = (r.npcs || []).map(n =>
    `- ${n.name}, ${n.role.replace(/^The /, 'the ')} (${n.gender}, ${n.age}; ${n.look}). `
    + (n.at ? `Found at ${n.at}.` : `Not here yet: arrives ${n.arrives || 'later'}.`)
    + (n.liar ? ` LIES: ${r.liar?.secret}.` : '')).join('\n');
  const places = (r.places || []).map(p =>
    `- ${p.name}${p.site ? ' (a fight site)' : ''}: ${p.blurb || ''}`).join('\n');
  const sites = (r.sites || []).map((s, i) =>
    `- ${i + 1}. ${s.name}${s.lair ? ' (the lair, for the finale)' : ''}: ${s.limit}. `
    + `Rule in play: ${s.rule}. ${s.weather}.`).join('\n');
  return [
    '# This campaign',
    `The job, as the party was told it: ${r.job}.`,
    `Setting: ${r.setting}. Mood: ${r.vibe}. Layout: ${r.layout}`,
    `Why it is happening: ${r.why}.`,
    `The party's stake: ${r.stake}.`,
    `SECRET, who lies: ${r.liar?.role} - ${r.liar?.secret}.`,
    `SECRET, the truth (lands at the turn): ${r.truth}.`,
    `The clock: ${r.clock}.`,
    `The boss: ${r.boss?.name}, which wants ${String(r.boss?.wants || '').toLowerCase()}. `
      + `Its lair is ${r.boss?.lair}.`,
    `The faction: ${r.faction?.name}, ${String(r.faction?.is || '').toLowerCase()}. `
      + `They serve because: ${r.faction?.serve}. They fight: ${r.faction?.fight}. `
      + `They break when: ${r.faction?.breaks}.`,
    `Its minions: ${(r.minions || []).join(', ')}. The faction describes them; the numbers are the bestiary's.`,
    `The party starts at: ${r.start}.`,
    '', 'The places on the map:', places,
    '', 'The three fight sites:', sites,
    '', 'The people:', npcs,
  ].join('\n');
}

/* The clock and the story so far, from the page. */
function sessionText(s) {
  if (!s) return '';
  const fights = (s.fights || []).map(f => `${f.size} at ${f.place} (${f.won ? 'won' : 'lost'})`);
  return [
    `SESSION: ${s.minutes} minutes played. By the skeleton this is: ${s.beat}.`
      + (s.next ? ` Next: ${s.next}.` : ''),
    s.late ? 'YOU ARE RUNNING LATE. Cut toward the finale, as the rulebook says.' : null,
    `Fights so far: ${fights.length ? fights.join('; ') : 'none'}.`,
    `Catch Your Breath: ${s.rested ? 'already used this session' : 'not used yet'}.`,
    s.place ? `The party is at: ${s.place}.` : null,
    s.picture ? `The picture on screen shows: ${s.picture}` : null,
    s.here && s.here.length ? `People here: ${s.here.join('; ')}.` : null,
    s.known ? `Places the party KNOWS: ${s.known.join(', ') || 'none'}. Every other place is undiscovered.` : null,
    s.met ? `People the party has MET: ${s.met.join(', ') || 'nobody yet'}. Everyone else is a stranger to them.` : null,
    (s.notes || []).length ? 'What the table has learned:\n' + s.notes.map(n => `  - ${n}`).join('\n') : null,
  ].filter(Boolean).join('\n');
}

/* The phase, the menu, and what the dice already said. This is what replaces
   the DM working anything out. */
function phaseSummary(phase, legal, outcome) {
  const out = [`PHASE: ${String(phase || 'awaiting').toUpperCase()}`];
  if (outcome && outcome.length) {
    out.push('WHAT JUST HAPPENED (already rolled - narrate this, add nothing):');
    outcome.forEach(l => out.push(`  ${l}`));
  }
  if (legal) {
    out.push(`LEGAL ACTIONS for ${legal.who} right now:`);
    out.push(`  movement left: ${legal.movementLeft} squares`);
    out.push(`  may move to: ${legal.moveTo.length ? legal.moveTo.join(' ') : 'nowhere'}`);
    out.push(legal.attacks.length
      ? '  may attack: ' + legal.attacks.map(a =>
          `${a.target} with ${a.weapon} (+${a.bonus}, ${a.damage}, ${a.distance} away)`).join('; ')
      : '  may attack: NOTHING is in reach');
    out.push(legal.abilities.length
      ? '  may use: ' + legal.abilities.map(a =>
          `${a.name}${a.dc ? ` (DC ${a.dc}` : ' (healing'}, ${a.range} squares) - ${a.does}`).join('; ')
      : `  may use: no abilities available (${legal.spellUses} Spell Uses)`);
    out.push(`  dash: ${legal.canDash ? 'yes' : 'no'} · end turn: yes`);
    out.push(`  ${legal.improvise}`);
  }
  return out.join('\n');
}

function tableSummary(t, started) {
  if (!t) return '';
  const sheet = p => `  ${p.name} the ${p.archetype} (${p.gender}${p.species ? ', ' + p.species : ''}) — `
    + `${p.hp}/${p.max} HP, ${p.state}, ${p.uses} Spell Uses`
    + `${p.conds ? ', ' + p.conds : ''}${p.carries ? `, carrying ${p.carries}` : ''}`;
  if (!started) return ['THE PARTY:', ...t.party.map(sheet)].join('\n');
  return [
    `Round ${t.round}. The order is: ${t.order.map(o => `${o.who} (${o.init})`).join(', ')}.`,
    `IT IS ${String(t.upNow).toUpperCase()}'S TURN.`,
    'THE PARTY:',
    ...t.party.map(p => sheet(p) + ` — at ${p.at}${p.dmRun ? ', you play this one' : ''}`)
  ].join('\n');
}

function boardSummary(s) {
  if (!s || !s.chars || !s.chars.length) return 'No game is running yet.';
  if (!s.started) return 'TOWN: no fight is running.';
  const active = s.chars[s.active] || s.chars[0];
  const foes = (s.foes || []).map(f =>
    `${f.name}: ${f.gone ? 'fled the field' : f.dead ? 'dead'
      : `at ${f.at}, ${f.hp}/${f.max} HP, AC ${f.ac}${f.fleeing ? ', trying to flee' : ''}`
        + `${f.trait ? `. ${f.trait}` : ''}${f.wants ? `. Wants: ${f.wants}` : ''}`}`
  ).join('\n  ');
  return [
    `FIGHT${s.fight ? ` (${s.fight.size}, at ${s.fight.place})` : ''}: round ${s.round}, `
      + `${s.turn === 'hero' ? `${active.name}'s turn` : "the enemy's turn"}.`,
    `Enemies:\n  ${foes || 'none'}`,
    /* Without these the DM proposes attacks from across the board: it was
       narrating a spell at twenty squares with a twelve-square reach. */
    s.you ? `${s.you.name}: Speed ${s.you.speed} squares (${s.you.left} left this turn). `
          + `Reach: ${(s.you.attacks || [])
               .map(w => `${w.name} up to ${w.range} square${w.range === 1 ? '' : 's'}`)
               .join(', ') || 'none'}. `
          + `Do not propose an attack on anything further away than that.` : null
  ].filter(Boolean).join('\n');
}

/* The map, straight from what the browser sent, so the grid and the DM's
   description of it cannot drift apart. */
function terrainSummary(t) {
  if (!t || !t.cols) return '';
  const list = a => (a || []).join(', ') || 'none';
  const lines = [
    `Board: ${t.cols} columns by ${t.rows} rows, ${t.first}1 top-left to ${t.last}${t.rows} bottom-right.`,
    t.scene ? `This fight is on "${t.scene}".` : null,
    `Walls (impassable, give half cover): ${list(t.walls)}.`,
    `Rubble and rough going (costs two squares to enter): ${list(t.rough)}.`,
  ];
  if ((t.cover || []).length)  lines.push(`Cover (passable, +2 AC behind it): ${list(t.cover)}.`);
  if ((t.water || []).length)  lines.push(`Water (rough going; Speed 0 under it): ${list(t.water)}.`);
  if ((t.hazard || []).length) lines.push(`Hazard (DC 15 save on entering): ${list(t.hazard)}.`);
  if ((t.pit || []).length)    lines.push(`Pits (DC 15 DEX save or fall): ${list(t.pit)}.`);
  if ((t.door || []).length)   lines.push(`Doors (chokepoints): ${list(t.door)}.`);
  lines.push('Everywhere else is open floor, whatever the artwork may show.');
  return lines.filter(Boolean).join('\n');
}

/* Pull [[move H9]] style markers out of the reply. Parsed here so the client
   only ever receives a typed list it can validate, and a malformed marker
   becomes nothing at all rather than leaking into what the player reads. */
export function extractActions(text) {
  const actions = [];
  const prose = text.replace(/\[\[([^\]]{1,200})\]\]/g, (_, raw) => {
    const body = raw.trim();
    const [head, ...rest] = body.split(':');
    const verb = head.trim().toLowerCase();
    const arg = rest.join(':').trim();

    let m;
    if ((m = verb.match(/^move\s+([a-z]{1,2}\s?\d{1,2})$/i)))
      actions.push({ kind: 'move', square: m[1].replace(/\s+/g, '').toUpperCase() });
    else if (verb === 'move' && /^[a-z]{1,2}\s?\d{1,2}$/i.test(arg))
      actions.push({ kind: 'move', square: arg.replace(/\s+/g, '').toUpperCase() });
    else if (verb === 'closer')   actions.push({ kind: 'closer', target: arg || null });
    else if (verb === 'attack')   actions.push({ kind: 'attack', target: arg || null });
    else if (verb === 'use' || verb === 'cast') {
      const [ab, tgt] = arg.split(/\s+at\s+/i);
      actions.push({ kind: 'use', ability: (ab || '').trim(), target: (tgt || '').trim() || null });
    }
    else if (verb.startsWith('check')) {
      /* "DC 15 WIS insight for Kestrel" - every part but the DC optional */
      const m2 = body.match(/DC\s*(\d+)\s*([A-Za-z]{3})?\s*([A-Za-z][A-Za-z ]*?)?\s*(?:\bfor\s+(.+))?$/i);
      actions.push({ kind: 'check',
                     dc: m2 ? +m2[1] : 15,
                     stat: m2 && m2[2] ? m2[2].toUpperCase() : 'DEX',
                     skill: m2 && m2[3] ? m2[3].trim().toLowerCase() : null,
                     who: m2 && m2[4] ? m2[4].trim() : null });
    }
    else if (verb === 'fight') {
      const [size, place] = arg.split(/\s+at\s+/i);
      const s = (size || '').trim().toLowerCase().replace(/[^a-z]/g, '');
      actions.push({ kind: 'fight',
                     size: ['warmup', 'standard', 'hard', 'finale'].includes(s) ? s : 'standard',
                     place: (place || '').trim() || null });
    }
    else if (verb === 'go' || verb === 'travel')  { if (arg) actions.push({ kind: 'go', place: arg }); }
    else if (verb === 'note')     { if (arg) actions.push({ kind: 'note', text: arg.slice(0, 160) }); }
    else if (verb === 'reveal')   { if (arg) actions.push({ kind: 'reveal', place: arg }); }
    else if (verb === 'meet')     { if (arg) actions.push({ kind: 'meet', name: arg }); }
    else if (verb === 'rest')     actions.push({ kind: 'rest' });
    else if (verb === 'dash')     actions.push({ kind: 'dash' });
    else if (verb === 'special')  actions.push({ kind: 'special' });
    else if (verb === 'end turn' || verb === 'end_turn' || verb === 'endturn')
      actions.push({ kind: 'end_turn' });
    return '';                                    // never show the marker
  }).replace(/\n{3,}/g, '\n\n').trim();

  // one of each slot at most, whatever it asked for - except discoveries,
  // since a reply can introduce two people at once
  const seen = new Set();
  const capped = actions.filter(a => {
    if (['reveal', 'meet', 'note'].includes(a.kind)) return true;
    const slot = ['move', 'closer'].includes(a.kind) ? 'move'
               : ['attack', 'use', 'check'].includes(a.kind) ? 'action' : a.kind;
    if (seen.has(slot)) return false;
    seen.add(slot);
    return true;
  });
  return { prose, actions: capped };
}

export default async function handler(req, res) {
  if (req.method !== 'POST') {
    return res.status(405).json({ error: 'Use POST.' });
  }
  if (!process.env.ANTHROPIC_API_KEY) {
    return res.status(500).json({ error: 'No API key configured on the server.' });
  }

  try {
    const { say, state, history, terrain, phase, legal, outcome, session } = req.body || {};
    const campaign = campaignId(req.body?.campaign);
    if (!campaign) return res.status(400).json({ error: 'No campaign is open.' });
    const spoken = typeof say === 'string' ? say : '';
    /* Silence is normal: the app calls with no speech to open a turn or to
       narrate a result. A request is only empty if it has no phase either. */
    if (!spoken && !phase && !(outcome && outcome.length)) {
      return res.status(400).json({ error: 'Nothing was said.' });
    }

    /* Ask before spending, never after. The roll comes from the database,
       never from the browser. */
    const [meter, camp] = await Promise.all([
      checkBefore(campaign, 'play'),
      db().from('campaigns').select('roll').eq('id', campaign).maybeSingle(),
    ]);
    if (meter.checkin) return res.status(200).json({ checkin: meter.checkin });
    const roll = camp?.data?.roll || DEFAULT_ROLL;

    /* The recent story, so the DM keeps its own thread. */
    const prior = (Array.isArray(history) ? history : []).slice(-16).map(m => ({
      role: m.who === 'dm' ? 'assistant' : 'user',
      content: String(m.text).replace(/<[^>]+>/g, '').slice(0, 800) || '…'
    }));
    /* the conversation has to open with the table, not the DM */
    while (prior.length && prior[0].role === 'assistant') prior.shift();
    const started = !!(state && state.started);

    const message = await client.beta.messages.create({
      model: MODEL,
      max_tokens: 2000,
      /* A refused turn is re-run on the model Anthropic recommends for that
         refusal, inside the same call, instead of reaching the table. */
      betas: ['server-side-fallback-2026-07-01'],
      fallbacks: 'default',
      /* Narration is not a reasoning problem, and people are waiting at a table. */
      output_config: { effort: 'low' },
      system: [
        { type: 'text', text: RULEBOOK },
        { type: 'text', text: PROTOCOL },
        { type: 'text', text: rollText(roll), cache_control: CACHE },
      ],
      messages: [
        ...prior,
        {
          role: 'user',
          content: [
            sessionText(session),
            boardSummary(state),
            tableSummary(state && state.table, started),
            started ? terrainSummary(terrain) : '',
            phaseSummary(phase, legal, outcome),
            spoken ? `THE TABLE SAYS: ${spoken.slice(0, 600)}`
                   : 'NOBODY SPOKE. Do the job the phase gives you.',
          ].filter(Boolean).join('\n\n')
        }
      ]
    });

    /* Paid for whatever came back, refusals included, so record it first. */
    const cost = claudeCost(MODEL, message.usage, message.model);
    const refused = message.stop_reason === 'refusal';
    const fellBack = message.model && message.model !== MODEL;
    if (refused || fellBack) {
      /* The intermittent refusal: written down with what triggered it, so it
         can be diagnosed from the logs rather than guessed at. */
      console.error('dm refusal', JSON.stringify({
        campaign, phase, served: message.model, refused,
        category: message.stop_details?.category ?? null,
        said: spoken.slice(0, 200),
      }));
    }
    await record(campaign, 'play', {
      provider: 'anthropic', model: message.model || MODEL, tokens: cost.tokens, usd: cost.usd,
      note: refused ? `refusal:${message.stop_details?.category ?? 'none'}:${phase || ''}`
          : fellBack ? `fallback:${phase || ''}` : (phase || null),
    });
    const spend = { spent: meter.spent + cost.usd, nextCheckin: meter.nextCheckin, last: cost.usd };

    if (refused) {
      return res.status(200).json({ text: 'The Dungeon Master pauses, and says nothing. (Try saying it another way.)', spend });
    }

    const text = message.content
      .filter(b => b.type === 'text')
      .map(b => b.text)
      .join('')
      .trim();

    const { prose, actions } = extractActions(text);

    /* The story log. A failure here must not cost the table its reply. */
    const log = [];
    if (spoken) log.push({ campaign_id: campaign, who: 'player', text: spoken.slice(0, 600) });
    if (prose)  log.push({ campaign_id: campaign, who: 'dm', text: prose });
    if (log.length) {
      const { error } = await db().from('messages').insert(log);
      if (error) console.error('story log not written', campaign, error.message);
    }

    return res.status(200).json({
      text: prose || '…',
      actions,
      spend,
      usage: {
        in: cost.tokens.input,
        cached: cost.tokens.cacheRead,
        out: cost.tokens.output
      }
    });
  } catch (err) {
    const status = err?.status ?? 500;
    /* Surface the useful part without ever echoing the key. */
    const msg = status === 401 ? 'The API key was rejected.'
              : status === 429 ? 'Rate limited — wait a moment and try again.'
              : status === 400 && /credit|billing/i.test(err?.message || '')
                ? 'The Anthropic account has no credit.'
              : `The Dungeon Master is unreachable (${status}).`;
    console.error('dm error', status, err?.message);
    return res.status(status).json({ error: msg });
  }
}
