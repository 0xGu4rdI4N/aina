"""
agent_brain.py — Core Brain Layer for aina (AI 4 aNAlog)
=======================================================
Uses Ollama's OpenAI-compatible API with tool/function calling to drive a
locally-running LLM agent that autonomously sizes a Common-Source Amplifier.

Ollama exposes an OpenAI-compatible endpoint at http://localhost:11434/v1
so we use the openai Python SDK — no Anthropic key required.

Recommended models (tool-use capable, ranked by quality):
    qwen2.5:14b         best reasoning, needs ~10 GB RAM
    qwen2.5:7b          good balance, ~5 GB RAM  (default)
    llama3.2:3b         smallest, ~2 GB RAM
    mistral:7b          solid alternative

Run `ollama pull qwen2.5:7b` before starting.
"""

import json
import logging
import os
from dataclasses import dataclass
from typing import Any, Optional

try:
    from openai import OpenAI
except ImportError:
    raise ImportError(
        "openai package is required: pip install openai"
    )

from circuit_env import BasicCircuitEnv

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class IterationResult:
    """Captures everything that happened in one agent iteration."""
    iteration:        int
    w:                float
    l:                float
    gain:             Optional[float]
    parasitic:        Optional[float]
    sim_status:       str
    reasoning:        str
    goal_reached:     bool = False
    sim_mode:         str  = "unknown"
    error_type:       Optional[str] = None
    diagnostic:       Optional[str] = None
    suggested_action: Optional[str] = None
    vout_dc:          Optional[float] = None
    latency_ms:       Optional[float] = None
    tokens:           Optional[dict] = None
    cost_usd:         float = 0.0


# ---------------------------------------------------------------------------
# Tool schema  (OpenAI / Ollama format)
# ---------------------------------------------------------------------------

EVALUATE_DESIGN_TOOL = {
    "type": "function",
    "function": {
        "name":        "evaluate_design",
        "description": (
            "Simulate a Common-Source Amplifier with the given MOSFET dimensions. "
            "Returns the small-signal AC gain at ~1 Hz in dB, DC output voltage Vout_dc, and layout "
            "parasitic capacitance. Also checks saturation headroom (Vds >= Vov = 0.3V) and "
            "catches SPICE convergence/timestep errors with actionable diagnostics. "
            "Physics: Gm = Kp*(W/L)*Vov, |Av| = Gm*Rout, C_para = W * 1.5 fF. "
            "Larger W increases Gm but raises Id and C_para. If W/L is too high, headroom collapses into triode."
        ),
        "parameters": {
            "type":     "object",
            "properties": {
                "w": {
                    "type":        "number",
                    "description": "MOSFET gate width in micrometres (um). Valid range: 1.0 to 50.0.",
                },
                "l": {
                    "type":        "number",
                    "description": "MOSFET gate length in micrometres (um). Valid range: 0.5 to 10.0.",
                },
            },
            "required": ["w", "l"],
        },
    },
}

# ---------------------------------------------------------------------------
# System prompt
# ---------------------------------------------------------------------------

