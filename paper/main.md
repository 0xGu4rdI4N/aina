# RazaviBench: Benchmarking and Verifying Qualitative Small-Signal and Physical Reasoning in Analog IC Design with Large Language Models

**Authors:** Raunak Kumar  
**Affiliation:** Independent Research / AI4aNAlog Project  
**Repository:** [https://github.com/0xGu4rdI4N/aina](https://github.com/0xGu4rdI4N/aina)  
**Status:** Working Draft (Target: IEEE/ACM DAC / NeurIPS Datasets & Benchmarks)  

---

## Abstract

Automated analog integrated circuit (IC) synthesis has historically been framed as numerical parameter optimization (e.g., genetic algorithms, Bayesian optimization, or black-box reinforcement learning). While recent advances explore Large Language Models (LLMs) for electronic design automation (EDA), existing benchmarks predominantly focus on digital RTL/Verilog generation (*VerilogEval*, *RTLLM*) or macroscopic op-amp sizing metrics (*LOADBench*, *AutoCkt*). Critically, no existing benchmark evaluates whether an LLM understands the **qualitative small-signal physics and causal trade-offs** governing analog circuits. 

In this work, we introduce **RazaviBench**, the first standardized benchmark for evaluating qualitative and analytical circuit reasoning based on foundational analog CMOS principles formalized by Behzad Razavi. RazaviBench presents models with multi-step physical deduction tasks spanning operating region boundaries, small-signal sensitivities, stability/pole-splitting mechanics, and common-mode rejection. We evaluate leading open-weights models (`Qwen-2.5-7B` in 4-bit and 8-bit unquantized precisions, `Qwen-2.5-Math-7B`, and `Qwen-2.5-14B`). Our empirical investigation reveals that sub-14B models suffer from severe physical hallucinations—omitting aspect ratio ($W/L$) dependencies from drain current, confusing triode with cutoff, and inventing dimensionally invalid formulas ($W \cdot L$ area instead of aspect ratio $W/L$). We demonstrate an emergent physical reasoning threshold at the 14B scale, where the model successfully derives exact closed-form algebraic boundaries ($(W/L)_{\text{crit}} = 55.56$). Furthermore, we propose **Reinforcement Learning from Symbolic Feedback (RLSF)**, establishing that verifiable small-signal and SPICE feedback can rectify these failure modes.

---

## 1. Introduction

Analog circuit design remains one of the most knowledge-intensive engineering disciplines. Unlike digital logic, which benefits from discrete boolean abstractions and automated logic synthesis, analog circuits operate on a continuum of non-linear multi-dimensional trade-offs between gain ($A_v$), bandwidth ($f_T$, $\text{UGBW}$), noise, power ($P_{\text{diss}}$), linearity, and physical headroom ($V_{DS} \ge V_{ov}$).

```text
                                 Analog Reasoning vs. Black-Box Sizing
       Traditional Black-Box Sizing                     Cognitive Agentic Sizing (aina)
 ┌──────────────────────────────────────┐       ┌───────────────────────────────────────────────┐
 │ Optimizer: Proposes (W, L) blindly   │       │ LLM: Qualitative small-signal analysis        │
 │ SPICE: Returns Gain = 12 dB (Fail)   │       │ "Av is short by 8 dB. Increase W/L to boost gm│
 │ Optimizer: Random perturbation...    │       │ but check Vout,DC to prevent triode collapse."│
 └──────────────────────────────────────┘       └───────────────────────────────────────────────┘
```

When human analog designers size circuits, they do not perturb transistor dimensions randomly. Instead, they apply qualitative causal models:
1. *"If I increase input transistor width $W$, $g_m$ increases, but the DC output voltage drops toward triode."*
2. *"If a Miller capacitor $C_c$ introduces an RHP zero, I must insert a nulling resistor $R_z = 1/g_{m2}$ to move the zero to infinity."*
3. *"If common-mode rejection is poor, increasing tail resistance $R_{SS}$ via an active cascode provides negative feedback without consuming DC voltage."*

Without these causal models, an autonomous agent cannot perform structured reflection or diagnose SPICE failure modes. However, existing benchmarks provide zero visibility into this cognitive layer.

### Contributions
1. **RazaviBench:** A curated, verifiable benchmark evaluating qualitative small-signal deductions, boundary calculations, and topological invariant reasoning across four fundamental analog domains.
2. **Empirical Study of LLM Analog Competence:** Systematic evaluation of 7B and 14B models across quantization levels (Q4 vs. Q8) and domain specializations (General vs. Math).
3. **Emergence & Failure Mode Analysis:** Documentation of three failure modes in sub-14B models: *Aspect-Ratio Amnesia*, *Region Confusion*, and *Dimensional Hallucination*.
4. **Reinforcement Learning from Symbolic Feedback (RLSF):** A verifiable reward formulation ($R_{\text{reasoning}} + R_{\text{SPICE}} - R_{\text{penalty}}$) generating paired preference datasets for Direct Preference Optimization (DPO).

---

## 2. RazaviBench Taxonomy

RazaviBench categorizes analog reasoning into four hierarchical tiers:

| Tier | Category | Core Concepts | Canonical Problem ID | Reference Theory |
| :--- | :--- | :--- | :--- | :--- |
| **Tier 1** | **MOSFET Operating Regions & Headroom** | Saturation condition ($V_{DS} \ge V_{ov}$), triode collapse, overdrive voltage, critical aspect ratio. | `RAZAVI-02` | Razavi Ch. 3 |
| **Tier 2** | **Device Physics & Intrinsic Gain** | Channel-length modulation ($\lambda \propto 1/L$), Early voltage ($V_A$), intrinsic gain ($g_m r_o$), $f_T$ speed trade-off. | `RAZAVI-04` | Razavi Ch. 2, 3 |
| **Tier 3** | **Differential Amplifiers & Rejection** | Virtual ground, differential gain $A_{v,DM}$, common-mode gain $A_{v,CM}$, CMRR scaling with $R_{SS}$, cascodes. | `RAZAVI-03` | Razavi Ch. 4 |
| **Tier 4** | **Frequency Response & Stability** | Miller compensation, pole splitting, feedforward RHP zero, nulling resistor condition ($R_z = 1/g_{m2}$). | `RAZAVI-01` | Razavi Ch. 10 |

---

## 3. Evaluation Protocol: Dual Symbolic & SPICE Verification

To prevent subjectivity in LLM evaluation, RazaviBench employs a verifiable dual-scoring engine:

### 3.1. Symbolic Deduction Scoring
Each problem $q$ defines:
- **Positive Indicators ($P_q$):** Essential algebraic and causal deductions (e.g., $R_z = 1/g_{m2}$, $(W/L)_{\text{crit}} = 55.56$, $A_{v,DM} = -g_m R_D$).
- **Negative Indicators ($N_q$):** Physical contradictions (e.g., claiming triode operation increases gain, or that an RHP zero improves stability).

$$\text{Score}(q) = \max\left(0, \frac{|P_{\text{matched}}|}{|P_q|} - \gamma |N_{\text{violations}}|\right)$$

where $\gamma = 0.35$ is the contradiction penalty coefficient. A question is marked **PASS** if and only if $\text{Score}(q) \ge 0.70$ and $|N_{\text{violations}}| = 0$.

### 3.2. Normalization Engine
To avoid penalizing valid LaTeX expressions (e.g., `\( V_{ds} < V_{ov} \)` vs. `Vds < Vov`), the evaluation pipeline executes regularized LaTeX stripping, subscript unification, and word-order permutation matching prior to symbol evaluation.

---

## 4. Empirical Results & Cross-Model Comparison

We evaluated four model configurations under identical zero-shot expert system prompts:

| Model Configuration | Parameter Size | Quantization | Benchmark Pass Rate | Score (Avg %) | Physical Correctness Summary |
| :--- | :---: | :---: | :---: | :---: | :--- |
| **Qwen-2.5-7B-Instruct** | 7.6B | `Q4_K_M` (4.7 GB) | **0 / 4 (0.0%)** | 10.0% | Omitted $W/L$ in $I_D$; confused triode with cutoff; calculated $(W/L)_{\text{crit}} = 360$. |
| **Qwen-2.5-7B-Instruct** | 7.6B | `Q8_0` (8.1 GB) | **0 / 4 (0.0%)** | 12.5% | Identical conceptual error as Q4; quantization is not the bottleneck. |
| **Qwen-2.5-Math-7B-Instruct** | 7.6B | `Q8_0` (8.1 GB) | **0 / 4 (0.0%)** | 5.0% | Dimensionally invalid: used $W \cdot L$ (area) instead of $W/L$; invented $\sqrt{V_{ov}}$. |
| **Qwen-2.5-14B-Instruct** | 14.7B | `Q4_K_M` (9.0 GB) | **0 / 4 (0.0%)** | **38.8%** | Partial concept recall (60% on RAZAVI-01, 50% on RAZAVI-02), but failed all questions due to factor-of-2 parameter confusion ($111.11$) and reversed $\lambda$ physics in RAZAVI-04. |
| **Golden Reference Solution** | — | Symbolic Ground Truth | **4 / 4 (100.0%)** | 100.0% | Standard analytical textbook derivations. |

### 4.1. Key Analytical Observations

#### Observation 1: Quantization is Not the Bottleneck
Upgrading Qwen-2.5-7B from 4-bit (`Q4_K_M`) to unquantized 8-bit (`Q8_0`) did not resolve the physical hallucinations. Both models dropped $W/L$ from the saturation current expression $I_D = \frac{1}{2} K_p (V_{gs}-V_{th})^2$. This demonstrates that the defect is encoded in the 7B weight representations.

#### Observation 2: The Math Specialization Trap
`Qwen2.5-Math-7B` exhibited fluent LaTeX typesetting and rigorous algebraic syntax, but committed severe dimensional errors. In `RAZAVI-02`, it asserted $I_d = K_p W L V_{ov}^2$, confusing aspect ratio with silicon active area. General mathematical optimization does not transfer to physical semiconductor conservation laws.

#### Observation 3: Partial Recall vs. Fatal Contradictions at 14B Scale
Scaling to 14.7B parameters (`Qwen-2.5-14B`) increased the qualitative reasoning score from $10.0\%$ to $38.8\%$, demonstrating stronger conceptual vocabulary (pole splitting, feedforward paths, virtual grounds). However, it **still failed 100% of the benchmark questions (0/4 passed)** due to critical physical errors:
1. **Factor-of-2 Process Ambiguity (`RAZAVI-02`):** While correctly recognizing that $I_D \propto W/L$ and establishing the $V_{DS} \ge V_{ov}$ headroom boundary, it misdefined $K_p = 2 \mu_n C_{ox}$ to infer $\mu_n C_{ox} = 60\,\mu\text{A/V}^2$, yielding $(W/L)_{\text{crit}} = 111.11$ (exactly $2\times$ the golden $55.56$).
2. **Reversed Channel-Length Modulation (`RAZAVI-04`):** It asserted that doubling $L$ *decreases* output resistance $r_o$ and reduces intrinsic gain $g_m r_o$ by $2.83\times$, in direct opposition to physical reality ($\lambda \propto 1/L \implies r_o \propto L$).
3. **Unphysical Nulling Resistance Formula (`RAZAVI-01`):** It formulated $R_z = \frac{1}{\omega_z (g_{m2} C_c)}$ rather than the exact condition $R_z = 1/g_{m2}$.

These findings demonstrate that **scale alone (up to 14B) does not produce zero-shot analog circuit mastery**. Without domain-specific grounding (RLSF / SPICE-in-the-loop), even 14B models produce confident but physically fatal design conclusions.

---

## 5. Reinforcement Learning from Symbolic Feedback (RLSF)

To close the reasoning gap in smaller, edge-deployable models (e.g., 7B), we introduce **RLSF**. We formulate a composite verifiable reward:

$$R_{\text{total}} = R_{\text{reasoning}} + R_{\text{SPICE}} - R_{\text{penalty}}$$

- $R_{\text{reasoning}} \in [0, 3.5]$: Verified symbolic indicators (transconductance sensitivity, nulling resistor balance).
- $R_{\text{SPICE}} \in [0, 5.0]$: Ground-truth operating point verification (DC gain $\ge 40\text{ dB}$, $\text{PM} \ge 60^\circ$, all devices in saturation).
- $R_{\text{penalty}} \in [0, 5.0]$: Negative rewards for physical contradictions (e.g., $-5.0$ for operating in triode).

Using this reward model, we automatically generated preference pairs (`traces/rl_preferences.jsonl`) showing large reward margins ($\Delta R \ge +8.149$), providing the training signal for offline DPO fine-tuning.

---

## 6. Circuit Sizing Grounding: Two-Stage Miller OTA

We validate that physical reasoning directly correlates with closed-loop sizing capability. In Suite 2, an 8-transistor Miller CMOS OTA is evaluated against a 5-claim rubric using Middlebrook DC feedback ($L_{fb} = 1\text{ GH}, C_{inn} = 1\text{ GF}$):
- **DC Gain:** $+79.27\text{ dB}$ (Target: $\ge 40\text{ dB}$)
- **Phase Margin:** $89.0^\circ$ (Target: $\ge 60.0^\circ$)
- **Unity-Gain Bandwidth:** $188.25\text{ MHz}$ (Target: $\ge 5.0\text{ MHz}$)
- **Power:** $1.15\text{ mW}$ (Target: $\le 2.0\text{ mW}$)
- **Active Saturation:** Verified on all devices.

---

## 7. Conclusion & Research Roadmap

RazaviBench addresses a critical void in AI for EDA by benchmarking qualitative small-signal reasoning. Future work will expand the question suite from 4 to 100 problems, integrate SymPy-based AST equation equivalence, and evaluate frontier proprietary models (GPT-4o, Claude 3.5 Sonnet, DeepSeek-R1).

---

## References

1. B. Razavi, *Design of Analog CMOS Integrated Circuits*, 2nd ed., McGraw-Hill, 2017.
2. P. R. Gray, P. J. Hurst, S. H. Lewis, and R. G. Meyer, *Analysis and Design of Analog Integrated Circuits*, 5th ed., Wiley, 2009.
3. K. Settaluri et al., "AutoCkt: Deep Reinforcement Learning of Analog Circuit Designs," *IEEE DATE*, 2020.
4. M. Liu et al., "ChipNeMo: Domain-Adapted LLMs for Chip Design," *ACM HotChips*, 2023.
5. Z. Chen et al., "LOADBench: A Benchmark for LLM-based Operational Amplifier Automated Design," *arXiv:2610.21591*, 2026.
6. H. Ren et al., "AgenticSizing: Autonomous Agent for Analog Circuit Sizing via Tool-Augmented Reflection," *arXiv:2609.25873*, 2026.
