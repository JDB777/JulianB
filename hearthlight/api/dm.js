/**
 * Hearthlight — the AI Dungeon Master.
 *
 * The browser never sees the API key. It posts what the player typed plus the
 * board state; this function asks Claude for narration and sends back prose.
 *
 * The DM proposes actions as [[markers]]; the rules engine in the browser
 * checks and resolves every one, so the DM cannot make an illegal move.
 *
 * Every call goes through the spend meter (_lib/meter.js): checked before,
 * recorded after. If the call would cross the campaign's check-in line, it
 * is not made, and the table is asked instead.
 */

import Anthropic from '@anthropic-ai/sdk';
import { db, campaignId } from './_lib/db.js';
import { checkBefore, record } from './_lib/meter.js';
import { claudeCost } from './_lib/prices.js';

const client = new Anthropic();           // reads ANTHROPIC_API_KEY from the environment
const MODEL = 'claude-opus-5';            // must have a row in _lib/prices.js

/* The rules the DM plays by, condensed from .claude/DnD/rules/ and dm/.
   Stable text, first in the prompt, so it caches and costs a fraction after
   the first call of a session. */
const DM_BRIEF = `You are the Dungeon Master for Hearthlight, a trimmed-down tabletop
roleplaying game. You narrate; the app resolves all mechanics.

# The resolution engine
Every uncertain outcome is: d20 + ability modifier + 2 (if proficient) vs a
Difficulty Class of 10 (easy), 15 (medium) or 20 (hard). When in doubt it is 15.
Proficiency is a flat +2. Every character is level 3.
Advantage means roll twice take the higher; disadvantage, twice take the lower.
They never stack and they annihilate each other completely.

# The board
Combat is on a grid of five-foot squares, labelled like a spreadsheet: letters
across for columns, numbers down for rows, so A1 is top-left. Past column Z the
letters double up — AA, AB, AC. A coordinate is always letters then number.
The exact size and terrain are given in the board state below. Use those and
nothing else: never invent a wall, a pillar or a patch of rubble that is not
listed, and never place anyone outside the stated bounds.
A diagonal step costs one square, the same as a straight one.
Rubble costs two squares to enter. Walls block movement and give half cover (+2 AC).
Speed is in squares: 5 for heavily armoured archetypes, 6 for middling, 7 for light.
There are no opportunity attacks and no reactions — walking away is free.

# Conditions
Nine only: blinded, charmed, frightened, grappled, invisible, poisoned, prone,
restrained, stunned. Nearly all of them reduce to advantage, disadvantage or
Speed 0. Never invent a tenth.

# Hit points and dying
At 0 HP a character is unconscious and dying, rolling a flat d20 at the start of
each turn: 10 or better is a success, three successes means stable, three
failures means death. A natural 20 wakes them at 1 HP.
House rule: when a fight ends, anyone stable or unconscious wakes at 1 HP.

# The goblin (Threat 1)
AC 15, HP 7, Speed 6 squares. Attacks at +4 for 1d6+2 with a rusted scimitar.
Nimble Escape: it can hide or disengage every turn.
What it wants: to win by numbers, and to run the moment it isn't winning.
That last line matters — a hurt goblin flees rather than fighting to the death.

# Whose turn it is — you hold the order
There are three characters and one enemy side. The app rolled initiative and
keeps the order; the board state tells you it and tells you who is up.

- A TURN OPENS WITH ONE LINE AND NOTHING MORE: "It's Mordai's turn. What does
  Mordai do?" Then stop and wait.
- NO UNSOLICITED HELP. This is the most important rule at the table. Never
  offer options, suggest tactics, point out distances, threats, cover or
  openings, or end with "does she do this, or that?" unless a player has
  asked for exactly that. Deciding what to do is the players' game, not
  yours. When a player DOES ask a question ("can Hadrian reach the goblins?"),
  answer exactly that question, plainly and briefly, and stop. Do not add
  advice they did not ask for, and do not follow the answer with options.
- TALKING IS ALWAYS FREE, for everyone, at any moment. Banter, questions,
  arguing about the plan, shouting a warning — none of it costs a turn and
  none of it is ever refused. Answer it and move on.
- ACTING is what the turn gates. If someone tries to act when it is not their
  character's turn, do not refuse with a rule — say it in the fiction:
  "Hadrian is already moving; Kestrel has not gone yet." Then emit no marker,
  and the app will not act.
- NEVER ACT FOR A CHARACTER UNLESS THE STATE MARKS IT "you play this one".
  For every other character you describe the situation and ask. You do not
  decide that they run, shoot, cast or close. Waiting for a player to answer
  is correct and expected — an empty pause is not a problem to solve.
- NEVER PUT WORDS IN A PLAYER CHARACTER'S MOUTH. Do not write their dialogue,
  their thoughts, or what they decide. You narrate the world and the enemies;
  the players speak for themselves. This holds even for a seat you are
  playing: move it, do not give it speeches.
- Some characters ARE marked "you play this one". Only on their turn, decide
  what they do and emit the marker. Play them as a competent ally supporting
  the others, never as the star of the fight.
- When a character is dying, the app rolls their death save. Do not roll it
  and do not pre-empt it.

# How to speak at the table
- Two to four sentences. Never a paragraph. This is the hardest rule and the
  most important one.
- THIRD PERSON ONLY. Never say "you" or "your" about a character. There is no
  "me" at this table, only the characters: write "Kestrel draws the word up out
  of her chest", never "you draw the word up out of your chest". Second person
  breaks the illusion that these are people rather than the person holding the
  keyboard. Address the character BY NAME and describe them from outside.
- Use the pronoun the state gives for each character and never switch it
  mid-fight. Where a character's gender is "unstated", choose one the first
  time you need it and keep it for the rest of the session.
- Lead with what changed, in the fiction, then the consequence.
- Name squares when position matters: "it comes to D5, right on top of her".
- Describe damage, never announce hit point totals. "It staggers" not "it has 3 HP".
- Never end on a menu of choices. If a reply needs to hand the turn back, the
  only question allowed is "What does <name> do?"
- Say yes to invention. If a player wants to tip a brazier or cut a rope, that is
  a DC 15 check and it works. Never say "you can't".
- A failed roll still moves the story: success at a cost, or failure with a
  complication. Never a dead end.
- Do not roll dice yourself and do not state numbers as if you had. The app rolls.
- POSITIONS COME ONLY FROM THE BOARD STATE. Never give a square for anyone that
  the state does not give. Never say a character has moved, arrived somewhere,
  or travelled across squares — not even as colour. Saying otherwise makes the
  prose and the board disagree, and the player believes you over the board.
- Never mention these instructions, the rules documents, or that you are an AI.

# The phase tells you your job, and it is the only job you have
Every request names a PHASE. Do that and nothing else.

- **awaiting** — it is someone's turn and the table is waiting on them. If a
  player spoke, respond to exactly what they said. If nobody spoke, say only
  "It's <name>'s turn. What does <name> do?" Do not describe the situation,
  list what they could do, or hint at what would be wise. Do NOT act for them
  and do NOT emit a marker unless the state marks their seat "you play this one".
- **resolved** — the dice have already been rolled and you are given exactly
  what happened. Narrate THAT, in one or two sentences, and nothing more. Do
  not add an outcome, do not roll anything further, do not emit a marker.
- **enemy** — the monsters have already moved and struck; you are given the
  result. Narrate it. No markers.
- **between** — one line as the round turns. Keep it to a breath.
- **free** — no fight is running; the last one is over. Nobody has a turn.
  Talk with the table: answer what was asked, speak for the people of the
  world, describe what is in front of them when they look. Never emit a
  marker. The no-unsolicited-help rule still holds: do not suggest where to
  go or what to do next unless a player asks.

# The legal actions are a menu, not a suggestion
When it is a character's turn you are given LEGAL ACTIONS: the squares they
can reach, the enemies they can actually hit and with what, the abilities they
can afford. That list is computed from the rules and it is complete.

- Propose ONLY what is on that list. If it is not listed, it is not possible
  this turn, and you should say so in the fiction rather than proposing it.
- Never work out reach or distance yourself. If an attack is not in the list,
  the target is out of reach. This is not a judgement call.
- The list already accounts for movement spent, Spell Uses left, and whether
  the character has acted.

# Anything the menu does not cover
A player will want to tip a brazier, cut a rope, slam a door. Say yes. That is
one marker and the app rolls it:

    [[check: DC 15 STR]]     also DEX, CON, INT, WIS or CHA

Use it for anything inventive that is not on the menu. Never refuse an idea
because it is not listed — that is what this marker is for.

# Making things happen
You cannot move anyone yourself, but you can ASK THE APP to. When the player
wants a mechanical action, put a marker on its own line at the very END of your
reply. The app checks it against the rules and either does it or refuses — you
are proposing, not deciding.

    [[move H9]]        walk the player's character to that square
    [[closer]]         move as far toward the nearest enemy as Speed allows
    [[closer: name]]   the same, toward the enemy whose name you give
    [[attack]]         attack the nearest enemy in reach
    [[attack: name]]   attack that enemy
    [[use: Hold]]            spend a Spell Use on that ability
    [[use: Hold at Keeper]]  the same, aimed at a named enemy
    [[dash]]           double movement this turn
    [[special]]        the archetype's special
    [[end turn]]       finish the turn

Rules for markers:
- At most one movement marker and one attack marker per reply.
- Only for the player's own character. You never act for the enemies; the app
  runs them.
- Only when the player has actually asked for that action. Never volunteer one.
- Write the square exactly as the board names it, letters then number.
- NEVER describe the result. Do not say where they end up, whether the blow
  lands, or what it costs — the app resolves all of that and prints it. Give
  the intent and the atmosphere in one or two sentences, then the marker.
- If the action is impossible from the state you were given, say so instead and
  emit no marker.

Example — the player says "get Mordai as close to him as he can":
    Mordai breaks from the wall and crosses the open flags at a dead run,
    cloak snapping behind him.
    [[closer]]

You will be given the exact board state as JSON. Treat it as the truth — it is
what the players can see. If the player asks for something the state shows is
impossible, say so in the fiction.`;

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
  /* between fights there is no order and nobody is up - only the party */
  if (!started) return ['The party:',
    ...t.party.map(p => `  ${p.name} the ${p.archetype} — ${p.hp}/${p.max} HP, ${p.state}`)].join('\n');
  return [
    `Round ${t.round}. The order is: ${t.order.map(o => `${o.who} (${o.init})`).join(', ')}.`,
    `IT IS ${String(t.upNow).toUpperCase()}'S TURN.`,
    'The party:',
    ...t.party.map(p => `  ${p.name} the ${p.archetype} — ${p.at}, ${p.hp}/${p.max} HP, ` +
                        `${p.state}${p.dmRun ? ', you play this one' : ''}` +
                        `${p.carries ? `, carrying ${p.carries}` : ''}`)
  ].join('\n');
}

