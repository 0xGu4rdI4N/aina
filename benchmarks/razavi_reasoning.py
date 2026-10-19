"""
razavi_reasoning.py — Razavi Domain Reasoning Benchmark for Analog ICs
=====================================================================
Evaluates an LLM or agent's qualitative and analytical circuit reasoning against
canonical problems in analog CMOS IC design (inspired by Behzad Razavi's foundational
analog principles: Miller pole splitting, headroom exhaustion, CMRR, and intrinsic gain).

Provides verifiable symbolic checks for Reinforcement Learning with Verifiable Rewards (RLVR).
"""

import re
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional


@dataclass
class RazaviQuestion:
    """A standardized analog circuit domain reasoning problem."""
    qid: str
    title: str
    domain: str
    difficulty: str  # "Introductory", "Intermediate", "Advanced"
    prompt: str
    required_concepts: List[str]
    positive_indicators: List[str]
    negative_indicators: List[str]
    golden_explanation: str
    reference_answer: str


def get_default_razavi_suite() -> List[RazaviQuestion]:
    """Returns the canonical Razavi analog reasoning benchmark suite."""
    return [
        RazaviQuestion(
            qid="RAZAVI-01",
            title="Miller Compensation & RHP Zero Elimination",
            domain="Frequency Response & Stability",
            difficulty="Advanced",
            prompt=(
                "Consider a two-stage CMOS operational transconductance amplifier (OTA) with a "
                "compensation capacitor Cc connected between the output of stage 1 and the output of stage 2. "
                "1. Explain the mechanism of pole splitting and state the approximate dominant pole frequency. "
                "2. Why does a Right-Half-Plane (RHP) zero appear in the transfer function? "
                "3. How does adding a nulling resistor Rz in series with Cc eliminate or move this zero into the LHP, "
                "and what is the optimal condition for Rz in terms of stage 2 transconductance gm2?"
            ),
            required_concepts=[
                "pole splitting",
                "dominant pole",
                "RHP zero",
                "nulling resistor",
                "gm2",
            ],
            positive_indicators=[
                r"(?i)pole\s+splitting",
                r"(?i)gm2\s*[\*\/]?\s*r1\s*r2\s*cc|1\s*/\s*\(\s*gm2\s*r1\s*r2\s*cc\)",
                r"(?i)feedforward\s+(path|current)|through\s+cc",
                r"(?i)rz\s*=\s*1\s*/\s*gm2|1\s*/\s*gm2",
                r"(?i)left-half\s+plane|lhp|cancel\s+(the\s+)?(second|nondominant)\s+pole",
            ],
            negative_indicators=[
                r"(?i)rhp\s+zero\s+improves\s+phase\s+margin",  # False: RHP zero degrades phase margin!
                r"(?i)rz\s+decreases\s+dc\s+gain",             # False: Rz does not alter DC gain
                r"(?i)increasing\s+cc\s+destabilizes",         # False: Cc provides dominant pole compensation
            ],
            golden_explanation=(
                "Miller capacitor Cc causes pole splitting: the dominant pole shifts to ~1/(gm2*R1*R2*Cc), "
                "while the output pole shifts to ~gm2/CL. A high-frequency feedforward path through Cc to the output "
                "creates an RHP zero at z = gm2/Cc, which introduces -90° phase lag and degrades phase margin. "
                "Adding nulling resistor Rz in series with Cc alters the zero location to z = 1 / (Cc * (1/gm2 - Rz)). "
                "Setting Rz = 1/gm2 eliminates the zero entirely (moves it to infinity), and setting Rz > 1/gm2 moves it "
                "into the LHP where it provides phase lead (+90°), often used to cancel the non-dominant pole."
            ),
            reference_answer=(
                "1. Pole Splitting: Connecting Cc across the inverting second stage (gain -gm2*R2) multiplies the effective "
                "input capacitance via the Miller effect to ~gm2*R2*Cc. This pushes the dominant pole down to "
                "p1 ≈ 1 / (gm2 * R1 * R2 * Cc). Simultaneously, the non-dominant pole is pushed out to p2 ≈ gm2 / CL.\n"
                "2. RHP Zero: At high frequencies, signal flows forward directly from stage 1 through Cc to the output "
                "without phase inversion. Because the feedforward path is in-phase with the input while the main amplifier "
                "path is inverting (-gm2), they cancel at s = +gm2/Cc, creating a Right-Half-Plane (RHP) zero that adds "
                "phase lag without gain rolloff, severely degrading phase margin.\n"
                "3. Nulling Resistor Rz: Placing Rz in series with Cc creates a zero at z = 1 / [Cc * (1/gm2 - Rz)]. "
                "Choosing Rz = 1/gm2 pushes the zero to infinity (eliminating it). Choosing Rz = (1 + CL/Cc) / gm2 moves the "
                "zero into the Left-Half-Plane (LHP) to exactly cancel the second pole p2, boosting phase margin."
            ),
        ),
        RazaviQuestion(
            qid="RAZAVI-02",
            title="Triode Headroom Collapse in Resistive-Load CS Amplifier",
            domain="MOSFET Biasing & Physical Operating Regions",
            difficulty="Introductory",
            prompt=(
                "In an NMOS Common-Source amplifier with supply Vdd = 3.3 V, load resistor Rd = 10 kΩ, and gate overdrive "
                "Vov = Vgs - Vth = 0.3 V (level-1 process with Kp = 120 µA/V²): "
                "1. If transistor width W is increased while L is fixed, describe what happens to transconductance gm and "
                "drain current Id in saturation. "
                "2. What happens to the DC output voltage Vout,DC as W increases, and what is the physical condition for the "
                "transistor to leave saturation and enter the triode region? "
                "3. Calculate the critical aspect ratio (W/L)crit at which saturation headroom collapses."
            ),
            required_concepts=[
                "saturation",
                "triode",
                "Vds >= Vov",
                "drain current",
                "critical W/L",
            ],
            positive_indicators=[
                r"(?i)gm\s+increases|id\s+increases",
                r"(?i)vout\s*(,|decreases|drops|falls)",
                r"(?i)vds\s*(<|<=|less\s+than)\s*vov|vds\s*<\s*0\.3",
                r"(?i)55|55\.5|55\.6|56",  # Critical W/L: (3.3 - 0.3) / (0.5 * 120u * 0.3^2 * 10k) = 3.0 / 0.054 = 55.55
            ],
            negative_indicators=[
                r"(?i)vout\s+increases\s+as\s+w\s+increases",  # False: Id increases so Vout drops
                r"(?i)gm\s+increases\s+in\s+triode",          # False: gm collapses in triode
            ],
            golden_explanation=(
                "In saturation, Id = 0.5 * Kp * (W/L) * Vov^2 and gm = Kp * (W/L) * Vov. Increasing W increases both Id and gm. "
                "However, Vout,DC = Vdd - Id * Rd decreases linearly with W/L. For saturation, M1 requires Vds >= Vov = 0.3 V. "
                "Therefore, Vdd - Id * Rd >= 0.3 V implies Id * Rd <= 3.0 V, so Id <= 300 µA. "
                "Since Id = 5.4 µA * (W/L), (W/L)crit = 300 µA / 5.4 µA = 55.56. Beyond W/L = 55.56, M1 collapses into triode."
            ),
            reference_answer=(
                "1. Saturation Relationships: As W increases with fixed L, drain current Id = 0.5*Kp*(W/L)*Vov^2 increases "
                "proportionally (5.4 µA per unit W/L), and transconductance gm = Kp*(W/L)*Vov increases proportionally (36 µA/V per unit W/L).\n"
                "2. DC Output & Triode Boundary: As Id increases, the voltage drop across Rd increases, causing Vout,DC = Vdd - Id*Rd "
                "to fall. Saturation requires Vds >= Vgs - Vth = Vov (here Vds >= 0.3 V). When Vout,DC falls below 0.3 V, M1 leaves saturation "
                "and collapses into the triode region, causing gm to collapse and output resistance ro to plummet.\n"
                "3. Critical W/L: To maintain Vds >= 0.3 V on a 3.3 V rail, the maximum allowable drop across Rd is 3.3 V - 0.3 V = 3.0 V. "
                "Max Id = 3.0 V / 10 kΩ = 300 µA. Equating 0.5 * 120e-6 * (W/L) * (0.3)^2 = 300e-6 gives: "
                "5.4e-6 * (W/L) = 300e-6 => (W/L)crit = 300 / 5.4 = 55.56."
            ),
        ),
        RazaviQuestion(
            qid="RAZAVI-03",
            title="Differential Pair CMRR & Tail Resistance Dependency",
            domain="Differential Amplifiers & Common-Mode Rejection",
            difficulty="Intermediate",
            prompt=(
                "Consider a symmetric NMOS differential pair with resistive loads Rd and a real tail current source modeled "
                "with finite output resistance Rss. "
                "1. Derive the differential-mode voltage gain Av,DM and the common-mode voltage gain Av,CM. "
                "2. Express the Common-Mode Rejection Ratio (CMRR) in terms of small-signal parameters gm, Rd, and Rss. "
                "3. Why does increasing tail resistance Rss improve CMRR, and what circuit technique is commonly used to boost Rss "
                "without sacrificing voltage headroom?"
            ),
            required_concepts=[
                "differential gain",
                "common-mode gain",
                "CMRR",
                "Rss",
                "cascode tail",
            ],
            positive_indicators=[
                r"(?i)av,?dm\s*=\s*-?\s*gm\s*\*?\s*rd",
                r"(?i)av,?cm\s*[:=≈].*(gm\s*\*?\s*rd|rd\s*/\s*\(?2\s*\*?\s*rss\)?)",
                r"(?i)cmrr\s*[:=≈].*(gm\s*\*?\s*rss|2\s*\*?\s*gm\s*\*?\s*rss)",
                r"(?i)cascode|active\s+current\s+source|regulated\s+cascode",
            ],
            negative_indicators=[
                r"(?i)cmrr\s+decreases\s+as\s+rss\s+increases",  # False
                r"(?i)av,?dm\s+depends\s+strongly\s+on\s+rss",   # False: differential virtual ground isolates Rss
            ],
            golden_explanation=(
                "Differential gain is Av,DM = -gm * Rd because the tail node acts as a virtual ground. "
                "Common-mode gain is Av,CM ≈ -Rd / (2 * Rss) (or -gm*Rd / (1 + 2*gm*Rss)). "
                "CMRR = |Av,DM / Av,CM| ≈ 1 + 2*gm*Rss ≈ 2*gm*Rss. Increasing Rss increases negative feedback for common-mode signals, "
                "attenuating Av,CM and boosting CMRR. Cascode current sources are used to boost Rss by gm*ro without consuming excessive DC voltage."
            ),
            reference_answer=(
                "1. Voltage Gains: In differential mode, the tail node is a virtual ground, yielding Av,DM = -gm * Rd. "
                "In common-mode, both sides move in tandem; the tail resistance Rss sees 2*Id, appearing as 2*Rss per branch: "
                "Av,CM = -gm*Rd / (1 + 2*gm*Rss) ≈ -Rd / (2*Rss).\n"
                "2. CMRR: CMRR = |Av,DM / Av,CM| = 1 + 2*gm*Rss ≈ 2*gm*Rss (in decibels: 20*log10(2*gm*Rss)).\n"
                "3. Physical Role of Rss: Higher Rss provides stronger negative source-degeneration feedback against common-mode disturbances. "
                "To boost Rss by a factor of gm*ro without sacrificing supply headroom, designers employ a cascode tail current source or "
                "regulated (gain-boosted) cascode."
            ),
        ),
        RazaviQuestion(
            qid="RAZAVI-04",
            title="Channel-Length Modulation & Intrinsic Gain Trade-offs",
            domain="Device Physics & Intrinsic Gain",
            difficulty="Intermediate",
            prompt=(
                "In analog CMOS design, the intrinsic gain of a MOSFET is defined as gm * ro. "
                "Assume a designer increases gate length L by a factor of 2 (L_new = 2 * L_old) while keeping W/L constant "
                "and maintaining the same bias current Id. "
                "1. How do transconductance gm, output resistance ro, and channel-length modulation parameter λ scale with L? "
                "2. How does the intrinsic voltage gain gm * ro change? "
                "3. What trade-off in gate parasitic capacitance Cgg and transition frequency fT does this scaling incur?"
            ),
            required_concepts=[
                "intrinsic gain",
                "lambda",
                "ro increases",
                "ft decreases",
                "parasitic capacitance",
            ],
            positive_indicators=[
                r"(?i)gm\s+(remains\s+constant|unchanged|same|is\s+unchanged)",
                r"(?i)lambda\s+(is\s+inversely|decreases|halved|drops|scales\s+inversely)",
                r"(?i)ro\s+(doubles|increases|scales\s+with\s+l)",
                r"(?i)gm\s*\*?\s*ro\s+(doubles|increases|scales)",
                r"(?i)(cgg|capacitance)\s+.*(quadruples|increases|four-fold)|(ft|frequency)\s+.*(decreases|drops|halved|4)",
            ],

            negative_indicators=[
                r"(?i)ro\s+decreases\s+as\s+l\s+increases",  # False: ro = 1/(lambda*Id) increases because lambda ~ 1/L
                r"(?i)ft\s+increases\s+with\s+larger\s+l",   # False: fT ~ gm / Cgg decreases with larger L
            ],
            golden_explanation=(
                "Since W/L and Id are fixed, Vov and gm remain constant. Parameter λ is inversely proportional to channel length (λ ∝ 1/L), "
                "so doubling L halves λ and doubles output resistance ro = 1/(λ*Id). Thus, intrinsic gain gm*ro doubles (+6 dB). "
                "However, gate area W*L quadruples (since W also doubled to maintain W/L), increasing gate capacitance Cgg by 4x "
                "and reducing transition frequency fT ≈ gm / (2π*Cgg) by 4x."
            ),
            reference_answer=(
                "1. Scaling of gm, ro, and λ: Because W/L and Id are fixed, the overdrive Vov and transconductance gm = sqrt(2*Kp*(W/L)*Id) "
                "remain constant. The channel-length modulation parameter λ scales inversely with length (λ ∝ 1/L). Therefore, doubling L "
                "halves λ, which doubles output resistance ro = 1 / (λ * Id).\n"
                "2. Intrinsic Gain: Since gm is unchanged and ro doubles, the intrinsic gain gm * ro doubles (an increase of +6.02 dB).\n"
                "3. Speed Penalty: To keep W/L constant while L doubles, W must also double. The total gate area W*L quadruples (2W * 2L = 4*W*L). "
                "Consequently, gate capacitance Cgg = Cox * W * L increases four-fold, and unity-gain cutoff frequency fT ≈ gm / (2π * Cgg) "
                "drops by a factor of 4, sacrificing high-frequency speed for voltage gain."
            ),
        ),
    ]


