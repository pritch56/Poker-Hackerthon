"""A/B test for four Apex configurations on identical engine seeds:

  current     — full stack (Tier 2 + deep profiler + predictive model)
  tier2       — Tier 2 only (deep profiler/predictive disabled by toggle)
  hybrid_50   — Tier 2 for first 50 hands, then full stack
  hybrid_100  — Tier 2 for first 100 hands, then full stack

Reports per-version mean / median / busts / bust-distribution from N matches.

Usage:  python tests/run_ab_versions.py --matches 30
"""

import argparse
import importlib.util
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from engine.game import PokerEngine, STARTING_STACK


def load_bot(path):
    spec = importlib.util.spec_from_file_location(f"bot_{Path(path).parent.name}", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def warmup(bot):
    try:
        bot.decide({"type": "warmup"})
    except Exception:
        pass


def run_match(bots, seed, hands=400):
    bot_ids = list(bots.keys())
    stacks = {b: STARTING_STACK for b in bot_ids}
    match_log = []
    dealer = 0
    for hand_num in range(hands):
        alive = [b for b in bot_ids if stacks[b] > 0]
        if len(alive) < 2:
            break
        engine = PokerEngine(
            hand_id=f"h{hand_num}", bot_ids=alive,
            dealer_seat=dealer % len(alive),
            starting_stacks={b: stacks[b] for b in alive},
            seed=seed * 1000003 + hand_num,
        )
        state = engine.start_hand()
        state["match_action_log"] = match_log[-200:]
        steps = 0
        while state.get("type") == "action_request":
            seat = state["seat_to_act"]
            bid = alive[seat]
            try:
                action = bots[bid].decide(state)
            except Exception:
                action = {"action": "fold"}
            if not isinstance(action, dict) or "action" not in action:
                action = {"action": "fold"}
            match_log.append({
                "hand_num": hand_num, "seat": seat, "bot_id": bid,
                "action": action.get("action"), "amount": action.get("amount"),
            })
            state = engine.apply_action(seat, action)
            if state.get("type") == "action_request":
                state["match_action_log"] = match_log[-200:]
            steps += 1
            if steps > 1000:
                break
        for bid, s in state["final_stacks"].items():
            stacks[bid] = s
        dealer += 1
    return stacks


VERSIONS = [
    ("current",    0),
    ("tier2",      1000),
    ("hybrid_50",  50),
    ("hybrid_100", 100),
]


def summarise(name, deltas):
    n = len(deltas)
    avg = sum(deltas) / n
    busts = sum(1 for d in deltas if d == -STARTING_STACK)
    sorted_d = sorted(deltas)
    median = sorted_d[n // 2]
    print(f"\n  === {name} ===")
    print(f"    N={n}  avg={avg:+.0f}  median={median:+d}  "
          f"min={sorted_d[0]:+d}  max={sorted_d[-1]:+d}  busts={busts}/{n}")
    print(f"    sorted: {sorted_d}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--matches", type=int, default=30)
    ap.add_argument("--hands", type=int, default=400)
    ap.add_argument("--seed-base", type=int, default=0)
    args = ap.parse_args()

    print("Loading bots (Apex precompute ~22s)...", flush=True)
    t0 = time.time()
    apex = load_bot(REPO / "bots" / "mybot" / "bot.py")
    refs = {
        "shark":         load_bot(REPO / "bots" / "shark" / "bot.py"),
        "aggressor":     load_bot(REPO / "bots" / "aggressor" / "bot.py"),
        "mathematician": load_bot(REPO / "bots" / "mathematician" / "bot.py"),
        "template":      load_bot(REPO / "bots" / "template" / "bot.py"),
        "ref_bot_2":     load_bot(REPO / "bots" / "ref_bot_2" / "bot.py"),
    }
    warmup(apex)
    for r in refs.values():
        warmup(r)
    print(f"  loaded in {time.time()-t0:.1f}s", flush=True)

    bots = {"mybot": apex, **refs}

    results = {}
    for version_name, deep_after in VERSIONS:
        print(f"\n========== {version_name} (deep_after={deep_after}) ==========",
              flush=True)
        apex._DEEP_AFTER_HAND = deep_after
        deltas = []
        v_t0 = time.time()
        for i in range(args.matches):
            apex._reset_match_state()
            seed = args.seed_base + i
            stacks = run_match(bots, seed, hands=args.hands)
            d = stacks["mybot"] - STARTING_STACK
            deltas.append(d)
            if (i + 1) % 5 == 0 or i == args.matches - 1:
                running = sum(deltas) / len(deltas)
                print(f"  match {i+1}/{args.matches} d={d:+d} (avg so far: {running:+.0f})",
                      flush=True)
        results[version_name] = deltas
        summarise(version_name, deltas)
        print(f"  {version_name} took {time.time()-v_t0:.1f}s")

    # Final comparison table
    print("\n" + "=" * 70)
    print("  FINAL COMPARISON  (identical seeds across all versions)")
    print("=" * 70)
    print(f"  {'Version':<14} {'Avg':>10} {'Median':>10} {'Min':>10} {'Max':>10} {'Busts':>8}")
    print("  " + "-" * 64)
    for name in [v[0] for v in VERSIONS]:
        d = results[name]
        n = len(d)
        avg = sum(d) / n
        sd = sorted(d)
        busts = sum(1 for x in d if x == -STARTING_STACK)
        print(f"  {name:<14} {avg:>+10.0f} {sd[n//2]:>+10d} "
              f"{sd[0]:>+10d} {sd[-1]:>+10d} {busts:>4}/{n}")

    # Per-seed head-to-head: how often does each version win?
    print()
    print("  Seed-by-seed head-to-head (which version delivered the highest delta?)")
    wins = {name: 0 for name, _ in VERSIONS}
    ties = 0
    for i in range(args.matches):
        scores = [(name, results[name][i]) for name, _ in VERSIONS]
        max_score = max(s for _, s in scores)
        winners = [n for n, s in scores if s == max_score]
        if len(winners) > 1:
            ties += 1
        for w in winners:
            wins[w] += 1.0 / len(winners)
    for name, _ in VERSIONS:
        print(f"    {name:<14} won {wins[name]:>5.1f} / {args.matches}  "
              f"({wins[name]/args.matches*100:.0f}%)")
    if ties:
        print(f"    ties: {ties}")


if __name__ == "__main__":
    main()
