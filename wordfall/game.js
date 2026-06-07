// game.js — WordFall core logic

import { createClient } from 'https://cdn.jsdelivr.net/npm/@supabase/supabase-js/+esm'
import { loadWords, isValidWord } from './wordlist.js'

// ── Config ───────────────────────────────────────────────────────────────────
const COLS          = 10
const ROWS          = 10
const SPAWN_COL     = 4      // 0-indexed center-ish column
const BASE_INTERVAL = 1000   // ms per auto-drop at game start
const MIN_INTERVAL  = 150    // ms per auto-drop at max speed
const SPEED_EVERY   = 3      // words cleared before each speed tick
const SPEED_REDUCE  = 40     // ms removed per tick

// Scrabble-derived letter point values
const PV = {
  A:1, B:3, C:3, D:2, E:1, F:4, G:2, H:4, I:1, J:8,
  K:5, L:1, M:3, N:1, O:1, P:3, Q:10, R:1, S:1, T:1,
  U:1, V:4, W:4, X:8, Y:4, Z:10
}

// ── Supabase ─────────────────────────────────────────────────────────────────
const sb = createClient(
  'https://oqfjfmthtpqooixcdfyi.supabase.co',
  'sb_publishable_VvgAKDEdsd3IB3PsHF6Oag_CrBEC7d2'
)

// ── State ─────────────────────────────────────────────────────────────────────
let board        = []      // board[row][col] = 'A'-'Z' | null
let active       = null    // { letter, row, col }
let nextLetter   = null
let deck         = []
let deckIdx      = 0
let score        = 0
let wordsCleared = 0
let longestWord  = ''
let running      = false
let animating    = false
let dropMs       = BASE_INTERVAL
let lastDrop     = 0

// ── DOM ───────────────────────────────────────────────────────────────────────
const $ = id => document.getElementById(id)
const loadScreen = $('loading-screen')
const loadBar    = $('loading-bar')
const appEl      = $('app')
const boardEl    = $('board')
const scoreEl    = $('score')
const nextEl     = $('next-letter')
const lastWordEl = $('last-word')
const overlay    = $('modal-overlay')
const finalScore = $('final-score')
const finalWord  = $('final-word')
const finalCount = $('final-count')
const nameInput  = $('player-name')
const lbList     = $('scores-list')

// ── Deck ──────────────────────────────────────────────────────────────────────
function freshDeck() {
  const a = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ'.split('')
  for (let i = a.length - 1; i > 0; i--) {
    const j = Math.floor(Math.random() * (i + 1));
    [a[i], a[j]] = [a[j], a[i]]
  }
  return a
}

function draw() {
  if (deckIdx >= deck.length) { deck = freshDeck(); deckIdx = 0 }
  return deck[deckIdx++]
}

// ── Board DOM ─────────────────────────────────────────────────────────────────
function buildGrid() {
  boardEl.innerHTML = ''
  board = Array.from({ length: ROWS }, () => Array(COLS).fill(null))
  for (let r = 0; r < ROWS; r++) {
    for (let c = 0; c < COLS; c++) {
      const d = document.createElement('div')
      d.className = 'cell'
      d.id = `g${r}_${c}`
      boardEl.appendChild(d)
    }
  }
}

function cell(r, c) { return document.getElementById(`g${r}_${c}`) }

function render() {
  for (let r = 0; r < ROWS; r++) {
    for (let c = 0; c < COLS; c++) {
      const el = cell(r, c)
      const isActive = active && active.row === r && active.col === c
      el.className = 'cell' + (isActive ? ' active' : board[r][c] ? ' locked' : '')
      el.textContent = isActive ? active.letter : (board[r][c] || '')
    }
  }
}

// ── Piece logic ───────────────────────────────────────────────────────────────
function spawn() {
  const letter = nextLetter || draw()
  nextLetter = draw()
  nextEl.textContent = nextLetter

  if (board[0][SPAWN_COL] !== null) { endGame(); return }
  active = { letter, row: 0, col: SPAWN_COL }
  lastDrop = performance.now()
  render()
}

function canDown() {
  return active && active.row < ROWS - 1 && board[active.row + 1][active.col] === null
}

