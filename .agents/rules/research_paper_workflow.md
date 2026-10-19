# Research Paper Maintenance & Empirical Observation Protocol

## Scope & Objective
This workspace maintains an academic research paper draft ([`paper/main.md`](file:///Users/raunak/code/aina/paper/main.md)) and companion supplementary material ([`paper/supplementary.md`](file:///Users/raunak/code/aina/paper/supplementary.md)) targeting top EDA / Machine Learning publication venues (ACM/IEEE DAC, ICCAD, NeurIPS Datasets & Benchmarks).

Every empirical finding, model evaluation, and physical reasoning observation must be systematically integrated into these documents.

---

## Mandatory Workflows

### 1. Ingestion of New Benchmark Results
Whenever a new model or configuration is evaluated (via `benchmark_runner.py` or agent sizing in `main.py`):
1. **Quantitative Update in [`paper/main.md`](file:///Users/raunak/code/aina/paper/main.md):**
   - Update Table 4 (Empirical Results & Cross-Model Comparison) with:
     - Model Name and Parameter Size (e.g., 7B, 14B).
     - Quantization Level (e.g., `Q4_K_M`, `Q8_0`, FP16).
     - Benchmark Pass Rate (e.g., $X/4$).
     - Average Score percentage.
     - A concise 1-sentence diagnostic of physical correctness.
2. **Qualitative Log in [`paper/supplementary.md`](file:///Users/raunak/code/aina/paper/supplementary.md):**
   - Append raw model transcript excerpts under **Appendix B (Model Hallucination Transcripts vs. Sound Derivations)**.
   - Categorize the specific failure mode:
     - *Aspect-Ratio Amnesia* (omitting $W/L$ from current equations).
     - *Region Confusion* (conflating triode with cutoff or breakdown).
     - *Dimensional Inconsistency* (multiplying $W \cdot L$ area instead of aspect ratio $W/L$).
     - *Emergent Correctness* (sound physical derivations with exact boundary calculations).

### 2. SPICE and Topology Changes
Whenever transistor netlists, technology parameters (e.g., Level-1, BSIM, SkyWater 130nm), or Middlebrook feedback testbenches are modified:
1. Verify Middlebrook closed-loop DC ($L_{fb} = 1\text{ GH}$) and open-loop AC ($C_{inn} = 1\text{ GF}$) isolation.
2. Document the updated schematic, operating point metrics, and AC transfer curves in **Appendix C** of `paper/supplementary.md`.

### 3. Synchronization Tooling
Run the automated record synchronizer after multi-model runs:
```bash
python3 scripts/update_paper_records.py
```

### 4. Tone and Scientific Rigor
- Maintain IEEE/ACM conference formatting with clear section hierarchies.
- Use standard LaTeX math notation for all circuit formulas ($I_D, g_m, r_o, V_{ov}, V_{DS}, C_c, R_z$).
- Attribute pedagogical problems to Prof. Behzad Razavi (*Design of Analog CMOS Integrated Circuits*) and op-amp rubrics to *LOADBench* / *AutoCkt*.