def build_system_prompt(target_gain: float) -> str:
    """Builds a physics-grounded system prompt tailored to the specified target gain."""
    target_av = 10.0 ** (target_gain / 20.0)
    estimated_wl = (target_av / 9500.0) / 36e-6

    return f"""\
You are aina, an expert analog IC design assistant. Your task is to size
the MOSFET in a Common-Source (CS) Amplifier to achieve voltage gain >= {target_gain:.1f} dB.

CIRCUIT (matches the SPICE netlist exactly):
  Topology : nMOS CS amp, Rd = 10 kOhm, Vdd = 3.3 V, Vbias = 1.0 V
  Process  : Level-1 NMOS, Kp = 120 uA/V^2, Vto = 0.7 V, lambda = 0.02
  Bias     : Vov = Vgs - Vto = 0.3 V
  Parasitic: C_para (fF) = W (um) * 1.5  -- layout penalty

KEY EQUATIONS & PHYSICAL CONSTRAINTS:
  Gm     = Kp * (W/L) * Vov = 120e-6 * (W/L) * 0.3 = 36e-6 * (W/L)   [A/V]
  Id     = 0.5 * Kp * (W/L) * Vov^2 = 5.4e-6 * (W/L)                  [A]
  Vout_dc= Vdd - Id * Rd = 3.3 - 0.054 * (W/L)                        [V]
  Rout   = Rd || (1 / (0.02 * Id))                                    [Ohm]
  |Av|   = Gm * Rout  (DC gain magnitude)

CRITICAL HEADROOM & SATURATION RULE:
  For saturation amplification, Vds (= Vout_dc) MUST remain >= Vov (0.3 V).
  If W/L exceeds ~55.5 (e.g. W=40 um, L=0.5 um -> W/L = 80), the drain current drop
  Id * Rd exceeds 3.0 V, driving M1 into the TRIODE/LINEAR region!
  In the triode region, Gm collapses, output resistance plummets, and gain drops sharply.
  Keep W/L within the operating window: high enough for gain, but low enough for Vout_dc >= 0.3 V.

FAILURE RECOVERY & DEBUGGING:
  If evaluate_design returns a status other than "SUCCESS" (e.g., "PHYSICS_VIOLATION",
  "TIMESTEP_TOO_SMALL", "CONVERGENCE_ERROR", or "TRIODE_REGION_HEADROOM_EXHAUSTED"):
  - Inspect the returned "diagnostic" and "suggested_action" fields.
  - If triode headroom collapsed: immediately REDUCE W or INCREASE L to lower Id.
  - If SPICE solver numerical error: adjust W and L slightly to move away from the numerical singularity.
  - Use the diagnostic feedback to recover in your next candidate sizing.

DESIGN SPACE:
  W : 1.0 to 50.0 um
  L : 0.5 to 10.0 um
  Target: gain >= {target_gain:.1f} dB  (i.e. |Av| >= {target_av:.2f})

STRATEGY:
  1. Target condition: Gm * Rout >= {target_av:.2f}.
  2. With Rout ~ 9.5 kOhm: estimated required W/L >= {estimated_wl:.1f}.
  3. Keep saturation headroom in mind: balance W/L for maximum gain without crushing Vout_dc.
  4. LANGUAGE: Always formulate your reasoning and replies in English.

RULES:
  - Call evaluate_design ONCE per response with your chosen (W, L).
  - After seeing the result, analyze the gap and adjust W/L accordingly.
  - Once gain >= {target_gain:.1f} dB (and Vds >= 0.3V), say exactly "Design Verified: Goal Reached" and stop.
"""


# ---------------------------------------------------------------------------
# Agent brain
# ---------------------------------------------------------------------------

