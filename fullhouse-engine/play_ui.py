"""Interactive bot tester.

Run:   python play_ui.py
Open:  http://localhost:5001

Lets you build any poker situation by hand (hole cards, board, per-player stacks
and bets) and asks bots/mybot/bot.py what it would do. Shows the action plus
diagnostics: pot odds, equity estimate, hand label, and active-opponent count.
"""

import os
import sys
import time
import types

from flask import Flask, jsonify, render_template_string, request

# Make sure the local eval7 shim is found
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

# Load bots/mybot/bot.py as a module — but skip the ~22s equity-table precompute
# that runs at module load. The bot is designed to use the sandbox's 30s warmup
# window for that; for interactive testing we just want fast startup. Without
# the precomputed table the bot falls back to its heuristic equity estimate,
# which is fine for spot-checking decisions.
BOT_PATH = os.path.join(HERE, "bots", "mybot", "bot.py")
print(f"[play_ui] loading bot from {BOT_PATH} ...")
with open(BOT_PATH, "r", encoding="utf-8") as f:
    bot_src = f.read()
bot_src = bot_src.replace("\n_build_equity_table()\n", "\n# _build_equity_table()  # skipped by play_ui\n")

mybot = types.ModuleType("mybot")
mybot.__file__ = BOT_PATH
exec(compile(bot_src, BOT_PATH, "exec"), mybot.__dict__)
print(f"[play_ui] bot loaded: {getattr(mybot, 'BOT_NAME', '?')}")

try:
    mybot.decide({"type": "warmup"})
except Exception as e:
    print(f"[warn] warmup raised: {e}")

app = Flask(__name__)


