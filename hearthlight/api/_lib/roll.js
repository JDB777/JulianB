/**
 * The campaign roll that goes with the art in assets/: what the DM runs.
 *
 * Every new campaign is given a copy (api/campaign.js), and the copy lives in
 * campaigns.roll from then on, so a campaign keeps its story even after this
 * file changes. Phase 3 replaces this with a fresh roll per campaign.
 *
 * Reconstructed 2026-10-15 for "Take custody of a prisoner and ask nothing".
 * The art's own prompts gave the NPCs, the liar (the gaoler), the mood, the
 * three sites and the boss. The workbook had already been rerolled, so the
 * why, the stake, the truth and the clock were taken from the Quest_Generator
 * row whose liar is the gaoler, and the faction from the five that fit a
 * CONSPIRACY truth. Site rules are Location_Generator's.
 *
 * Places are on a 100 x 100 plan of a 3:2 picture: x across, y down, the top
 * left corner of each building's footprint. The page draws the pins from these
 * numbers, so the labels are always legible and always on the right building.
 */

export const DEFAULT_ROLL = {
  version: 1,
  job: 'Take custody of a prisoner and ask nothing',
  setting: 'A prison gaol',
  why: 'The court moved and nobody told the gaol',
  stake: 'One of you put him here',
  liar: { role: 'The gaoler', secret: 'The prisoner left three days ago' },
  truth: 'The prisoner is innocent and the court knows',
  truth_type: 'CONSPIRACY',
  clock: 'The relief escort arrives at dawn',
  vibe: 'Luxurious - far too comfortable for a gaol',
  layout: 'Cells down one side, yard in the middle, gatehouse the only way out, '
        + 'everything overlooked from the wall walk.',

  boss: {
    name: 'the Evil Eel Keeper', creature: 'Eel',
    wants: 'To protect something it will not name',
    lair: 'The gatehouse',
  },
  faction: {
    name: 'The watch',
    is: 'The people whose actual job this is',
    serve: 'Orders, and they have not questioned them',
    fight: 'By the book, in pairs, and they send for more',
    breaks: 'Correct paperwork, or an order from someone senior',
  },
  minions: ['Cultist', 'Orc raider', 'Goblin'],

  /* the three fight sites, in the order the skeleton reaches them */
  sites: [
    { name: 'The cell block', limit: 'Something overhead that will come down',
      rule: 'When it goes: DC 15 DEX save beneath it or take 2d6',
      weather: 'Unnaturally quiet' },
    { name: 'The yard at exercise', limit: 'Crowded with people who live here',
      rule: 'DIFFICULT TERRAIN, and a miss by 5 or more hits a bystander',
      weather: 'Dusk, and the light going faster than you would like' },
    { name: 'The gatehouse', limit: 'Walls and partitions everywhere',
      rule: 'No sightline longer than 4 squares',
      weather: 'Unnaturally quiet', lair: true },
  ],

  npcs: [
    { role: 'The gaoler', name: 'Brienne Gorunn', gender: 'unstated', age: 'In their prime',
      look: 'Soft-handed, indoor; a nose broken more than once',
      at: "The gaoler's office", liar: true },
    { role: 'The prisoner', name: 'Hadrian Oakenshield', gender: 'unstated', age: 'Middle years, tired',
      look: 'Slight, quick; flour to the elbows', at: 'The cell block' },
    { role: 'The clerk', name: 'Arlo Garrick', gender: 'female', age: 'Middle years, tired',
      look: 'Heavy through the shoulders; a missing back tooth, visible when she laughs',
      at: "The gaoler's office" },
    { role: 'The chaplain', name: 'Sylas Underbough', gender: 'unstated', age: 'In their prime',
      look: 'Rangy; mud to the knee, dry', at: 'The chapel' },
    { role: 'The relief escort', name: 'Una Wolfsbane', gender: 'male', age: 'Middle years, tired',
      look: 'Compact and solid; a wedding ring worn on a chain, not a finger',
      at: null, arrives: 'at dawn, by the road' },
  ],

  start: 'The road to the gate',
  places: [
    { name: 'The wall walk', x: 4, y: 4, w: 78, h: 9,
      blurb: 'A walkway along the top of the wall. It overlooks everything.' },
    { name: 'The cell block', x: 4, y: 18, w: 22, h: 62, site: true,
      blurb: 'Cells down one side, under a sagging ceiling.' },
    { name: 'The yard at exercise', x: 32, y: 20, w: 30, h: 44, site: true,
      blurb: 'The middle of the gaol, crowded at dusk.' },
    { name: "The gaoler's office", x: 32, y: 72, w: 15, h: 18,
      blurb: 'Ledgers, keys, and a better fire than a gaol needs.' },
    { name: 'The chapel', x: 51, y: 72, w: 11, h: 18,
      blurb: 'Small, cold, and kept very clean.' },
    { name: 'The gatehouse', x: 67, y: 22, w: 15, h: 40, site: true,
      blurb: 'The only way in or out. Something keeps the cistern under it.' },
    { name: 'The road to the gate', x: 87, y: 34, w: 10, h: 18,
      blurb: 'Mud, ruts, and the gate ahead.' },
  ],
};
