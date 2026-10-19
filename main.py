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
from agent_brain import AgentBrain, IterationResult, MockAgentBrain
from tracer import ObservabilityTracer

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
MAGENTA= "\033[95m"


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
    w_over_l = (res.w / res.l) if res.l > 0 else 0.0
    print(f"  {'W':>12} = {_c(f'{res.w:.2f} um', BOLD)}   {'L':>6} = {_c(f'{res.l:.2f} um', BOLD)}  (W/L = {w_over_l:.1f})")

    if res.sim_status == "SUCCESS":
        print(f"  {'Gain':>12} = {_gain_colour(res.gain, target)}")
        print(f"  {'C_para':>12} = {_c(f'{res.parasitic:.2f} fF', BOLD)}")
        if res.vout_dc is not None:
            print(f"  {'Vout (DC)':>12} = {_c(f'{res.vout_dc:.3f} V', BOLD)} (Vds saturation >= 0.3V: {_c('PASS', GREEN)})")
        print(f"  {'Sim mode':>12} = {_c(res.sim_mode, DIM)}")
    else:
        status_color = RED if res.sim_status in ("SIMULATION_FAILED", "PARSING_ERROR") else YELLOW
        print(f"  {'Status':>12} = {_c(res.sim_status, status_color, BOLD)}")
        if res.error_type:
            print(f"  {'Error Type':>12} = {_c(res.error_type, RED, BOLD)}")
        if res.vout_dc is not None:
            print(f"  {'Vout (DC)':>12} = {_c(f'{res.vout_dc:.3f} V', RED, BOLD)} (Vds < 0.3V -> {_c('TRIODE COLLAPSE', RED, BOLD)})")
        if res.diagnostic:
            print(f"\n  {_c('Diagnostic:', BOLD, RED)}")
            diag_wrapped = textwrap.fill(res.diagnostic, width=64, initial_indent="    ", subsequent_indent="    ")
            print(_c(diag_wrapped, RED))
        if res.suggested_action:
            print(f"\n  {_c('Recovery Hint:', BOLD, YELLOW)}")
            rec_wrapped = textwrap.fill(res.suggested_action, width=64, initial_indent="    ", subsequent_indent="    ")
            print(_c(rec_wrapped, YELLOW))

    # Telemetry
    if res.tokens and res.latency_ms is not None:
        p_tok = res.tokens.get("prompt", 0)
        c_tok = res.tokens.get("completion", 0)
        tot_tok = res.tokens.get("total", p_tok + c_tok)
        telemetry_str = f"Tokens: {tot_tok} ({p_tok} in / {c_tok} out) | Latency: {res.latency_ms/1000.0:.2f}s"
        print(f"  {'Telemetry':>12} = {_c(telemetry_str, DIM, MAGENTA)}")

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
    p.add_argument("--demo",        action="store_true",  help="Run instant demo mode with simulated LLM & mock SPICE (zero local setup required)")
    p.add_argument("--mock",        action="store_true",  help="Force analytic mock simulator (no Ngspice required)")
    p.add_argument("--max-iters",   type=int,   default=10,   metavar="N", help="Max agentic iterations")
    p.add_argument("--target-gain", type=float, default=20.0, metavar="G", help="Target gain in dB")
    p.add_argument("--model",       type=str,   default="qwen2.5:7b", help="Ollama LLM model name")
    p.add_argument("--phoenix",     action="store_true",  help="Launch Arize Phoenix local observability UI & trace LLM calls")
    p.add_argument("--trace-dir",   type=str,   default="traces", help="Directory to save structured JSONL telemetry logs")
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
    if args.demo:
        print(_c("  Mode        : Instant Demo (Zero Local Setup Required)", BOLD, MAGENTA))
    print(f"\n  Target gain : {_c(f'>= {args.target_gain:.1f} dB', BOLD, GREEN)}")
    print(f"  Max iters   : {_c(str(args.max_iters), BOLD)}")
    print(f"  LLM model   : {_c('mock-qwen2.5:7b' if args.demo else args.model, BOLD)}")

    # ── Observability & Tracing ──────────────────────────────────────────────
    tracer = ObservabilityTracer(
        trace_dir=args.trace_dir,
        enable_phoenix=args.phoenix,
    )
    print(f"  Trace file  : {_c(str(tracer.trace_file), DIM)}")
    if tracer.phoenix_url:
        print(f"  Phoenix UI  : {_c(tracer.phoenix_url, BOLD, CYAN)}")

    # ── Environment ───────────────────────────────────────────────────────────
    try:
        use_mock = True if (args.mock or args.demo) else None
        env = BasicCircuitEnv(use_mock=use_mock)
    except EnvironmentError as exc:
        print(_c(f"\n  [ERROR] {exc}", RED, BOLD))
        return 1

    print(f"  Sim mode    : {_c(env.mode, BOLD)}")

    # ── Agent ─────────────────────────────────────────────────────────────────
    if args.demo:
        brain = MockAgentBrain(
            env         = env,
            max_iters   = args.max_iters,
            target_gain = args.target_gain,
            model       = "mock-qwen2.5:7b",
            tracer      = tracer,
        )
    else:
        try:
            brain = AgentBrain(
                env         = env,
                max_iters   = args.max_iters,
                target_gain = args.target_gain,
                model       = args.model,
                tracer      = tracer,
            )
        except EnvironmentError as exc:
            print(_c(f"\n  [ERROR] {exc}", RED, BOLD))
            return 1

    # ── Agentic loop ──────────────────────────────────────────────────────────
    print(f"\n{_bar('─')}")
    print(_c("  Starting agentic loop…", BOLD))

    history: list[IterationResult] = []

    # We hook into brain._step to print results as they arrive
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
        err_msg = str(exc)
        if any(term in err_msg for term in ["Connection error", "ConnectError", "11434", "connection refused", "Failed to connect"]):
            print(_c("\n  [ERROR] Could not connect to Ollama at http://localhost:11434.", RED, BOLD))
            print(_c("  Ollama is required for live LLM execution ('ollama serve' && 'ollama pull qwen2.5:7b').", YELLOW))
            print(_c("\n  💡 Instant Demo / No-Prerequisite Mode:", BOLD, GREEN))
            print(_c("     To test the complete agent loop without running Ollama or compiling Ngspice, run:", GREEN))
            print(_c("       python main.py --demo", BOLD, GREEN))
            print(_c("     Or run the dynamic validation suite:", GREEN))
            print(_c("       python validate.py", BOLD, GREEN))
            return 1

        print(_c(f"\n  [FATAL] {exc}", RED, BOLD))
        if args.verbose:
            import traceback
            traceback.print_exc()
        return 1

    # ── Summary & Observability Telemetry ─────────────────────────────────────
    solved = any(r.goal_reached for r in history)
    if history:
        _print_summary(history, args.target_gain)

    tracer.print_summary(solved=solved)

    return 0 if solved else 2


if __name__ == "__main__":
    sys.exit(main())

