"""Swiss-format stress tournament for the Apex bot.

Loads:
  * bots/mybot/bot.py                        (the Apex bot — focus of the test)
  * bots/{shark,aggressor,mathematician,template,ref_bot_2}/bot.py
  * bots/stress/*/bot.py                     (~60 archetype variants)

Plays N Swiss rounds of 400-hand 6-bot matches, prints the full final
standings, and highlights Apex's rank / cumulative delta / top-64 status.
With --repeat > 1, runs the whole tournament multiple times and reports
the rank distribution including mean, std-dev, and a 95% CI.

Parallelism: matches within a round are run concurrently using
ThreadPoolExecutor (bots release the GIL during eval7 C-extension calls,
so there is real speedup on multi-core machines).

Usage:
  python tests/run_stress_tournament.py --rounds 5 --hands 400 --repeat 1
  python tests/run_stress_tournament.py --quick              # 2 rounds, 200 hands
  python tests/run_stress_tournament.py --baseline 5000      # exit 1 if mean delta < 5000
  python tests/run_stress_tournament.py --workers 4          # parallel match threads
"""

import argparse
import importlib.util
import math
import random
import sys
import time
import traceback
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from engine.game import PokerEngine, STARTING_STACK, BIG_BLIND
from engine.tournament import swiss_pairing, compute_standings

MATCH_LOG_MAX = 200
MATCH_LOG_TRIM = 400   # cap raw list inside play_match to avoid unbounded growth
TABLE_SIZE = 6
APEX_BOT_ID = "mybot"
TOP_CUT = 64
MAX_STEPS_PER_HAND = 1500

# Archetype prefix groups — stress bots are named e.g. "maniac_01"
ARCHETYPE_PREFIXES = {
    "maniac":    "maniac",
    "nit":       "nit",
    "station":   "station",
    "lag":       "lag",
    "tag":       "tag",
    "bluff":     "bluff",
    "overbet":   "overbet",
    "pushfold":  "pushfold",
    "potodds":   "potodds",
    "minraiser": "minraiser",
    "posn":      "posn",
    "random":    "random",
}


# ─── Loading ────────────────────────────────────────────────────────────────

