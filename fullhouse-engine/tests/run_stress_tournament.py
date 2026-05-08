"""Swiss-format stress tournament for the Apex bot.

Loads:
  * bots/mybot/bot.py                        (the Apex bot — focus of the test)
  * bots/{shark,aggressor,mathematician,template,ref_bot_2}/bot.py
  * bots/stress/*/bot.py                     (~60 archetype variants)

Plays N Swiss rounds of 400-hand 6-bot matches, prints the full final
standings, and highlights Apex's rank / cumulative delta / top-64 status.
With --repeat > 1, runs the whole tournament multiple times and reports
the rank distribution.

Usage:
  python tests/run_stress_tournament.py --rounds 5 --hands 400 --repeat 1
"""

import argparse
import importlib.util
import random
import sys
import time
import traceback
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from engine.game import PokerEngine, STARTING_STACK
from engine.tournament import swiss_pairing, compute_standings

MATCH_LOG_MAX = 200
TABLE_SIZE = 6
APEX_BOT_ID = "mybot"
TOP_CUT = 64


# ─── Loading ────────────────────────────────────────────────────────────────

def _load_one(path: Path):
    spec = importlib.util.spec_from_file_location(f"bot_{path.parent.name}", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def discover_bots():
    """Return dict bot_id → (Path bot_path, module).
    bot_id is the parent directory name."""
    paths = {}
    # Apex
    apex = REPO / "bots" / "mybot" / "bot.py"
    if apex.is_file():
        paths[APEX_BOT_ID] = apex
    # Reference bots
    for name in ("shark", "aggressor", "mathematician", "template", "ref_bot_2"):
        p = REPO / "bots" / name / "bot.py"
        if p.is_file():
            paths[name] = p
    # Stress bots
    stress_dir = REPO / "bots" / "stress"
    if stress_dir.is_dir():
        for sub in sorted(stress_dir.iterdir()):
            if sub.is_dir() and (sub / "bot.py").is_file():
                paths[sub.name] = sub / "bot.py"
    return paths


def load_field(paths):
    bots = {}
    for bid, p in paths.items():
        try:
            t0 = time.time()
            mod = _load_one(p)
            try:
                mod.decide({"type": "warmup"})
            except Exception:
                pass
            bots[bid] = mod
            elapsed = time.time() - t0
            if elapsed > 1.0:
                print(f"  loaded {bid} in {elapsed:.1f}s", flush=True)
        except Exception as e:
            print(f"  FAILED to load {bid}: {e}", file=sys.stderr)
    return bots


# ─── Match loop ─────────────────────────────────────────────────────────────

def play_match(match_id, bot_ids, bots, hands=400, seed=None,
               error_counts=None):
    """Run a single match.  Returns dict bot_id → chip_delta."""
    stacks = {b: STARTING_STACK for b in bot_ids}
    match_log = []
    dealer = 0
    if error_counts is None:
        error_counts = {}

    for hand_num in range(hands):
        alive = [b for b in bot_ids if stacks[b] > 0]
        if len(alive) < 2:
            break
        hand_id = f"{match_id}_h{hand_num:04d}"
        hand_seed = (seed * 1000003 + hand_num) if seed is not None else None
        engine = PokerEngine(
            hand_id=hand_id, bot_ids=alive,
            dealer_seat=dealer % len(alive),
            starting_stacks={b: stacks[b] for b in alive},
            seed=hand_seed,
        )
        state = engine.start_hand()
        state["match_action_log"] = match_log[-MATCH_LOG_MAX:]
        steps = 0
        while state.get("type") == "action_request":
            seat = state["seat_to_act"]
            bid = alive[seat]
            try:
                action = bots[bid].decide(state)
                if not isinstance(action, dict) or "action" not in action:
                    error_counts[bid] = error_counts.get(bid, 0) + 1
                    action = {"action": "fold"}
            except Exception:
                error_counts[bid] = error_counts.get(bid, 0) + 1
                action = {"action": "fold"}
            match_log.append({"hand_num": hand_num, "seat": seat, "bot_id": bid,
                              "action": action.get("action"),
                              "amount": action.get("amount")})
            state = engine.apply_action(seat, action)
            if state.get("type") == "action_request":
                state["match_action_log"] = match_log[-MATCH_LOG_MAX:]
            steps += 1
            if steps > 1500:
                break
        for bid, s in state["final_stacks"].items():
            stacks[bid] = s
        dealer += 1

    return {b: stacks[b] - STARTING_STACK for b in bot_ids}


# ─── Tournament ─────────────────────────────────────────────────────────────

def run_tournament(bots, paths, rounds=5, hands=400, seed=None, verbose=True):
    bot_ids = list(bots.keys())
    rng = random.Random(seed)

    # Round 1 — random shuffle then table_size groups (no standings yet)
    shuffled = bot_ids[:]
    rng.shuffle(shuffled)

    cumulative = {b: 0 for b in bot_ids}
    matches_played = {b: 0 for b in bot_ids}
    best_match = {b: -10_000 for b in bot_ids}
    error_counts = {}
    all_match_results = []

    for rnd in range(1, rounds + 1):
        if rnd == 1:
            # First round: random tables
            tables = []
            i = 0
            while i < len(shuffled):
                remaining = len(shuffled) - i
                if remaining < TABLE_SIZE and tables:
                    tables[-1].extend([{"bot_id": b, "bot_path": str(paths[b])} for b in shuffled[i:]])
                    break
                tables.append([{"bot_id": b, "bot_path": str(paths[b])}
                               for b in shuffled[i:i + TABLE_SIZE]])
                i += TABLE_SIZE
        else:
            standings = [{
                "bot_id": b,
                "bot_path": str(paths[b]),
                "cumulative_delta": cumulative[b],
            } for b in bot_ids]
            tables = swiss_pairing(standings, table_size=TABLE_SIZE)

        if verbose:
            print(f"\n  -- Round {rnd}/{rounds}: {len(tables)} tables --", flush=True)
        rnd_t0 = time.time()
        for ti, table in enumerate(tables):
            tbl_ids = [t["bot_id"] for t in table]
            mid = f"r{rnd}_t{ti}"
            t0 = time.time()
            deltas = play_match(mid, tbl_ids, bots, hands=hands,
                                seed=(seed + rnd * 1000 + ti) if seed is not None else None,
                                error_counts=error_counts)
            elapsed = time.time() - t0
            for bid, d in deltas.items():
                cumulative[bid] += d
                matches_played[bid] += 1
                if d > best_match[bid]:
                    best_match[bid] = d
                all_match_results.append({"bot_id": bid, "bot_path": str(paths[bid]),
                                          "chip_delta": d})
            if verbose and APEX_BOT_ID in tbl_ids:
                d = deltas[APEX_BOT_ID]
                print(f"    table {ti}: {tbl_ids} ({elapsed:.1f}s, "
                      f"apex d={d:+d}, cum={cumulative[APEX_BOT_ID]:+d})",
                      flush=True)
        if verbose:
            print(f"  round {rnd} done in {time.time()-rnd_t0:.1f}s", flush=True)

    standings = compute_standings(all_match_results)
    return standings, error_counts


# ─── Reporting ──────────────────────────────────────────────────────────────

def print_standings(standings, highlight=APEX_BOT_ID):
    print()
    print(f"{'Rank':>4}  {'Bot':<24} {'CumDelta':>10} {'Matches':>8} {'BestDelta':>10}")
    print("-" * 64)
    for i, s in enumerate(standings, start=1):
        marker = "  <<< APEX" if s["bot_id"] == highlight else ""
        cut = " (cut)" if i <= TOP_CUT else ""
        print(f"{i:>4}  {s['bot_id']:<24} {s['cumulative_delta']:>+10d} "
              f"{s['matches_played']:>8d} {s['best_match_delta']:>+10d}{marker}{cut}")


def apex_summary(standings, errors):
    rank = next(i for i, s in enumerate(standings, 1)
                if s["bot_id"] == APEX_BOT_ID)
    apex = next(s for s in standings if s["bot_id"] == APEX_BOT_ID)
    in_cut = rank <= TOP_CUT
    print()
    print("=" * 64)
    print(f"  APEX  rank={rank}/{len(standings)}  "
          f"cum_delta={apex['cumulative_delta']:+d}  "
          f"matches={apex['matches_played']}  "
          f"best={apex['best_match_delta']:+d}  "
          f"top-{TOP_CUT}={'YES' if in_cut else 'NO'}")
    print("=" * 64)
    if errors:
        top_err = sorted(errors.items(), key=lambda kv: -kv[1])[:8]
        print(f"\n  Bot errors (auto-folds): {sum(errors.values())} total across "
              f"{len(errors)} bots")
        for bid, n in top_err:
            print(f"    {bid:<24} {n}")
    return rank, apex["cumulative_delta"], in_cut


# ─── Multi-tournament summary ───────────────────────────────────────────────

def print_repeat_summary(results, n_field):
    """results: list of (rank, cum_delta, in_cut)."""
    ranks = [r[0] for r in results]
    deltas = [r[1] for r in results]
    cuts = sum(1 for r in results if r[2])
    print()
    print("=" * 64)
    print(f"  REPEAT SUMMARY ({len(results)} tournaments, field={n_field})")
    print("-" * 64)
    print(f"  Apex rank   mean={sum(ranks)/len(ranks):.1f}  "
          f"median={sorted(ranks)[len(ranks)//2]}  "
          f"best={min(ranks)}  worst={max(ranks)}")
    print(f"  Cum delta   mean={sum(deltas)/len(deltas):+.0f}  "
          f"min={min(deltas):+d}  max={max(deltas):+d}")
    print(f"  Top-{TOP_CUT} hit-rate: {cuts}/{len(results)} = "
          f"{cuts/len(results)*100:.0f}%")
    print()
    # Histogram
    print("  Rank histogram:")
    bins = [(1, 5), (6, 10), (11, 20), (21, 32), (33, 48), (49, 64), (65, 99)]
    for lo, hi in bins:
        cnt = sum(1 for r in ranks if lo <= r <= hi)
        bar = "#" * cnt
        print(f"    {lo:>3}-{hi:<3}  {cnt:>3}  {bar}")
    print("=" * 64)


# ─── Main ───────────────────────────────────────────────────────────────────

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--rounds", type=int, default=5)
    ap.add_argument("--hands", type=int, default=400)
    ap.add_argument("--repeat", type=int, default=1)
    ap.add_argument("--seed", type=int, default=None)
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args()

    print("Discovering bots...")
    paths = discover_bots()
    print(f"  Found {len(paths)} bots")
    if APEX_BOT_ID not in paths:
        print(f"  ERROR: Apex ({APEX_BOT_ID}) not found", file=sys.stderr)
        sys.exit(1)

    print("Loading bots (Apex precompute may take ~22s)...", flush=True)
    t0 = time.time()
    bots = load_field(paths)
    print(f"  Loaded {len(bots)}/{len(paths)} bots in {time.time()-t0:.1f}s",
          flush=True)

    if args.repeat == 1:
        standings, errors = run_tournament(bots, paths, rounds=args.rounds,
                                           hands=args.hands, seed=args.seed,
                                           verbose=not args.quiet)
        print_standings(standings)
        apex_summary(standings, errors)
    else:
        results = []
        all_errors = {}
        for run in range(1, args.repeat + 1):
            print(f"\n========== Tournament {run}/{args.repeat} ==========",
                  flush=True)
            t0 = time.time()
            run_seed = (args.seed + run * 7919) if args.seed is not None else None
            standings, errors = run_tournament(bots, paths,
                                               rounds=args.rounds,
                                               hands=args.hands,
                                               seed=run_seed,
                                               verbose=not args.quiet)
            for k, v in errors.items():
                all_errors[k] = all_errors.get(k, 0) + v
            r = apex_summary(standings, errors)
            results.append(r)
            print(f"  Tournament {run} took {time.time()-t0:.1f}s", flush=True)
        print_repeat_summary(results, len(bots))
        if all_errors:
            print(f"\nTotal bot errors across all tournaments: {sum(all_errors.values())}")


if __name__ == "__main__":
    main()
