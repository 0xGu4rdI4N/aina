# Razavi Domain Reasoning Benchmark — Run Report

- **Model**: `qwen2.5:7b`
- **Timestamp**: `20261019_172059`
- **Overall Benchmark Score**: `88.8%` (4/4 passed)

---

## RAZAVI-01: Miller Compensation & RHP Zero Elimination [PASSED]

- **Score**: `100.0%`
- **Feedback**: Rigorous analog domain deduction verified.

### Model's Output & Reasoning Stream

```text
1. Pole Splitting: Connecting Cc across the inverting second stage (gain -gm2*R2) multiplies the effective input capacitance via the Miller effect to ~gm2*R2*Cc. This pushes the dominant pole down to p1 ≈ 1 / (gm2 * R1 * R2 * Cc). Simultaneously, the non-dominant pole is pushed out to p2 ≈ gm2 / CL.
2. RHP Zero: At high frequencies, signal flows forward directly from stage 1 through Cc to the output without phase inversion. Because the feedforward path is in-phase with the input while the main amplifier path is inverting (-gm2), they cancel at s = +gm2/Cc, creating a Right-Half-Plane (RHP) zero that adds phase lag without gain rolloff, severely degrading phase margin.
3. Nulling Resistor Rz: Placing Rz in series with Cc creates a zero at z = 1 / [Cc * (1/gm2 - Rz)]. Choosing Rz = 1/gm2 pushes the zero to infinity (eliminating it). Choosing Rz = (1 + CL/Cc) / gm2 moves the zero into the Left-Half-Plane (LHP) to exactly cancel the second pole p2, boosting phase margin.
```

---

## RAZAVI-02: Triode Headroom Collapse in Resistive-Load CS Amplifier [PASSED]

- **Score**: `75.0%`
- **Feedback**: Missing 1 key analytical deductions. Rigorous analog domain deduction verified.

### Model's Output & Reasoning Stream

```text
1. Saturation Relationships: As W increases with fixed L, drain current Id = 0.5*Kp*(W/L)*Vov^2 increases proportionally (5.4 µA per unit W/L), and transconductance gm = Kp*(W/L)*Vov increases proportionally (36 µA/V per unit W/L).
2. DC Output & Triode Boundary: As Id increases, the voltage drop across Rd increases, causing Vout,DC = Vdd - Id*Rd to fall. Saturation requires Vds >= Vgs - Vth = Vov (here Vds >= 0.3 V). When Vout,DC falls below 0.3 V, M1 leaves saturation and collapses into the triode region, causing gm to collapse and output resistance ro to plummet.
3. Critical W/L: To maintain Vds >= 0.3 V on a 3.3 V rail, the maximum allowable drop across Rd is 3.3 V - 0.3 V = 3.0 V. Max Id = 3.0 V / 10 kΩ = 300 µA. Equating 0.5 * 120e-6 * (W/L) * (0.3)^2 = 300e-6 gives: 5.4e-6 * (W/L) = 300e-6 => (W/L)crit = 300 / 5.4 = 55.56.
```

---

## RAZAVI-03: Differential Pair CMRR & Tail Resistance Dependency [PASSED]

- **Score**: `100.0%`
- **Feedback**: Rigorous analog domain deduction verified.

### Model's Output & Reasoning Stream

```text
1. Voltage Gains: In differential mode, the tail node is a virtual ground, yielding Av,DM = -gm * Rd. In common-mode, both sides move in tandem; the tail resistance Rss sees 2*Id, appearing as 2*Rss per branch: Av,CM = -gm*Rd / (1 + 2*gm*Rss) ≈ -Rd / (2*Rss).
2. CMRR: CMRR = |Av,DM / Av,CM| = 1 + 2*gm*Rss ≈ 2*gm*Rss (in decibels: 20*log10(2*gm*Rss)).
3. Physical Role of Rss: Higher Rss provides stronger negative source-degeneration feedback against common-mode disturbances. To boost Rss by a factor of gm*ro without sacrificing supply headroom, designers employ a cascode tail current source or regulated (gain-boosted) cascode.
```

---

## RAZAVI-04: Channel-Length Modulation & Intrinsic Gain Trade-offs [PASSED]

- **Score**: `80.0%`
- **Feedback**: Missing 1 key analytical deductions. Rigorous analog domain deduction verified.

### Model's Output & Reasoning Stream

```text
1. Scaling of gm, ro, and λ: Because W/L and Id are fixed, the overdrive Vov and transconductance gm = sqrt(2*Kp*(W/L)*Id) remain constant. The channel-length modulation parameter λ scales inversely with length (λ ∝ 1/L). Therefore, doubling L halves λ, which doubles output resistance ro = 1 / (λ * Id).
2. Intrinsic Gain: Since gm is unchanged and ro doubles, the intrinsic gain gm * ro doubles (an increase of +6.02 dB).
3. Speed Penalty: To keep W/L constant while L doubles, W must also double. The total gate area W*L quadruples (2W * 2L = 4*W*L). Consequently, gate capacitance Cgg = Cox * W * L increases four-fold, and unity-gain cutoff frequency fT ≈ gm / (2π * Cgg) drops by a factor of 4, sacrificing high-frequency speed for voltage gain.
```

---

