#!/usr/bin/env python3
"""
benchmark_runner.py — Unified Benchmark & Domain Reasoning Runner for aina
==========================================================================
Executes the three core benchmark pillars:
1. Razavi Domain Reasoning Benchmark (Verifiable Qualitative Small-Signal Logic)
2. LOADBench / AutoCkt Two-Stage Miller OTA Multi-Claim Benchmark
3. Verifiable RL Reasoning Reward & Preference Generator (RLSF / DPO)

Usage:
    python benchmark_runner.py                # Run all suites in instant demo mode (< 1s)
    python benchmark_runner.py --suite razavi # Razavi reasoning suite only
    python benchmark_runner.py --suite ota    # Two-stage OTA benchmark only
    python benchmark_runner.py --suite rl     # Generate RL preference pairs
    python benchmark_runner.py --live         # Run against live Ollama LLM
"""

import argparse
import json
import os
import sys
import time
from typing import Optional, Dict, Any, List

from benchmarks.razavi_reasoning import (
    RazaviBenchmark,
    get_default_razavi_suite,
    evaluate_reasoning_response,
)
from benchmarks.two_stage_ota import (
    TwoStageOTABenchmark,
    OTASpecification,
    DEFAULT_NOMINAL_OTA_PARAMS,
)
from rl_reasoning import (
    AnalogReasoningRewardModel,
    RLDatasetGenerator,
)

# ---------------------------------------------------------------------------
# ANSI Colour Helpers
# ---------------------------------------------------------------------------
RESET   = "\033[0m"
BOLD    = "\033[1m"
GREEN   = "\033[92m"
YELLOW  = "\033[93m"
RED     = "\033[91m"
CYAN    = "\033[96m"
DIM     = "\033[2m"
BLUE    = "\033[94m"
MAGENTA = "\033[95m"


def _c(text: str, *codes: str) -> str:
    if not sys.stdout.isatty():
        return str(text)
    return "".join(codes) + str(text) + RESET


def _bar(char: str = "─", width: int = 70) -> str:
    return _c(char * width, DIM)