function moveLeft() {
  if (!active || animating) return
  if (active.col > 0 && board[active.row][active.col - 1] === null) {
    active.col--; render()
  }
}

function moveRight() {
  if (!active || animating) return
  if (active.col < COLS - 1 && board[active.row][active.col + 1] === null) {
    active.col++; render()
  }
}

function moveDown() {
  if (!active || animating) return
  if (canDown()) { active.row++; lastDrop = performance.now(); render() }
  else lock()
}

// ── Lock + word processing ────────────────────────────────────────────────────
async function lock() {
  if (!active) return
  board[active.row][active.col] = active.letter
  active = null
  animating = true
  render()
  await cascade()
  animating = false
  if (running) spawn()
}

// Repeatedly find, flash, clear, and gravity until no words remain
async function cascade() {
  while (true) {
    const words = findWords()
    if (words.length === 0) break
    await flashClear(words)
    gravity()
    render()
  }
}

// ── Word detection ────────────────────────────────────────────────────────────
function findWords() {
  const found = []

  // Scan rows (horizontal)
  for (let r = 0; r < ROWS; r++) {
    const str = board[r].map(l => l || ' ').join('')
    scanLine(str, (word, start) => {
      found.push({ word, cells: wordCells(word, r, start, 'h') })
    })
  }

  // Scan columns (vertical)
  for (let c = 0; c < COLS; c++) {
    const str = board.map(row => row[c] || ' ').join('')
    scanLine(str, (word, start) => {
      found.push({ word, cells: wordCells(word, start, c, 'v') })
    })
  }

  return found
}

// For each start position in a string, find the LONGEST valid word.
// Breaks on spaces (gaps between locked letters).
function scanLine(str, cb) {
  for (let s = 0; s < str.length; s++) {
    if (str[s] === ' ') continue
    let best = null
    for (let e = s + 3; e <= str.length; e++) {
      const slice = str.slice(s, e)
      if (slice.includes(' ')) break
      if (isValidWord(slice)) best = { word: slice, start: s }
    }
    if (best) cb(best.word, best.start)
  }
}

function wordCells(word, row, col, dir) {
  return Array.from({ length: word.length }, (_, i) =>
    dir === 'h' ? { r: row, c: col + i } : { r: row + i, c: col }
  )
}

// ── Flash, score, clear ───────────────────────────────────────────────────────
async function flashClear(words) {
  const hit = new Set()

  for (const { word, cells } of words) {
    const pts = [...word].reduce((s, l) => s + (PV[l] || 0), 0)
    score += pts
    wordsCleared++
    if (word.length > longestWord.length) longestWord = word
    cells.forEach(({ r, c }) => hit.add(`${r},${c}`))
  }

  scoreEl.textContent = score

  const banner = words.map(w => w.word).join('  +  ')
  flashBanner(banner)

  // Animate cells
  const dominated = []
  for (const key of hit) {
    const [r, c] = key.split(',').map(Number)
    const el = cell(r, c)
    el.classList.add('flash')
    dominated.push({ el, r, c })
  }

  await sleep(960) // matches CSS: 0.12s × 8 iterations

  for (const { el, r, c } of dominated) {
    el.classList.remove('flash')
    board[r][c] = null
  }

  // Speed up every SPEED_EVERY words
  const level = Math.floor(wordsCleared / SPEED_EVERY)
  dropMs = Math.max(MIN_INTERVAL, BASE_INTERVAL - level * SPEED_REDUCE)
}

// ── Gravity ───────────────────────────────────────────────────────────────────
function gravity() {
  for (let c = 0; c < COLS; c++) {
    const letters = []
    for (let r = 0; r < ROWS; r++) {
      if (board[r][c] !== null) letters.push(board[r][c])
    }
    // Pack letters to the bottom; top rows become null
    for (let r = 0; r < ROWS; r++) {
      const idx = r - (ROWS - letters.length)
      board[r][c] = idx >= 0 ? letters[idx] : null
    }
  }
}

// ── Helpers ───────────────────────────────────────────────────────────────────
function sleep(ms) { return new Promise(r => setTimeout(r, ms)) }

