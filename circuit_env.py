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
from typing import Optional

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

    NETLIST_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "netlists")
    NETLIST_TEMPLATE_FILE = os.path.join(NETLIST_DIR, "common_source_template.sp")

    # Fallback template if netlists/common_source_template.sp is not found
    DEFAULT_NETLIST_TEMPLATE = """\
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
  op
  print v(out)
  ac dec 10 1 100G
  let gain_mag = db(v(out))
  print gain_mag[0]
.endc
.end
"""
    NETLIST_TEMPLATE = DEFAULT_NETLIST_TEMPLATE

    W_MIN, W_MAX = 1.0,  50.0   # um
    L_MIN, L_MAX = 0.5,  10.0   # um

    def __init__(self, use_mock=None, netlist_template_path: Optional[str] = None):
        ngspice_found = shutil.which("ngspice") is not None

        if use_mock is True:
            self._mode = "mock"
        elif use_mock is False:
            if not ngspice_found:
                raise EnvironmentError("Ngspice not found in PATH.")
            self._mode = "ngspice"
        else:
            self._mode = "ngspice" if ngspice_found else "mock"

        # Load netlist template from disk or fallback
        template_file = netlist_template_path or self.NETLIST_TEMPLATE_FILE
        if os.path.exists(template_file):
            try:
                with open(template_file, "r") as fh:
                    self.netlist_template = fh.read()
                logger.info("Loaded SPICE netlist template from %s", template_file)
            except Exception as exc:
                logger.warning("Could not read %s (%s); using default template", template_file, exc)
                self.netlist_template = self.DEFAULT_NETLIST_TEMPLATE
        else:
            self.netlist_template = self.DEFAULT_NETLIST_TEMPLATE

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
        w_m = w * 1e-6
        l_m = l * 1e-6
        Kp = 120e-6
        Vov = 0.3
        Vdd = 3.3
        Rd = 10e3

        Id_sat = 0.5 * Kp * (w_m / l_m) * (Vov ** 2)
        Vout_dc = Vdd - Id_sat * Rd

        # Physics check: Headroom & saturation boundary
        if Vout_dc < Vov:
            gain = _mock_gain_db(w, l, parasitic_c)
            return {
                "status": "PHYSICS_VIOLATION",
                "error_type": "TRIODE_REGION_HEADROOM_EXHAUSTED",
                "vout_dc": round(Vout_dc, 3),
                "gain": gain,
                "parasitic": parasitic_c,
                "diagnostic": (
                    f"Transistor M1 has collapsed into the triode/linear region (Vds = {Vout_dc:.3f} V < Vov = 0.300 V). "
                    f"The drain current Id causes an excessive voltage drop across Rd = 10 kΩ, exceeding the 3.3V supply rail."
                ),
                "suggested_action": (
                    "Reduce gate width W or increase gate length L to decrease drain current Id, "
                    "restoring Vds >= 0.3 V to maintain saturation amplification."
                ),
                "mode": "mock",
            }

        gain = _mock_gain_db(w, l, parasitic_c)
        return {
            "status": "SUCCESS",
            "gain": gain,
            "parasitic": parasitic_c,
            "vout_dc": round(Vout_dc, 3),
            "mode": "mock",
        }

    def _run_ngspice(self, w, l, parasitic_c) -> dict:
        template = getattr(self, "netlist_template", self.DEFAULT_NETLIST_TEMPLATE)
        netlist  = template.format(W_val=w, L_val=l, C_para=parasitic_c)
        netlist_path = os.path.join(self.NETLIST_DIR, "temp_run.sp") if os.path.isdir(self.NETLIST_DIR) else "temp_run.sp"

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
            return {
                "status": "SIMULATION_FAILED",
                "error_type": "NGSPICE_NOT_FOUND",
                "diagnostic": "Ngspice binary was not found in PATH.",
                "suggested_action": "Install ngspice or run with --mock flag.",
                "mode": "ngspice",
            }
        except subprocess.TimeoutExpired:
            return {
                "status": "SIMULATION_FAILED",
                "error_type": "SIMULATION_TIMEOUT",
                "diagnostic": "Ngspice simulation timed out (>10 s).",
                "suggested_action": "Circuit is experiencing severe numerical convergence hang. Step back to previous dimensions.",
                "mode": "ngspice",
            }
        except Exception as exc:
            return {
                "status": "SIMULATION_FAILED",
                "error_type": "EXECUTION_EXCEPTION",
                "diagnostic": str(exc),
                "suggested_action": "Check system environment and permissions.",
                "mode": "ngspice",
            }
        finally:
            if os.path.exists(netlist_path):
                os.remove(netlist_path)

        combined = result.stdout + result.stderr

        # 1. Parse DC Operating Point voltage at node out: v(out) = <val>
        match_dc = re.search(
            r'\bv\(out\)\s*=\s*([+-]?[0-9]*\.?[0-9]+(?:[eE][+-]?[0-9]+)?)',
            combined, re.IGNORECASE,
        )
        vout_dc = float(match_dc.group(1)) if match_dc else None

        # 2. Parse small-signal AC gain
        match_gain = re.search(
            r'gain_mag\s*\[\s*0\s*\]\s*=\s*([+-]?[0-9]*\.?[0-9]+(?:[eE][+-]?[0-9]+)?)',
            combined, re.IGNORECASE,
        )
        if not match_gain:
            match_gain = re.search(
                r'\bgain\b\s*(?:\[\s*\d+\s*\])?\s*=\s*([+-]?[0-9]*\.?[0-9]+(?:[eE][+-]?[0-9]+)?)',
                combined, re.IGNORECASE,
            )

        gain = round(float(match_gain.group(1)), 2) if match_gain else None

        # 3. Check for physical headroom / triode collapse
        if vout_dc is not None and vout_dc < 0.300:
            diag = diagnose_spice_log(combined, vout_dc=vout_dc, gain=gain)
            diag["mode"] = "ngspice"
            diag["parasitic"] = parasitic_c
            return diag

        # 4. Check for normal valid amplification
        if gain is not None and gain >= 0.0:
            return {
                "status":    "SUCCESS",
                "gain":      gain,
                "parasitic": parasitic_c,
                "vout_dc":   round(vout_dc, 3) if vout_dc is not None else None,
                "mode":      "ngspice",
            }

        # 5. Intercept SPICE convergence / numerical errors
        diag = diagnose_spice_log(combined, vout_dc=vout_dc, gain=gain)
        diag["mode"] = "ngspice"
        diag["parasitic"] = parasitic_c
        return diag


