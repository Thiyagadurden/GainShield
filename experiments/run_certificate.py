"""Stage C: compute the stability certificate and its verification evidence.

Outputs
  results/certificate.npz                 gain-region masks + worst-case margins
  results/certificate_summary.json        region sizes, baseline margins, timing
  results/linear_vs_nonlinear.csv         critical-gain check: linear model vs nonlinear sim
  results/figures/kp_ki_regions.png       the four regions in the Kp-Ki plane
  results/figures/nyquist_baseline.png    baseline loop over uncertainty vertices
"""
from __future__ import annotations

import time

import numpy as np
import pandas as pd

from common import FIGS, RESULTS, get_certificate, load_config, write_json
from gainshield.controllers.baseline import baseline_gains
from gainshield.controllers.pi import PIGains
from gainshield.disturbances.scenarios import Event, Scenario
from gainshield.evaluation import plots
from gainshield.plant.charger import PlantVariation
from gainshield.simulation import FixedPIAgent, simulate
from gainshield.stability.certify import certify_point
from gainshield.stability.linear_model import (LinearPlant, default_w_grid, k_interval, loop_margins,
                                               nominal_plant, pi_freq_response, plant_freq_response,
                                               spectral_radius)


def linear_vs_nonlinear(cfg) -> pd.DataFrame:
    """Critical gain multiplier predicted by the linear model vs observed in the nonlinear plant."""
    g = baseline_gains(cfg)
    rows = []
    for C_pu, d in [(1.0, 1.0), (1.0, 1.5), (1.0, 2.0), (0.8, 1.5), (1.2, 2.0)]:
        pl = nominal_plant(cfg, C_pu=C_pu, delay=d)
        ms = np.arange(1, 25, 0.02)
        r = np.array([spectral_radius(pl, g.Kp * m, g.Ki * m) for m in ms])
        m_lin = float(ms[np.argmax(r >= 1)])
        sc = Scenario("crit", "", 0.12, 10e3, events=(Event(0.01, "vref", 801.0),), noise_scale=0.0,
                      variation=PlantVariation(C_pu=C_pu, delay_samples=d))
        res = []
        for f in (0.97, 1.03):
            df = simulate(cfg, sc, FixedPIAgent(cfg, PIGains(g.Kp * m_lin * f, g.Ki * m_lin * f))).df
            e = (df.v - df.v_ref).abs().to_numpy()
            res.append(bool(e[1000:].max() < e[300:700].max()))  # decaying -> stable
        rows.append({"C_pu": C_pu, "delay_samples": d, "linear_critical_multiplier": m_lin,
                     "nonlinear_stable_at_0.97x": res[0], "nonlinear_stable_at_1.03x": res[1],
                     "agrees_within_3pct": res[0] and not res[1]})
    return pd.DataFrame(rows)


def plot_regions(cfg, cert, path) -> None:
    import matplotlib.pyplot as plt
    plots.style()
    fig, ax = plt.subplots(figsize=(6.0, 4.6))
    KP, KI = np.meshgrid(cert.Kp, cert.Ki)
    lv = np.zeros_like(KP)
    lv[cert.nominal] = 1
    lv[cert.robust_stable] = 2
    lv[cert.certified] = 3
    from matplotlib.colors import ListedColormap
    cmap = ListedColormap(["#f3f2ee", "#d6e4f5", "#8fb6e8", plots.BLUE])
    ax.pcolormesh(KP, KI, lv, cmap=cmap, shading="nearest", vmin=-0.5, vmax=3.5)
    ax.contour(KP, KI, cert.screened.astype(float), levels=[0.5], colors=[plots.INK2], linewidths=1.0, linestyles="--")
    g = baseline_gains(cfg)
    ax.plot(g.Kp, g.Ki, marker="D", ms=8, color=plots.ORANGE, mec="white", mew=1.2, ls="none", label="manual baseline")
    ax.set_xscale("log"); ax.set_yscale("log")
    ax.set_xlabel("Kp [A/V]"); ax.set_ylabel("Ki [A/(V s)]")
    from matplotlib.patches import Patch
    from matplotlib.lines import Line2D
    handles = [Patch(color="#f3f2ee", label="unstable (nominal)"), Patch(color="#d6e4f5", label="nominally stable"),
               Patch(color="#8fb6e8", label="robustly stable (proof, k-interval)"),
               Patch(color=plots.BLUE, label="CERTIFIED: robust + PM/GM/MM"),
               Line2D([], [], color=plots.INK2, ls="--", label="Monte-Carlo screened boundary"),
               Line2D([], [], marker="D", color=plots.ORANGE, ls="none", label="manual baseline")]
    ax.legend(handles=handles, loc="upper left", fontsize=7, bbox_to_anchor=(1.01, 1.0))
    ax.set_title("PI gain regions over the uncertainty set", loc="left")
    ax.grid(False)
    plots.save(fig, path)


