"""In-process match runner for Windows dev (avoids signal.SIGALRM in runner.py).

Usage:
    python tests/run_local_match.py --hands 400 \
        bots/mybot/bot.py bots/shark/bot.py bots/aggressor/bot.py \
        bots/mathematician/bot.py bots/template/bot.py bots/ref_bot_2/bot.py
"""

import sys
import os
import argparse
import importlib.util
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from engine.game import PokerEngine, STARTING_STACK

MATCH_LOG_MAX_ENTRIES = 200


def load_bot(path):
    spec = importlib.util.spec_from_file_location(f"bot_{Path(path).parent.name}", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def run_match(bot_paths, n_hands=400, seed=None, verbose=False):
    bots = {}
    for bid, path in bot_paths.items():
        try:
            bots[bid] = load_bot(path)
            # warmup (ignored if it fails)
            try:
                bots[bid].decide({"type": "warmup"})
            except Exception:
                pass
        except Exception as e:
            print(f"  failed to load {bid}: {e}", file=sys.stderr)

    bot_ids = list(bots.keys())
    stacks = {b: STARTING_STACK for b in bot_ids}
    match_log = []
    dealer = 0
    decision_times = {b: [] for b in bot_ids}
    errors = {b: 0 for b in bot_ids}

    for hand_num in range(n_hands):
        alive = [b for b in bot_ids if stacks[b] > 0]
        if len(alive) < 2:
            break
        hand_id = f"local_h{hand_num:04d}"
        engine = PokerEngine(
            hand_id=hand_id,
            bot_ids=alive,
            dealer_seat=dealer % len(alive),
            starting_stacks={b: stacks[b] for b in alive},
            seed=(seed * 1000003 + hand_num) if seed is not None else None,
        )
        state = engine.start_hand()
        state["match_action_log"] = match_log[-MATCH_LOG_MAX_ENTRIES:]

        steps = 0
        while state.get("type") == "action_request":
            seat = state["seat_to_act"]
            bid = alive[seat]
            t0 = time.time()
            try:
                action = bots[bid].decide(state)
                if not isinstance(action, dict) or "action" not in action:
                    action = {"action": "fold"}
            except Exception as e:
                errors[bid] += 1
                action = {"action": "fold"}
            decision_times[bid].append(time.time() - t0)

            match_log.append({
                "hand_num": hand_num, "seat": seat, "bot_id": bid,
                "action": action.get("action"), "amount": action.get("amount"),
            })
            state = engine.apply_action(seat, action)
            if state.get("type") == "action_request":
                state["match_action_log"] = match_log[-MATCH_LOG_MAX_ENTRIES:]
            steps += 1
            if steps > 1000:
                break

        for bid, s in state["final_stacks"].items():
            stacks[bid] = s
        dealer += 1

        if verbose and hand_num % 50 == 49:
            print(f"  Hand {hand_num+1}/{n_hands}: " +
                  ", ".join(f"{b}={stacks[b]}" for b in bot_ids))

    return stacks, decision_times, errors


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("bots", nargs="+")
    ap.add_argument("--hands", type=int, default=400)
    ap.add_argument("--seed", type=int, default=None)
    ap.add_argument("--verbose", action="store_true")
    args = ap.parse_args()

    paths = {}
    for path in args.bots:
        p = Path(path)
        bid = p.parent.name if p.parent.name and p.parent.name != "bots" else p.stem
        if bid in paths:
            bid = bid + "_" + str(len(paths))
        paths[bid] = path

    print(f"Match: {len(paths)} bots, {args.hands} hands, seed={args.seed}")
    t0 = time.time()
    stacks, times, errors = run_match(paths, args.hands, args.seed, args.verbose)
    elapsed = time.time() - t0

    print(f"\nMatch complete in {elapsed:.1f}s")
    print(f"{'Bot':<20} {'Stack':>10} {'delta':>10} {'avg ms':>9} {'p99 ms':>9} {'errs':>6}")
    print("-" * 72)
    for bid in sorted(stacks, key=lambda b: -stacks[b]):
        ts = times[bid] or [0]
        avg = sum(ts) / len(ts) * 1000
        p99 = sorted(ts)[int(len(ts) * 0.99)] * 1000 if ts else 0
        delta = stacks[bid] - STARTING_STACK
        sign = "+" if delta >= 0 else ""
        print(f"{bid:<20} {stacks[bid]:>10} {sign}{delta:>9} {avg:>9.2f} {p99:>9.2f} {errors[bid]:>6}")


if __name__ == "__main__":
    main()