PAGE = r"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<title>Apex — Bot Tester</title>
<style>
* { box-sizing: border-box; margin: 0; padding: 0; }
body { background: #0d1410; color: #d8e0d8; font-family: 'Inter', system-ui, sans-serif; font-size: 14px; }
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;700&family=Share+Tech+Mono&display=swap');

.app { max-width: 1280px; margin: 0 auto; padding: 20px; }

header { display: flex; align-items: center; gap: 16px; padding-bottom: 16px; border-bottom: 1px solid #1f2d22; margin-bottom: 20px; }
.logo { font-family: 'Share Tech Mono', monospace; font-size: 22px; color: #00ff88; letter-spacing: 2px; }
.subtitle { color: #6a8070; font-size: 13px; }

.layout { display: grid; grid-template-columns: 1.4fr 1fr; gap: 20px; }
@media (max-width: 1024px) { .layout { grid-template-columns: 1fr; } }

.card-panel { background: #121a14; border: 1px solid #1f2d22; border-radius: 8px; padding: 18px; }
h2 { font-size: 11px; letter-spacing: 2px; color: #7aa890; text-transform: uppercase; margin-bottom: 14px; font-weight: 700; }

/* Card slots */
.cards-row { display: flex; flex-wrap: wrap; gap: 8px; margin-bottom: 18px; }
.card-slot {
  width: 60px; height: 84px; border: 2px dashed #2d4030; border-radius: 6px;
  display: flex; align-items: center; justify-content: center;
  background: #0d1410; cursor: pointer; font-size: 22px; font-weight: 700;
  user-select: none; transition: all 0.1s;
}
.card-slot:hover { border-color: #00ff88; }
.card-slot.filled { border: 1px solid #2d4030; background: #fafafa; color: #111; }
.card-slot.filled.suit-h, .card-slot.filled.suit-d { color: #d23030; }
.card-slot.filled.suit-s, .card-slot.filled.suit-c { color: #111; }
.card-slot.empty { color: #3a5040; font-size: 28px; }

.streets { color: #6a8070; font-size: 12px; margin-bottom: 8px; }

/* Players */
.players-grid { display: flex; flex-direction: column; gap: 8px; }
.player-row {
  display: grid; grid-template-columns: 28px 56px 50px 50px 1fr 1fr 100px 70px;
  gap: 8px; align-items: center;
  padding: 8px; background: #0d1410; border: 1px solid #1f2d22; border-radius: 6px;
}
.player-row.me { border-color: #00ff88; background: #0f1d14; }
.player-row.dealer-seat { box-shadow: inset 0 0 0 1px #ffcc44; }
.seat-num { color: #6a8070; font-family: 'Share Tech Mono', monospace; font-weight: 700; text-align: center; }
.pos-tag {
  font-family: 'Share Tech Mono', monospace; font-size: 11px; font-weight: 700;
  text-align: center; padding: 3px 4px; border-radius: 3px; letter-spacing: 0.5px;
  background: #1f2d22; color: #7aa890;
}
.pos-tag.btn { background: #4a3a14; color: #ffcc44; }
.pos-tag.sb, .pos-tag.bb { background: #14304a; color: #88ccff; }
.player-row input[type=number], .player-row select {
  background: #0a0f0c; border: 1px solid #1f2d22; color: #d8e0d8;
  padding: 5px 6px; border-radius: 4px; font-family: inherit; font-size: 13px;
  width: 100%;
}
.player-row input[type=number]:focus, .player-row select:focus { border-color: #00ff88; outline: none; }
.player-row .me-radio, .player-row .dealer-radio { display: flex; justify-content: center; }
.player-row label { font-size: 11px; color: #6a8070; }
.col-label { font-size: 10px; color: #6a8070; text-transform: uppercase; letter-spacing: 1px; padding-bottom: 2px; }
.col-labels { display: grid; grid-template-columns: 28px 56px 50px 50px 1fr 1fr 100px 70px; gap: 8px; padding: 0 8px; }

.controls { display: flex; gap: 10px; margin-top: 16px; flex-wrap: wrap; align-items: center; }
button {
  background: #00ff88; color: #0d1410; border: none; font-family: inherit;
  font-size: 13px; font-weight: 700; padding: 10px 22px; cursor: pointer;
  border-radius: 6px; letter-spacing: 0.5px; transition: all 0.1s;
}
button:hover { background: #00cc6a; }
button.ghost { background: transparent; border: 1px solid #2d4030; color: #d8e0d8; }
button.ghost:hover { border-color: #00ff88; color: #00ff88; }

.global-inputs { display: grid; grid-template-columns: repeat(5, 1fr); gap: 12px; margin-bottom: 14px; }
.global-inputs > div { background: #0d1410; padding: 8px 10px; border: 1px solid #1f2d22; border-radius: 6px; }
.global-inputs label { display: block; color: #6a8070; font-size: 10px; text-transform: uppercase; letter-spacing: 1px; margin-bottom: 4px; }
.global-inputs input, .global-inputs select {
  width: 100%; background: #0a0f0c; border: 1px solid #1f2d22; color: #d8e0d8;
  padding: 6px 8px; border-radius: 4px; font-family: inherit; font-size: 14px;
}

/* Output panel */
.action-display {
  background: #0d1410; border-left: 4px solid #00ff88;
  padding: 24px; margin-bottom: 16px; border-radius: 6px;
}
.action-label { color: #6a8070; font-size: 11px; letter-spacing: 2px; text-transform: uppercase; margin-bottom: 8px; }
.action-text { font-size: 38px; font-weight: 700; color: #00ff88; font-family: 'Share Tech Mono', monospace; letter-spacing: 1px; }
.action-text.fold { color: #ff6464; }
.action-text.call, .action-text.check { color: #ffcc44; }
.action-text.raise, .action-text.all_in { color: #00ff88; }
.action-text.idle { color: #3a5040; font-size: 22px; }

.diagnostics {
  display: grid; grid-template-columns: 1fr 1fr; gap: 8px;
  background: #0d1410; padding: 14px; border: 1px solid #1f2d22; border-radius: 6px;
}
.diag-item { padding: 6px 0; border-bottom: 1px solid #1f2d22; }
.diag-item:last-child, .diag-item:nth-last-child(2) { border-bottom: none; }
.diag-key { color: #6a8070; font-size: 11px; text-transform: uppercase; letter-spacing: 1px; }
.diag-val { color: #d8e0d8; font-family: 'Share Tech Mono', monospace; font-size: 14px; margin-top: 2px; }
.diag-val.warn { color: #ff6464; }

.error { background: #1f1414; border-left: 4px solid #ff6464; padding: 12px; color: #ff8080; border-radius: 4px; margin-bottom: 12px; font-family: 'Share Tech Mono', monospace; font-size: 13px; }

/* Card picker modal */
.modal-bg {
  position: fixed; inset: 0; background: rgba(0,0,0,0.7); z-index: 100;
  display: none; align-items: center; justify-content: center;
}
.modal-bg.show { display: flex; }
.modal {
  background: #121a14; border: 1px solid #2d4030; border-radius: 10px;
  padding: 20px; max-width: 520px; width: 90%;
}
.modal-title { color: #d8e0d8; font-size: 14px; margin-bottom: 14px; }
.deck { display: grid; grid-template-columns: repeat(13, 1fr); gap: 4px; }
.deck-card {
  aspect-ratio: 5/7; background: #fafafa; color: #111; border-radius: 4px;
  display: flex; align-items: center; justify-content: center; cursor: pointer;
  font-weight: 700; font-size: 14px; user-select: none; border: 2px solid transparent;
}
.deck-card.suit-h, .deck-card.suit-d { color: #d23030; }
.deck-card:hover { border-color: #00ff88; }
.deck-card.used { opacity: 0.25; cursor: not-allowed; }
.deck-suit-row { display: contents; }
.suit-label { grid-column: 1; color: #7aa890; font-weight: 700; display: flex; align-items: center; justify-content: center; }
.modal-controls { display: flex; gap: 10px; margin-top: 14px; justify-content: flex-end; }
</style>
</head>
<body>
<div class="app">
  <header>
    <span class="logo">APEX_TESTER</span>
    <span class="subtitle">Build a spot. Ask the bot what to do.</span>
  </header>

  <div class="layout">
    <!-- LEFT: situation builder -->
    <div>
      <div class="card-panel" style="margin-bottom: 14px;">
        <h2>Your Hole Cards</h2>
        <div class="cards-row" id="hole-cards">
          <div class="card-slot empty" data-slot="hole-0">+</div>
          <div class="card-slot empty" data-slot="hole-1">+</div>
        </div>

        <h2>Community / Board <span class="streets" id="street-label">(preflop)</span></h2>
        <div class="cards-row" id="board-cards">
          <div class="card-slot empty" data-slot="board-0">+</div>
          <div class="card-slot empty" data-slot="board-1">+</div>
          <div class="card-slot empty" data-slot="board-2">+</div>
          <div class="card-slot empty" data-slot="board-3">+</div>
          <div class="card-slot empty" data-slot="board-4">+</div>
        </div>
      </div>

      <div class="card-panel" style="margin-bottom: 14px;">
        <h2>Pot &amp; Sizing</h2>
        <div class="global-inputs">
          <div>
            <label>Small Blind</label>
            <input type="number" id="sb" value="50" min="0" onchange="onBlindsChange()">
          </div>
          <div>
            <label>Big Blind</label>
            <input type="number" id="bb" value="100" min="0" onchange="onBlindsChange()">
          </div>
          <div>
            <label>Pot before this street</label>
            <input type="number" id="pot-prev" value="0" min="0">
          </div>
          <div>
            <label>Last raise size</label>
            <input type="number" id="last-raise" value="100" min="0">
          </div>
          <div>
            <label>Hand #</label>
            <input type="number" id="hand-num" value="1" min="1">
          </div>
        </div>
      </div>

      <div class="card-panel">
        <h2>Players (seat order, clockwise)</h2>
        <div class="col-labels">
          <span class="col-label">#</span>
          <span class="col-label">Pos</span>
          <span class="col-label">You</span>
          <span class="col-label">Btn</span>
          <span class="col-label">Stack</span>
          <span class="col-label">Bet (street)</span>
          <span class="col-label">Status</span>
          <span class="col-label"></span>
        </div>
        <div class="players-grid" id="players"></div>
        <div class="controls">
          <button class="ghost" onclick="addPlayer()">+ Add Player</button>
          <button class="ghost" onclick="resetPlayers()">Reset</button>
        </div>
      </div>

      <div class="controls" style="margin-top: 18px;">
        <button onclick="decide()">Get Bot Decision &rarr;</button>
        <button class="ghost" onclick="finishHand()">Finish Hand</button>
        <button class="ghost" onclick="clearAll()">Clear All</button>
      </div>
    </div>

    <!-- RIGHT: output -->
    <div>
      <div class="card-panel">
        <h2>Bot Decision</h2>
        <div class="action-display">
          <div class="action-label">Recommended Action</div>
          <div class="action-text idle" id="action-text">— ready —</div>
        </div>
        <div id="error-area"></div>
        <div class="diagnostics">
          <div class="diag-item"><div class="diag-key">Hand</div><div class="diag-val" id="diag-hand">—</div></div>
          <div class="diag-item"><div class="diag-key">Street</div><div class="diag-val" id="diag-street">—</div></div>
          <div class="diag-item"><div class="diag-key">Pot</div><div class="diag-val" id="diag-pot">—</div></div>
          <div class="diag-item"><div class="diag-key">Amount Owed</div><div class="diag-val" id="diag-owed">—</div></div>
          <div class="diag-item"><div class="diag-key">Pot Odds</div><div class="diag-val" id="diag-podds">—</div></div>
          <div class="diag-item"><div class="diag-key">Equity (vs random)</div><div class="diag-val" id="diag-equity">—</div></div>
          <div class="diag-item"><div class="diag-key">Active Opponents</div><div class="diag-val" id="diag-opps">—</div></div>
          <div class="diag-item"><div class="diag-key">Decision Time</div><div class="diag-val" id="diag-time">—</div></div>
        </div>
      </div>
    </div>
  </div>
</div>

<!-- Card picker modal -->
<div class="modal-bg" id="modal">
  <div class="modal">
    <div class="modal-title" id="modal-title">Pick a card</div>
    <div class="deck" id="deck"></div>
    <div class="modal-controls">
      <button class="ghost" onclick="clearSlot()">Clear slot</button>
      <button class="ghost" onclick="closeModal()">Cancel</button>
    </div>
  </div>
</div>

<!-- Winner picker modal -->
<div class="modal-bg" id="winner-modal">
  <div class="modal">
    <div class="modal-title">Who won the pot? <span id="winner-pot" style="color:#7aa890"></span></div>
    <div id="winner-list" style="display:flex;flex-direction:column;gap:6px;"></div>
    <div class="modal-controls">
      <button class="ghost" onclick="closeWinnerModal()">Cancel</button>
    </div>
  </div>
</div>

<script>
const RANKS = ['A','K','Q','J','T','9','8','7','6','5','4','3','2'];
const SUITS = ['s','h','d','c'];
const SUIT_GLYPH = { s: '♠', h: '♥', d: '♦', c: '♣' };

// State
const state = {
  cards: { 'hole-0': null, 'hole-1': null, 'board-0': null, 'board-1': null, 'board-2': null, 'board-3': null, 'board-4': null },
  players: [],
  pickingSlot: null,
  dealer: 0,         // seat index of the button
};

// ----- Position labels -----
// Order going clockwise from the button (BTN is dealer's seat).
const POS_TABLE = {
  2: ['BTN/SB', 'BB'],
  3: ['BTN', 'SB', 'BB'],
  4: ['BTN', 'SB', 'BB', 'UTG'],
  5: ['BTN', 'SB', 'BB', 'UTG', 'CO'],
  6: ['BTN', 'SB', 'BB', 'UTG', 'HJ', 'CO'],
  7: ['BTN', 'SB', 'BB', 'UTG', 'UTG+1', 'HJ', 'CO'],
  8: ['BTN', 'SB', 'BB', 'UTG', 'UTG+1', 'MP', 'HJ', 'CO'],
};

function activeIndices() {
  // Players that are not busted (stack > 0 OR all-in counts as in the hand).
  // For position purposes, busted players (stack 0 + folded) are excluded.
  const idxs = [];
  state.players.forEach((p, i) => {
    if (!(p.status === 'folded' && p.stack <= 0)) idxs.push(i);
  });
  return idxs;
}

function positionLabels() {
  // Returns an object { seatIndex: label } based on dealer + active players.
  const labels = {};
  const active = activeIndices();
  const n = active.length;
  if (n === 0) return labels;
  const tbl = POS_TABLE[n] || POS_TABLE[8];
  // Find dealer's spot in active list (or nearest active going forward).
  let start = active.indexOf(state.dealer);
  if (start === -1) {
    // Dealer is busted — pick next active clockwise.
    for (let off = 1; off < state.players.length; off++) {
      const cand = (state.dealer + off) % state.players.length;
      const ai = active.indexOf(cand);
      if (ai !== -1) { start = ai; break; }
    }
    if (start === -1) start = 0;
  }
  for (let k = 0; k < n; k++) {
    const seatIdx = active[(start + k) % n];
    labels[seatIdx] = tbl[k] || ('P' + (k+1));
  }
  return labels;
}

// ----- Players -----
function defaultPlayers() {
  return [
    { name: 'Seat 1 (You)', stack: 10000, bet: 0, status: 'active', isMe: true  },
    { name: 'Seat 2',        stack: 10000, bet: 0, status: 'active', isMe: false },
    { name: 'Seat 3',        stack: 10000, bet: 0, status: 'active', isMe: false },
    { name: 'Seat 4',        stack: 10000, bet: 0, status: 'active', isMe: false },
    { name: 'Seat 5',        stack: 10000, bet: 0, status: 'active', isMe: false },
    { name: 'Seat 6',        stack: 10000, bet: 0, status: 'active', isMe: false },
  ];
}

function posClass(label) {
  if (!label) return '';
  if (label.startsWith('BTN')) return 'btn';
  if (label === 'SB') return 'sb';
  if (label === 'BB') return 'bb';
  return '';
}

function renderPlayers() {
  const el = document.getElementById('players');
  const labels = positionLabels();
  el.innerHTML = '';
  state.players.forEach((p, i) => {
    const row = document.createElement('div');
    const isDealer = (i === state.dealer);
    row.className = 'player-row' + (p.isMe ? ' me' : '') + (isDealer ? ' dealer-seat' : '');
    const lab = labels[i] || '—';
    row.innerHTML = `
      <div class="seat-num">${i+1}</div>
      <div class="pos-tag ${posClass(lab)}">${lab}</div>
      <div class="me-radio"><input type="radio" name="me" ${p.isMe?'checked':''} onchange="setMe(${i})"></div>
      <div class="dealer-radio"><input type="radio" name="dealer" ${isDealer?'checked':''} onchange="setDealer(${i})"></div>
      <input type="number" min="0" value="${p.stack}" onchange="updPlayer(${i},'stack',this.value)">
      <input type="number" min="0" value="${p.bet}" onchange="updPlayer(${i},'bet',this.value)">
      <select onchange="updPlayer(${i},'status',this.value)">
        <option value="active" ${p.status==='active'?'selected':''}>active</option>
        <option value="folded" ${p.status==='folded'?'selected':''}>folded</option>
        <option value="all_in" ${p.status==='all_in'?'selected':''}>all-in</option>
      </select>
      <button class="ghost" style="padding:5px 10px;font-size:11px" onclick="removePlayer(${i})">remove</button>
    `;
    el.appendChild(row);
  });
}

function setMe(i) { state.players.forEach((p,j) => p.isMe = (i===j)); renderPlayers(); }
function setDealer(i) { state.dealer = i; renderPlayers(); }
function updPlayer(i, key, val) { state.players[i][key] = (key==='status') ? val : parseInt(val||0); }
function addPlayer() {
  const n = state.players.length + 1;
  state.players.push({ name: 'Seat '+n, stack: 10000, bet: 0, status: 'active', isMe: false });
  renderPlayers();
}
function removePlayer(i) {
  if (state.players.length <= 2) return;
  state.players.splice(i,1);
  if (state.dealer >= state.players.length) state.dealer = 0;
  if (!state.players.some(p => p.isMe)) state.players[0].isMe = true;
  renderPlayers();
}
function resetPlayers() { state.players = defaultPlayers(); state.dealer = 0; renderPlayers(); }

function onBlindsChange() { /* purely informational; bets are user-controlled */ }

// ----- Cards -----
function renderCard(slot, card) {
  const el = document.querySelector(`[data-slot="${slot}"]`);
  if (!card) {
    el.className = 'card-slot empty';
    el.textContent = '+';
  } else {
    const rank = card[0], suit = card[1];
    el.className = 'card-slot filled suit-' + suit;
    el.textContent = rank + SUIT_GLYPH[suit];
  }
}

function setCard(slot, card) {
  state.cards[slot] = card;
  renderCard(slot, card);
  updateStreetLabel();
}

function updateStreetLabel() {
  const n = ['board-0','board-1','board-2','board-3','board-4'].filter(s => state.cards[s]).length;
  const labels = ['preflop','preflop','preflop','flop','turn','river'];
  document.getElementById('street-label').textContent = '(' + labels[n] + ')';
}

document.querySelectorAll('.card-slot').forEach(el => {
  el.addEventListener('click', () => {
    state.pickingSlot = el.getAttribute('data-slot');
    openModal();
  });
});

function usedCards() {
  return new Set(Object.entries(state.cards)
    .filter(([k,v]) => v && k !== state.pickingSlot)
    .map(([k,v]) => v));
}

function openModal() {
  document.getElementById('modal-title').textContent = 'Pick a card for ' + state.pickingSlot;
  const deck = document.getElementById('deck');
  deck.innerHTML = '';
  const used = usedCards();
  for (const suit of SUITS) {
    for (const rank of RANKS) {
      const card = rank + suit;
      const div = document.createElement('div');
      div.className = 'deck-card suit-' + suit + (used.has(card) ? ' used' : '');
      div.textContent = rank + SUIT_GLYPH[suit];
      if (!used.has(card)) {
        div.onclick = () => { setCard(state.pickingSlot, card); closeModal(); };
      }
      deck.appendChild(div);
    }
  }
  document.getElementById('modal').classList.add('show');
}

function closeModal() {
  document.getElementById('modal').classList.remove('show');
  state.pickingSlot = null;
}

function clearSlot() {
  if (state.pickingSlot) setCard(state.pickingSlot, null);
  closeModal();
}

function clearAll() {
  Object.keys(state.cards).forEach(k => setCard(k, null));
  resetPlayers();
  document.getElementById('hand-num').value = 1;
  document.getElementById('pot-prev').value = 0;
  document.getElementById('action-text').textContent = '— ready —';
  document.getElementById('action-text').className = 'action-text idle';
  ['diag-hand','diag-street','diag-pot','diag-owed','diag-podds','diag-equity','diag-opps','diag-time']
    .forEach(id => document.getElementById(id).textContent = '—');
}

// ----- Finish hand -----
function totalPot() {
  const potPrev = parseInt(document.getElementById('pot-prev').value || 0);
  const bets = state.players.reduce((s,p) => s + (parseInt(p.bet) || 0), 0);
  return potPrev + bets;
}

function finishHand() {
  const pot = totalPot();
  if (pot <= 0) {
    document.getElementById('error-area').innerHTML =
      '<div class="error">No chips in the pot — set blinds/bets before finishing the hand.</div>';
    return;
  }
  document.getElementById('winner-pot').textContent = '(' + pot.toLocaleString() + ' chips)';
  const list = document.getElementById('winner-list');
  list.innerHTML = '';
  state.players.forEach((p, i) => {
    if (p.status === 'folded') return;  // folded players can't win
    const btn = document.createElement('button');
    btn.className = 'ghost';
    btn.style.cssText = 'text-align:left;padding:10px 14px;font-size:13px;';
    btn.textContent = `Seat ${i+1}${p.isMe?' (You)':''} — stack ${p.stack.toLocaleString()}, bet ${p.bet.toLocaleString()}`;
    btn.onclick = () => awardPot(i);
    list.appendChild(btn);
  });
  document.getElementById('winner-modal').classList.add('show');
}

function closeWinnerModal() {
  document.getElementById('winner-modal').classList.remove('show');
}

function nextActiveSeat(from) {
  // Find the next seat clockwise that has chips and isn't "folded with stack 0".
  const n = state.players.length;
  for (let off = 1; off <= n; off++) {
    const s = (from + off) % n;
    const p = state.players[s];
    if (p.stack > 0) return s;
  }
  return from;
}

function awardPot(winnerIdx) {
  const pot = totalPot();
  state.players[winnerIdx].stack += pot;

  // Reset bets and pot-from-prev-streets.
  state.players.forEach(p => { p.bet = 0; });
  document.getElementById('pot-prev').value = 0;

  // Re-activate non-busted players for the new hand.
  state.players.forEach(p => {
    if (p.stack > 0) p.status = 'active';
    else p.status = 'folded';   // out of chips => sitting out
  });

  // Rotate the dealer button clockwise to next player with chips.
  state.dealer = nextActiveSeat(state.dealer);

  // Post blinds for the new hand.
  const sb = parseInt(document.getElementById('sb').value || 0);
  const bb = parseInt(document.getElementById('bb').value || 0);
  postBlinds(sb, bb);

  // Clear the cards.
  ['hole-0','hole-1','board-0','board-1','board-2','board-3','board-4'].forEach(s => setCard(s, null));

  // Bump hand number and reset min-raise to BB.
  document.getElementById('hand-num').value =
    (parseInt(document.getElementById('hand-num').value || 1) + 1);
  document.getElementById('last-raise').value = bb;

  closeWinnerModal();
  renderPlayers();

  // Reset diagnostics
  document.getElementById('action-text').textContent = '— next hand —';
  document.getElementById('action-text').className = 'action-text idle';
  ['diag-hand','diag-street','diag-pot','diag-owed','diag-podds','diag-equity','diag-opps','diag-time']
    .forEach(id => document.getElementById(id).textContent = '—');
}

function postBlinds(sb, bb) {
  // Find SB and BB seats based on dealer + active count. Heads-up rule: dealer
  // posts the small blind. With 3+ players, SB = next active after dealer.
  const active = state.players.map((p,i) => p.stack > 0 ? i : -1).filter(i => i >= 0);
  if (active.length < 2) return;

  let sbSeat, bbSeat;
  if (active.length === 2) {
    sbSeat = state.dealer;
    bbSeat = nextActiveSeat(state.dealer);
  } else {
    sbSeat = nextActiveSeat(state.dealer);
    bbSeat = nextActiveSeat(sbSeat);
  }

  const sbPlayer = state.players[sbSeat];
  const bbPlayer = state.players[bbSeat];
  const sbAmt = Math.min(sb, sbPlayer.stack);
  const bbAmt = Math.min(bb, bbPlayer.stack);
  sbPlayer.stack -= sbAmt; sbPlayer.bet = sbAmt;
  bbPlayer.stack -= bbAmt; bbPlayer.bet = bbAmt;
}

// ----- Decide -----
async function decide() {
  const hole = [state.cards['hole-0'], state.cards['hole-1']];
  const board = ['board-0','board-1','board-2','board-3','board-4']
    .map(k => state.cards[k]).filter(Boolean);

  const errArea = document.getElementById('error-area');
  errArea.innerHTML = '';

  if (!hole[0] || !hole[1]) {
    errArea.innerHTML = '<div class="error">Pick both hole cards first.</div>';
    return;
  }
  if (board.length === 1 || board.length === 2) {
    errArea.innerHTML = '<div class="error">Board needs 0, 3, 4, or 5 cards.</div>';
    return;
  }
  if (!state.players.some(p => p.isMe)) {
    errArea.innerHTML = '<div class="error">Mark which seat is you.</div>';
    return;
  }

  const payload = {
    hole_cards: hole,
    community_cards: board,
    players: state.players,
    dealer: state.dealer,
    sb: parseInt(document.getElementById('sb').value || 50),
    bb: parseInt(document.getElementById('bb').value || 100),
    pot_prev: parseInt(document.getElementById('pot-prev').value || 0),
    last_raise: parseInt(document.getElementById('last-raise').value || 100),
    hand_num: parseInt(document.getElementById('hand-num').value || 1),
  };

  document.getElementById('action-text').textContent = '...thinking';
  document.getElementById('action-text').className = 'action-text idle';

  try {
    const res = await fetch('/decide', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
    const data = await res.json();
    if (data.error) {
      errArea.innerHTML = '<div class="error">' + data.error + '</div>';
      document.getElementById('action-text').textContent = 'ERROR';
      document.getElementById('action-text').className = 'action-text fold';
      return;
    }
    showResult(data);
  } catch (e) {
    errArea.innerHTML = '<div class="error">Request failed: ' + e + '</div>';
  }
}

function showResult(data) {
  const a = data.action;
  let txt = a.action.toUpperCase();
  if (a.action === 'raise')   txt = 'RAISE TO ' + a.amount.toLocaleString();
  if (a.action === 'all_in')  txt = 'ALL-IN ' + (a.amount ? a.amount.toLocaleString() : '');
  document.getElementById('action-text').textContent = txt;
  document.getElementById('action-text').className = 'action-text ' + a.action;

  document.getElementById('diag-hand').textContent   = data.hand_label || '—';
  document.getElementById('diag-street').textContent = data.street;
  document.getElementById('diag-pot').textContent    = data.pot.toLocaleString();
  document.getElementById('diag-owed').textContent   = data.amount_owed.toLocaleString();
  document.getElementById('diag-podds').textContent  = (data.pot_odds*100).toFixed(1) + '%';
  document.getElementById('diag-equity').textContent = (data.equity*100).toFixed(1) + '%';
  document.getElementById('diag-opps').textContent   = data.n_opp;
  document.getElementById('diag-time').textContent   = data.elapsed_ms.toFixed(0) + ' ms';
}

// Init
state.players = defaultPlayers();
renderPlayers();
</script>
</body>
</html>
"""


@app.route("/")
def index():
    return render_template_string(PAGE)


def _synth_action_log(players: list, dealer: int, sb: int, bb: int,
                      hero_seat: int, street: str) -> list:
    """Build a plausible action_log from the UI state.

    The bot reads action_log to (a) determine its position via the
    `small_blind` action's seat and (b) detect whether it's facing a raise.
    Without these entries the GTO preflop blueprint never fires and the bot
    falls through to a more conservative path that's heavy on fold/all-in.
    """
    in_hand = [p["seat"] for p in players if p.get("state") != "busted"]
    if len(in_hand) < 2:
        return []

    # SB / BB seats (HU rule: dealer posts SB)
    if len(in_hand) == 2:
        sb_seat = dealer if dealer in in_hand else in_hand[0]
        bb_seat = next(s for s in in_hand if s != sb_seat)
    else:
        d_idx = in_hand.index(dealer) if dealer in in_hand else 0
        sb_seat = in_hand[(d_idx + 1) % len(in_hand)]
        bb_seat = in_hand[(d_idx + 2) % len(in_hand)]

    log = [
        {"seat": sb_seat, "action": "small_blind", "amount": sb},
        {"seat": bb_seat, "action": "big_blind",   "amount": bb},
    ]

    if street != "preflop":
        return log  # postflop: blinds are enough for position labeling

    # Preflop action order: UTG first (BB+1) → ... → BTN → SB → BB.
    # HU: SB acts first after blinds.
    if len(in_hand) == 2:
        order = [sb_seat, bb_seat]
    else:
        bb_idx = in_hand.index(bb_seat)
        order = [in_hand[(bb_idx + 1 + k) % len(in_hand)]
                 for k in range(len(in_hand))]

    current = bb  # bet to call after blinds posted
    by_seat = {p["seat"]: p for p in players}

    for seat in order:
        if seat == hero_seat:
            continue  # hero hasn't acted yet
        p = by_seat.get(seat)
        if not p:
            continue
        bet = int(p.get("bet_this_street", 0) or 0)
        is_folded = p.get("is_folded") or p.get("state") == "folded"
        is_all_in = p.get("is_all_in") or p.get("state") == "all_in"

        if is_folded:
            log.append({"seat": seat, "action": "fold", "amount": 0})
        elif bet > current:
            log.append({
                "seat": seat,
                "action": "all_in" if is_all_in else "raise",
                "amount": bet,
            })
            current = bet
        elif bet == current and bet > 0 and seat != sb_seat and seat != bb_seat:
            log.append({"seat": seat, "action": "call", "amount": bet})
        # else: blind matches its own posting amount (no extra action)
        # or bet < current (incomplete bet — skip rather than guess)

    return log


def _build_game_state(payload: dict) -> dict:
    """Translate the UI payload into the engine's game_state dict."""
    hole = payload["hole_cards"]
    board = payload["community_cards"]
    raw_players = payload["players"]
    pot_prev = int(payload.get("pot_prev", 0))
    last_raise = int(payload.get("last_raise", 100))
    hand_num = int(payload.get("hand_num", 1))
    bb = int(payload.get("bb", 100))
    sb = int(payload.get("sb", 50))
    dealer = int(payload.get("dealer", 0))

    n_board = len(board)
    street = "preflop" if n_board == 0 else "flop" if n_board == 3 else "turn" if n_board == 4 else "river"

    # Seats are 0-indexed in the engine, but in the UI we show 1-based.
    your_seat = next((i for i, p in enumerate(raw_players) if p.get("isMe")), 0)

    players = []
    bets = []
    for i, p in enumerate(raw_players):
        status = p.get("status", "active")
        is_folded = (status == "folded")
        is_all_in = (status == "all_in")
        bet_this = int(p.get("bet", 0) or 0)
        bets.append(bet_this)
        players.append({
            "seat": i,
            "bot_id": "You" if i == your_seat else f"Opp{i+1}",
            "stack": int(p.get("stack", 10000) or 0),
            "state": "folded" if is_folded else "all_in" if is_all_in else "active",
            "is_folded": is_folded,
            "is_all_in": is_all_in,
            "bet_this_street": bet_this,
            "hole_cards": None,
        })

    me = players[your_seat]
    current_bet = max(bets) if bets else 0
    owed = max(0, current_bet - me["bet_this_street"])
    pot = pot_prev + sum(bets)
    min_raise_to = current_bet + max(last_raise, bb)

    action_log = _synth_action_log(players, dealer, sb, bb, your_seat, street)

    return {
        "type": "action_request",
        "hand_id": hand_num,
        "street": street,
        "seat_to_act": your_seat,
        "pot": pot,
        "community_cards": board,
        "current_bet": current_bet,
        "min_raise_to": min_raise_to,
        "amount_owed": owed,
        "can_check": owed == 0,
        "your_cards": hole,
        "your_stack": me["stack"],
        "your_bet_this_street": me["bet_this_street"],
        "players": players,
        "action_log": action_log,
        "match_action_log": [],
    }


def _diagnostics(game_state: dict) -> dict:
    """Compute extra info to show alongside the bot's action."""
    hole = game_state["your_cards"]
    board = game_state["community_cards"]
    pot = game_state["pot"]
    owed = game_state["amount_owed"]

    # Pot odds (break-even equity)
    pot_odds = owed / (pot + owed) if owed > 0 else 0.0

    # Active opponents
    n_opp = sum(1 for p in game_state["players"]
                if p["seat"] != game_state["seat_to_act"]
                and not p.get("is_folded")
                and p.get("state") != "busted")

    # Hand label + equity
    try:
        hand_label = mybot._canonical_hand(hole[0], hole[1])
    except Exception:
        hand_label = "?"

    equity = 0.0
    if game_state["street"] == "preflop":
        try:
            equity = mybot._multiway_equity(hand_label, max(n_opp, 1))
        except Exception:
            equity = 0.0
    else:
        try:
            result = mybot._monte_carlo_equity(hole, board, max(n_opp, 1), time_budget=0.4)
            equity = result[0] if isinstance(result, tuple) else result
        except Exception:
            equity = 0.0

    return {
        "pot_odds": pot_odds,
        "n_opp": n_opp,
        "hand_label": hand_label,
        "equity": equity,
    }


@app.route("/decide", methods=["POST"])
def decide_route():
    payload = request.get_json(force=True) or {}
    try:
        game_state = _build_game_state(payload)
    except Exception as e:
        return jsonify({"error": f"could not build game state: {e}"}), 400

    # Sync the bot's hardcoded blind constants with the UI's blind structure.
    # The bot uses BIG_BLIND/SMALL_BLIND for BB-relative thresholds (push/fold
    # under 12 BB, GTO blueprint above 30 BB) and for open sizing. Without
    # this sync, lowering the blinds in the UI keeps the bot's thresholds in
    # absolute chips, which makes deep stacks look short and triggers
    # push/fold mode inappropriately.
    mybot.BIG_BLIND = int(payload.get("bb", 100))
    mybot.SMALL_BLIND = int(payload.get("sb", 50))

    t0 = time.time()
    try:
        action = mybot.decide(game_state)
    except Exception as e:
        return jsonify({"error": f"bot raised: {e}"}), 500
    elapsed_ms = (time.time() - t0) * 1000

    diag = _diagnostics(game_state)

    return jsonify({
        "action": action,
        "street": game_state["street"],
        "pot": game_state["pot"],
        "amount_owed": game_state["amount_owed"],
        "elapsed_ms": elapsed_ms,
        **diag,
    })


if __name__ == "__main__":
    print("\n" + "=" * 50)
    print("  APEX BOT TESTER")
    print("=" * 50)
    print("  Open:  http://localhost:5001")
    print("  Bot:   bots/mybot/bot.py")
    print("=" * 50 + "\n")
    app.run(debug=False, threaded=True, port=5001)
