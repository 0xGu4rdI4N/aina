"""
tracer.py — Structured Observability & Tracing Layer for aina
============================================================
Logs token counts, latency, cost estimation, circuit parameters, and simulation
diagnostics per agent iteration. Integrates with Arize Phoenix (via OpenInference /
OpenTelemetry) and writes structured JSONL telemetry logs for optimization analysis.
"""

import json
import logging
import os
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# Standard token cost estimations per 1M tokens (USD)
# Local Ollama is always $0.00
PRICING_TABLE = {
    "qwen": {"prompt": 0.0, "completion": 0.0},
    "llama": {"prompt": 0.0, "completion": 0.0},
    "mistral": {"prompt": 0.0, "completion": 0.0},
    "gpt-4o": {"prompt": 2.50, "completion": 10.00},
    "gpt-4o-mini": {"prompt": 0.15, "completion": 0.60},
    "claude-3-5-sonnet": {"prompt": 3.00, "completion": 15.00},
}


class ObservabilityTracer:
    """
    Structured telemetry tracer and Arize Phoenix integration.
    """

    def __init__(
        self,
        trace_dir: str = "traces",
        enable_phoenix: bool = False,
        phoenix_port: int = 6006,
    ):
        self.trace_dir = Path(trace_dir)
        self.trace_dir.mkdir(parents=True, exist_ok=True)

        self.session_id = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.trace_file = self.trace_dir / f"run_{self.session_id}.jsonl"
        self.latest_file = self.trace_dir / "latest.jsonl"

        self.enable_phoenix = enable_phoenix
        self.phoenix_url: Optional[str] = None
        self.phoenix_session: Any = None

        self.start_time = time.time()
        self.records: List[Dict[str, Any]] = []

        # Totals
        self.total_prompt_tokens = 0
        self.total_completion_tokens = 0
        self.total_tokens = 0
        self.total_cost_usd = 0.0
        self.step_latencies: List[float] = []

        if self.enable_phoenix:
            self._init_phoenix(port=phoenix_port)

    def _init_phoenix(self, port: int = 6006) -> None:
        """Initialize Arize Phoenix local app & OpenInference instrumentation."""
        try:
            import phoenix as px
            from openinference.instrumentation.openai import OpenAIInstrumentor

            logger.info("Initializing Arize Phoenix on port %d...", port)
            self.phoenix_session = px.launch_app(port=port)
            OpenAIInstrumentor().instrument()
            self.phoenix_url = f"http://localhost:{port}"
            logger.info("Arize Phoenix active at %s", self.phoenix_url)
        except Exception as exc:
            logger.warning("Could not launch Arize Phoenix: %s. Traces will still be logged to JSONL.", exc)
            self.phoenix_url = None

    def estimate_cost(self, model_name: str, prompt_tokens: int, completion_tokens: int) -> float:
        """Calculate estimated cost in USD based on model prefix."""
        model_lower = model_name.lower()
        pricing = {"prompt": 0.0, "completion": 0.0}

        for key, rates in PRICING_TABLE.items():
            if key in model_lower:
                pricing = rates
                break

        cost = (prompt_tokens / 1_000_000.0) * pricing["prompt"] + (
            completion_tokens / 1_000_000.0
        ) * pricing["completion"]
        return round(cost, 6)

    def log_step(
        self,
        iteration: int,
        model: str,
        latency_ms: float,
        prompt_tokens: int,
        completion_tokens: int,
        w: float,
        l: float,
        sim_result: Dict[str, Any],
        reasoning: str,
        goal_reached: bool,
    ) -> Dict[str, Any]:
        """Record and serialize a single agent step."""
        total_tokens = prompt_tokens + completion_tokens
        step_cost = self.estimate_cost(model, prompt_tokens, completion_tokens)

        self.total_prompt_tokens += prompt_tokens
        self.total_completion_tokens += completion_tokens
        self.total_tokens += total_tokens
        self.total_cost_usd += step_cost
        self.step_latencies.append(latency_ms / 1000.0)

        aspect_ratio = round(w / l, 2) if l > 0 else 0.0

        record = {
            "session_id": self.session_id,
            "iteration": iteration,
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "model": model,
            "latency_ms": round(latency_ms, 2),
            "telemetry": {
                "prompt_tokens": prompt_tokens,
                "completion_tokens": completion_tokens,
                "total_tokens": total_tokens,
                "cost_usd": step_cost,
                "cumulative_cost_usd": round(self.total_cost_usd, 6),
            },
            "circuit_parameters": {
                "w_um": round(w, 2),
                "l_um": round(l, 2),
                "aspect_ratio_w_over_l": aspect_ratio,
                "parasitic_capacitance_ff": sim_result.get("parasitic"),
            },
            "simulation": {
                "status": sim_result.get("status"),
                "gain_db": sim_result.get("gain"),
                "sim_mode": sim_result.get("mode"),
                "vout_dc_v": sim_result.get("vout_dc"),
                "error_type": sim_result.get("error_type"),
                "diagnostic": sim_result.get("diagnostic"),
                "suggested_action": sim_result.get("suggested_action"),
            },
            "agent_state": {
                "reasoning_snippet": reasoning[:300] if reasoning else "",
                "goal_reached": goal_reached,
            },
        }

        self.records.append(record)

        # Write to JSONL
        line = json.dumps(record) + "\n"
        with open(self.trace_file, "a", encoding="utf-8") as fh:
            fh.write(line)
        with open(self.latest_file, "a", encoding="utf-8") as fh:
            fh.write(line)

        return record

    def print_summary(self, solved: bool) -> None:
        """Print a rich terminal summary of token usage, latency, and observability data."""
        total_time = time.time() - self.start_time
        avg_latency = (
            sum(self.step_latencies) / len(self.step_latencies)
            if self.step_latencies
            else 0.0
        )

        bold = "\033[1m"
        cyan = "\033[96m"
        green = "\033[92m"
        dim = "\033[2m"
        reset = "\033[0m"

        def _c(t: str, *codes: str) -> str:
            if not sys.stdout.isatty():
                return t
            return "".join(codes) + str(t) + reset

        bar = _c("─" * 68, dim)
        double_bar = _c("═" * 68, dim)

        print(f"\n{double_bar}")
        print(_c("  OBSERVABILITY & TELEMETRY SUMMARY", bold, cyan))
        print(double_bar)

        print(f"  {'Total Wall Time':<24} : {_c(f'{total_time:.2f} s', bold)}")
        print(f"  {'Avg Step Latency':<24} : {_c(f'{avg_latency:.2f} s', bold)}")
        print(f"  {'Total Iterations':<24} : {_c(str(len(self.records)), bold)}")
        print(bar)
        print(f"  {'Prompt Tokens':<24} : {_c(str(self.total_prompt_tokens), bold)}")
        print(f"  {'Completion Tokens':<24} : {_c(str(self.total_completion_tokens), bold)}")
        print(f"  {'Total Tokens':<24} : {_c(str(self.total_tokens), bold, green)}")
        print(f"  {'Estimated Cost':<24} : {_c(f'${self.total_cost_usd:.4f} (Local = $0.00)', bold)}")
        print(bar)
        print(f"  {'Trace Log (JSONL)':<24} : {_c(str(self.trace_file), dim)}")
        if self.phoenix_url:
            print(f"  {'Arize Phoenix UI':<24} : {_c(self.phoenix_url, bold, cyan)}")
        print(double_bar)
