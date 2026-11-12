"""Figures for the slide deck, in the GainShield palette (re-generated from results/ and the trained model).

    python presentation/deck_figures.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
from matplotlib.colors import ListedColormap  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "experiments"))
from common import RESULTS, get_certificate, load_config, load_model  # noqa: E402
from gainshield.controllers.baseline import baseline_gains  # noqa: E402
from gainshield.disturbances.scenarios import Event, Scenario, scenario_by_name  # noqa: E402
from gainshield.simulation import FixedPIAgent, simulate  # noqa: E402

OUT = ROOT / "presentation" / "assets"
NAVY = "#0F1E3D"
BLUE = "#1F4FBF"
STEEL = "#5B6B86"
BASE = "#9AA3B2"
HAIR = "#D5DBE5"
AMBER = "#E9A100"
RED = "#C23B3B"
MIST = "#EEF2F8"


def style():
    plt.rcParams.update({
        "font.family": "Carlito", "font.size": 11, "axes.titlesize": 11, "axes.labelsize": 10.5,
        "axes.edgecolor": HAIR, "axes.labelcolor": STEEL, "xtick.color": STEEL, "ytick.color": STEEL,
        "axes.grid": True, "grid.color": "#E9ECF2", "grid.linewidth": 0.7, "axes.spines.top": False,
        "axes.spines.right": False, "lines.linewidth": 1.8, "legend.frameon": False, "savefig.dpi": 300,
        "figure.dpi": 100,
    })


def regions(cfg, cert):
    style()
    fig, ax = plt.subplots(figsize=(5.4, 4.3))
    KP, KI = np.meshgrid(cert.Kp, cert.Ki)
    lv = np.zeros_like(KP)
    lv[cert.nominal] = 1
    lv[cert.robust_stable] = 2
    lv[cert.certified] = 3
    ax.pcolormesh(KP, KI, lv, cmap=ListedColormap(["#F4F5F8", "#DCE4F2", "#9DB4E0", BLUE]), shading="nearest",
                  vmin=-0.5, vmax=3.5, edgecolors="none")
    ax.contour(KP, KI, cert.screened.astype(float), levels=[0.5], colors=[NAVY], linewidths=0.9, linestyles="--")
    t = json.loads((RESULTS / "tuning_summary.json").read_text())
    rec = np.array([[v["Kp"], v["Ki"]] for v in t["recommended"].values()])
    ax.plot(rec[:, 0], rec[:, 1], "o", ms=6.5, color="white", mec=NAVY, mew=1.3, ls="none")
    g = baseline_gains(cfg)
    ax.plot(g.Kp, g.Ki, "D", ms=8.5, color=AMBER, mec="white", mew=1.2)
    ax.set_xscale("log"); ax.set_yscale("log")
    ax.set_xlabel("Kp  [A/V]"); ax.set_ylabel("Ki  [A/(V·s)]")
    ax.grid(False)
    bb = dict(boxstyle="round,pad=0.25", fc="white", ec="none", alpha=0.95)
    ax.annotate("manual baseline", (g.Kp, g.Ki), (0.24, 22), textcoords="data", fontsize=9.5, color=NAVY, bbox=bb,
                arrowprops=dict(arrowstyle="-", color="white", lw=0.9))
    ax.annotate("GainShield deployed gains\n(8 tuning contexts)", tuple(rec[np.argmax(rec[:, 0])]), (3.2, 18),
                fontsize=9.5, color=NAVY, bbox=bb, arrowprops=dict(arrowstyle="-", color=NAVY, lw=0.8))
    ax.text(0.25, 3000, "unstable", fontsize=9.5, color=STEEL)
    fig.savefig(OUT / "fig_regions.png", bbox_inches="tight", transparent=False, facecolor="white")
    plt.close(fig)


def reversal(cfg, cert):
    style()
    gs = load_model(cfg, cert)
    sc = scenario_by_name("g2v_to_v2g")
    err = {"C": float(np.random.default_rng(991).normal(0, 0.015)), "tau": float(np.random.default_rng(992).normal(0, 0.05)),
           "delay": float(np.random.default_rng(993).normal(0, 0.05))}
    rb = simulate(cfg, sc, FixedPIAgent(cfg, baseline_gains(cfg)), seed=0, ctx_error=err).df
    rg = simulate(cfg, sc, gs.agent(), seed=0, ctx_error=err).df
    fig, ax = plt.subplots(2, 1, figsize=(5.6, 3.9), sharex=True, gridspec_kw={"height_ratios": [2.3, 1]})
    for d, c, lab, lw in [(rb, BASE, "manual PI", 1.8), (rg, BLUE, "GainShield", 2.0)]:
        ax[0].plot(1e3 * d.t, d.v, color=c, label=lab, lw=lw)
        ax[1].step(1e3 * d.t, d.Kp, color=c, where="post", lw=lw)
    ax[0].axhline(800, color=STEEL, lw=0.7)
    ax[0].set_xlim(30, 160)
    ax[0].set_ylabel("V_dc  [V]")
    ax[1].set_ylabel("Kp  [A/V]")
    ax[1].set_xlabel("time  [ms]")
    ax[0].legend(loc="upper right", fontsize=10, bbox_to_anchor=(1.0, 1.02))
    ax[0].text(92, 816, "battery power +15 kW → −15 kW at 50 ms", fontsize=9.5, color=STEEL)
    fig.align_ylabels(ax)
    fig.savefig(OUT / "fig_reversal.png", bbox_inches="tight", facecolor="white")
    plt.close(fig)


def fault(cfg, cert):
    from faults import FaultInjectingAgent
    from gainshield.controllers.pi import PIGains
    from gainshield.core import GainShieldFlags
    style()
    gs = load_model(cfg, cert)
    sc = Scenario("steady10", "", 0.30, 10e3, events=(Event(0.05, "p_load", 10e3),))
    runs = {}
    for name, flags in [("monitor or fallback disabled", GainShieldFlags(runtime_monitor=False)),
                        ("GainShield (monitor + fallback)", GainShieldFlags())]:
        gs.flags = flags
        ag = FaultInjectingAgent(cfg, gs, gain_fault=(0.06, PIGains(0.30, 1500.0)))
        ag.monitor.enabled = flags.runtime_monitor
        runs[name] = simulate(cfg, sc, ag, seed=0).df
    fig, ax = plt.subplots(figsize=(5.8, 2.9))
    ax.axhspan(760, 840, color=MIST, lw=0)
    ax.plot(1e3 * runs["monitor or fallback disabled"].t, runs["monitor or fallback disabled"].v, color=RED, lw=1.4,
            label="monitor or fallback disabled")
    ax.plot(1e3 * runs["GainShield (monitor + fallback)"].t, runs["GainShield (monitor + fallback)"].v, color=BLUE, lw=2.0,
            label="GainShield: monitor + fallback")
    ax.axvline(60, color=NAVY, lw=0.8, ls="--")
    ax.text(63, 866, "unstable gains written (gate bypassed)", fontsize=9.5, color=NAVY, va="top", ha="left")
    ax.text(292, 842, "±5 % band", fontsize=9, color=STEEL, ha="right", va="bottom")
    ax.set_ylim(720, 870); ax.set_xlim(0, 300)
    ax.set_xlabel("time  [ms]"); ax.set_ylabel("V_dc  [V]")
    ax.legend(loc="lower left", fontsize=9.5, ncol=2, bbox_to_anchor=(0.0, 1.0))
    fig.savefig(OUT / "fig_fault.png", bbox_inches="tight", facecolor="white")
    plt.close(fig)


if __name__ == "__main__":
    cfg = load_config()
    cert = get_certificate(cfg)
    regions(cfg, cert); reversal(cfg, cert); fault(cfg, cert)
    print("deck figures written to", OUT)
