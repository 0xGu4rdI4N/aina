"""
circuit_env.py — Environment Layer for aina (AI 4 aNAlog)
=========================================================
Manages a fixed Common-Source Amplifier netlist, injects agent-chosen
transistor dimensions (W, L), enforces the layout parasitic penalty,
runs Ngspice, and returns structured simulation results.

Parasitic penalty model:
    C_parasitic (fF) = W (µm) × 1.5

DC operating point design:
    Vbias = 1.0 V  →  Vov = Vgs - Vto = 0.3 V
    Rd    = 10 kΩ  →  keeps M1 in saturation for W = 1 to 50 µm
    This gives a gain range of ~5 dB (W=5) to ~25 dB (W=50,L=1),
    allowing the agent to converge to >= 20 dB realistically.
"""

import subprocess
import re
import math
import shutil
import os
import logging

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Analytic mock — Level-1 MOSFET physics (mirrors the SPICE netlist exactly)
#
#   Id   = (Kp/2) * (W/L) * Vov^2
#   Gm   = Kp * (W/L) * Vov
#   Gds  = lambda * Id
#   Rout = Rd || (1/Gds)
#   |Av| = Gm * Rout / sqrt(1 + (f/fp)^2)
#   fp   = 1 / (2*pi * Rout * C_load)
# ---------------------------------------------------------------------------
def _mock_gain_db(w: float, l: float, parasitic_f: float) -> float:
    """
    Analytic approximation of CS-amp AC gain (dB) at 1 Hz.
    Parameters match the SPICE netlist exactly.
    """
    Kp     = 120e-6   # A/V^2  (.model kp=120u)
    Vto    = 0.7      # V      (.model vto=0.7)
    lam    = 0.02     # 1/V    (.model lambda=0.02)
    Vbias  = 1.0      # V      (gate bias DC)
    Rd     = 10e3     # Ohm    (load resistor)
    Vdd    = 3.3      # V
    f_eval = 1.0      # Hz     (first AC sweep point)

    Vov = Vbias - Vto   # = 0.3 V

    w_m = w * 1e-6
    l_m = l * 1e-6

    Id   = 0.5 * Kp * (w_m / l_m) * (Vov ** 2)
    Gm   = Kp * (w_m / l_m) * Vov
    Gds  = lam * Id
    ro   = 1.0 / Gds if Gds > 0 else 1e12
    Rout = (Rd * ro) / (Rd + ro)

    # Total load cap: intrinsic Cgd + layout parasitic
    Cox    = 8.6e-3
    C_gd   = 0.5 * Cox * w_m * l_m
    C_para = parasitic_f * 1e-15
    C_load = C_gd + C_para

    fp = 1.0 / (2 * math.pi * Rout * C_load) if C_load > 0 else 1e18

    Av_DC       = Gm * Rout
    gain_linear = Av_DC / math.sqrt(1.0 + (f_eval / fp) ** 2)
    gain_dB     = 20.0 * math.log10(max(gain_linear, 1e-12))

    return round(gain_dB, 2)


