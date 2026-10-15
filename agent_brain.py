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
from typing import Optional

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
    iteration:    int
    w:            float
    l:            float
    gain:         Optional[float]
    parasitic:    Optional[float]
    sim_status:   str
    reasoning:    str
    goal_reached: bool = False
    sim_mode:     str  = "unknown"


# ---------------------------------------------------------------------------
# Tool schema  (OpenAI / Ollama format)
# ---------------------------------------------------------------------------

EVALUATE_DESIGN_TOOL = {
    "type": "function",
    "function": {
        "name":        "evaluate_design",
        "description": (
            "Simulate a Common-Source Amplifier with the given MOSFET dimensions. "
            "Returns the small-signal AC gain at ~1 Hz in dB and the layout "
            "parasitic capacitance. "
            "Physics: Gm = Kp*(W/L)*Vov, |Av| = Gm*Rout, C_para = W * 1.5 fF. "
            "Larger W increases Gm (good) but also C_para (bad — rolls off gain). "
            "Shorter L increases W/L ratio and hence Gm, but raises Gds. "
            "Target: gain >= 30 dB."
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
  Bias     : Vov = Vgs - Vto = 0.3 V  (M1 in saturation for all W in 1..50 um)
  Parasitic: C_para (fF) = W (um) * 1.5  -- layout penalty

KEY EQUATIONS:
  Gm     = Kp * (W/L) * Vov = 120e-6 * (W/L) * 0.3 = 36e-6 * (W/L)   [A/V]
  Id     = 0.5 * Kp * (W/L) * Vov^2 = 5.4e-6 * (W/L)                  [A]
  Gds    = lambda * Id = 0.02 * Id                                       [A/V]
  Rout   = Rd || (1/Gds)  ~  9.0 to 10.0 kOhm depending on W/L
  |Av|   = Gm * Rout  (DC gain magnitude)

DESIGN SPACE:
  W : 1.0 to 50.0 um
  L : 0.5 to 10.0 um
  Target: gain >= {target_gain:.1f} dB  (i.e. |Av| >= {target_av:.2f})

STRATEGY:
  1. Target condition: Gm * Rout >= {target_av:.2f}.
  2. With Rout ~ 9.5 kOhm: estimated W/L >= {estimated_wl:.1f}.
  3. Larger W raises C_para (fF = W*1.5). Prefer keeping L near minimum (0.5 um)
     to maximize W/L without excessive W and parasitic capacitance.
  4. LANGUAGE: Always formulate your reasoning and replies in English.

RULES:
  - Call evaluate_design ONCE per response with your chosen (W, L).
  - After seeing the result, analyze the gap and adjust W/L accordingly.
  - Once gain >= {target_gain:.1f} dB, say exactly "Design Verified: Goal Reached" and stop.
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
    ):
        self.env         = env
        self.max_iters   = max_iters
        self.target_gain = target_gain
        self.model       = model

        # Ollama's OpenAI-compatible base URL
        self.client = OpenAI(
            base_url = f"{host.rstrip('/')}/v1",
            api_key  = "ollama",   # required by sdk but ignored by Ollama
        )

        self.messages: list[dict]            = []
        self.history:  list[IterationResult] = []
        self._consecutive_failures           = 0
        self._MAX_CONSECUTIVE_FAILURES       = 3

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

        # ── 1. Ask the LLM ────────────────────────────────────────────────────
        response = self.client.chat.completions.create(
            model    = self.model,
            messages = self.messages,
            tools    = [EVALUATE_DESIGN_TOOL],
            tool_choice = "auto",
        )

        msg = response.choices[0].message
        self.messages.append(msg.model_dump(exclude_none=True))

        # ── 2. Extract tool call ───────────────────────────────────────────────
        tool_calls   = msg.tool_calls or []
        content_text = msg.content or ""

        if not tool_calls:
            # LLM didn't call the tool — check if it declared victory
            goal_reached = any(p in content_text.lower() for p in self.GOAL_PHRASES)
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
            )

        # Use the first tool call (there should only be one)
        tc = tool_calls[0]
        try:
            args = json.loads(tc.function.arguments)
            w    = float(args["w"])
            l    = float(args["l"])
        except (KeyError, ValueError, json.JSONDecodeError) as exc:
            logger.error("Bad tool args: %s — raw: %s", exc, tc.function.arguments)
            return IterationResult(
                iteration  = iteration,
                w          = 0.0,
                l          = 0.0,
                gain       = None,
                parasitic  = None,
                sim_status = "BAD_TOOL_ARGS",
                reasoning  = content_text,
            )

        # ── 3. Run the simulator ───────────────────────────────────────────────
        sim_result = self.env.evaluate_design(w, l)
        logger.info(
            "Simulation  W=%.2f L=%.2f  ->  %s",
            w, l,
            f"gain={sim_result.get('gain')} dB, parasitic={sim_result.get('parasitic')} fF"
            if sim_result["status"] == "SUCCESS"
            else sim_result["status"],
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

        follow_msg     = follow_up.choices[0].message
        reasoning_text = (follow_msg.content or "").strip()
        self.messages.append(follow_msg.model_dump(exclude_none=True))

        # ── 6. Determine outcome ──────────────────────────────────────────────
        if sim_result["status"] == "SUCCESS":
            self._consecutive_failures = 0
            gain      = sim_result["gain"]
            parasitic = sim_result["parasitic"]
            sim_mode  = sim_result.get("mode", "unknown")

            goal_reached = (
                gain >= self.target_gain
                or any(p in reasoning_text.lower() for p in self.GOAL_PHRASES)
            )

            return IterationResult(
                iteration   = iteration,
                w           = w,
                l           = l,
                gain        = gain,
                parasitic   = parasitic,
                sim_status  = "SUCCESS",
                reasoning   = reasoning_text,
                goal_reached= goal_reached,
                sim_mode    = sim_mode,
            )
        else:
            self._consecutive_failures += 1
            return IterationResult(
                iteration  = iteration,
                w          = w,
                l          = l,
                gain       = None,
                parasitic  = None,
                sim_status = sim_result["status"],
                reasoning  = reasoning_text,
                sim_mode   = sim_result.get("mode", "unknown"),
            )
