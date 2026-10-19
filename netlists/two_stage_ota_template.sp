* aina Benchmark — Two-Stage Miller CMOS Operational Transconductance Amplifier (OTA)
* Inspired by LOADBench (SkyWater 130nm) & AutoCkt
* ======================================================================================

.model nmos_ota nmos (level=1 vto=0.7 kp=120u lambda=0.02)
.model pmos_ota pmos (level=1 vto=-0.7 kp=40u lambda=0.03)

* Power Supplies
Vdd vdd 0 3.3
Vss vss 0 0.0

* Bias Voltages
Vbias_tail vbias_tail 0 DC 1.1
Vbias_load vbias_load 0 DC 1.1

* Input Sources with Middlebrook DC Feedback Loop
* L_fb provides negative feedback at DC (0 Hz) to ensure exact equilibrium self-biasing
* C_inn shorts inn to ground at AC frequencies (> 1 Hz) so the AC response is 100% open-loop
Vinp inp 0 DC 1.65 AC 1.0
L_fb out inn 1G
C_inn inn 0 1G


* ── Stage 1: Differential Pair with Active Current Mirror ──
* Tail Current Source
M0 ntail vbias_tail 0 0 nmos_ota W={W_tail}u L={L_tail}u

* Input Differential Pair
M1 n1 inn ntail 0 nmos_ota W={W_in}u L={L_in}u
M2 n2 inp ntail 0 nmos_ota W={W_in}u L={L_in}u

* PMOS Current Mirror Active Load
M3 n1 n1 vdd vdd pmos_ota W={W_cm}u L={L_cm}u
M4 n2 n1 vdd vdd pmos_ota W={W_cm}u L={L_cm}u

* ── Stage 2: Common-Source Gain Stage ──
* Driver PMOS
M5 out n2 vdd vdd pmos_ota W={W_stage2}u L={L_stage2}u

* Current Source NMOS Load
M6 out vbias_load 0 0 nmos_ota W={W_load2}u L={L_load2}u

* ── Frequency Compensation & Load ──
* Miller Compensation (Cc in series with nulling resistor Rz)
Cc n2 n_rz {Cc_val}p
Rz n_rz out {Rz_val}k

* Load Capacitance
Cload out 0 {Cload_val}p

* ── Simulation Control Block ──
.control
  op
  print v(out) v(n2) v(ntail)
  ac dec 20 10 1G
  let gain_db = db(v(out))
  let phase_deg = cph(v(out)) * 180 / 3.141592653589793

  * Output low-frequency DC gain (at 10 Hz)
  print gain_db[0]
  
  * Find unity gain frequency (gain_db = 0) and phase margin
  meas ac ugbw_freq when gain_db=0
  meas ac phase_at_ugbw find phase_deg when gain_db=0
.endc

.end
