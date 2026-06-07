// wordlist.js — loads Scrabble-valid English words, exposes isValidWord()

let WORD_SET = new Set()

export async function loadWords(onProgress = () => {}) {
  try {
    onProgress(5)
    const res = await fetch(
      'https://raw.githubusercontent.com/dolph/dictionary/master/enable1.txt'
    )
    if (!res.ok) throw new Error('fetch failed')

    // Stream with real byte-progress so the loading bar tracks the actual download
    const total = parseInt(res.headers.get('content-length') || '0', 10)
    const reader = res.body.getReader()
    const chunks = []
    let received = 0
    while (true) {
      const { done, value } = await reader.read()
      if (done) break
      chunks.push(value)
      received += value.length
      if (total > 0) onProgress(5 + Math.round((received / total) * 75))
    }

    onProgress(82)
    const merged = new Uint8Array(received)
    let off = 0
    for (const chunk of chunks) { merged.set(chunk, off); off += chunk.length }

    onProgress(90)
    const words = new TextDecoder().decode(merged)
      .split('\n')
      .map(w => w.trim().toUpperCase())
      .filter(w => w.length >= 3 && /^[A-Z]+$/.test(w))

    WORD_SET = new Set([...words, ...CORE_WORDS])
    onProgress(100)
  } catch {
    onProgress(50)
    WORD_SET = new Set(CORE_WORDS)
    onProgress(100)
  }
}

export function isValidWord(word) {
  return WORD_SET.has(word.toUpperCase())
}