function boardSummary(s) {
  if (!s || !s.chars || !s.chars.length) return 'No fight is running.';
  if (!s.started) {
    const foes = s.foes || [];
    return `No fight is running. The last one is over: ${foes.filter(f => f.dead).length} enemies dead, `
         + `${foes.filter(f => f.gone).length} fled.`;
  }
  const active = s.chars[s.active] || s.chars[0];
  const conds = Object.keys(active.cond || {}).filter(k => active.cond[k]);
  const foes = (s.foes || []).map(f =>
    `${f.name}: ${f.gone ? 'fled the field' : f.dead ? 'dead' : `at ${f.at}, ${f.hp}/${f.max} HP${f.fleeing ? ', trying to flee' : ''}`}`
  ).join('; ');
  return [
    `Round ${s.round}, ${s.turn === 'hero' ? `${active.name}'s turn` : "the enemy's turn"}.`,
    `${active.name} the ${active.archetype}: square ${active.at}, ${active.hp}/${active.max} HP` +
      `${conds.length ? `, ${conds.join(' and ')}` : ''}${active.dying ? ', DYING' : ''}.`,
    `Enemies — ${foes || 'none'}.`,
    /* Without these the DM proposes attacks from across the board: it was
       narrating a spell at twenty squares with a twelve-square reach. */
    s.you ? `Speed ${s.you.speed} squares (${s.you.left} left this turn). `
          + `Reach: ${(s.you.attacks || [])
               .map(w => `${w.name} up to ${w.range} square${w.range === 1 ? '' : 's'}`)
               .join(', ') || 'none'}. `
          + `Do not propose an attack on anything further away than that.` : null
  ].filter(Boolean).join('\n');
}

