"""
main.py — Orchestrator for aina (AI 4 aNAlog)
=============================================
Boots the environment, triggers the agent brain, and drives the agentic
loop to completion. Prints a rich terminal trace and a results summary.

Usage:
    python main.py [--mock] [--max-iters N] [--target-gain G] [--model M]

Flags:
    --mock         Force the analytic mock simulator (no Ngspice needed).
    --max-iters N  Maximum iterations before giving up (default: 10).
    --target-gain G  Target gain in dB (default: 20.0).
    --model M      Ollama model name (default: qwen2.5:7b).
"""

import argparse
import logging
import os
import sys
import textwrap

from circuit_env import BasicCircuitEnv
from agent_brain import AgentBrain, IterationResult

# ---------------------------------------------------------------------------
# Terminal colour helpers (no external deps — pure ANSI)
# ---------------------------------------------------------------------------

RESET  = "\033[0m"
BOLD   = "\033[1m"
GREEN  = "\033[92m"
YELLOW = "\033[93m"
RED    = "\033[91m"
CYAN   = "\033[96m"
DIM    = "\033[2m"
BLUE   = "\033[94m"


def _c(text: str, *codes: str) -> str:
    """Wrap text in ANSI codes (only when stdout is a TTY)."""
    if not sys.stdout.isatty():
        return text
    return "".join(codes) + str(text) + RESET


def _bar(char: str = "─", width: int = 68) -> str:
    return _c(char * width, DIM)


# ---------------------------------------------------------------------------
# Formatting helpers
# ---------------------------------------------------------------------------

def _gain_colour(gain: float, target: float) -> str:
    if gain >= target:
        return _c(f"{gain:+.2f} dB", BOLD, GREEN)
    elif gain >= target * 0.85:
        return _c(f"{gain:+.2f} dB", YELLOW)
    return _c(f"{gain:+.2f} dB", RED)


def _print_iteration(res: IterationResult, target: float) -> None:
    """Pretty-print a single iteration result to stdout."""
    hdr = _c(f"  Iteration {res.iteration}", BOLD, CYAN)
    print(f"\n{_bar()}")
    print(hdr)
    print(_bar())

    # Parameters chosen
    print(f"  {'W':>10} = {_c(f'{res.w:.2f} um', BOLD)}")
    print(f"  {'L':>10} = {_c(f'{res.l:.2f} um', BOLD)}")

    if res.sim_status == "SUCCESS":
        print(f"  {'Gain':>10} = {_gain_colour(res.gain, target)}")
        print(f"  {'C_para':>10} = {_c(f'{res.parasitic:.2f} fF', BOLD)}")
        print(f"  {'Sim mode':>10} = {_c(res.sim_mode, DIM)}")
    else:
        print(f"  {'Status':>10} = {_c(res.sim_status, RED, BOLD)}")

    # Agent reasoning (wrapped to 64 chars)
    if res.reasoning:
        print(f"\n  {_c('Agent reasoning:', BOLD, BLUE)}")
        wrapped = textwrap.fill(res.reasoning, width=64, initial_indent="    ", subsequent_indent="    ")
        print(_c(wrapped, DIM))

    if res.goal_reached:
        banner = "  ✓  Design Verified: Goal Reached  ✓"
        print(f"\n  {_c(banner, BOLD, GREEN)}")