// Core fallback — guaranteed to be available offline (~700 words)
const CORE_WORDS = `
ace act add age ago aid aim air all and ant any ape arc are ark arm art ash ask ate awe axe
bad bag ban bar bat bay bed beg bid big bit bow box boy bud bug bun bus but buy
cab can cap car cat cod cog cop cot cow cry cub cup cut
dab dam day den dew dig dim dip doe dog dot dry dub due dug dye
ear eat eel egg elk elm end era eve ewe eye
fad fan far fat fed few fig fin fit fix fly foe fog for fur
gap gas gel gem get god got gum gun gut guy gym
ham has hat hay her him hip his hit hog hop hot how hub hug hum hut
ice ill inn ion its ivy
jab jam jar jaw jet jig job jog jot joy jug jut
keg kid kit
lab lad lag lap law lax lay led leg let lid lip lit log lot low
mad man map mar mat may men met mob mop mow mud mug
nab nag nap net new nil nod nor not now nub nun
oak oar oat odd off oil old one opt orb ore our out owe owl own
pad pal pan pat paw pay pea peg pen pet pie pig pin pit pod pot pry pub pun pup put
rag ram ran rap rat raw ray red rib rid rig rim rip rob rod rot row rub rug run rut rye
sag sap sat saw say sea set sew shy sip sit six ski sky sly sob sod son sow soy spa spy sub sum sun sup
tab tan tap tar tax ten the tie tin tip toe ton top tow toy tub tug two
urn use
van vat vet via vie vow
wad war was wax way web wed wee wet who why wig win wit woe wok won woo
yak yam yap yew you
zap zip
able ache acid aged also apex arch area army aunt away
babe baby back bald ball band bang bank bare bark barn base bash bass bath bead beam bean bear beat beef been beer bell belt bend bird bite bled blew blue blur boat body bold bolt bond bone book boom bore born both bowl bump burn bush buzz
cage cake calf call calm came camp card care cart case cast cave cell chat chef chin chip city clam claw clay clip coal coat coil coin cold colt come cone cook cool cope cord core corn cost crop crow curl cute
dame dark dart dash dawn dead deal dean dear debt deed deep deny desk dial dice diet dime dirt dish disk dock dome done doom door dose dove down drag draw drip drop drum duel dumb dump dune dusk dust
each earl earn east edge else emit epic even ever evil exam
face fact fail fair fall fame farm fast fate feel feet fell felt fern file fill film find fine fire firm fish fist flag flat flaw fled flew flex flip flow foam fold folk fond foot ford fore fork form fort foul four free fuel full fund fuse
gate gave gaze gear gene give glad glee glue goat gold golf gust
hack hail hair half hall halt hand hang hard hare harm harp hash haze head heal heap heat heel help herb here hero hide high hike hill hint hive hole holy home hood hook horn host hour huge hull hunt hurt hymn
idea idle inch iron item
jack jade jail jazz jerk join joke jump just
keen keep kick kill kind king kiss knee knew knot know
lace lack lady lake lamp land lane lash last late lawn lazy lead leaf leak lean leap lend lens less lift like lime line link lion list live load lock loft lone long look loom lose loss loud lure lurk
made maid mail main make male mall malt many mark mart mast mate mean meat melt mere mess mice mild mile milk mill mime mind mine mint miss moan mole monk mood moon moor more most move much mule muse musk myth
nail name navy near neck need news nice nine none noon norm nose note null
oath once only open oven over
pace page paid palm park part past path peak pear peel peer pick pile pine pink pipe plan play plea plow plus poem poet pole poll pond pool poor port pose post pour prey prod prop pull pump pure push
quit
race rack rage raid rain rake ramp rang rank rant rare rash rate rave read real reap rear reel rein rest rich ride ring riot rise risk road roam roar robe rock rode role roof room root rope rose ruin rule rush rust
safe sage sail sake sale salt same sand sane sang sank save scan scar seal seam shed shin ship shop shot show shut sick sign silk sing sink site size skin skip slam slap slid slim slip slit slow slug snap soar sock soft soil sold sole some song soon sore sort soul span spin spit spot star stay stem step stir stop stub such suit sure surf swam swan swap swim
tail tale tall tame tank tape task team tear tell tend test that them then they thin this tide tile till time tiny tire toad told toll tomb tone took tool torn toss town trap tree trim trip true tuck tune turf twin type ugly undo unit upon used user
vale vane vein very vest view vine void volt vote
wade wake walk wall warm wart wave weak weed week well went were west what when whim whip wide wife wild wile will wilt wipe wire wise wish with woke wolf wood wool word wore worm wren
yell zero zone zoom
about above abuse actor acute admit adopt adult after again agile agree ahead alarm album alert align alley allow alone along aloud alter angel anger angle ankle annex annoy apple apply arena argue arise arrow aside asset attic avoid award aware awful
badge basic basin basis beach beard beast begin being below black blade blame bland blank blast blaze blend blink block blood bloom blown blues board boost booth bound brain brand brave bread break breed brick bride brief bring brisk broad broke brook broom brown brush built bulge bulky bully bunch burst buyer
cabin canal candy carry cause cease chain chair chalk chase cheap cheat check cheek cheer chest child chose claim class clean clear clerk click cliff climb clock clone close cloth cloud clown color could couch count court cover crack craft crane crash crawl crazy cream creek cross crowd crown cruel crush curve cycle
daily dance death debut decay dense depot depth digit dirty dizzy dodge doubt dough draft drain dream dress drift drink drive drove dying
eager eagle early earth eight elite empty enemy enjoy enter equal error essay event every exact extra
faint fairy false fancy fatal feast fever fiber field fifth fifty fight final first fixed flame flash flesh float flood floor flour fluid flute focus force forge found fresh front frost froze fruit funny
giant given globe gloom gloss glove going grace grade grain grant grape grasp grass great greed green greet grief grill grind groan groom gross group grove guard guide guild gusto
habit happy harsh haste haunt heart heavy herbs hinge honor horse hotel human humor
ideal image imply index inner input irony issue
joint judge juice juicy
karma knack kneel knife knock known
label laden lance large laser later layer learn leave legal level light limit liver local logic loose lower loyal lucky
magic major maker match mayor media mercy merge merry metal minor model money month moral motor mount mouse mouth movie music
night noise noble north noted novel nurse
ocean offer often olive order other outer owner
paint panel paper party pause peace pearl pedal penny pilot pinch place plain plant plate plaza pluck point power press price pride prime print probe proof prose proud prove
queen quest quick quiet quite quota quote
radar radio raise rally rapid reach ready realm rebel reply rider ridge right rigid risky rival river robot rocky rough round route royal ruler rusty
scene screw seize serve seven shade shame shape share sharp sheep sheet shelf shift shore short sight since sixth sixty skill slate sleep slide slope small smart smell smile smoke snake solar solve sorry south space spare spark speak spear spend spine squad stack staff stage stair stake stall stamp stand stark start steal steam steel steep steer stick still stock stone storm story stove strap straw strip stump style sugar suite sunny super swift sword
table taste teach teeth there thick think thorn those three threw throw tiger tight tired title today token total touch tough tower towel trade trail train trash treat trend trial trick tried troop trout truce truly trust truth twice
under union until usual utter valid value venom verse video vigor visit vital voice voter
waste watch water wedge weigh while which white whole whose witch witty woman women world worry worse worst worth wrist wrong
yacht yield young youth zebra
`.trim().split(/\s+/).map(w => w.toUpperCase())
