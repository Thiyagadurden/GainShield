"""Matplotlib figures with one consistent, colour-blind-checked palette.

Categorical order (validated adjacent-pair CVD separation): blue, orange, aqua.
GainShield = blue, manual baseline = orange; limits are drawn as dark-grey
dashed lines (not a series colour); status red is reserved for violations.
"""
from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402

BLUE = "#2a78d6"
ORANGE = "#eb6834"
AQUA = "#1baf7a"
VIOLET = "#6250d6"
INK = "#0b0b0b"
INK2 = "#52514e"
GRID = "#e4e3df"
RED = "#e34948"
SERIES = {"gainshield": BLUE, "baseline": ORANGE}


def style() -> None:
    plt.rcParams.update({
        "figure.dpi": 110, "savefig.dpi": 200, "font.size": 9, "axes.titlesize": 10,
        "axes.labelsize": 9, "axes.edgecolor": INK2, "axes.labelcolor": INK, "xtick.color": INK2,
        "ytick.color": INK2, "axes.grid": True, "grid.color": GRID, "grid.linewidth": 0.6,
        "axes.spines.top": False, "axes.spines.right": False, "lines.linewidth": 1.6,
        "legend.frameon": False, "font.family": "DejaVu Sans",
    })


def save(fig, path: str | Path) -> Path:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(p, bbox_inches="tight")
    plt.close(fig)
    return p


def response_overlay(cfg, results: dict, title: str, path: str | Path, t_window: tuple[float, float] | None = None):
    """Voltage, current and active Kp for several agents on one scenario."""
    style()
    fig, ax = plt.subplots(3, 1, figsize=(6.4, 5.2), sharex=True, gridspec_kw={"height_ratios": [2.2, 1.6, 1]})
    Vref = cfg.plant.Vdc_ref_V
    band = cfg.constraints.V_band_op * Vref
    for name, df in results.items():
        c = SERIES.get(name, VIOLET)
        t = 1e3 * df["t"]
        ax[0].plot(t, df["v"], color=c, label=name)
        ax[1].plot(t, df["i_d"], color=c, label=name)
        ax[2].step(t, df["Kp"], color=c, where="post", label=name)
    t_all = 1e3 * next(iter(results.values()))["t"]
    for s in (-1, 1):
        ax[0].axhline(Vref + s * band, color=INK2, ls="--", lw=0.9)
    ax[0].axhline(Vref, color=INK2, lw=0.6, alpha=0.6)
    ax[0].set_ylabel("V_dc [V]")
    ymin = min(df["v"].min() for df in results.values())
    ymax = max(df["v"].max() for df in results.values())
    pad = max(5.0, 0.15 * (ymax - ymin))
    ax[0].set_ylim(min(ymin - pad, Vref - 5), max(ymax + pad, Vref + 5))
    ax[0].text(t_all.iloc[-1], Vref + band, " +5 % band", va="center", fontsize=7, color=INK2) if Vref + band < ax[0].get_ylim()[1] else None
    Imax = cfg.converter.I_grid_max_A
    ax[1].axhline(Imax, color=INK2, ls="--", lw=0.9)
    ax[1].axhline(-Imax, color=INK2, ls="--", lw=0.9)
    ax[1].set_ylabel("i_d [A]")
    ax[2].set_ylabel("Kp [A/V]")
    ax[2].set_xlabel("time [ms]")
    ax[0].legend(loc="lower right", ncol=len(results))
    ax[0].set_title(title, loc="left")
    if t_window:
        ax[2].set_xlim(1e3 * t_window[0], 1e3 * t_window[1])
    fig.align_ylabels(ax)
    return save(fig, path)
