"""
rl_reasoning.py — Verifiable Reinforcement Learning from SPICE & Physics Feedback (RLSF)
========================================================================================
Implements a verifiable reward modeling and training dataset generator for analog IC
reasoning, inspired by Reinforcement Learning with Verifiable Rewards (RLVR) and
Group Relative Policy Optimization (GRPO / DeepSeek-R1 style).

In analog circuits, ground truth is physically deterministic:
  Reward = R_domain_reasoning (verifiable physics) + R_spice_rubric (simulation) - Penalty_format
"""

import json
import math
import os
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from benchmarks.razavi_reasoning import get_default_razavi_suite, evaluate_reasoning_response
from benchmarks.two_stage_ota import TwoStageOTABenchmark, DEFAULT_NOMINAL_OTA_PARAMS


@dataclass
class VerifiableRewardBreakdown:
    """Detailed components of an analog reasoning reward signal."""
    total_reward: float
    domain_reasoning_reward: float
    spice_rubric_reward: float
    format_penalty: float
    verifiable_claims_passed: int
    total_claims: int
    physics_violations: List[str]
    diagnostics: List[str]


class AnalogReasoningRewardModel:
    """
    Verifiable Physics Reward Model for Analog IC Reasoning.
    Unlike standard LLM reward models, this computes mathematically verified rewards
    derived from small-signal circuit laws and SPICE simulation metrics.
    """

    def __init__(self, target_gain_db: float = 20.0, min_pm_deg: float = 60.0):
        self.target_gain_db = target_gain_db
        self.min_pm_deg = min_pm_deg

    def evaluate_reasoning_and_action(
        self,
        prompt: str,
        reasoning_trace: str,
        proposed_params: Dict[str, float],
        sim_result: Dict[str, Any],
    ) -> VerifiableRewardBreakdown:
        """
        Computes composite verifiable reward for an agent step:
        R = R_reasoning + R_spice - R_penalty
        """
        diagnostics = []
        physics_violations = []

        # ── 1. Domain Reasoning & Symbolic Checks (R_reasoning: -2.0 to +2.0) ──
        reasoning_score = 0.0

        # Physical Rule 1: gm sensitivity with W (gm ~ W/L)
        if re.search(r"(?i)increas(e|ing)\s+w.*increas(e|ing|es)\s+(gm|transconductance)", reasoning_trace):
            reasoning_score += 0.5
        elif re.search(r"(?i)increas(e|ing)\s+w.*decreas(e|ing|es)\s+(gm|transconductance)", reasoning_trace):
            reasoning_score -= 1.0
            physics_violations.append("Stated that increasing W decreases transconductance gm.")

        # Physical Rule 2: Triode / Saturation Headroom check
        if re.search(r"(?i)vds\s*(<|<=|less\s+than)\s*(vov|0\.3)", reasoning_trace):
            if "triode" in reasoning_trace.lower():
                reasoning_score += 0.5  # Correctly deduced triode transition
        if re.search(r"(?i)triode.*collapse|headroom.*exhausted", reasoning_trace):
            reasoning_score += 0.5

        # Physical Rule 3: Channel-length modulation (ro ~ L)
        if re.search(r"(?i)increas(e|ing)\s+l.*increas(e|ing|es)\s+(ro|output\s+resistance)", reasoning_trace):
            reasoning_score += 0.5

        # ── 2. SPICE Simulation Rubric Reward (R_spice: -2.0 to +3.0) ──────────
        spice_score = 0.0
        status = sim_result.get("status", "UNKNOWN")
        gain = sim_result.get("gain")
        pm = sim_result.get("phase_margin")
        vout_dc = sim_result.get("vout_dc")

        claims_passed = 0
        total_claims = 3

        # Claim A: DC Operating Point / Headroom
        if vout_dc is not None:
            if vout_dc >= 0.3:
                spice_score += 1.0
                claims_passed += 1
            else:
                spice_score -= 1.5
                physics_violations.append(f"Vds ({vout_dc:.3f} V) collapsed below Vov = 0.3 V.")
        elif status == "SUCCESS":
            spice_score += 1.0
            claims_passed += 1

        # Claim B: Voltage Gain Target
        if gain is not None:
            if gain >= self.target_gain_db:
                # Scaled reward for meeting and exceeding spec without excess
                excess = min(10.0, gain - self.target_gain_db)
                spice_score += 1.5 + (excess * 0.05)
                claims_passed += 1
            else:
                # Proportional shortfall penalty
                gap = self.target_gain_db - gain
                spice_score -= min(2.0, gap * 0.2)
                diagnostics.append(f"Gain ({gain:.2f} dB) fell short of target ({self.target_gain_db:.1f} dB).")

        # Claim C: Error Handling & Convergence
        if status == "SUCCESS":
            claims_passed += 1
            spice_score += 0.5
        elif status == "PHYSICS_VIOLATION":
            spice_score -= 0.5
            diagnostics.append(f"Physical boundary violation: {sim_result.get('error_type')}")
        else:
            spice_score -= 1.5
            diagnostics.append(f"Simulation failure: {status}")

        # ── 3. Format & Parameter Integrity Penalty ────────────────────────────
        format_penalty = 0.0
        w = proposed_params.get("w", 0.0)
        l = proposed_params.get("l", 0.0)

        if w < 1.0 or w > 50.0:
            format_penalty += 1.0
            physics_violations.append(f"W={w} um out of bounds [1.0, 50.0]")
        if l < 0.5 or l > 10.0:
            format_penalty += 1.0
            physics_violations.append(f"L={l} um out of bounds [0.5, 10.0]")

        # Total Composite Reward
        total_reward = round(reasoning_score + spice_score - format_penalty, 3)

        return VerifiableRewardBreakdown(
            total_reward=total_reward,
            domain_reasoning_reward=round(reasoning_score, 3),
            spice_rubric_reward=round(spice_score, 3),
            format_penalty=round(format_penalty, 3),
            verifiable_claims_passed=claims_passed,
            total_claims=total_claims,
            physics_violations=physics_violations,
            diagnostics=diagnostics,
        )


