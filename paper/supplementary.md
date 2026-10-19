# RazaviBench: Supplementary Material & Experimental Observation Log

**Companion to:** *RazaviBench: Benchmarking and Verifying Qualitative Small-Signal and Physical Reasoning in Analog IC Design with Large Language Models*  
**Repository:** [https://github.com/0xGu4rdI4N/aina](https://github.com/0xGu4rdI4N/aina)  

---

## Appendix A: Detailed Benchmark Problem Formulations

### Problem `RAZAVI-01`: Miller Compensation & RHP Zero Elimination
* **Domain:** Frequency Response & Stability (Razavi Chapter 10)
* **Difficulty:** Advanced
* **Prompt:**
  ```text
  Consider a two-stage CMOS operational transconductance amplifier (OTA) with a compensation
  capacitor Cc connected between the output of stage 1 and the output of stage 2.
  1. Explain the mechanism of pole splitting and state the approximate dominant pole frequency.
  2. Why does a Right-Half-Plane (RHP) zero appear in the transfer function?
  3. How does adding a nulling resistor Rz in series with Cc eliminate or move this zero into
     the LHP, and what is the optimal condition for Rz in terms of stage 2 transconductance gm2?
  ```
* **Golden Derivation:**
  Connecting $C_c$ across the inverting second stage (gain $-g_{m2} R_2$) multiplies the effective input capacitance to $\approx g_{m2} R_2 C_c$. This pushes the dominant pole down to:
  $$p_1 \approx \frac{1}{g_{m2} R_1 R_2 C_c}$$
  while the output pole moves to $p_2 \approx \frac{g_{m2}}{C_L}$. High-frequency feedforward through $C_c$ bypasses the inversion, creating an RHP zero at $z = +g_{m2}/C_c$ introducing $-90^\circ$ phase lag. Adding $R_z$ in series sets the zero to:
  $$z = \frac{1}{C_c \left(\frac{1}{g_{m2}} - R_z\right)}$$
  Choosing $R_z = 1/g_{m2}$ eliminates the zero ($z \to \infty$). Choosing $R_z = (1 + C_L/C_c)/g_{m2}$ places the zero in the LHP to cancel $p_2$.

---

### Problem `RAZAVI-02`: Triode Headroom Collapse in Resistive-Load CS Amplifier
* **Domain:** MOSFET Biasing & Physical Operating Regions (Razavi Chapter 3)
* **Difficulty:** Introductory
* **Prompt:**
  ```text
  In an NMOS Common-Source amplifier with supply Vdd = 3.3 V, load resistor Rd = 10 kΩ, and gate
  overdrive Vov = Vgs - Vth = 0.3 V (level-1 process with Kp = 120 µA/V²):
  1. If transistor width W is increased while L is fixed, describe what happens to transconductance
     gm and drain current Id in saturation.
  2. What happens to the DC output voltage Vout,DC as W increases, and what is the physical
     condition for the transistor to leave saturation and enter the triode region?
  3. Calculate the critical aspect ratio (W/L)crit at which saturation headroom collapses.
  ```
* **Golden Derivation:**
  In saturation:
  $$I_D = \frac{1}{2} K_p \left(\frac{W}{L}\right) V_{ov}^2, \quad g_m = K_p \left(\frac{W}{L}\right) V_{ov}$$
  Both scale proportionally with $W/L$. Output voltage drops: $V_{out,DC} = V_{DD} - I_D R_D$.
  Active saturation requires $V_{DS} \ge V_{ov} = 0.3\text{ V}$.
  At the boundary:
  $$V_{DD} - I_D R_D = 0.3\text{ V} \implies I_D = \frac{3.3 - 0.3}{10\text{ k}\Omega} = 300\,\mu\text{A}$$
  $$\left(\frac{W}{L}\right)_{\text{crit}} = \frac{300\,\mu\text{A}}{\frac{1}{2} \cdot 120\,\mu\text{A/V}^2 \cdot (0.3\text{ V})^2} = \frac{300}{5.4} = \mathbf{55.56}$$

---

### Problem `RAZAVI-03`: Differential Pair CMRR & Tail Resistance Dependency
* **Domain:** Differential Amplifiers & Common-Mode Rejection (Razavi Chapter 4)
* **Difficulty:** Intermediate
* **Prompt:**
  ```text
  Consider a symmetric NMOS differential pair with resistive loads Rd and a real tail current source
  modeled with finite output resistance Rss.
  1. Derive the differential-mode voltage gain Av,DM and the common-mode voltage gain Av,CM.
  2. Express the Common-Mode Rejection Ratio (CMRR) in terms of small-signal parameters gm, Rd, and Rss.
  3. Why does increasing tail resistance Rss improve CMRR, and what circuit technique is commonly
     used to boost Rss without sacrificing voltage headroom?
  ```
* **Golden Derivation:**
  In differential mode, the tail node is a virtual ground: $A_{v,DM} = -g_m R_D$.
  In common-mode, both sides move symmetrically, degenerating the pair by $2 R_{SS}$:
  $$A_{v,CM} = -\frac{g_m R_D}{1 + 2 g_m R_{SS}} \approx -\frac{R_D}{2 R_{SS}}$$
  $$\text{CMRR} = \left|\frac{A_{v,DM}}{A_{v,CM}}\right| = 1 + 2 g_m R_{SS} \approx 2 g_m R_{SS}$$
  To boost $R_{SS}$ by $g_m r_o$ without consuming DC voltage headroom, designers employ cascode or regulated cascode tail current sources.

---

### Problem `RAZAVI-04`: Channel-Length Modulation & Intrinsic Gain Trade-offs
* **Domain:** Device Physics & Intrinsic Gain (Razavi Chapter 2 & 3)
* **Difficulty:** Intermediate
* **Prompt:**
  ```text
  In analog CMOS design, the intrinsic gain of a MOSFET is defined as gm * ro.
  Assume a designer increases gate length L by a factor of 2 (L_new = 2 * L_old) while keeping
  W/L constant and maintaining the same bias current Id.
  1. How do transconductance gm, output resistance ro, and channel-length modulation parameter λ scale with L?
  2. How does the intrinsic voltage gain gm * ro change?
  3. What trade-off in gate parasitic capacitance Cgg and transition frequency fT does this scaling incur?
  ```
* **Golden Derivation:**
  Because $W/L$ and $I_D$ are fixed, overdrive $V_{ov}$ and $g_m$ remain constant. Channel-length modulation scales inversely with length ($\lambda \propto 1/L$), so doubling $L$ halves $\lambda$, which doubles $r_o = 1/(\lambda I_D)$. Consequently, intrinsic gain $g_m r_o$ doubles (+6.02 dB).
  However, keeping $W/L$ constant while $L$ doubles requires $W$ to double. The total gate area $W \cdot L$ quadruples ($2W \cdot 2L = 4WL$), quadrupling gate capacitance $C_{gg}$ and reducing unity-gain transit frequency $f_T \approx \frac{g_m}{2\pi C_{gg}}$ by a factor of 4.

---

## Appendix B: Model Hallucination Transcripts vs. Sound Derivations

### Case Study: `RAZAVI-02` (Headroom Collapse)

#### 1. Qwen-2.5-7B (4-bit & 8-bit unquantized)
```text
[Failure Mode: Aspect-Ratio Amnesia & Cutoff Confusion]
"In saturation, Id = 1/2 * Kp * (Vgs - Vth)^2.
 Since Vov = 0.3 V is constant, Id is also constant and DOES NOT CHANGE WITH W.
 As W increases, gm increases, but Id remains constant...
 The condition for the transistor to leave saturation and enter the triode region is
 when Vgs is less than the threshold voltage Vth plus Vov...
 Critical aspect ratio: (W/L)crit = 2 * Id / 0.3 V = 360."
```
* **Diagnosis:** Omitted $W/L$ from the current formula; confused the triode boundary ($V_{DS} < V_{ov}$) with sub-threshold cutoff ($V_{GS} < V_{TH}$); arrived at 360 via dimensional nonsense.

#### 2. Qwen-2.5-Math-7B-Instruct (8-bit)
```text
[Failure Mode: Dimensional Inconsistency & Area Multiplication]
"The transductance gm is given by: gm = (2 * Kp * W / L) * sqrt(Vov).
 The drain current Id in saturation is given by: Id = Kp * W * L * Vov^2.
 The condition for the transistor to leave saturation is when Vov becomes zero: Vgs = Vth.
 The gate voltage is given by: Vgs = Vin - (Id * Rd) / 2..."
```
* **Diagnosis:** Multiplied $W \times L$ (gate area in $\mu\text{m}^2$) instead of dividing by aspect ratio ($W/L$); invented $\sqrt{V_{ov}}$ for $g_m$; claimed gate voltage drops through the load resistor.

#### 3. Qwen-2.5-14B-Instruct (Partial Recall with Critical Physics Contradictions)
* **Run Pass Rate:** 0 / 4 (0.0%), Average Score: 38.8%
* **Trace File:** `traces/benchmarks/razavi_qwen2.5_14b_20261019_173826.json`

```text
[Failure Mode A: Factor-of-2 Process Ambiguity in RAZAVI-02]
"Given Kp = 120 uA/V^2, which implies mu_n * Cox = Kp / 2 = 60 uA/V^2...
 Equating: 0.3 mA = 0.045 * 60e-6 * (W/L)
 (W/L)crit = (0.3 / 2.7) * 10^3 = 111.11."
```
* **Diagnosis:** The model understood the physical boundary ($V_{DS} \ge V_{ov}$ and $V_{out,DC} = V_{DD} - I_D R_D$) and scaled $I_D \propto W/L$, but erroneously divided $K_p$ by 2 (interpreting $K_p$ as $2 \mu_n C_{ox}$), resulting in $(W/L)_{\text{crit}} = 111.11$ (exactly $2\times$ the golden 55.56).

```text
[Failure Mode B: Reversed Channel-Length Modulation in RAZAVI-04]
"Assuming lambda does not change significantly with L... ro is inversely proportional to L:
 ro_new = ro_old / 2.
 The intrinsic gain decreases by a factor of 2*sqrt(2) or approximately 2.83:
 gain_new = gain_old / (2*sqrt(2))."
```
* **Diagnosis:** Complete 180-degree physical contradiction. In CMOS physics, channel-length modulation parameter $\lambda$ scales inversely with length ($\lambda \propto 1/L$), meaning longer channel devices have *less* modulation and therefore *higher* output resistance ($r_o = 1/(\lambda I_D) \propto L$). The model claimed $r_o$ and intrinsic gain decrease when $L$ is doubled.

```text
[Failure Mode C: Unphysical Nulling Resistance Formula in RAZAVI-01]
"The value of the nulling resistor Rz should be chosen such that:
 Rz = 1 / (omega_z * gm2 * Cc)..."
```
* **Diagnosis:** Hallucinated a frequency-dependent formula with $\omega_z$ in the denominator instead of the fundamental frequency-independent condition $R_z = 1/g_{m2}$.

---

## Appendix C: SPICE Simulation Environment & Middlebrook Loop

The Two-Stage Miller OTA testbench in [`benchmarks/two_stage_ota.py`](file:///Users/raunak/code/aina/benchmarks/two_stage_ota.py) implements the Middlebrook feedback loop to ensure correct DC biasing without altering AC frequency response:

```text
               Middlebrook Closed-Loop DC / Open-Loop AC Testbench
                          L_fb = 1 GH (Short at DC, Open at AC)
                    ┌───────────────█████████───────────────┐
                    │                                       │
     Vin,DC (1.65V) │                                       ▼
     ───────────────┴──||────────► INN ┌─────────┐
                        C_inn = 1 GF   │ Two-    │
                                       │ Stage   ├────────► OUT (AC measurement)
     Vin,AC (1.65V + 1V AC) ─────────► INP │ OTA     │
                                       └─────────┘
```

* **SPICE Netlist:** [`netlists/two_stage_ota_template.sp`](file:///Users/raunak/code/aina/netlists/two_stage_ota_template.sp)
* **Simulator:** Ngspice-47 (macOS ARM64, `/opt/homebrew/bin/ngspice`)
* **Execution Latency:** 0.06s for complete AC frequency sweep ($1\text{ Hz}$ to $10\text{ GHz}$) and DC operating point (`.op`).

---

## Appendix D: Hardware Setup & Model Telemetry

* **Host Machine:** Apple Silicon (macOS, 16 GB Unified Memory)
* **Local Inference Engine:** Ollama v0.40.4 (`llama.cpp` backend with Metal GPU acceleration)
* **Active Execution Budget:** Max 10 GB RAM allocated to model weights and KV cache.

| Model Identifier | File Size | Memory Footprint | Avg. Latency / Question | Context Window |
| :--- | :---: | :---: | :---: | :---: |
| `qwen2.5:7b` | 4.7 GB | ~4.68 GB | 60–90 s | 32,768 tokens |
| `qwen2.5:7b-instruct-q8_0` | 8.1 GB | ~8.10 GB | 80–110 s | 32,768 tokens |
| `hf.co/bartowski/Qwen2.5-Math-7B-Instruct-GGUF:Q8_0` | 8.1 GB | ~8.10 GB | 70–100 s | 32,768 tokens |
| `qwen2.5:14b` | 9.0 GB | ~8.90 GB | 90–130 s | 32,768 tokens |
