"""Stage D/E: online safe tuning sessions over the training contexts.

Each session runs closed-loop probe episodes on the (simulated) plant, with
every candidate passing the independent supervisor gate and the runtime monitor.

Outputs
  results/gainshield_model.pkl          trained contextual GP models
  results/tuning_history.csv            one row per proposal (accepted or rejected)
  results/audit/tuning_audit.jsonl      complete audit log of the sessions
  results/tuning_summary.json
  results/figures/gain_evolution.png
  results/figures/safe_set_nominal.png
"""
from __future__ import annotations

import time

import numpy as np
import pandas as pd

from common import FIGS, RESULTS, GainShield, env_info, get_certificate, load_config, save_model, write_json
from gainshield.audit.logger import AuditLogger, verify_gain_trace
from gainshield.core import default_training_contexts
from gainshield.evaluation import plots


def plot_gain_evolution(hist: pd.DataFrame, baseline, path) -> None:
    import matplotlib.pyplot as plt
    plots.style()
    fig, ax = plt.subplots(3, 1, figsize=(7.2, 5.4), sharex=True)
    x = np.arange(len(hist))
    acc = hist["accepted"].to_numpy(bool)
    for a, col, lab in [(ax[0], "Kp", "Kp [A/V]"), (ax[1], "Ki", "Ki [A/(V s)]")]:
        a.plot(x[acc], hist.loc[acc, col], "o", ms=4, color=plots.BLUE, label="evaluated (accepted)")
        a.plot(x[~acc], hist.loc[~acc, col], "x", ms=5, color=plots.RED, label="rejected by supervisor")
        a.axhline(getattr(baseline, col), color=plots.ORANGE, ls="--", lw=1, label="baseline")
        a.set_ylabel(lab)
        a.set_yscale("log")
    ax[2].plot(x[acc], hist.loc[acc, "J"], "o", ms=4, color=plots.BLUE)
    ax[2].axhline(1.0, color=plots.ORANGE, ls="--", lw=1)
    ax[2].set_ylabel("probe cost J")
    ax[2].set_xlabel("tuning iteration (all sessions)")
    for b in hist.index[hist["iter"] == 0]:
        for a in ax:
            a.axvline(b - 0.5, color=plots.GRID, lw=1.2)
    for b in hist.index[hist["iter"] == 0]:
        ax[0].text(b, ax[0].get_ylim()[1], hist.loc[b, "context"], fontsize=6, rotation=0, va="bottom", color=plots.INK2)
    ax[0].legend(fontsize=7, ncol=3, loc="lower left")
    plots.save(fig, path)


def plot_safe_set(gs: GainShield, z, cfg, path, title) -> None:
    import matplotlib.pyplot as plt
    plots.style()
    P = gs.bo.predict(z)
    S = gs.bo.safe_mask(P)
    G = gs.bo.cand_gains
    fig, ax = plt.subplots(figsize=(5.6, 4.2))
    sc = ax.scatter(G[:, 0], G[:, 1], c=P["muJ"], s=22, cmap="Blues_r", marker="s", edgecolors="none")
    ax.scatter(G[~S, 0], G[~S, 1], s=24, facecolors="none", edgecolors=plots.INK2, linewidths=0.6, marker="s",
               label="certified but not yet GP-safe")
    X = np.array(gs.bo.X)
    if len(X):
        kp = np.exp(gs.bo._lkp[0] + X[:, 0] * (gs.bo._lkp[1] - gs.bo._lkp[0]))
        ki = np.exp(gs.bo._lki[0] + X[:, 1] * (gs.bo._lki[1] - gs.bo._lki[0]))
        ax.plot(kp, ki, "o", ms=3, color=plots.INK, alpha=0.6, label="probe episodes (all contexts)")
    r = gs.bo.recommend(z)
    ax.plot(r.gains.Kp, r.gains.Ki, "*", ms=14, color=plots.AQUA, mec="white", label="recommended")
    ax.plot(gs.baseline.Kp, gs.baseline.Ki, "D", ms=7, color=plots.ORANGE, mec="white", label="baseline")
    ax.set_xscale("log"); ax.set_yscale("log")
    ax.set_xlabel("Kp [A/V]"); ax.set_ylabel("Ki [A/(V s)]")
    cb = fig.colorbar(sc, ax=ax); cb.set_label("GP mean cost J")
    ax.legend(fontsize=7, loc="lower left")
    ax.set_title(title, loc="left")
    plots.save(fig, path)


def main(n_iters: int | None = None, seed: int = 1) -> GainShield:
    cfg = load_config()
    cert = get_certificate(cfg)
    audit = AuditLogger(RESULTS / "audit" / "tuning_audit.jsonl", run_id=f"tuning_seed{seed}")
    gs = GainShield(cfg, cert, audit=audit)
    t0 = time.perf_counter()
    rows = []
    for i, tc in enumerate(default_training_contexts()):
        rows += gs.tune_context(tc, n_iters=n_iters, seed=seed * 100 + i)
    wall = time.perf_counter() - t0
    hist = pd.DataFrame(rows)
    hist.to_csv(RESULTS / "tuning_history.csv", index=False)
    save_model(gs)
    acc = hist[hist["accepted"]]
    recs = {}
    for i, tc in enumerate(default_training_contexts()):
        ctx, _ = gs.context_estimate(tc, np.random.default_rng(seed * 100 + i))
        r = gs.bo.recommend(ctx.as_vector(cfg))
        sub = acc[acc["context"] == tc.name]
        base = sub[sub["kind"].isin(["init", "seed"])].iloc[0]
        recs[tc.name] = {"Kp": r.gains.Kp, "Ki": r.gains.Ki, "pred_J": r.mu_J,
                         "baseline_J_measured": float(base["J"]), "best_J_measured": float(sub["J"].min())}
    summary = {
        "contexts": len(default_training_contexts()),
        "proposals": int(len(hist)), "episodes_run": int(len(acc)),
        "rejected_by_supervisor": int((~hist["accepted"]).sum()),
        "rejection_reasons": hist.loc[~hist["accepted"], "reason"].str.split(" exceeds| >| <|:").str[0].value_counts().to_dict(),
        "episodes_aborted_by_monitor": int(acc["aborted"].sum()),
        "episodes_with_true_band_violation": int(acc["true_v_viol"].sum()),
        "episodes_with_trip": int(acc["true_trip"].sum()),
        "max_true_dev_V": float(acc["max_dev_V"].max()),
        "min_measured_m_v": float(acc["m_v"].min()),
        "bo_iteration_ms_median": float(np.median(gs.bo_times_ms)),
        "bo_iteration_ms_p95": float(np.percentile(gs.bo_times_ms, 95)),
        "wall_seconds_total": wall,
        "audit_records": len(audit.records),
        "audit_gain_trace_problems": verify_gain_trace(audit.records),
        "recommended": recs,
        "environment": env_info(),
    }
    write_json(RESULTS / "tuning_summary.json", summary)
    plot_gain_evolution(hist, gs.baseline, FIGS / "gain_evolution.png")
    ctx0, _ = gs.context_estimate(default_training_contexts()[0], np.random.default_rng(seed * 100))
    plot_safe_set(gs, ctx0.as_vector(cfg), cfg, FIGS / "safe_set_nominal.png", "GP cost & safe set, nominal 10 kW context")
    print({k: v for k, v in summary.items() if k not in ("environment",)})
    return gs


if __name__ == "__main__":
    main()