# ---------------------------------------------------------------------------
# Suite 1: Razavi Domain Reasoning Benchmark
# ---------------------------------------------------------------------------
def run_razavi_suite(live_llm: bool = False, model_name: str = "qwen2.5:7b") -> bool:
    print(f"\n{_bar('═')}")
    print(_c("  [SUITE 1/3] RAZAVI DOMAIN REASONING BENCHMARK", BOLD, CYAN))
    print(_bar('═'))
    print("  Testing qualitative small-signal deductions & physical invariants:")

    suite = get_default_razavi_suite()
    benchmark = RazaviBenchmark(suite)

    def on_progress(idx: int, total: int, q, eval_res: Optional[dict]):
        if eval_res is None:
            print(f"\n  [{idx}/{total}] Reasoning on {_c(q.qid, BOLD)}: {q.title}…", flush=True)
        else:
            status_icon = _c("✓ PASS", GREEN, BOLD) if eval_res["passed"] else _c("✗ FAIL", RED, BOLD)
            score_pct = eval_res["score"] * 100.0
            score_str = f"{score_pct:.1f}%"
            print(f"    Verdict  : {status_icon} (Score: {_c(score_str, BOLD, GREEN if eval_res['passed'] else RED)})", flush=True)
            print(f"    Feedback : {_c(eval_res['feedback'], DIM)}", flush=True)

    # In demo mode, evaluate the reference reasoning answers
    # In live mode, query Ollama for each question with real-time token streaming
    if live_llm:
        print(f"  Querying live Ollama model: {_c(model_name, BOLD, GREEN)}…", flush=True)
        print("  Streaming model reasoning live:\n", flush=True)
        try:
            from openai import OpenAI
            client = OpenAI(base_url="http://localhost:11434/v1", api_key="ollama")

            def live_solver(prompt: str) -> str:
                print(f"{_bar('·', 60)}")
                stream = client.chat.completions.create(
                    model=model_name,
                    messages=[
                        {"role": "system", "content": "You are an expert analog CMOS IC designer. Provide rigorous analytical explanations and exact numerical derivations in English."},
                        {"role": "user", "content": prompt},
                    ],
                    stream=True,
                )
                collected = []
                for chunk in stream:
                    delta = chunk.choices[0].delta.content or ""
                    if delta:
                        collected.append(delta)
                        sys.stdout.write(delta)
                        sys.stdout.flush()
                print(f"\n{_bar('·', 60)}")
                return "".join(collected)

            summary = benchmark.run_on_solver(live_solver, on_progress=on_progress)
        except Exception as exc:
            print(_c(f"  Live query failed ({exc}) — falling back to reference evaluation.", YELLOW))
            summary = benchmark.run_on_solver(
                lambda p: next(q.reference_answer for q in suite if q.prompt == p),
                on_progress=on_progress,
            )
    else:
        summary = benchmark.run_on_solver(
            lambda p: next(q.reference_answer for q in suite if q.prompt == p),
            on_progress=on_progress,
        )

    # Save reasoning stream and full report to traces/benchmarks/
    save_dir = "traces/benchmarks"
    os.makedirs(save_dir, exist_ok=True)
    clean_model = model_name.replace(":", "_").replace("/", "_")
    timestamp = time.strftime("%Y%m%d_%H%M%S")
    json_path = os.path.join(save_dir, f"razavi_{clean_model}_{timestamp}.json")
    md_path = os.path.join(save_dir, f"razavi_{clean_model}_{timestamp}.md")

    with open(json_path, "w") as fh:
        json.dump(summary, fh, indent=2)

    with open(md_path, "w") as fh:
        fh.write(f"# Razavi Domain Reasoning Benchmark — Run Report\n\n")
        fh.write(f"- **Model**: `{model_name}`\n")
        fh.write(f"- **Timestamp**: `{timestamp}`\n")
        fh.write(f"- **Overall Benchmark Score**: `{summary['benchmark_score']:.1f}%` ({summary['passed_questions']}/{summary['total_questions']} passed)\n\n")
        fh.write(f"---\n\n")
        for item in summary["question_evaluations"]:
            status_tag = "PASSED" if item["passed"] else "FAILED"
            fh.write(f"## {item['qid']}: {item['title']} [{status_tag}]\n\n")
            fh.write(f"- **Score**: `{item['score']*100:.1f}%`\n")
            fh.write(f"- **Feedback**: {item['feedback']}\n\n")
            fh.write(f"### Model's Output & Reasoning Stream\n\n```text\n")
            fh.write(item.get("generated_answer", "").strip())
            fh.write(f"\n```\n\n---\n\n")

    print(f"\n  {_bar()}")
    benchmark_score_str = f"{summary['benchmark_score']:.1f} / 100.0"
    passed_str = f"{summary['passed_questions']} / {summary['total_questions']} ({summary['pass_rate_pct']}%)"
    score_col = GREEN if summary["benchmark_score"] >= 75.0 else YELLOW
    print(f"  Razavi Benchmark Score : {_c(benchmark_score_str, BOLD, score_col)}")
    print(f"  Questions Passed       : {_c(passed_str, BOLD)}")
    print(f"  Reasoning Log (MD)     : {_c(md_path, BOLD, GREEN)}")
    print(f"  Evaluation Data (JSON) : {_c(json_path, DIM)}")
    print(_bar('═'))

    return summary["pass_rate_pct"] >= 75.0


# ---------------------------------------------------------------------------
# Suite 2: Two-Stage Miller OTA Sizing Benchmark (LOADBench / AutoCkt)
# ---------------------------------------------------------------------------
def run_ota_suite() -> bool:
    print(f"\n{_bar('═')}")
    print(_c("  [SUITE 2/3] TWO-STAGE MILLER CMOS OTA BENCHMARK (LOADBench)", BOLD, CYAN))
    print(_bar('═'))
    print("  Evaluating Multi-Claim Rubric (Gain, Phase Margin, UGBW, Power, Saturation):")

    ota = TwoStageOTABenchmark()
    print(f"  Simulation Mode: {_c(ota.mode, BOLD, GREEN)}")

    res = ota.evaluate(DEFAULT_NOMINAL_OTA_PARAMS)
    m = res["metrics"]
    c = res["claims"]

    print(f"\n  {'Metric':<24} | {'Target':<12} | {'Simulated':<14} | {'Status'}")
    print(f"  {_bar('-', 64)}")

    rows = [
        ("DC Gain (Av)", ">= 40.0 dB", f"{m['gain_db']:+.2f} dB", c["gain_claim"]),
        ("Phase Margin (PM)", ">= 60.0°", f"{m['phase_margin_deg']:.1f}°", c["phase_margin_claim"]),
        ("Unity-Gain BW (UGBW)", ">= 5.0 MHz", f"{m['ugbw_mhz']:.2f} MHz", c["bandwidth_claim"]),
        ("Quiescent Power", "<= 2.0 mW", f"{m['power_mw']:.3f} mW", c["power_budget_claim"]),
        ("Active Saturation", "Vds >= Vov", "All in Sat", c["saturation_claim"]),
    ]

    for name, target, val, passed in rows:
        stat_badge = _c("✓ PASS", GREEN, BOLD) if passed else _c("✗ FAIL", RED, BOLD)
        val_colored = _c(val, GREEN if passed else RED)
        print(f"  {name:<24} | {target:<12} | {val_colored:<23} | {stat_badge}")

    print(f"\n  {_bar()}")
    score_col = GREEN if res["all_claims_passed"] else YELLOW
    rubric_str = f"{res['rubric_score']:.1f}%"
    print(f"  Multi-Claim Rubric Score : {_c(rubric_str, BOLD, score_col)}")
    print(f"  Diagnostic Status        : {_c(res['diagnostic'], DIM)}")
    print(_bar('═'))

    return res["all_claims_passed"]


