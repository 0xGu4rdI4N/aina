# aina Project Guidelines & Research Paper Maintenance Rules

This repository maintains both autonomous analog circuit sizing tools and an academic research paper targeting DAC/ICCAD/NeurIPS:
- **Main Paper:** [`paper/main.md`](file:///Users/raunak/code/aina/paper/main.md)
- **Supplementary Material & Observation Log:** [`paper/supplementary.md`](file:///Users/raunak/code/aina/paper/supplementary.md)
- **Detailed Workflow Rules:** [`.agents/rules/research_paper_workflow.md`](file:///Users/raunak/code/aina/.agents/rules/research_paper_workflow.md)

## Core Directives for Agent Collaborators

1. **Maintain Paper Synchronization:** Whenever benchmark evaluations (`benchmark_runner.py`), model comparisons, or SPICE simulations are run, record both quantitative results in `paper/main.md` and qualitative reasoning transcripts in `paper/supplementary.md`.
2. **Preserve Physics Grounding:** Respect verified circuit laws ($V_{DS} \ge V_{ov}$ for active saturation, Middlebrook DC feedback loops for op-amps, $R_z = 1/g_{m2}$ for Miller RHP zero cancellation).
3. **Execution Safety:** All benchmarks and agent sizing loops must remain fully operational in both zero-dependency offline mode (analytic mock) and live hardware mode (Ngspice + local Ollama).