# ---------------------------------------------------------------------------
class BasicCircuitEnv:
    """
    Wraps a Common-Source Amplifier netlist and exposes evaluate_design().

    Parameters
    ----------
    use_mock : bool or None
        True  -> always use the analytic mock (no Ngspice required).
        False -> always use Ngspice (raises EnvironmentError if missing).
        None  -> auto-detect: Ngspice if found in PATH, mock otherwise.
    """

    # Netlist uses:
    #   Vbias = 1.0 V  (gate DC bias, Vov = 0.3 V)
    #   Rd    = 10 kΩ
    NETLIST_TEMPLATE = """\
* aina v1.0 -- Common-Source Amplifier (AI 4 aNAlog)
* --------------------------------------------------
.model nfet nmos (level=1 vto=0.7 kp=120u lambda=0.02)

* Power supply
Vdd vdd 0 3.3

* Gate bias: Vgs = 1.0 V, Vov = 0.3 V, M1 in saturation for W = 1..50 um
Vbias gate 0 DC 1.0 AC 1

* Main transistor (agent-chosen dimensions)
M1 out gate 0 0 nfet W={W_val}u L={L_val}u

* Resistive load (10 kOhm gives sufficient gain headroom)
Rd vdd out 10k

* Layout parasitic capacitance  [fF = W_um * 1.5]
Cparasitic out 0 {C_para}f

* AC analysis: 10 pts/decade, 1 Hz to 100 GHz
.control
  ac dec 10 1 100G
  let gain_mag = db(v(out))
  print gain_mag[0]
.endc
.end
"""

    W_MIN, W_MAX = 1.0,  50.0   # um
    L_MIN, L_MAX = 0.5,  10.0   # um

    def __init__(self, use_mock=None):
        ngspice_found = shutil.which("ngspice") is not None

        if use_mock is True:
            self._mode = "mock"
        elif use_mock is False:
            if not ngspice_found:
                raise EnvironmentError("Ngspice not found in PATH.")
            self._mode = "ngspice"
        else:
            self._mode = "ngspice" if ngspice_found else "mock"

        logger.info("BasicCircuitEnv initialised -- simulation mode: %s", self._mode)

    @property
    def mode(self) -> str:
        return self._mode

    def evaluate_design(self, w: float, l: float) -> dict:
        """
        Evaluate a transistor sizing (W, L) and return simulation results.

        Parameters
        ----------
        w : MOSFET gate width  (um), clamped to [W_MIN, W_MAX]
        l : MOSFET gate length (um), clamped to [L_MIN, L_MAX]

        Returns
        -------
        dict:
            status     : "SUCCESS" | "SIMULATION_FAILED" | "PARSING_ERROR"
            gain       : float (dB)   -- on SUCCESS
            parasitic  : float (fF)   -- on SUCCESS
            mode       : "ngspice" | "mock"
            log/error  : str          -- on failure
        """
        w = float(w)
        l = float(l)

        w_clamped = max(self.W_MIN, min(w, self.W_MAX))
        l_clamped = max(self.L_MIN, min(l, self.L_MAX))
        if w_clamped != w or l_clamped != l:
            logger.warning(
                "Design (W=%.1f, L=%.1f) out of bounds -> clamped to (W=%.1f, L=%.1f)",
                w, l, w_clamped, l_clamped,
            )
        w, l = w_clamped, l_clamped

        parasitic_c = round(w * 1.5, 3)   # fF

        if self._mode == "mock":
            return self._run_mock(w, l, parasitic_c)
        return self._run_ngspice(w, l, parasitic_c)

    def _run_mock(self, w, l, parasitic_c) -> dict:
        gain = _mock_gain_db(w, l, parasitic_c)
        return {"status": "SUCCESS", "gain": gain, "parasitic": parasitic_c, "mode": "mock"}

    def _run_ngspice(self, w, l, parasitic_c) -> dict:
        netlist      = self.NETLIST_TEMPLATE.format(W_val=w, L_val=l, C_para=parasitic_c)
        netlist_path = "temp_run.sp"

        with open(netlist_path, "w") as fh:
            fh.write(netlist)

        try:
            result = subprocess.run(
                ["ngspice", "-b", netlist_path],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                timeout=10,
            )
        except FileNotFoundError:
            return {"status": "SIMULATION_FAILED", "error": "ngspice not found in PATH", "mode": "ngspice"}
        except subprocess.TimeoutExpired:
            return {"status": "SIMULATION_FAILED", "error": "Ngspice timed out (>10 s)", "mode": "ngspice"}
        except Exception as exc:
            return {"status": "SIMULATION_FAILED", "error": str(exc), "mode": "ngspice"}
        finally:
            if os.path.exists(netlist_path):
                os.remove(netlist_path)

        combined = result.stdout + result.stderr

        # Primary: "gain_mag[0] = <value>"
        match = re.search(
            r'gain_mag\s*\[\s*0\s*\]\s*=\s*([+-]?[0-9]*\.?[0-9]+(?:[eE][+-]?[0-9]+)?)',
            combined, re.IGNORECASE,
        )
        # Fallback: any "gain = <value>" or "gain[0] = <value>"
        if not match:
            match = re.search(
                r'\bgain\b\s*(?:\[\s*\d+\s*\])?\s*=\s*([+-]?[0-9]*\.?[0-9]+(?:[eE][+-]?[0-9]+)?)',
                combined, re.IGNORECASE,
            )

        if match:
            return {
                "status":    "SUCCESS",
                "gain":      round(float(match.group(1)), 2),
                "parasitic": parasitic_c,
                "mode":      "ngspice",
            }

        logger.debug("Ngspice raw output:\n%s", combined)
        return {"status": "PARSING_ERROR", "log": combined[:2000], "mode": "ngspice"}
