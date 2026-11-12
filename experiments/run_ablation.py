"""Deliverable 6 (ablation): remove one safety/learning component at a time.

  A  complete GainShield
  B  without certified gain-region enforcement (BO searches the whole box; gate skips certificate)
  C  without GP uncertainty checking (safe set from GP MEAN only; gate skips sigma check)
  D  without runtime monitoring
  E  without context awareness (context-blind GP; global certificate only)
  F  without fallback (monitor alarms but nothing is rolled back)

All variants: same training contexts, seeds, iteration budget and evaluation
scenarios. Isolated simulation only - unsafe configurations must never be
connected to hardware.

Outputs: results/ablation.csv, results/ablation.json, results/figures/ablation.png
"""
from __future__ import annotations

import math
import sys
import time

import numpy as np
import pandas as pd

from common import FIGS, RESULTS, GainShield, GainShieldFlags, get_certificate, load_config, write_json
from faults import FaultInjectingAgent
from gainshield.audit.logger import AuditLogger
from gainshield.controllers.baseline import baseline_gains
from gainshield.controllers.pi import PIGains
from gainshield.core import default_training_contexts
from gainshield.disturbances.scenarios import Event, Scenario, scenario_by_name
from gainshield.evaluation import plots
from gainshield.evaluation.metrics import scenario_metrics
from gainshield.simulation import FixedPIAgent, simulate
from gainshield.stability.certify import certify_point, robust_stable_all_nodes

VARIANTS = {
    "A complete": GainShieldFlags(),
    "B no certified region": GainShieldFlags(certified_region=False),
    "C no GP uncertainty": GainShieldFlags(gp_uncertainty=False),
    "D no runtime monitor": GainShieldFlags(runtime_monitor=False),
    "E no context": GainShieldFlags(context_aware=False),
    "F no fallback": GainShieldFlags(fallback=False),
    "B+C plain constrained BO": GainShieldFlags(certified_region=False, gp_uncertainty=False),
}
EVAL_SCEN = ["load_increase", "load_decrease", "g2v_to_v2g", "cap_minus20", "cap_plus20", "delay_long", "combined"]


def evaluate(cfg, gs: GainShield, seeds=(0, 1)) -> dict:
    rows = []
    for s in EVAL_SCEN:
        sc = scenario_by_name(s)
        for seed in seeds:
            ag = gs.agent()
            ag.monitor.enabled = gs.flags.runtime_monitor
            r = simulate(cfg, sc, ag, seed=seed)
            rb = simulate(cfg, sc, FixedPIAgent(cfg, gs.baseline), seed=seed)
            m = scenario_metrics(cfg, r.df, sc.first_event_t)
            mb = scenario_metrics(cfg, rb.df, sc.first_event_t)
            rows.append({"peak_rel": m["peak_dev_pct"] / mb["peak_dev_pct"], "iae_rel": m["IAE_Vs"] / mb["IAE_Vs"],
                         "ripple_rel": m["i_ripple_A"] / mb["i_ripple_A"], "v_viol_ms": m["v_viol_ms"],
                         "trip": m["v_trip"]})
    d = pd.DataFrame(rows)
    return {"deploy_peak_dev_vs_baseline": float(d.peak_rel.mean()), "deploy_IAE_vs_baseline": float(d.iae_rel.mean()),
            "deploy_ripple_vs_baseline": float(d.ripple_rel.mean()), "deploy_v_viol_ms": float(d.v_viol_ms.sum()),
            "deploy_trips": int(d.trip.sum())}


def fault_test(cfg, gs: GainShield) -> dict:
    sc = Scenario("steady10", "", 0.30, 10e3, events=(Event(0.05, "p_load", 10e3),))
    ag = FaultInjectingAgent(cfg, gs, gain_fault=(0.06, PIGains(0.30, 1500.0)))
    ag.monitor.enabled = gs.flags.runtime_monitor
    r = simulate(cfg, sc, ag, seed=0)
    m = scenario_metrics(cfg, r.df, 0.05)
    return {"fault_detected": bool(ag.events), "fault_rolled_back": ag.rollbacks > 0,
            "fault_peak_dev_pct": m["peak_dev_pct"], "fault_v_viol_ms": m["v_viol_ms"]}


def main(n_iters: int = 20, seed: int = 1, only: list[str] | None = None) -> pd.DataFrame:
    cfg = load_config()
    cert = get_certificate(cfg)
    rows = []
    for name, flags in VARIANTS.items():
        if only and name.split()[0] not in only:
            continue
        t0 = time.perf_counter()
        gs = GainShield(cfg, cert, flags=flags, audit=AuditLogger(run_id=name))
        hist = []
        for i, tc in enumerate(default_training_contexts()):
            hist += gs.tune_context(tc, n_iters=n_iters, seed=seed * 100 + i)
        h = pd.DataFrame(hist)
        acc = h[h.accepted]
        row = {"variant": name, "episodes": int(len(acc)), "rejected": int((~h.accepted).sum()),
               "tuning_monitor_aborts": int(acc.aborted.sum()),
               "tuning_unsafe_episodes": int((acc.true_v_viol > 0).sum()),
               "tuning_trips": int(acc.true_trip.sum()),
               "tuning_max_dev_V": float(acc.max_dev_V.max()),
               "tuning_min_m_v": float(acc.m_v.min()),
               # gains applied to the plant that are NOT robustly stable over U (exact tier-1 check)
               "tuning_not_robustly_stable_gains": int((~robust_stable_all_nodes(cfg, acc.Kp.to_numpy(), acc.Ki.to_numpy())).sum()),
               # gains applied that miss the global worst-case margin requirements
               "tuning_gains_below_global_margins": int(sum(not certify_point(cfg, k, i)["margins_ok"]
                                                            for k, i in zip(acc.Kp, acc.Ki))),
               "mean_probe_J": float(acc.J.mean())}
        row.update(evaluate(cfg, gs))
        row.update(fault_test(cfg, gs))
        row["seconds"] = time.perf_counter() - t0
        rows.append(row)
        print(row, flush=True)
    df = pd.DataFrame(rows)
    df.to_csv(RESULTS / "ablation.csv", index=False)
    write_json(RESULTS / "ablation.json", rows)
    import matplotlib.pyplot as plt
    plots.style()
    fig, ax = plt.subplots(1, 3, figsize=(10.5, 3.0), sharey=True)
    y = np.arange(len(df))
    ax[0].barh(y, df.deploy_peak_dev_vs_baseline, color=plots.BLUE, height=0.6)
    ax[0].axvline(1.0, color=plots.ORANGE, ls="--", lw=1)
    ax[0].set_xlabel("deployed peak deviation / baseline")
    ax[1].barh(y, df.tuning_unsafe_episodes + df.tuning_monitor_aborts, color=plots.RED, height=0.6)
    ax[1].set_xlabel("unsafe or aborted tuning episodes")
    ax[2].barh(y, df.fault_peak_dev_pct, color=plots.INK2, height=0.6)
    ax[2].axvline(5, color=plots.RED, ls=":", lw=1)
    ax[2].set_xlabel("peak dev. after injected unstable gains [%]")
    ax[0].set_yticks(y, df.variant)
    ax[0].invert_yaxis()
    for a in ax:
        a.grid(axis="y", visible=False)
    plots.save(fig, FIGS / "ablation.png")
    return df


if __name__ == "__main__":
    main(only=sys.argv[1:] or None)