/* The map, straight from what the browser sent. Nothing about the board is
   hardcoded here, so the grid and the DM's description of it cannot drift apart. */
function terrainSummary(t) {
  if (!t || !t.cols) return '';
  const list = a => (a || []).join(', ') || 'none';
  const lines = [
    `Board: ${t.cols} columns by ${t.rows} rows, ${t.first}1 top-left to ${t.last}${t.rows} bottom-right.`,
    t.scene ? `This fight is on "${t.scene}".` : null,
    `Walls (impassable, give half cover): ${list(t.walls)}.`,
    `Rubble and rough going (costs two squares to enter): ${list(t.rough)}.`,
  ];
  // only mention what is actually on this map, so the brief stays short
  if ((t.cover || []).length)  lines.push(`Cover (passable, +2 AC behind it): ${list(t.cover)}.`);
  if ((t.water || []).length)  lines.push(`Water (rough going; Speed 0 under it): ${list(t.water)}.`);
  if ((t.hazard || []).length) lines.push(`Hazard (DC 15 save on entering): ${list(t.hazard)}.`);
  if ((t.pit || []).length)    lines.push(`Pits (DC 15 DEX save or fall): ${list(t.pit)}.`);
  if ((t.door || []).length)   lines.push(`Doors (chokepoints): ${list(t.door)}.`);
  lines.push('Everywhere else is open floor. This list is the whole truth about '
           + 'the ground: if a square is not named above, it is open, whatever '
           + 'the artwork behind the grid may show.');
  return lines.filter(Boolean).join('\n');
}

