* aina v1.0 -- Common-Source Amplifier Template (AI4aNAlog)
* ============================================================================
* Parameterized netlist template used by aina's agentic sizing loop.
* Placeholders {W_val}, {L_val}, and {C_para} are dynamically substituted
* during closed-loop evaluation.
*
* Topology:
*   NMOS Common-Source Amplifier with resistive load (Rd = 10 kOhm)
*   DC Gate Bias: Vbias = 1.0 V (Vov = Vgs - Vto = 0.3 V -> saturation)
*   Supply Rails: Vdd = 3.3 V, Gnd = 0 V
* ============================================================================

* 1. MOS Transistor Model (Level-1 Shichman-Hodges)
.model nfet nmos (
+  level  = 1
+  vto    = 0.70
+  kp     = 120u
+  lambda = 0.02
+)

* 2. Voltage Sources
* Power Supply Rail
Vdd vdd 0 DC 3.3

* Gate DC Bias + Small-Signal AC Drive
* Vgs = 1.0 V keeps M1 in saturation across W in [1, 50] um
Vbias gate 0 DC 1.0 AC 1.0

* 3. Active Devices
* Sized by the AI agent: Width (W_val) and Channel Length (L_val) in um
M1 out gate 0 0 nfet W={W_val}u L={L_val}u

* 4. Passive Elements
* Resistive Drain Load (10 kOhm)
Rd vdd out 10k

* Layout Parasitic Capacitance Penalty (C_parasitic = 1.5 fF per um of width)
Cparasitic out 0 {C_para}f

* 5. Simulation & Analysis Control
.control
  * Compute DC operating point to verify saturation headroom (Vds >= 0.3 V)
  op
  print v(out)

  * Small-signal AC frequency sweep: 10 points/decade from 1 Hz to 100 GHz
  ac dec 10 1 100G

  * Extract low-frequency AC voltage gain magnitude in dB
  let gain_mag = db(v(out))
  print gain_mag[0]
.endc

.end