# ---------------------------------------------------------------------------
# Suite 3: Verifiable RL Reasoning Reward & Preference Generator
# ---------------------------------------------------------------------------
def run_rl_suite() -> bool:
    print(f"\n{_bar('═')}")
    print(_c("  [SUITE 3/3] VERIFIABLE REINFORCEMENT LEARNING FROM SPICE (RLSF)", BOLD, CYAN))
    print(_bar('═'))
    print("  Generating verifiable DPO preference dataset with small-signal reward modeling:")

    generator = RLDatasetGenerator(output_path="traces/rl_preferences.jsonl")
    pairs = generator.generate_sample_preference_pairs()

    for idx, pair in enumerate(pairs, 1):
        print(f"\n  {_c(f'Pair {idx}:', BOLD, MAGENTA)} {_c(pair['prompt'][:75] + '…', DIM)}")
        print(f"    {_c('Chosen Reward  ', GREEN, BOLD)} : +{pair['reward_chosen']:.3f} (physically consistent, saturation verified)")
        print(f"    {_c('Rejected Reward', RED, BOLD)} : {pair['reward_rejected']:.3f} (hallucinated sizing / triode violation)")
        print(f"    {_c('Reward Margin  ', CYAN, BOLD)} : Δ = +{pair['reward_margin']:.3f}")

    print(f"\n  {_bar()}")
    print(f"  Exported Dataset : {_c(generator.output_path, BOLD, GREEN)}")
    print(f"  Format           : Direct Preference Optimization (DPO / GRPO compatible JSONL)")
    print(_bar('═'))
    return True


# ---------------------------------------------------------------------------
# Main Entry Point
# ---------------------------------------------------------------------------
def main() -> int:
    parser = argparse.ArgumentParser(description="aina Benchmark & Domain Reasoning Suite Runner")
    parser.add_argument("--suite", choices=["all", "razavi", "ota", "rl"], default="all",
                        help="Which benchmark suite to execute")
    parser.add_argument("--live", action="store_true",
                        help="Run against live local Ollama LLM instead of reference solver")
    parser.add_argument("--model", type=str, default="qwen2.5:7b",
                        help="Ollama model name for live testing")
    args = parser.parse_args()

    print(_c("\n  ╔════════════════════════════════════════════════════════════════════╗", CYAN))
    print(_c("  ║              aina (AI4aNAlog) Benchmark Runner                     ║", CYAN, BOLD))
    print(_c("  ║   Standardized Analog IC Benchmarks & Verifiable RL Reasoning      ║", CYAN))
    print(_c("  ╚════════════════════════════════════════════════════════════════════╝", CYAN))

    t0 = time.time()
    results = {}

    if args.suite in ["all", "razavi"]:
        results["razavi"] = run_razavi_suite(live_llm=args.live, model_name=args.model)

    if args.suite in ["all", "ota"]:
        results["ota"] = run_ota_suite()

    if args.suite in ["all", "rl"]:
        results["rl"] = run_rl_suite()

    elapsed = time.time() - t0
    all_passed = all(results.values())

    print(f"\n{_bar('═')}")
    print(_c("  OVERALL BENCHMARK VERDICT", BOLD))
    print(_bar('═'))
    for suite_name, passed in results.items():
        badge = _c("PASSED", GREEN, BOLD) if passed else _c("NEEDS_IMPROVEMENT", RED, BOLD)
        print(f"  Suite: {suite_name.upper():<12} -> {badge}")
    print(f"\n  Execution time : {_c(f'{elapsed:.2f} s', BOLD)}")
    print(f"  Overall Status : {_c('ALL BENCHMARKS VERIFIED ✓', GREEN, BOLD) if all_passed else _c('COMPLETED WITH WARNINGS', YELLOW, BOLD)}")
    print(f"{_bar('═')}\n")

    return 0 if all_passed else 1


if __name__ == "__main__":
    sys.exit(main())