# ---------------------------------------------------------------------------
# SPICE Diagnostic Parser & Recovery Expert
# ---------------------------------------------------------------------------

def _extract_error_snippet(log_text: str) -> str:
    """Extracts concise error lines from raw SPICE output."""
    lines = [
        line.strip()
        for line in log_text.splitlines()
        if line.strip() and not line.strip().startswith("Doing analysis")
    ]
    error_lines = [
        l for l in lines
        if any(k in l.lower() for k in ["error", "warning", "failed", "limit", "fatal", "singular"])
    ]
    if error_lines:
        return " | ".join(error_lines[:3])
    return " | ".join(lines[-3:]) if lines else "No diagnostic lines found."


def diagnose_spice_log(
    log_text: str,
    vout_dc: Optional[float] = None,
    gain: Optional[float] = None,
) -> dict:
    """
    Classifies raw Ngspice stdout/stderr and returns structured diagnostic
    metadata with specific recovery suggestions for the agent.
    """
    text_lower = log_text.lower()

    # 1. Physics / Headroom check: Triode collapse
    if vout_dc is not None and vout_dc < 0.300:
        return {
            "status": "PHYSICS_VIOLATION",
            "error_type": "TRIODE_REGION_HEADROOM_EXHAUSTED",
            "vout_dc": round(vout_dc, 3),
            "gain": gain,
            "diagnostic": (
                f"Transistor M1 has collapsed into the triode/linear region (Vds = {vout_dc:.3f} V < Vov = 0.300 V). "
                f"The drain current Id causes an excessive voltage drop across Rd = 10 kΩ, starving the output headroom."
            ),
            "suggested_action": (
                "Reduce gate width W or increase gate length L to decrease drain current Id, "
                "restoring Vds >= 0.3 V to maintain saturation amplification."
            ),
            "raw_log_snippet": _extract_error_snippet(log_text),
        }

    # 2. Timestep too small
    if "timestep too small" in text_lower or "time step too small" in text_lower:
        return {
            "status": "SIMULATION_FAILED",
            "error_type": "TIMESTEP_TOO_SMALL",
            "diagnostic": "Transient/AC solver failed: Numerical timestep became too small to maintain integration stability.",
            "suggested_action": "Avoid extreme parameter jumps or aspect ratios. Step dimensions more moderately.",
            "raw_log_snippet": _extract_error_snippet(log_text),
        }

    # 3. Non-convergence
    if any(k in text_lower for k in ["no convergence", "convergence failed", "iteration limit reached", "pseudo-transient failed"]):
        return {
            "status": "SIMULATION_FAILED",
            "error_type": "CONVERGENCE_ERROR",
            "diagnostic": "SPICE solver reached maximum iterations without finding an equilibrium operating point.",
            "suggested_action": "The chosen (W, L) produces numerical instability. Step back to previous stable sizing.",
            "raw_log_snippet": _extract_error_snippet(log_text),
        }

    # 4. Singular matrix / floating nodes
    if "singular matrix" in text_lower or "matrix is singular" in text_lower:
        return {
            "status": "SIMULATION_FAILED",
            "error_type": "SINGULAR_MATRIX",
            "diagnostic": "Matrix inversion failed: Node impedance is infinite or Jacobian matrix is singular.",
            "suggested_action": "Check transistor connections and avoid extreme boundary values.",
            "raw_log_snippet": _extract_error_snippet(log_text),
        }

    # 5. Operating point failure
    if "operating point failed" in text_lower or "op failed" in text_lower:
        return {
            "status": "SIMULATION_FAILED",
            "error_type": "DC_OP_FAILED",
            "diagnostic": "DC operating point calculation failed to settle.",
            "suggested_action": "Device dimensions or bias conditions prevent DC bias settlement. Return to a known operating range.",
            "raw_log_snippet": _extract_error_snippet(log_text),
        }

    # 6. Negative gain / attenuation
    if gain is not None and gain < 0.0:
        return {
            "status": "PHYSICS_VIOLATION",
            "error_type": "GAIN_ATTENUATION_HEADROOM_VIOLATION",
            "gain": gain,
            "diagnostic": f"Circuit produces negative gain ({gain:.2f} dB), indicating severe attenuation or improper biasing.",
            "suggested_action": "The transistor is likely cut off or driven into triode. Reduce W/L ratio.",
            "raw_log_snippet": _extract_error_snippet(log_text),
        }

    # Generic fallback error
    return {
        "status": "SIMULATION_FAILED",
        "error_type": "UNCLASSIFIED_SIM_ERROR",
        "diagnostic": f"Ngspice execution failed. Log snippet: {_extract_error_snippet(log_text)}",
        "suggested_action": "Inspect netlist parameters and return to a safer operating point within valid bounds.",
        "raw_log_snippet": _extract_error_snippet(log_text),
    }
