"""Deliverable 5: GainShield vs manually tuned PI under identical conditions.

Both controllers run the SAME scenario objects, the SAME seeds (noise and
context-estimation error sequences), the same plant parameters, initial
conditions, duration, sampling period and constraints.

Outputs
  results/evaluation_runs.csv          one row per (scenario, seed, controller)
  results/evaluation_summary.csv       mean / std per scenario and controller
  results/evaluation_summary.json      headline numbers + statistical tests
  results/audit/evaluation_audit.jsonl GainShield decisions during evaluation
  results/figures/eval_<scenario>.png  voltage / current / Kp overlays (seed 0)
  results/figures/eval_bars.png        per-scenario comparison
"""
from __future__ import annotations

import time

import numpy as np
import pandas as pd
from scipy import stats

from common import FIGS, RESULTS, env_info, get_certificate, load_config, load_model, write_json
from gainshield.audit.logger import AuditLogger, verify_gain_trace
from gainshield.controllers.baseline import baseline_gains
from gainshield.disturbances.scenarios import standard_suite
from gainshield.evaluation import plots
from gainshield.evaluation.metrics import scenario_metrics
from gainshield.simulation import FixedPIAgent, simulate
from gainshield.stability.linear_model import LinearPlant, k_from_context, loop_margins

N_SEEDS = 5
METRICS = ["settling_time_ms", "peak_dev_pct", "recovery_os_pct", "IAE_Vs", "v_viol_ms", "v_trip", "i_viol_ms",
           "i_ripple_A"]


def true_plant_margins(cfg, res) -> dict:
    """Worst linear margins of every gain pair that was active, on the TRUE plant at the final operating point."""
    tp = res.true_params
    vg = float(res.df["vg_pu"].iloc[-1])
    k = k_from_context(cfg, tp["C_F"] / cfg.plant.C_nom_F, vg)
    pl = LinearPlant(k, tp["tau_i_s"], tp["delay_samples"], cfg.converter.Ts)
    pairs = res.df[["Kp", "Ki"]].drop_duplicates().to_numpy()
    ms = [loop_margins(cfg, pl, kp, ki) for kp, ki in pairs]
    return {"PM_true_deg": min(m["PM"] for m in ms), "GM_true_dB": min(m["GM"] for m in ms),
            "MM_true": min(m["MM"] for m in ms), "n_gain_sets": len(pairs)}


def plot_bars(summary: pd.DataFrame, path) -> None:
    import matplotlib.pyplot as plt
    plots.style()
    scen = summary["scenario"].unique()
    fig, axes = plt.subplots(1, 3, figsize=(10.5, 3.6), sharey=True)
    y = np.arange(len(scen))
    for ax, (m, lab) in zip(axes, [("peak_dev_pct_mean", "peak deviation [% of Vref]"),
                                    ("IAE_Vs_mean", "IAE [V s]"),
                                    ("settling_time_ms_mean", "settling time [ms]")]):
        for off, ctrl in [(-0.2, "baseline"), (0.2, "gainshield")]:
            vals = [summary[(summary.scenario == s) & (summary.controller == ctrl)][m].iloc[0] for s in scen]
            ax.barh(y + off, vals, height=0.38, color=plots.SERIES[ctrl], label=ctrl)
        ax.set_xlabel(lab)
        ax.grid(axis="y", visible=False)
    axes[0].set_yticks(y, scen)
    axes[0].invert_yaxis()
    axes[0].legend(loc="lower right", fontsize=7)
    fig.suptitle("Mean over 5 seeds, identical disturbances", x=0.01, ha="left", fontsize=10)
    plots.save(fig, path)