function flashBanner(text) {
  lastWordEl.textContent = text
  lastWordEl.classList.add('visible')
  setTimeout(() => lastWordEl.classList.remove('visible'), 2200)
}

// ── Game loop ─────────────────────────────────────────────────────────────────
function loop(ts) {
  if (!running) return
  if (!animating && active && ts - lastDrop >= dropMs) {
    lastDrop = ts
    if (canDown()) { active.row++; render() } else lock()
  }
  requestAnimationFrame(loop)
}

// ── Game over ─────────────────────────────────────────────────────────────────
async function endGame() {
  running = false
  finalScore.textContent = score
  finalWord.textContent  = longestWord || '—'
  finalCount.textContent = wordsCleared
  await loadLB()
  overlay.classList.remove('hidden')
}

// ── Supabase helpers ──────────────────────────────────────────────────────────
async function saveScore(name) {
  try {
    await sb.from('scores').insert({
      player_name:   (name || 'ANON').toUpperCase().trim().slice(0, 12),
      score,
      longest_word:  longestWord || null,
      words_spelled: wordsCleared
    })
  } catch { /* swallow — leaderboard is bonus, not required */ }
  await loadLB()
}

async function loadLB() {
  try {
    const { data } = await sb
      .from('scores')
      .select('player_name, score, longest_word')
      .order('score', { ascending: false })
      .limit(10)
    if (!data) return
    lbList.innerHTML = data.map((s, i) => `
      <li>
        <span class="lb-name">${i + 1}. ${s.player_name}</span>
        <span class="lb-word">${s.longest_word || ''}</span>
        <span>${s.score}</span>
      </li>`).join('')
  } catch { /* leaderboard failure is non-fatal */ }
}

// ── Start / Restart ───────────────────────────────────────────────────────────
function startGame() {
  board        = Array.from({ length: ROWS }, () => Array(COLS).fill(null))
  active       = null
  deck         = freshDeck()
  deckIdx      = 0
  score        = 0
  wordsCleared = 0
  longestWord  = ''
  dropMs       = BASE_INTERVAL
  animating    = false
  running      = true

  scoreEl.textContent = 0
  lastWordEl.classList.remove('visible')
  overlay.classList.add('hidden')

  buildGrid()
  nextLetter = draw()
  spawn()
  requestAnimationFrame(loop)
}

// ── Input: touch hold-repeat ──────────────────────────────────────────────────
let holdT = null, holdI = null

function startHold(fn) {
  fn()
  holdT = setTimeout(() => { holdI = setInterval(fn, 80) }, 220)
}
function stopHold() {
  clearTimeout(holdT); clearInterval(holdI)
  holdT = null; holdI = null
}

function bindBtn(id, fn) {
  const el = $(id)
  el.addEventListener('pointerdown', e => { e.preventDefault(); startHold(fn) })
}
document.addEventListener('pointerup',     stopHold)
document.addEventListener('pointercancel', stopHold)

bindBtn('btn-left',  moveLeft)
bindBtn('btn-right', moveRight)
bindBtn('btn-down',  moveDown)

// Keyboard fallback (desktop / keyboard-connected tablet)
document.addEventListener('keydown', e => {
  if (e.key === 'ArrowLeft')  { e.preventDefault(); moveLeft()  }
  if (e.key === 'ArrowRight') { e.preventDefault(); moveRight() }
  if (e.key === 'ArrowDown')  { e.preventDefault(); moveDown()  }
  if (e.key === ' ')          { e.preventDefault(); moveDown()  }
})

// Modal actions
$('btn-submit').addEventListener('click', async () => {
  const btn = $('btn-submit')
  btn.disabled = true; btn.textContent = '...'
  await saveScore(nameInput.value)
  btn.textContent = 'SAVED'
})

$('btn-restart').addEventListener('click', () => {
  nameInput.value = ''
  $('btn-submit').disabled = false
  $('btn-submit').textContent = 'SAVE'
  startGame()
})

// ── Boot ──────────────────────────────────────────────────────────────────────
;(async () => {
  await loadWords(pct => { loadBar.style.width = `${pct}%` })
  await sleep(250)
  loadScreen.style.display = 'none'
  appEl.classList.remove('hidden')
  startGame()
})()