def _load_one(path: Path):
    spec = importlib.util.spec_from_file_location(f"bot_{path.parent.name}", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def discover_bots():
    """Return dict bot_id → Path.  bot_id is the parent directory name."""
    paths = {}
    apex = REPO / "bots" / "mybot" / "bot.py"
    if apex.is_file():
        paths[APEX_BOT_ID] = apex
    for name in ("shark", "aggressor", "mathematician", "template", "ref_bot_2",
                 "equitybot"):
        p = REPO / "bots" / name / "bot.py"
        if p.is_file():
            paths[name] = p
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

def play_match(match_id, bot_ids, bots, hands=400, seed=None, error_counts=None,
               track_times=False):
    """Run a single match.  Returns (chip_delta dict, decision_times dict).

    match_log is capped at MATCH_LOG_TRIM entries to avoid unbounded growth
    across 400 hands.  The engine only ever sees the last MATCH_LOG_MAX entries.
    """
    stacks = {b: STARTING_STACK for b in bot_ids}
    match_log = []
    dealer = 0
    if error_counts is None:
        error_counts = {}
    decision_times = {b: [] for b in bot_ids} if track_times else None

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
            t0 = time.time() if track_times else None
            try:
                action = bots[bid].decide(state)
                if not isinstance(action, dict) or "action" not in action:
                    error_counts[bid] = error_counts.get(bid, 0) + 1
                    action = {"action": "fold"}
            except Exception:
                error_counts[bid] = error_counts.get(bid, 0) + 1
                action = {"action": "fold"}
            if track_times and t0 is not None:
                decision_times[bid].append(time.time() - t0)
            match_log.append({"hand_num": hand_num, "seat": seat, "bot_id": bid,
                               "action": action.get("action"),
                               "amount": action.get("amount")})
            # Cap raw log to avoid unbounded growth
            if len(match_log) > MATCH_LOG_TRIM:
                match_log = match_log[-MATCH_LOG_MAX:]
            state = engine.apply_action(seat, action)
            if state.get("type") == "action_request":
                state["match_action_log"] = match_log[-MATCH_LOG_MAX:]
            steps += 1
            if steps > MAX_STEPS_PER_HAND:
                break
        for bid, s in state["final_stacks"].items():
            stacks[bid] = s
        dealer += 1

    deltas = {b: stacks[b] - STARTING_STACK for b in bot_ids}
    return deltas, decision_times


# ─── Tournament ─────────────────────────────────────────────────────────────

def run_tournament(bots, paths, rounds=5, hands=400, seed=None, verbose=True,
                   workers=1):
    bot_ids = list(bots.keys())
    rng = random.Random(seed)

    shuffled = bot_ids[:]
    rng.shuffle(shuffled)

    cumulative = {b: 0 for b in bot_ids}
    matches_played = {b: 0 for b in bot_ids}
    best_match = {b: -10_000 for b in bot_ids}
    wins = {b: 0 for b in bot_ids}      # times Apex (or any bot) finished 1st at their table
    error_counts = {}
    all_match_results = []
    apex_round_ranks = []               # rank after each round

    # Per-archetype delta accumulator for Apex
    apex_vs_archetype = defaultdict(lambda: [0, 0])  # prefix -> [sum_delta, n_matches]

    for rnd in range(1, rounds + 1):
        if rnd == 1:
            tables = []
            i = 0
            while i < len(shuffled):
                remaining = len(shuffled) - i
                if remaining < TABLE_SIZE and tables:
                    tables[-1].extend([{"bot_id": b, "bot_path": str(paths[b])}
                                       for b in shuffled[i:]])
                    break
                tables.append([{"bot_id": b, "bot_path": str(paths[b])}
                               for b in shuffled[i:i + TABLE_SIZE]])
                i += TABLE_SIZE
        else:
            standings_input = [{
                "bot_id": b,
                "bot_path": str(paths[b]),
                "cumulative_delta": cumulative[b],
            } for b in bot_ids]
            tables = swiss_pairing(standings_input, table_size=TABLE_SIZE)

        if verbose:
            print(f"\n  -- Round {rnd}/{rounds}: {len(tables)} tables "
                  f"({'parallel x' + str(workers) if workers > 1 else 'serial'}) --",
                  flush=True)
        rnd_t0 = time.time()

        def _run_table(args):
            ti, table = args
            tbl_ids = [t["bot_id"] for t in table]
            mid = f"r{rnd}_t{ti}"
            t0 = time.time()
            deltas, _ = play_match(mid, tbl_ids, bots, hands=hands,
                                   seed=(seed + rnd * 1000 + ti) if seed is not None else None,
                                   error_counts=error_counts)
            return ti, tbl_ids, deltas, time.time() - t0

        table_args = list(enumerate(tables))
        if workers > 1:
            futures = []
            with ThreadPoolExecutor(max_workers=workers) as ex:
                futures = {ex.submit(_run_table, a): a for a in table_args}
                results_this_round = [f.result() for f in as_completed(futures)]
        else:
            results_this_round = [_run_table(a) for a in table_args]

        for ti, tbl_ids, deltas, elapsed in results_this_round:
            # Table winner (highest delta)
            table_winner = max(deltas, key=lambda b: deltas[b])
            wins[table_winner] = wins.get(table_winner, 0) + 1

            for bid, d in deltas.items():
                cumulative[bid] += d
                matches_played[bid] += 1
                if d > best_match[bid]:
                    best_match[bid] = d
                all_match_results.append({"bot_id": bid, "bot_path": str(paths.get(bid, "")),
                                          "chip_delta": d})

            if APEX_BOT_ID in tbl_ids:
                d = deltas[APEX_BOT_ID]
                if verbose:
                    print(f"    table {ti}: {tbl_ids} ({elapsed:.1f}s, "
                          f"apex d={d:+d}, cum={cumulative[APEX_BOT_ID]:+d})",
                          flush=True)
                # Attribute this delta to each archetype present at the table
                for opp in tbl_ids:
                    if opp == APEX_BOT_ID:
                        continue
                    prefix = _archetype_prefix(opp)
                    apex_vs_archetype[prefix][0] += d
                    apex_vs_archetype[prefix][1] += 1

        if verbose:
            print(f"  round {rnd} done in {time.time()-rnd_t0:.1f}s", flush=True)

        # Snapshot Apex's rank after this round
        interim = compute_standings(all_match_results)
        apex_rank = next((i for i, s in enumerate(interim, 1)
                          if s["bot_id"] == APEX_BOT_ID), None)
        apex_round_ranks.append(apex_rank)
        if verbose and apex_rank is not None:
            print(f"  Apex rank after round {rnd}: {apex_rank}/{len(bot_ids)}", flush=True)

    standings = compute_standings(all_match_results)
    return standings, error_counts, apex_round_ranks, dict(apex_vs_archetype), wins


def _archetype_prefix(bot_id: str) -> str:
    """Map a stress bot_id like 'maniac_03' to its archetype prefix."""
    for prefix in ARCHETYPE_PREFIXES:
        if bot_id.startswith(prefix):
            return prefix
    # Reference bots get their own group
    for ref in ("shark", "aggressor", "mathematician", "template", "ref_bot_2",
                "equitybot"):
        if bot_id == ref:
            return "reference"
    return "other"


# ─── Reporting ──────────────────────────────────────────────────────────────

def print_standings(standings, highlight=APEX_BOT_ID, top_n=None):
    rows = standings if top_n is None else standings[:top_n]
    n_total = len(standings)
    print()
    print(f"{'Rank':>4}  {'Bot':<24} {'CumDelta':>10} {'Matches':>8} "
          f"{'BestDelta':>10} {'Pct':>6}")
    print("-" * 72)
    for i, s in enumerate(rows, start=1):
        marker = "  <<< APEX" if s["bot_id"] == highlight else ""
        cut = " (cut)" if i <= TOP_CUT else ""
        pct = f"{i / n_total * 100:.0f}%"
        print(f"{i:>4}  {s['bot_id']:<24} {s['cumulative_delta']:>+10d} "
              f"{s['matches_played']:>8d} {s['best_match_delta']:>+10d} "
              f"{pct:>6}{marker}{cut}")


def _bb100(cum_delta: int, matches_played: int, hands_per_match: int) -> float:
    """Big-blinds won per 100 hands (standard poker metric)."""
    total_hands = matches_played * hands_per_match
    if total_hands == 0:
        return 0.0
    return cum_delta / (BIG_BLIND * total_hands) * 100


def apex_summary(standings, errors, round_ranks, vs_archetype, wins, n_field,
                 hands_per_match: int = 400):
    rank = next(i for i, s in enumerate(standings, 1)
                if s["bot_id"] == APEX_BOT_ID)
    apex = next(s for s in standings if s["bot_id"] == APEX_BOT_ID)
    in_cut = rank <= TOP_CUT
    pct = rank / n_field * 100
    bb100 = _bb100(apex["cumulative_delta"], apex["matches_played"], hands_per_match)
    print()
    print("=" * 70)
    print(f"  APEX  rank={rank}/{n_field} ({pct:.0f}th pct)  "
          f"cum_delta={apex['cumulative_delta']:+d}  "
          f"BB/100={bb100:+.1f}  "
          f"matches={apex['matches_played']}  "
          f"table_wins={wins.get(APEX_BOT_ID, 0)}  "
          f"top-{TOP_CUT}={'YES' if in_cut else 'NO'}")

    # Round-by-round rank trend
    if round_ranks:
        trend = " -> ".join(str(r) for r in round_ranks)
        print(f"  Rank trend (by round): {trend}")

    print("=" * 70)

    # Per-archetype breakdown
    if vs_archetype:
        print()
        print("  Apex P&L vs archetype groups:")
        print(f"  {'Archetype':<14} {'AvgDelta/Match':>15} {'Matches':>9}")
        print("  " + "-" * 42)
        for prefix, (total, n) in sorted(vs_archetype.items(), key=lambda kv: -kv[1][0]):
            avg = total / n if n else 0
            print(f"  {prefix:<14} {avg:>+15.0f} {n:>9}")

    # Decision-time warning (if tracked)
    if errors:
        top_err = sorted(errors.items(), key=lambda kv: -kv[1])[:8]
        print(f"\n  Bot errors (auto-folds): {sum(errors.values())} total "
              f"across {len(errors)} bots")
        for bid, n in top_err:
            print(f"    {bid:<24} {n}")

    return rank, apex["cumulative_delta"], in_cut


# ─── Multi-tournament summary ────────────────────────────────────────────────

def _stddev(vals):
    if len(vals) < 2:
        return 0.0
    n = len(vals)
    mean = sum(vals) / n
    return math.sqrt(sum((x - mean) ** 2 for x in vals) / (n - 1))


def print_repeat_summary(results, n_field):
    """results: list of (rank, cum_delta, in_cut)."""
    ranks = [r[0] for r in results]
    deltas = [r[1] for r in results]
    cuts = sum(1 for r in results if r[2])
    n = len(results)
    rank_sd = _stddev(ranks)
    delta_sd = _stddev(deltas)
    # 95% CI = mean ± 1.96 * sd / sqrt(n)
    delta_ci = 1.96 * delta_sd / math.sqrt(n) if n > 1 else 0
    rank_ci  = 1.96 * rank_sd  / math.sqrt(n) if n > 1 else 0

    print()
    print("=" * 70)
    print(f"  REPEAT SUMMARY ({n} tournaments, field={n_field})")
    print("-" * 70)
    print(f"  Apex rank   mean={sum(ranks)/n:.1f} ±{rank_ci:.1f} (95% CI)  "
          f"sd={rank_sd:.1f}  "
          f"median={sorted(ranks)[n//2]}  "
          f"best={min(ranks)}  worst={max(ranks)}")
    print(f"  Cum delta   mean={sum(deltas)/n:+.0f} ±{delta_ci:.0f} (95% CI)  "
          f"sd={delta_sd:.0f}  "
          f"min={min(deltas):+d}  max={max(deltas):+d}")
    print(f"  Top-{TOP_CUT} hit-rate: {cuts}/{n} = {cuts/n*100:.0f}%")
    print()
    print("  Rank histogram:")
    bins = [(1, 5), (6, 10), (11, 20), (21, 32), (33, 48), (49, 64), (65, 99)]
    for lo, hi in bins:
        cnt = sum(1 for r in ranks if lo <= r <= hi)
        bar = "#" * cnt
        print(f"    {lo:>3}-{hi:<3}  {cnt:>3}  {bar}")
    print("=" * 70)
    return sum(deltas) / n  # return mean delta for regression gate


# ─── Decision-time report ────────────────────────────────────────────────────

def run_timing_check(bots, paths, hands=50, seed=42):
    """Run a short match with timing enabled and report p99 latency per bot."""
    bot_ids = list(bots.keys())[:TABLE_SIZE]
    print(f"\n  Timing check ({hands} hands, {len(bot_ids)} bots)...", flush=True)
    _, dtimes = play_match("timing", bot_ids, bots, hands=hands, seed=seed,
                           track_times=True)
    if dtimes is None:
        return
    print(f"  {'Bot':<24} {'avg ms':>9} {'p99 ms':>9} {'max ms':>9} {'calls':>7}")
    print("  " + "-" * 56)
    for bid in sorted(bot_ids, key=lambda b: b == APEX_BOT_ID, reverse=True):
        ts = dtimes.get(bid) or []
        if not ts:
            continue
        avg = sum(ts) / len(ts) * 1000
        s = sorted(ts)
        p99 = s[max(0, int(len(s) * 0.99) - 1)] * 1000
        mx = s[-1] * 1000
        flag = "  *** SLOW ***" if p99 > 500 else ""
        print(f"  {bid:<24} {avg:>9.1f} {p99:>9.1f} {mx:>9.1f} {len(ts):>7}{flag}")


# ─── Heads-up isolation gauntlet ────────────────────────────────────────────

HU_NAMED_BOTS = ("shark", "aggressor", "mathematician", "ref_bot_2", "equitybot")
HU_HANDS      = 2000     # enough hands to get a meaningful BB/100 estimate
HU_SEEDS      = 3        # run each matchup N times with different seeds, average


def run_hu_gauntlet(bots: dict, paths: dict, hands: int = HU_HANDS,
                    seeds: int = HU_SEEDS, workers: int = 1) -> None:
    """
    Run Apex heads-up against each named reference bot.

    Uses multiple seeds to reduce variance, reports BB/100 for each opponent
    plus a combined average.  Heads-up removes multi-way variance so the
    signal is much cleaner than the full-field tournament.
    """
    if APEX_BOT_ID not in bots:
        print("  HU gauntlet: Apex not loaded, skipping.", file=sys.stderr)
        return

    opponents = [b for b in HU_NAMED_BOTS if b in bots]
    if not opponents:
        print("  HU gauntlet: no named opponents loaded.", file=sys.stderr)
        return

    print()
    print("=" * 70)
    print(f"  HEADS-UP GAUNTLET  ({hands} hands × {seeds} seeds per matchup)")
    print(f"  {'Opponent':<20} {'BB/100':>8}  {'AvgDelta':>10}  {'Samples':>8}")
    print("  " + "-" * 52)

    all_bb100 = []

    def _run_hu_seed(args):
        opp, seed_idx = args
        seed = 9999 + seed_idx * 31337
        deltas, _ = play_match(
            f"hu_{opp}_s{seed_idx}", [APEX_BOT_ID, opp], bots,
            hands=hands, seed=seed,
        )
        return opp, deltas.get(APEX_BOT_ID, 0)

    tasks = [(opp, si) for opp in opponents for si in range(seeds)]

    if workers > 1:
        with ThreadPoolExecutor(max_workers=workers) as ex:
            raw = list(ex.map(_run_hu_seed, tasks))
    else:
        raw = [_run_hu_seed(t) for t in tasks]

    # Aggregate per opponent
    opp_deltas: dict = {opp: [] for opp in opponents}
    for opp, d in raw:
        opp_deltas[opp].append(d)

    for opp in opponents:
        ds = opp_deltas[opp]
        avg_delta = sum(ds) / len(ds) if ds else 0
        bb = _bb100(int(avg_delta), 1, hands)
        all_bb100.append(bb)
        marker = "  *** LOSING ***" if bb < 0 else ""
        print(f"  {opp:<20} {bb:>+8.1f}  {avg_delta:>+10.0f}  {len(ds)*hands:>8}{marker}")

    combined = sum(all_bb100) / len(all_bb100) if all_bb100 else 0
    print("  " + "-" * 52)
    print(f"  {'COMBINED avg':<20} {combined:>+8.1f}")
    print("=" * 70)


# ─── Main ───────────────────────────────────────────────────────────────────

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--rounds",   type=int,   default=5)
    ap.add_argument("--hands",    type=int,   default=400)
    ap.add_argument("--repeat",   type=int,   default=1)
    ap.add_argument("--seed",     type=int,   default=None)
    ap.add_argument("--quiet",    action="store_true")
    ap.add_argument("--workers",  type=int,   default=1,
                    help="parallel match threads per round (default: 1 = serial)")
    ap.add_argument("--top",      type=int,   default=None,
                    help="only print top N bots in standings (default: all)")
    ap.add_argument("--quick",    action="store_true",
                    help="shorthand for --rounds 2 --hands 200 --repeat 1")
    ap.add_argument("--timing",   action="store_true",
                    help="run a short timing check before the tournament")
    ap.add_argument("--baseline", type=float, default=None,
                    help="exit 1 if mean cum_delta < BASELINE (regression gate)")
    ap.add_argument("--hu", action="store_true",
                    help="run heads-up gauntlet vs named bots after tournament")
    ap.add_argument("--hu-only", action="store_true",
                    help="run ONLY the heads-up gauntlet (skip full tournament)")
    ap.add_argument("--hu-hands", type=int, default=HU_HANDS,
                    help=f"hands per HU matchup (default: {HU_HANDS})")
    ap.add_argument("--hu-seeds", type=int, default=HU_SEEDS,
                    help=f"seeds per HU matchup (default: {HU_SEEDS})")
    args = ap.parse_args()

    if args.quick:
        args.rounds = 2
        args.hands  = 200

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

    if args.timing:
        run_timing_check(bots, paths)

    if args.hu_only:
        run_hu_gauntlet(bots, paths, hands=args.hu_hands, seeds=args.hu_seeds,
                        workers=args.workers)
        return

    if args.repeat == 1:
        standings, errors, round_ranks, vs_arch, wins = run_tournament(
            bots, paths, rounds=args.rounds, hands=args.hands, seed=args.seed,
            verbose=not args.quiet, workers=args.workers,
        )
        print_standings(standings, top_n=args.top)
        rank, cum_delta, in_cut = apex_summary(
            standings, errors, round_ranks, vs_arch, wins, len(bots),
            hands_per_match=args.hands)

        if args.baseline is not None:
            if cum_delta < args.baseline:
                print(f"\n  REGRESSION: cum_delta {cum_delta:+.0f} < baseline {args.baseline:+.0f}",
                      file=sys.stderr)
                sys.exit(1)
            else:
                print(f"\n  OK: cum_delta {cum_delta:+.0f} >= baseline {args.baseline:+.0f}")

        if args.hu:
            run_hu_gauntlet(bots, paths, hands=args.hu_hands, seeds=args.hu_seeds,
                            workers=args.workers)
    else:
        results = []
        all_errors = {}
        for run in range(1, args.repeat + 1):
            print(f"\n========== Tournament {run}/{args.repeat} ==========", flush=True)
            t0 = time.time()
            run_seed = (args.seed + run * 7919) if args.seed is not None else None
            standings, errors, round_ranks, vs_arch, wins = run_tournament(
                bots, paths, rounds=args.rounds, hands=args.hands, seed=run_seed,
                verbose=not args.quiet, workers=args.workers,
            )
            for k, v in errors.items():
                all_errors[k] = all_errors.get(k, 0) + v
            r = apex_summary(standings, errors, round_ranks, vs_arch, wins, len(bots),
                             hands_per_match=args.hands)
            results.append(r)
            print(f"  Tournament {run} took {time.time()-t0:.1f}s", flush=True)

        mean_delta = print_repeat_summary(results, len(bots))
        if all_errors:
            print(f"\nTotal bot errors across all tournaments: {sum(all_errors.values())}")

        if args.baseline is not None:
            if mean_delta < args.baseline:
                print(f"\n  REGRESSION: mean delta {mean_delta:+.0f} < baseline {args.baseline:+.0f}",
                      file=sys.stderr)
                sys.exit(1)
            else:
                print(f"\n  OK: mean delta {mean_delta:+.0f} >= baseline {args.baseline:+.0f}")

        if args.hu:
            run_hu_gauntlet(bots, paths, hands=args.hu_hands, seeds=args.hu_seeds,
                            workers=args.workers)


if __name__ == "__main__":
    main()