def _print_summary(history: list[IterationResult], target: float) -> None:
    """Print a tabular summary of all iterations."""
    print(f"\n{_bar('═')}")
    print(_c("  RESULTS SUMMARY", BOLD))
    print(_bar('═'))

    header = f"  {'Iter':>4}  {'W (um)':>8}  {'L (um)':>8}  {'Gain (dB)':>10}  {'C_para (fF)':>12}  {'Status'}"
    print(_c(header, BOLD))
    print(_bar())

    for r in history:
        gain_str = f"{r.gain:>+.2f}" if r.gain is not None else "    N/A"
        para_str = f"{r.parasitic:>8.2f}" if r.parasitic is not None else "     N/A"
        status   = "✓ GOAL MET" if r.goal_reached else r.sim_status

        row = f"  {r.iteration:>4}  {r.w:>8.2f}  {r.l:>8.2f}  {gain_str:>10}  {para_str:>12}  {status}"
        if r.goal_reached:
            print(_c(row, GREEN, BOLD))
        elif r.sim_status == "SUCCESS":
            print(row)
        else:
            print(_c(row, RED))

    print(_bar('═'))

    # Final verdict
    solved = any(r.goal_reached for r in history)
    if solved:
        winning = next(r for r in history if r.goal_reached)
        msg = (
            f"  Converged in {winning.iteration} iteration(s). "
            f"Final: W={winning.w:.2f} um, L={winning.l:.2f} um, "
            f"Gain={winning.gain:.2f} dB"
        )
        print(_c(msg, BOLD, GREEN))
    else:
        print(_c(f"  Agent did NOT meet the {target:.1f} dB target within {len(history)} iterations.", RED, BOLD))
    print(_bar('═'))


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="aina (AI 4 aNAlog): Autonomous Transistor Sizing with Agentic Feedback",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    p.add_argument("--mock",        action="store_true",  help="Force analytic mock (no Ngspice required)")
    p.add_argument("--max-iters",   type=int,   default=10,   metavar="N", help="Max agentic iterations")
    p.add_argument("--target-gain", type=float, default=20.0, metavar="G", help="Target gain in dB")
    p.add_argument("--model",       type=str,   default="qwen2.5:7b", help="Ollama LLM model name")
    p.add_argument("--verbose",     action="store_true",  help="Enable debug logging")
    return p.parse_args()


def main() -> int:
    args = parse_args()

    # ── Logging ──────────────────────────────────────────────────────────────
    log_level = logging.DEBUG if args.verbose else logging.WARNING
    logging.basicConfig(
        level   = log_level,
        format  = "%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
        datefmt = "%H:%M:%S",
    )

    # ── Banner ────────────────────────────────────────────────────────────────
    print(_c("\n  ╔══════════════════════════════════════════╗", CYAN))
    print(_c("  ║              aina  v1.0                  ║", CYAN, BOLD))
    print(_c("  ║   AI4aNAlog: Autonomous SPICE Sizing     ║", CYAN))
    print(_c("  ╚══════════════════════════════════════════╝", CYAN))
    print(f"\n  Target gain : {_c(f'>= {args.target_gain:.1f} dB', BOLD, GREEN)}")
    print(f"  Max iters   : {_c(str(args.max_iters), BOLD)}")
    print(f"  LLM model   : {_c(args.model, BOLD)}")

    # ── Environment ───────────────────────────────────────────────────────────
    try:
        env = BasicCircuitEnv(use_mock=True if args.mock else None)
    except EnvironmentError as exc:
        print(_c(f"\n  [ERROR] {exc}", RED, BOLD))
        return 1

    print(f"  Sim mode    : {_c(env.mode, BOLD)}")

    # ── Agent ─────────────────────────────────────────────────────────────────
    try:
        brain = AgentBrain(
            env         = env,
            max_iters   = args.max_iters,
            target_gain = args.target_gain,
            model       = args.model,
        )
    except EnvironmentError as exc:
        print(_c(f"\n  [ERROR] {exc}", RED, BOLD))
        return 1

    # ── Agentic loop ──────────────────────────────────────────────────────────
    print(f"\n{_bar('─')}")
    print(_c("  Starting agentic loop…", BOLD))

    history: list[IterationResult] = []

    # We hook into AgentBrain._step to print results as they arrive
    original_step = brain._step

    def _traced_step(iteration: int) -> IterationResult:
        result = original_step(iteration)
        _print_iteration(result, args.target_gain)
        return result

    brain._step = _traced_step

    try:
        history = brain.run()
    except KeyboardInterrupt:
        print(_c("\n\n  Interrupted by user.", YELLOW))
    except Exception as exc:
        print(_c(f"\n  [FATAL] {exc}", RED, BOLD))
        if args.verbose:
            import traceback
            traceback.print_exc()
        return 1

    # ── Summary ───────────────────────────────────────────────────────────────
    if history:
        _print_summary(history, args.target_gain)

    return 0 if any(r.goal_reached for r in history) else 2


if __name__ == "__main__":
    sys.exit(main())