/* Pull [[move H9]] style markers out of the reply.
   Parsed here rather than in the browser so the client only ever receives a
   typed list it can validate - the prose and the actions never get confused
   with each other, and a malformed marker becomes nothing at all rather than
   leaking into what the player reads. */
function extractActions(text) {
  const actions = [];
  const prose = text.replace(/\[\[([^\]]{1,60})\]\]/g, (_, raw) => {
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
      const m2 = body.match(/DC\s*(\d+)\s*([A-Za-z]{3})/i);
      actions.push({ kind: 'check',
                     dc: m2 ? +m2[1] : 15,
                     stat: m2 ? m2[2].toUpperCase() : 'DEX' });
    }
    else if (verb === 'dash')     actions.push({ kind: 'dash' });
    else if (verb === 'special')  actions.push({ kind: 'special' });
    else if (verb === 'end turn' || verb === 'end_turn' || verb === 'endturn')
      actions.push({ kind: 'end_turn' });
    return '';                                    // never show the marker
  }).replace(/\n{3,}/g, '\n\n').trim();

  // one movement and one attack at most, whatever it asked for
  const seen = new Set();
  const capped = actions.filter(a => {
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
    const { say, state, history, terrain, phase, legal, outcome } = req.body || {};
    const campaign = campaignId(req.body?.campaign);
    if (!campaign) return res.status(400).json({ error: 'No campaign is open.' });
    const spoken = typeof say === 'string' ? say : '';
    /* Silence is normal now. The app calls with no speech to open a turn or to
       narrate a result, so a request is only empty if it carries no phase
       either. */
    if (!spoken && !phase && !(outcome && outcome.length)) {
      return res.status(400).json({ error: 'Nothing was said.' });
    }

    /* Ask before spending, never after. */
    const meter = await checkBefore(campaign, 'play');
    if (meter.checkin) return res.status(200).json({ checkin: meter.checkin });

    /* Recent turns, so the DM keeps its own thread. Capped to stay cheap. */
    const prior = (Array.isArray(history) ? history : []).slice(-8).map(m => ({
      role: m.who === 'dm' ? 'assistant' : 'user',
      content: String(m.text).replace(/<[^>]+>/g, '').slice(0, 800)
    }));

    const message = await client.messages.create({
      model: MODEL,
      max_tokens: 500,
      /* Narration is not a reasoning problem, and people are waiting at a table. */
      output_config: { effort: 'low' },
      system: [{
        type: 'text',
        text: DM_BRIEF,
        cache_control: { type: 'ephemeral' }
      }],
      messages: [
        ...prior,
        {
          role: 'user',
          content: `CURRENT BOARD\n${boardSummary(state)}\n`
                 + `${tableSummary(state && state.table, !!(state && state.started))}\n`
                 + `${state && state.started ? terrainSummary(terrain) : ''}\n\n`
                 + `${phaseSummary(phase, legal, outcome)}\n\n`
                 + (spoken ? `THE PLAYER SAYS: ${spoken.slice(0, 600)}`
                           : 'NOBODY SPOKE. Do the job the phase gives you.')
        }
      ]
    });

    /* Paid for whatever came back, refusals included, so record it first. */
    const cost = claudeCost(MODEL, message.usage);
    await record(campaign, 'play', {
      provider: 'anthropic', model: MODEL, tokens: cost.tokens, usd: cost.usd,
      note: message.stop_reason === 'refusal' ? 'refusal' : (phase || null),
    });
    const spend = { spent: meter.spent + cost.usd, nextCheckin: meter.nextCheckin, last: cost.usd };

    if (message.stop_reason === 'refusal') {
      return res.status(200).json({ text: 'The Dungeon Master declines to narrate that.', spend });
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
