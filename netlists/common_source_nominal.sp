* aina v1.0 -- Common-Source Amplifier (Golden Converged Design)
* ============================================================================
* Standalone runnable Ngspice netlist representing the optimal converged
* operating point sized by aina (W = 20 um, L = 0.5 um, C_para = 30 fF).
*
* Sizing & Target Specifications:
*   Target Gain: >= 20.0 dB
*   Achieved Gain: +22.99 dB
*   DC Vout (Vds): 1.140 V (Saturation Headroom: Vds > Vov = 0.3 V -> PASS)
*   Drain Current (Id): 216 uA
*   Layout Parasitic: 30.0 fF
*
* To run directly in Ngspice:
*   ngspice -b netlists/common_source_nominal.sp
* ============================================================================

* 1. MOS Transistor Model (Level-1 Shichman-Hodges)
.model nfet nmos (
+  level  = 1
+  vto    = 0.70
+  kp     = 120u
+  lambda = 0.02
+)

* 2. Voltage Sources
Vdd   vdd  0  DC 3.3
Vbias gate 0  DC 1.0  AC 1.0

* 3. Active Devices (Nominal optimal design point: W = 20 um, L = 0.5 um)
M1 out gate 0 0 nfet W=20.0u L=0.5u

* 4. Passive Elements
Rd vdd out 10k
Cparasitic out 0 30.0f

* 5. Simulation & Analysis Control
.control
  op
  echo "--- DC OPERATING POINT (HEADROOM CHECK) ---"
  print v(out)
  ac dec 10 1 100G
  let gain_mag = db(v(out))
  echo "--- AC VOLTAGE GAIN (dB) ---"
  print gain_mag[0]
.endc

.end