def evaluate_reasoning_response(question: RazaviQuestion, response_text: str) -> Dict:
    """
    Evaluates an agent/LLM response against verifiable symbolic rubric indicators.

    Returns
    -------
    dict:
        score: float (0.0 to 1.0)
        passed: bool
        matched_positives: list of str
        detected_violations: list of str
        feedback: str (diagnostic for RL reward modeling)
    """
    pos_matches = []
    for pattern in question.positive_indicators:
        if re.search(pattern, response_text):
            pos_matches.append(pattern)

    neg_violations = []
    for pattern in question.negative_indicators:
        if re.search(pattern, response_text):
            neg_violations.append(pattern)

    # Score calculation
    pos_ratio = len(pos_matches) / len(question.positive_indicators) if question.positive_indicators else 1.0
    penalty = 0.35 * len(neg_violations)

    score = max(0.0, min(1.0, pos_ratio - penalty))
    passed = (score >= 0.70) and (len(neg_violations) == 0)

    feedback_notes = []
    if neg_violations:
        feedback_notes.append(f"Physical contradictions detected ({len(neg_violations)} violations).")
    if pos_ratio < 1.0:
        missing_count = len(question.positive_indicators) - len(pos_matches)
        feedback_notes.append(f"Missing {missing_count} key analytical deductions.")
    if passed:
        feedback_notes.append("Rigorous analog domain deduction verified.")

    return {
        "qid": question.qid,
        "title": question.title,
        "score": round(score, 3),
        "passed": passed,
        "matched_positives": pos_matches,
        "detected_violations": neg_violations,
        "feedback": " ".join(feedback_notes) or "Evaluation complete.",
    }


class RazaviBenchmark:
    """Benchmark harness executing and scoring Razavi qualitative circuit problems."""

    def __init__(self, questions: Optional[List[RazaviQuestion]] = None):
        self.questions = questions or get_default_razavi_suite()

    def run_on_solver(self, solver_fn: Callable[[str], str]) -> Dict:
        """
        Runs the benchmark on a model callable (prompt -> response_text).

        Parameters
        ----------
        solver_fn : Callable taking prompt string and returning generated text.
        """
        results = []
        total_score = 0.0

        for q in self.questions:
            answer = solver_fn(q.prompt)
            eval_res = evaluate_reasoning_response(q, answer)
            eval_res["generated_answer"] = answer
            results.append(eval_res)
            total_score += eval_res["score"]

        avg_score = (total_score / len(self.questions)) * 100.0 if self.questions else 0.0
        pass_count = sum(1 for r in results if r["passed"])

        return {
            "total_questions": len(self.questions),
            "passed_questions": pass_count,
            "pass_rate_pct": round((pass_count / len(self.questions)) * 100.0, 1),
            "benchmark_score": round(avg_score, 1),
            "question_evaluations": results,
        }