def plot_nyquist(cfg, path) -> None:
    import matplotlib.pyplot as plt
    plots.style()
    g = baseline_gains(cfg)
    Ts = cfg.converter.Ts
    w = default_w_grid(Ts, 2000)
    kmin, kmax = k_interval(cfg)
    fig, ax = plt.subplots(figsize=(4.6, 4.2))
    th = np.linspace(0, 2 * np.pi, 200)
    ax.plot(-1 + cfg.constraints.MM_min * np.cos(th), cfg.constraints.MM_min * np.sin(th), color=plots.RED, lw=1, ls="--",
            label=f"modulus-margin disk r={cfg.constraints.MM_min}")
    lo, hi = cfg.plant.tau_i_range_s
    d0, d1 = cfg.converter.delay_range_samples
    for k in (kmin, kmax):
        for tau, d in [(lo, d0), (hi, d1)]:
            L = plant_freq_response(LinearPlant(k, tau, d, Ts), w) * pi_freq_response(g.Kp, g.Ki, w, Ts)[0]
            ax.plot(L.real, L.imag, lw=1.0, color=plots.BLUE if d == d0 else plots.ORANGE, alpha=0.9 if k == kmax else 0.5)
    ax.plot([-1], [0], "k+", ms=10)
    ax.set_xlim(-3, 1); ax.set_ylim(-2.5, 1.5)
    ax.set_aspect("equal")
    ax.set_xlabel("Re L"); ax.set_ylabel("Im L")
    ax.set_title("Baseline loop, uncertainty vertices", loc="left")
    ax.legend(fontsize=7, loc="lower left")
    plots.save(fig, path)


def main() -> None:
    cfg = load_config()
    t0 = time.perf_counter()
    cert = get_certificate(cfg, recompute=True)
    t_cert = time.perf_counter() - t0
    g = baseline_gains(cfg)
    base_cert = certify_point(cfg, g.Kp, g.Ki)
    base_nom = loop_margins(cfg, nominal_plant(cfg), g.Kp, g.Ki)
    lvn = linear_vs_nonlinear(cfg)
    lvn.to_csv(RESULTS / "linear_vs_nonlinear.csv", index=False)
    n = cert.certified.size
    summary = {
        "grid_points": int(n),
        "fraction_screened_MC": float(cert.screened.mean()),
        "fraction_nominal_stable": float(cert.nominal.mean()),
        "fraction_robust_stable": float(cert.robust_stable.mean()),
        "fraction_certified": float(cert.certified.mean()),
        "certified_but_not_screened": int((cert.certified & ~cert.screened).sum()),
        "certified_Kp_max": float(np.meshgrid(cert.Kp, cert.Ki)[0][cert.certified].max()),
        "certified_Ki_max": float(np.meshgrid(cert.Kp, cert.Ki)[1][cert.certified].max()),
        "k_interval": cert.meta.get("k_interval"),
        "baseline_gains": {"Kp": g.Kp, "Ki": g.Ki},
        "baseline_nominal_margins": base_nom,
        "baseline_worst_case": base_cert,
        "linear_model_predicts_nonlinear_instability_within_3pct": bool(lvn["agrees_within_3pct"].all()),
        "compute_seconds": t_cert,
    }
    write_json(RESULTS / "certificate_summary.json", summary)
    plot_regions(cfg, cert, FIGS / "kp_ki_regions.png")
    plot_nyquist(cfg, FIGS / "nyquist_baseline.png")
    print(lvn.to_string(index=False))
    print({k: v for k, v in summary.items() if k not in ("baseline_worst_case",)})


if __name__ == "__main__":
    main()