class AgentBrain:
    """
    Ollama-powered transistor sizing agent using OpenAI-compatible tool use.

    Parameters
    ----------
    env         : BasicCircuitEnv instance
    max_iters   : hard cap on the agentic loop (default 10)
    target_gain : gain threshold in dB (default 20.0)
    model       : Ollama model name (must support tool use)
    host        : Ollama server URL (default: http://localhost:11434)
    tracer      : Optional ObservabilityTracer instance for logging & telemetry
    """

    GOAL_PHRASES = [
        "design verified: goal reached",
        "goal reached",
        "target achieved",
        "design verified",
    ]

    def __init__(
        self,
        env: BasicCircuitEnv,
        max_iters: int   = 10,
        target_gain: float = 20.0,
        model: str       = "qwen2.5:7b",
        host: str        = "http://localhost:11434",
        tracer: Optional[Any] = None,
    ):
        self.env         = env
        self.max_iters   = max_iters
        self.target_gain = target_gain
        self.model       = model
        self.tracer      = tracer

        # Ollama's OpenAI-compatible base URL
        self.client = OpenAI(
            base_url = f"{host.rstrip('/')}/v1",
            api_key  = "ollama",   # required by sdk but ignored by Ollama
        )

        self.messages: list[dict]            = []
        self.history:  list[IterationResult] = []
        self._consecutive_failures           = 0
        self._MAX_CONSECUTIVE_FAILURES       = 5

    # ── Public API ────────────────────────────────────────────────────────────

    def run(self) -> list[IterationResult]:
        """
        Execute the agentic loop until goal is reached or max_iters exhausted.

        Returns
        -------
        list[IterationResult] — full history of all iterations.
        """
        logger.info(
            "Agent loop starting (model=%s, max_iters=%d, target=%.1f dB)",
            self.model, self.max_iters, self.target_gain,
        )

        self.messages = [
            {
                "role": "system",
                "content": build_system_prompt(self.target_gain),
            },
            {
                "role": "user",
                "content": (
                    f"Begin sizing the CS amplifier. Target: gain >= {self.target_gain:.1f} dB. "
                    "Use the evaluate_design tool to simulate each candidate. "
                    "Start with your best initial guess based on the circuit equations. "
                    "Always write your reasoning and responses in English."
                ),
            },
        ]

        for iteration in range(1, self.max_iters + 1):
            logger.info("── Iteration %d ──", iteration)
            result = self._step(iteration)
            self.history.append(result)

            if result.goal_reached:
                logger.info("Goal reached at iteration %d!", iteration)
                break

            if self._consecutive_failures >= self._MAX_CONSECUTIVE_FAILURES:
                logger.error("Too many consecutive failures — aborting.")
                break

        return self.history

    # ── Private helpers ───────────────────────────────────────────────────────

    def _step(self, iteration: int) -> IterationResult:
        """Run one full agent step: LLM call -> tool execution -> LLM response."""
        import time
        t_start = time.time()
        prompt_tokens = 0
        completion_tokens = 0

        # ── 1. Ask the LLM ────────────────────────────────────────────────────
        response = self.client.chat.completions.create(
            model    = self.model,
            messages = self.messages,
            tools    = [EVALUATE_DESIGN_TOOL],
            tool_choice = "auto",
        )

        if response.usage:
            prompt_tokens += getattr(response.usage, "prompt_tokens", 0) or 0
            completion_tokens += getattr(response.usage, "completion_tokens", 0) or 0

        msg = response.choices[0].message
        self.messages.append(msg.model_dump(exclude_none=True))

        # ── 2. Extract tool call ───────────────────────────────────────────────
        tool_calls   = msg.tool_calls or []
        content_text = msg.content or ""

        if not tool_calls:
            # LLM didn't call the tool — check if it declared victory
            goal_reached = any(p in content_text.lower() for p in self.GOAL_PHRASES)
            latency_ms = (time.time() - t_start) * 1000.0
            if goal_reached and self.history:
                last = self.history[-1]
                return IterationResult(
                    iteration   = iteration,
                    w           = last.w,
                    l           = last.l,
                    gain        = last.gain,
                    parasitic   = last.parasitic,
                    sim_status  = "SKIPPED",
                    reasoning   = content_text,
                    goal_reached= True,
                    sim_mode    = last.sim_mode,
                    error_type  = last.error_type,
                    vout_dc     = last.vout_dc,
                    latency_ms  = latency_ms,
                    tokens      = {"prompt": prompt_tokens, "completion": completion_tokens, "total": prompt_tokens + completion_tokens},
                )
            # Nudge the LLM to call the tool
            self.messages.append({
                "role":    "user",
                "content": (
                    "Please call evaluate_design with your next candidate (W, L). "
                    "Remember W range is 1.0-50.0 and L range is 0.5-10.0."
                ),
            })
            return IterationResult(
                iteration  = iteration,
                w          = 0.0,
                l          = 0.0,
                gain       = None,
                parasitic  = None,
                sim_status = "NO_TOOL_CALL",
                reasoning  = content_text,
                latency_ms = latency_ms,
                tokens     = {"prompt": prompt_tokens, "completion": completion_tokens, "total": prompt_tokens + completion_tokens},
            )

        # Use the first tool call (there should only be one)
        tc = tool_calls[0]
        try:
            args = json.loads(tc.function.arguments)
            w    = float(args["w"])
            l    = float(args["l"])
        except (KeyError, ValueError, json.JSONDecodeError) as exc:
            logger.error("Bad tool args: %s — raw: %s", exc, tc.function.arguments)
            latency_ms = (time.time() - t_start) * 1000.0
            return IterationResult(
                iteration  = iteration,
                w          = 0.0,
                l          = 0.0,
                gain       = None,
                parasitic  = None,
                sim_status = "BAD_TOOL_ARGS",
                reasoning  = content_text,
                latency_ms = latency_ms,
                tokens     = {"prompt": prompt_tokens, "completion": completion_tokens, "total": prompt_tokens + completion_tokens},
            )

        # ── 3. Run the simulator ───────────────────────────────────────────────
        sim_result = self.env.evaluate_design(w, l)
        logger.info(
            "Simulation  W=%.2f L=%.2f  ->  %s",
            w, l,
            f"gain={sim_result.get('gain')} dB, parasitic={sim_result.get('parasitic')} fF"
            if sim_result["status"] == "SUCCESS"
            else f"{sim_result.get('status')} ({sim_result.get('error_type')})",
        )

        # ── 4. Feed tool result back to the LLM ──────────────────────────────
        self.messages.append({
            "role":        "tool",
            "tool_call_id": tc.id,
            "content":     json.dumps(sim_result),
        })

        # ── 5. Ask LLM to reason about the result ────────────────────────────
        follow_up = self.client.chat.completions.create(
            model    = self.model,
            messages = self.messages,
            tools    = [EVALUATE_DESIGN_TOOL],
            tool_choice = "none",   # force text response, not another tool call
        )

        if follow_up.usage:
            prompt_tokens += getattr(follow_up.usage, "prompt_tokens", 0) or 0
            completion_tokens += getattr(follow_up.usage, "completion_tokens", 0) or 0

        follow_msg     = follow_up.choices[0].message
        reasoning_text = (follow_msg.content or "").strip()
        self.messages.append(follow_msg.model_dump(exclude_none=True))

        latency_ms = (time.time() - t_start) * 1000.0

        # ── 6. Determine outcome & record trace ────────────────────────────────
        gain             = sim_result.get("gain")
        parasitic        = sim_result.get("parasitic")
        sim_mode         = sim_result.get("mode", "unknown")
        error_type       = sim_result.get("error_type")
        diagnostic       = sim_result.get("diagnostic")
        suggested_action = sim_result.get("suggested_action")
        vout_dc          = sim_result.get("vout_dc")

        if sim_result["status"] == "SUCCESS":
            self._consecutive_failures = 0
            goal_reached = (
                (gain is not None and gain >= self.target_gain)
                or any(p in reasoning_text.lower() for p in self.GOAL_PHRASES)
            )
            sim_status = "SUCCESS"
        else:
            self._consecutive_failures += 1
            goal_reached = False
            sim_status = sim_result["status"]

        if self.tracer:
            self.tracer.log_step(
                iteration         = iteration,
                model             = self.model,
                latency_ms        = latency_ms,
                prompt_tokens     = prompt_tokens,
                completion_tokens = completion_tokens,
                w                 = w,
                l                 = l,
                sim_result        = sim_result,
                reasoning         = reasoning_text,
                goal_reached      = goal_reached,
            )

        tokens_dict = {
            "prompt": prompt_tokens,
            "completion": completion_tokens,
            "total": prompt_tokens + completion_tokens,
        }

        return IterationResult(
            iteration        = iteration,
            w                = w,
            l                = l,
            gain             = gain,
            parasitic        = parasitic,
            sim_status       = sim_status,
            reasoning        = reasoning_text,
            goal_reached     = goal_reached,
            sim_mode         = sim_mode,
            error_type       = error_type,
            diagnostic       = diagnostic,
            suggested_action = suggested_action,
            vout_dc          = vout_dc,
            latency_ms       = latency_ms,
            tokens           = tokens_dict,
        )