def main(n_seeds: int = N_SEEDS) -> pd.DataFrame:
    cfg = load_config()
    cert = get_certificate(cfg)
    audit = AuditLogger(RESULTS / "audit" / "evaluation_audit.jsonl", run_id="evaluation")
    gs = load_model(cfg, cert, audit=audit)
    base = baseline_gains(cfg)
    rows = []
    t0 = time.perf_counter()
    for sc in standard_suite():
        for seed in range(n_seeds):
            err = {"C": float(np.random.default_rng(seed + 991).normal(0, 0.015)),
                   "tau": float(np.random.default_rng(seed + 992).normal(0, 0.05)),
                   "delay": float(np.random.default_rng(seed + 993).normal(0, 0.05))}
            out = {}
            for name, agent in [("baseline", FixedPIAgent(cfg, base)), ("gainshield", gs.agent())]:
                r = simulate(cfg, sc, agent, seed=seed, ctx_error=err)
                m = scenario_metrics(cfg, r.df, sc.first_event_t)
                m.update(true_plant_margins(cfg, r))
                m.update({"scenario": sc.name, "category": sc.category, "seed": seed, "controller": name,
                          "compute_us_per_step": r.compute_us_per_step,
                          "rollbacks": int(getattr(agent, "rollbacks", 0)),
                          "monitor_alarms": len(getattr(agent, "events", [])),
                          "final_Kp": float(r.df["Kp"].iloc[-1]), "final_Ki": float(r.df["Ki"].iloc[-1])})
                if name == "gainshield":
                    m["decision_ms_mean"] = float(np.mean(agent.decision_times_ms)) if agent.decision_times_ms else np.nan
                    m["decisions"] = len(agent.decision_times_ms)
                rows.append(m)
                out[name] = r.df
            if seed == 0:
                plots.response_overlay(cfg, out, f"{sc.name}: {sc.description}", FIGS / f"eval_{sc.name}.png")
    wall = time.perf_counter() - t0
    df = pd.DataFrame(rows)
    df.to_csv(RESULTS / "evaluation_runs.csv", index=False)
    agg = df.groupby(["scenario", "controller"], sort=False)[METRICS + ["PM_true_deg", "MM_true", "compute_us_per_step"]] \
        .agg(["mean", "std"])
    agg.columns = [f"{a}_{b}" for a, b in agg.columns]
    agg = agg.reset_index()
    agg.to_csv(RESULTS / "evaluation_summary.csv", index=False)
    plot_bars(agg, FIGS / "eval_bars.png")

    # paired comparison (same scenario + seed)
    piv = df.pivot_table(index=["scenario", "seed"], columns="controller", values=["peak_dev_pct", "IAE_Vs", "settling_time_ms", "i_ripple_A"])
    tests = {}
    for m in ["peak_dev_pct", "IAE_Vs", "settling_time_ms", "i_ripple_A"]:
        a = piv[(m, "baseline")].to_numpy()
        b = piv[(m, "gainshield")].to_numpy()
        ok = np.isfinite(a) & np.isfinite(b)
        w = stats.wilcoxon(b[ok], a[ok]) if ok.sum() > 5 else None
        tests[m] = {"baseline_mean": float(np.mean(a[ok])), "gainshield_mean": float(np.mean(b[ok])),
                    "mean_relative_change_pct": float(100 * np.mean((b[ok] - a[ok]) / a[ok])),
                    "gainshield_better_count": int(np.sum(b[ok] < a[ok])), "pairs": int(ok.sum()),
                    "wilcoxon_p": float(w.pvalue) if w else None}
    per_scen = {}
    for s in df["scenario"].unique():
        d = df[df.scenario == s]
        bb, gg = d[d.controller == "baseline"], d[d.controller == "gainshield"]
        per_scen[s] = {m: {"baseline": float(bb[m].mean()), "gainshield": float(gg[m].mean()),
                           "change_pct": float(100 * (gg[m].mean() - bb[m].mean()) / bb[m].mean()) if bb[m].mean() else None}
                       for m in ["peak_dev_pct", "IAE_Vs", "settling_time_ms", "i_ripple_A", "PM_true_deg"]}
    g = df[df.controller == "gainshield"]
    b = df[df.controller == "baseline"]
    summary = {
        "runs_per_controller": int(len(g)), "seeds": n_seeds, "scenarios": int(df.scenario.nunique()),
        "voltage_violation_ms_total": {"baseline": float(b.v_viol_ms.sum()), "gainshield": float(g.v_viol_ms.sum())},
        "trips": {"baseline": int(b.v_trip.sum()), "gainshield": int(g.v_trip.sum())},
        "current_violation_ms_total": {"baseline": float(b.i_viol_ms.sum()), "gainshield": float(g.i_viol_ms.sum())},
        "min_true_PM_deg": {"baseline": float(b.PM_true_deg.min()), "gainshield": float(g.PM_true_deg.min())},
        "min_true_MM": {"baseline": float(b.MM_true.min()), "gainshield": float(g.MM_true.min())},
        "rollbacks_gainshield": int(g.rollbacks.sum()),
        "monitor_alarms_gainshield": {s_: int(v) for s_, v in g.groupby("scenario")["monitor_alarms"].sum().items() if v},
        "compute_us_per_step_median": {"baseline": float(b.compute_us_per_step.median()),
                                       "gainshield": float(g.compute_us_per_step.median())},
        "gain_decision_ms_mean": float(g.decision_ms_mean.mean()),
        "context_mask_ms": {"n": len(gs.mask_times_ms), "median": float(np.median(gs.mask_times_ms)) if gs.mask_times_ms else None},
        "paired_tests": tests, "per_scenario": per_scen,
        "audit_records": len(audit.records), "audit_gain_trace_problems": verify_gain_trace(audit.records),
        "wall_seconds": wall, "environment": env_info(),
    }
    write_json(RESULTS / "evaluation_summary.json", summary)
    print(agg[["scenario", "controller", "peak_dev_pct_mean", "IAE_Vs_mean", "settling_time_ms_mean", "i_ripple_A_mean", "PM_true_deg_mean"]].to_string(index=False))
    print({k: v for k, v in summary.items() if k not in ("per_scenario", "environment")})
    return df


if __name__ == "__main__":
    main()