class RLDatasetGenerator:
    """
    Generates DPO (Direct Preference Optimization) and GRPO training datasets
    pairing high-reward physical reasoning against low-reward flawed reasoning.
    """

    def __init__(self, output_path: str = "traces/rl_preferences.jsonl"):
        self.output_path = output_path
        self.reward_model = AnalogReasoningRewardModel()

    def generate_sample_preference_pairs(self) -> List[Dict]:
        """
        Creates canonical pairwise preference data for analog circuit reasoning training.
        """
        pairs = [
            {
                "prompt": (
                    "You are sizing an NMOS Common-Source amplifier (Rd=10k, Vdd=3.3V, Vbias=1.0V, Vov=0.3V). "
                    "Target: gain >= 20.0 dB. Your previous candidate W=10 um, L=0.5 um achieved gain = +17.33 dB. "
                    "Analyze the gain gap, verify saturation headroom, and propose the next (W, L)."
                ),
                "chosen": (
                    "Analysis: The current gain is 17.33 dB, falling short of the 20.0 dB target by 2.67 dB. "
                    "Gain magnitude is |Av| = gm * (Rd || ro). In saturation, gm = Kp * (W/L) * Vov. "
                    "To gain 2.67 dB, we need to increase transconductance gm by approximately 1.36x. "
                    "Doubling W from 10 um to 20 um while keeping L at minimum (0.5 um) will increase W/L to 40. "
                    "Headroom check: Drain current Id = 0.5 * 120u * 40 * (0.3)^2 = 216 uA. "
                    "The voltage drop across Rd is 216 uA * 10k = 2.16 V, giving Vout,DC = 3.3 - 2.16 = 1.14 V. "
                    "Since Vds = 1.14 V is comfortably above Vov = 0.3 V (0.84 V saturation margin), M1 remains strictly "
                    "in saturation. Propose: W=20.0 um, L=0.5 um."
                ),
                "rejected": (
                    "The gain is 17.33 dB. To increase gain, we should increase width W to 50 um and reduce L to 0.1 um. "
                    "Higher W always means higher gain regardless of operating region. The DC drop does not matter because "
                    "this is an AC small-signal analysis. Propose: W=50.0 um, L=0.1 um."
                ),
                "chosen_params": {"w": 20.0, "l": 0.5},
                "rejected_params": {"w": 50.0, "l": 0.1},
                "sim_chosen": {"status": "SUCCESS", "gain": 22.99, "vout_dc": 1.14},
                "sim_rejected": {"status": "PHYSICS_VIOLATION", "gain": -5.4, "vout_dc": 0.05, "error_type": "TRIODE_REGION_HEADROOM_EXHAUSTED"},
            },
            {
                "prompt": (
                    "In a Two-Stage Miller OTA, simulation shows Phase Margin = 42° at UGBW = 12 MHz with Cc = 1.0 pF and Rz = 0 Ω. "
                    "Target is Phase Margin >= 60°. What physical mechanism is degrading the phase margin and how should you adjust Cc and Rz?"
                ),
                "chosen": (
                    "Analysis: Phase margin is 42°, which is dangerously low and prone to ringing or oscillation. "
                    "Two physical mechanisms degrade phase margin: "
                    "1. A Right-Half-Plane (RHP) zero at z = gm5/Cc introduces -90° phase lag without amplitude rolloff. "
                    "2. The second pole p2 = gm5/CL is too close to UGBW. "
                    "Remedy: "
                    "First, introduce nulling resistor Rz = 1/gm5 in series with Cc. This eliminates the RHP zero by pushing it to infinity, "
                    "or we can choose Rz > 1/gm5 to pull the zero into the Left-Half-Plane (LHP) to cancel pole p2. "
                    "Second, increase Cc from 1.0 pF to 2.5 pF to lower UGBW and push the dominant pole further inward (stronger pole splitting). "
                    "This combination will restore phase margin >= 60°."
                ),
                "rejected": (
                    "Phase margin is 42°. To increase phase margin, we should decrease the compensation capacitor Cc to 0.2 pF. "
                    "A smaller capacitor charges faster and makes the amplifier respond quicker, which eliminates phase delay. "
                    "Rz can be left at zero because resistors only generate thermal noise."
                ),
                "chosen_params": {"Cc_val": 2.5, "Rz_val": 1.2},
                "rejected_params": {"Cc_val": 0.2, "Rz_val": 0.0},
                "sim_chosen": {"status": "SUCCESS", "phase_margin": 63.5, "gain": 46.2},
                "sim_rejected": {"status": "SPEC_UNSATISFIED", "phase_margin": 18.0, "gain": 44.0},
            }
        ]

        # Score both branches using verifiable reward
        scored_pairs = []
        for pair in pairs:
            r_chosen = self.reward_model.evaluate_reasoning_and_action(
                pair["prompt"], pair["chosen"], pair["chosen_params"], pair["sim_chosen"]
            )
            r_rejected = self.reward_model.evaluate_reasoning_and_action(
                pair["prompt"], pair["rejected"], pair["rejected_params"], pair["sim_rejected"]
            )
            scored_pairs.append({
                **pair,
                "reward_chosen": r_chosen.total_reward,
                "reward_rejected": r_rejected.total_reward,
                "reward_margin": round(r_chosen.total_reward - r_rejected.total_reward, 3),
            })

        # Save to JSONL
        os.makedirs(os.path.dirname(self.output_path), exist_ok=True)
        with open(self.output_path, "w", encoding="utf-8") as fh:
            for item in scored_pairs:
                fh.write(json.dumps(item) + "\n")

        return scored_pairs