class MockAgentBrain:
    """
    Deterministic Analog IC Agent that simulates the multi-turn reasoning,
    tool calls, and iterative reflection of Ollama (qwen2.5:7b) without
    requiring an active Ollama daemon or OpenAI API key.
    """

    def __init__(
        self,
        env: BasicCircuitEnv,
        max_iters: int = 10,
        target_gain: float = 20.0,
        model: str = "mock-qwen2.5:7b",
        tracer: Optional[Any] = None,
    ):
        self.env = env
        self.max_iters = max_iters
        self.target_gain = target_gain
        self.model = model
        self.tracer = tracer
        self.history: list[IterationResult] = []

    def run(self) -> list[IterationResult]:
        for iteration in range(1, min(self.max_iters, 2) + 1):
            result = self._step(iteration)
            self.history.append(result)
            if result.goal_reached:
                break
        return self.history

    def _step(self, iteration: int) -> IterationResult:
        import time
        time.sleep(0.12)  # Brief delay simulating real-time agent reasoning
        t_start = time.time()

        if iteration == 1:
            w, l = 10.0, 0.5
            sim = self.env.evaluate_design(w, l)
            reasoning = (
                f"The target AC voltage gain is >= {self.target_gain:.1f} dB. For initial sizing, "
                f"choosing W = {w:.1f} µm and minimum channel length L = {l:.1f} µm yields W/L = {w/l:.1f}. "
                f"The simulated gain is {sim['gain']:+.2f} dB, falling short of the {self.target_gain:.1f} dB specification by "
                f"{self.target_gain - sim['gain']:.2f} dB. DC output headroom is healthy at Vout = {sim.get('vout_dc', 2.22):.3f} V "
                f"(Vds > Vov = 0.3 V: PASS). To bridge the remaining gain deficit, transconductance Gm must be boosted "
                f"by increasing width W to 20.0 µm while maintaining minimum L to limit channel-length modulation."
            )
            tokens = {"prompt": 2640, "completion": 280, "total": 2920}
            goal_reached = False
        else:
            w, l = 20.0, 0.5
            sim = self.env.evaluate_design(w, l)
            goal_reached = sim.get("gain", 0.0) >= self.target_gain
            reasoning = (
                f"With W = {w:.1f} µm and L = {l:.1f} µm (W/L = {w/l:.1f}), transconductance increases to "
                f"satisfy the target. The simulated gain is {sim['gain']:+.2f} dB, exceeding the target specification "
                f"of {self.target_gain:.1f} dB. DC operating point check confirms Vout = {sim.get('vout_dc', 1.14):.3f} V "
                f"(Vds >= 0.3 V: saturation maintained with {sim.get('vout_dc', 1.14) - 0.3:.3f} V headroom). "
                f"Layout parasitic capacitance is {sim.get('parasitic', 30.0):.1f} fF. Design Verified: Goal Reached."
            )
            tokens = {"prompt": 2950, "completion": 310, "total": 3260}

        latency_ms = (time.time() - t_start) * 1000.0 + 150.0

        if self.tracer:
            self.tracer.log_step(
                iteration=iteration,
                model=self.model,
                latency_ms=latency_ms,
                prompt_tokens=tokens["prompt"],
                completion_tokens=tokens["completion"],
                w=w,
                l=l,
                sim_result=sim,
                reasoning=reasoning,
                goal_reached=goal_reached,
            )

        return IterationResult(
            iteration=iteration,
            w=w,
            l=l,
            gain=sim.get("gain"),
            parasitic=sim.get("parasitic"),
            sim_status=sim.get("status", "SUCCESS"),
            reasoning=reasoning,
            goal_reached=goal_reached,
            sim_mode=sim.get("mode", self.env.mode),
            error_type=sim.get("error_type"),
            diagnostic=sim.get("diagnostic"),
            suggested_action=sim.get("suggested_action"),
            vout_dc=sim.get("vout_dc"),
            latency_ms=latency_ms,
            tokens=tokens,
        )


