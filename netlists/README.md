# SPICE Netlists & Device Modeling Directory 📐⚡

This directory contains production-grade SPICE (`.sp`) netlists and templates for **aina** (**AI**4a**NA**log). Rather than treating circuit simulation as an abstract black-box mathematical equation, **aina** interfaces directly with physical SPICE netlists evaluated by **Ngspice-47**.

---

## Netlist Inventory

| File | Type | Description |
|------|------|-------------|
| [`common_source_template.sp`](common_source_template.sp) | Parameterized Template | Dynamic template injected with agent-chosen transistor width `{W_val}`, length `{L_val}`, and layout parasitic capacitance `{C_para}`. |
| [`common_source_nominal.sp`](common_source_nominal.sp) | Golden Reference | Standalone runnable netlist sized at the optimal convergence operating point ($W = 20\ \mu\text{m}, L = 0.5\ \mu\text{m}, C_{para} = 30\text{ fF}$). |

---

## Circuit Architecture

The benchmark topology is a classic **NMOS Common-Source (CS) Amplifier** with a resistive drain load:

```
               Vdd (3.3V)
                 │
                 ├──[ Rd = 10kΩ ]
                 │
                 ├───o Vout (DC operating point & AC output)
                 │   │
                 │  === C_parasitic (1.5 fF / µm × W)
                 │   │
                ┌┴┐  0 (GND)
  Vbias (1.0V) ─┤M1 (W, L)
  + Vac (1.0V)  └┬┘
                 │
               0 (GND)
```

### 1. Device Physics & Model Parameters

Level-1 Shichman-Hodges NMOS model (`nfet`):
- **Transconductance parameter ($K_p$):** $120\ \mu\text{A/V}^2$
- **Threshold voltage ($V_{to}$):** $0.70\text{ V}$
- **Channel-length modulation ($\lambda$):** $0.02\text{ V}^{-1}$
- **DC Gate Bias ($V_{bias}$):** $1.0\text{ V} \implies V_{ov} = V_{gs} - V_{to} = 0.30\text{ V}$
- **Power Supply ($V_{dd}$):** $3.3\text{ V}$
- **Drain Load Resistance ($R_d$):** $10\text{ k}\Omega$

### 2. Layout Parasitic Penalty Model

In real silicon layout, increasing transistor gate width $W$ broadens gate area and junction diffusion perimeters, introducing parasitic routing and junction capacitance. **aina** models this layout trade-off explicitly:

$$C_{\text{parasitic}} = 1.5\ \text{fF} \times W\ (\mu\text{m})$$

### 3. Saturation Headroom Protection

For linear amplification, transistor $M_1$ must satisfy the saturation condition:

$$V_{ds} \ge V_{ov} = 0.30\text{ V}$$

If the agent requests an excessively large $W/L$ ratio ($> 55$), drain current $I_d \cdot R_d$ exceeds the supply rail margin, collapsing $V_{out,DC}$ below $0.30\text{ V}$ into the **triode / linear region**. **aina** intercepts this condition and guides the agent to recover.

---

## Standalone Simulation

You can verify the golden nominal netlist directly without Python:

```bash
ngspice -b netlists/common_source_nominal.sp
```

Expected output:
```text
v(out)      = 1.093 V    (Saturation check: Vds >= 0.30 V: PASS)
gain_mag[0] = 22.99 dB   (Target: >= 20.0 dB: PASS)
```
