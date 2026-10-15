"""
plot_gain.py — Visualizing the Analog Parameter Landscape & Agent Convergence
=============================================================================
Computes the CS-amplifier gain landscape across transistor width (W) and length (L),
illustrates the layout parasitic capacitance penalty, highlights the target and sweet spot,
and marks the autonomous agent trajectory discovered by aina.
"""

import numpy as np
import matplotlib.pyplot as plt
from matplotlib.gridspec import GridSpec
import os

from circuit_env import _mock_gain_db


def generate_landscape_plot(output_path="assets/gain_landscape.png"):
    # Style settings for clean, modern look
    plt.style.use("seaborn-v0_8-whitegrid" if "seaborn-v0_8-whitegrid" in plt.style.available else "default")
    fig = plt.figure(figsize=(15, 6.8), dpi=300)
    gs = GridSpec(1, 2, width_ratios=[1.15, 1.0], wspace=0.28)

    # ---------------------------------------------------------
    # Panel 1: Gain vs Width (W) for various Channel Lengths (L)
    # ---------------------------------------------------------
    ax1 = fig.add_subplot(gs[0])

    w_vals = np.linspace(1.0, 50.0, 300)
    l_curves = [0.5, 1.0, 1.5, 2.5]
    colors = ["#2563eb", "#059669", "#d97706", "#dc2626"]

    for l_val, col in zip(l_curves, colors):
        gains = [_mock_gain_db(w, l_val, w * 1.5) for w in w_vals]
        ax1.plot(w_vals, gains, label=f"L = {l_val:.1f} µm", color=col, linewidth=2.2)

    # Target line (20 dB)
    ax1.axhline(20.0, color="#b91c1c", linestyle="--", linewidth=1.8, label="Target Gain (≥ 20 dB)")

    # Sweet spot region (where L=0.5 and Gain >= 20 dB with minimal W to reduce C_para)
    # At L=0.5, gain crosses 20 dB around W=14.5 µm
    sweet_w_min = 15.0
    sweet_w_max = 25.0
    ax1.axvspan(sweet_w_min, sweet_w_max, color="#10b981", alpha=0.12, label="Optimal Sizing Region")

    # Agent trajectory points
    # Step 1: (W=10, L=0.5) -> Gain = 17.33 dB
    # Step 2: (W=20, L=0.5) -> Gain = 22.99 dB
    ax1.scatter([10.0], [17.33], color="#f59e0b", s=110, zorder=5, edgecolor="black", linewidth=1.5)
    ax1.annotate(
        "Agent Step 1\n(W=10µm, 17.3 dB)",
        xy=(10.0, 17.33),
        xytext=(4.0, 19.5),
        arrowprops=dict(facecolor="#f59e0b", shrink=0.08, width=1.5, headwidth=7),
        fontsize=9,
        fontweight="bold",
        bbox=dict(boxstyle="round,pad=0.3", fc="#fef3c7", ec="#f59e0b", lw=1),
    )

    ax1.scatter([20.0], [22.99], color="#16a34a", marker="*", s=320, zorder=6, edgecolor="black", linewidth=1.2)
    ax1.annotate(
        "Agent Converged Point\n(W=20µm, L=0.5µm, 23.0 dB)",
        xy=(20.0, 22.99),
        xytext=(21.5, 23.8),
        arrowprops=dict(facecolor="#16a34a", shrink=0.08, width=1.8, headwidth=8),
        fontsize=9.5,
        fontweight="bold",
        bbox=dict(boxstyle="round,pad=0.35", fc="#dcfce7", ec="#16a34a", lw=1.2),
    )

    # Secondary axis on Panel 1 for Parasitic Capacitance
    ax1_twin = ax1.twinx()
    c_paras = w_vals * 1.5
    ax1_twin.plot(w_vals, c_paras, color="#6b7280", linestyle=":", linewidth=1.5, alpha=0.85)
    ax1_twin.set_ylabel("Parasitic Capacitance $C_{para}$ (fF)", color="#4b5563", fontsize=10.5, labelpad=8)
    ax1_twin.tick_params(axis="y", labelcolor="#4b5563")
    ax1_twin.grid(False)

    ax1.set_title("Analog Gain vs. Transistor Width ($W$)", fontsize=13, fontweight="bold", pad=12)
    ax1.set_xlabel("MOSFET Gate Width $W$ (µm)", fontsize=11, fontweight="medium")
    ax1.set_ylabel("Small-Signal Voltage Gain $|A_v|$ (dB)", fontsize=11, fontweight="medium")
    ax1.set_xlim(0, 50)
    ax1.set_ylim(0, 28)
    ax1.legend(loc="lower right", frameon=True, framealpha=0.92, fontsize=8.8)

    # ---------------------------------------------------------
    # Panel 2: 2D Contour Map of the (W, L) Design Space
    # ---------------------------------------------------------
    ax2 = fig.add_subplot(gs[1])

    w_grid = np.linspace(1.0, 50.0, 120)
    l_grid = np.linspace(0.5, 4.0, 100)
    W_mesh, L_mesh = np.meshgrid(w_grid, l_grid)
    Z_gain = np.zeros_like(W_mesh)

    for i in range(W_mesh.shape[0]):
        for j in range(W_mesh.shape[1]):
            w = W_mesh[i, j]
            l = L_mesh[i, j]
            Z_gain[i, j] = _mock_gain_db(w, l, w * 1.5)

    contour_filled = ax2.contourf(
        W_mesh, L_mesh, Z_gain, levels=25, cmap="viridis", alpha=0.9
    )
    cbar = fig.colorbar(contour_filled, ax=ax2, pad=0.03, aspect=24)
    cbar.set_label("Voltage Gain $|A_v|$ (dB)", fontsize=10.5, labelpad=8)

    # Contour line for the 20 dB specification
    cs = ax2.contour(
        W_mesh, L_mesh, Z_gain, levels=[20.0], colors=["#ef4444"], linewidths=[2.2], linestyles=["--"]
    )
    ax2.clabel(cs, inline=True, fmt="Target: %1.0f dB", fontsize=9.5)

    # Trace agent path
    ax2.plot([10.0, 20.0], [0.5, 0.5], "o-", color="#ffffff", linewidth=2.5, markersize=8, zorder=5)
    ax2.scatter([10.0], [0.5], color="#f59e0b", s=120, zorder=6, edgecolor="black", label="Step 1: (10, 0.5)")
    ax2.scatter([20.0], [0.5], color="#22c55e", marker="*", s=320, zorder=6, edgecolor="black", label="Goal: (20, 0.5)")

    ax2.annotate(
        "Agent Trajectory\n(17.3 dB → 23.0 dB)",
        xy=(15.0, 0.5),
        xytext=(15.0, 1.2),
        arrowprops=dict(facecolor="white", shrink=0.1, width=1.5, headwidth=6, edgecolor="black"),
        fontsize=9,
        fontweight="bold",
        color="black",
        bbox=dict(boxstyle="round,pad=0.3", fc="#ffffff", ec="#374151", lw=1),
        ha="center",
    )

    ax2.set_title("Design Space & Agent Trajectory in $(W, L)$", fontsize=13, fontweight="bold", pad=12)
    ax2.set_xlabel("MOSFET Gate Width $W$ (µm)", fontsize=11, fontweight="medium")
    ax2.set_ylabel("MOSFET Gate Length $L$ (µm)", fontsize=11, fontweight="medium")
    ax2.legend(loc="upper right", frameon=True, framealpha=0.92, fontsize=8.8)

    plt.tight_layout()
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    plt.savefig(output_path, dpi=300, bbox_inches="tight")
    print(f"✓ Gain landscape plot successfully generated and saved to: {output_path}")


if __name__ == "__main__":
    generate_landscape_plot()
