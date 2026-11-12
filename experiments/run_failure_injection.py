"""Deliverable 6 (failure analysis): deliberate failure-injection tests.

Every case is a pure simulation. Each records: the injected condition, which
mechanism detected it, the response, and the observed outcome on the TRUE plant.

Outputs
  results/failure_injection.csv / .json
  results/audit/failure_audit.jsonl
  results/figures/fault_unstable_gains.png
"""
from __future__ import annotations

import math

import numpy as np
import pandas as pd

from common import FIGS, RESULTS, get_certificate, load_config, load_model, write_json
from faults import FaultInjectingAgent
from gainshield.audit.logger import AuditLogger
from gainshield.controllers.baseline import baseline_gains
from gainshield.controllers.pi import PIGains
from gainshield.core import GainShieldFlags
from gainshield.disturbances.scenarios import Event, Scenario
from gainshield.evaluation import plots
from gainshield.evaluation.metrics import scenario_metrics
from gainshield.optimizer.safe_bo import Proposal
from gainshield.plant.charger import PlantVariation
from gainshield.simulation import ContextEstimate, FixedPIAgent, simulate
from gainshield.stability.linear_model import nominal_plant, spectral_radius

UNSTABLE = PIGains(0.30, 1500.0)


def _prop(g: PIGains, sd: float = 0.05, lcb: float = 0.5) -> Proposal:
    return Proposal(g, "test", 1.0, 0.1, lcb, lcb, sd, sd, 1, 1)


def gate_cases(cfg, gs) -> list[dict]:
    base = gs.baseline
    nom = ContextEstimate(1.0, cfg.plant.tau_i_nom_s, cfg.converter.delay_nom_samples, 1.0, 10e3)
    cases = [
        ("G1 candidate outside certified region", _prop(UNSTABLE), nom),
        ("G2 certified gains but GP margin uncertainty high", _prop(PIGains(1.5, 180.0), sd=0.4), nom),
        ("G3 certified gains but GP margin lower bound below threshold", _prop(PIGains(1.5, 180.0), lcb=0.05), nom),
        ("G4 context outside validated envelope (C = 0.6 pu)", _prop(PIGains(1.5, 180.0)),
         ContextEstimate(0.6, cfg.plant.tau_i_nom_s, 1.5, 1.0, 10e3)),
        ("G5 excessive gain step (x5 Kp)", _prop(PIGains(base.Kp * 5, base.Ki)), nom),
        ("G6 valid candidate (control case)", _prop(PIGains(1.5, 180.0)), nom),
    ]
    rows = []
    for name, p, ctx in cases:
        d = gs.gate.evaluate(p, ctx, base, base)
        rows.append({"case": name, "layer": "E: candidate gate", "detected": not d.accept,
                     "response": "rejected, baseline kept" if not d.accept else "accepted",
                     "reason": d.reason, "true_trip": 0.0, "peak_dev_pct": math.nan})
    return rows


def gs_flags_fallback(agent) -> bool:
    return bool(agent.flags.fallback)


def runtime_case(cfg, gs, name, scenario, flags=None, seed=0, no_sensor_checks=False, **fault) -> tuple[dict, pd.DataFrame]:
    gs.flags = flags or GainShieldFlags()
    agent = FaultInjectingAgent(cfg, gs, name="gainshield", **fault)
    agent.monitor.enabled = gs.flags.runtime_monitor
    if no_sensor_checks:
        agent.monitor.frozen_tol = -1.0
        agent.monitor.res_th = float("inf")
    r = simulate(cfg, scenario, agent, seed=seed)
    m = scenario_metrics(cfg, r.df, scenario.first_event_t)
    gs.flags = GainShieldFlags()
    ev = agent.events
    return ({"case": name, "layer": "E: runtime monitor + F: fallback",
             "detected": bool(ev), "detection": ev[0]["kind"] if ev else "none",
             "t_detect_ms": 1e3 * ev[0]["t"] if ev else math.nan,
             "response": ("baseline gains + virtual voltage sensor (observer)" if agent.monitor.sensor_failed
                          and gs_flags_fallback(agent) else
                          "rollback to baseline" if agent.rollbacks else
                          ("alarm only (fallback disabled)" if agent.violation_unhandled else
                           ("alarm, baseline already active" if ev else "none"))),
             "reason": ev[0]["detail"] if ev else "", "rollbacks": agent.rollbacks,
             "true_trip": m["v_trip"], "v_viol_ms": m["v_viol_ms"], "peak_dev_pct": m["peak_dev_pct"],
             "final_abs_err_V": float(abs(r.df["v"].iloc[-1] - 800.0))}, r.df)


def main() -> None:
    cfg = load_config()
    cert = get_certificate(cfg)
    audit = AuditLogger(RESULTS / "audit" / "failure_audit.jsonl", run_id="failure_injection")
    gs = load_model(cfg, cert, audit=audit)
    rho = spectral_radius(nominal_plant(cfg), UNSTABLE.Kp, UNSTABLE.Ki)
    rows = gate_cases(cfg, gs)
    steady = Scenario("steady10", "steady 10 kW", 0.30, 10e3, events=(Event(0.05, "p_load", 10e3),))
    figs = {}
    r, df = runtime_case(cfg, gs, "R1 unstable gains injected at 60 ms (gate bypassed)", steady,
                         gain_fault=(0.06, UNSTABLE))
    rows.append(r); figs["full GainShield"] = df
    r, df = runtime_case(cfg, gs, "R2 same, runtime monitor disabled (ablation D)", steady,
                         flags=GainShieldFlags(runtime_monitor=False), gain_fault=(0.06, UNSTABLE))
    rows.append(r); figs["monitor disabled"] = df
    r, df = runtime_case(cfg, gs, "R3 same, fallback disabled (ablation F)", steady,
                         flags=GainShieldFlags(fallback=False), gain_fault=(0.06, UNSTABLE))
    rows.append(r); figs["fallback disabled"] = df
    r, _ = runtime_case(cfg, gs, "R4 voltage-sensor spike +60 V for 0.3 ms", steady,
                        sensor_fault=(0.10, 0.1003, "offset", 60.0))
    rows.append(r)
    r, _ = runtime_case(cfg, gs, "R5 voltage sensor stuck at 800 V from 100 ms, load step at 150 ms",
                        Scenario("stuck", "", 0.30, 10e3, events=(Event(0.15, "p_load", 20e3),)),
                        sensor_fault=(0.10, 1.0, "stuck", 800.0))
    rows.append(r)
    r, _ = runtime_case(cfg, gs, "R5b sensor stuck at 800 V but still noisy (1 V rms), load step at 150 ms",
                        Scenario("stuck_noisy", "", 0.30, 10e3, events=(Event(0.15, "p_load", 20e3),)),
                        sensor_fault=(0.10, 1.0, "stuck_noisy", 800.0))
    rows.append(r)
    r, _ = runtime_case(cfg, gs, "R5-ref same stuck sensor, sensor checks disabled (previous GainShield)",
                        Scenario("stuck", "", 0.30, 10e3, events=(Event(0.15, "p_load", 20e3),)),
                        sensor_fault=(0.10, 1.0, "stuck", 800.0), no_sensor_checks=True)
    rows.append(r)
    r, _ = runtime_case(cfg, gs, "R6 plant outside model: C = 0.5 pu, delay 3 samples (context not updated)",
                        Scenario("drift", "", 0.30, 5e3, events=(Event(0.05, "p_load", 20e3),),
                                 variation=PlantVariation(C_pu=0.5, delay_samples=3.0)))
    rows.append(r)
    r, _ = runtime_case(cfg, gs, "R7 overload: 30 kW step at 0.80 pu grid (current limit)",
                        Scenario("overload", "", 0.30, 5e3, vg0_pu=0.80, events=(Event(0.05, "p_load", 30e3),)))
    rows.append(r)
    # baseline reference for R6/R7 (is it the gains or the plant?)
    for nm, sc in [("R6-ref baseline only, plant outside model",
                    Scenario("drift", "", 0.30, 5e3, events=(Event(0.05, "p_load", 20e3),),
                             variation=PlantVariation(C_pu=0.5, delay_samples=3.0))),
                   ("R7-ref baseline only, overload", Scenario("overload", "", 0.30, 5e3, vg0_pu=0.80,
                                                               events=(Event(0.05, "p_load", 30e3),)))]:
        rr = simulate(cfg, sc, FixedPIAgent(cfg, baseline_gains(cfg)), seed=0)
        m = scenario_metrics(cfg, rr.df, 0.05)
        rows.append({"case": nm, "layer": "reference", "detected": math.nan, "response": "n/a",
                     "true_trip": m["v_trip"], "v_viol_ms": m["v_viol_ms"], "peak_dev_pct": m["peak_dev_pct"],
                     "final_abs_err_V": float(abs(rr.df["v"].iloc[-1] - 800.0))})
    out = pd.DataFrame(rows)
    out.to_csv(RESULTS / "failure_injection.csv", index=False)
    write_json(RESULTS / "failure_injection.json", {"injected_unstable_gains": UNSTABLE.as_tuple(),
                                                     "injected_gains_nominal_spectral_radius": rho,
                                                     "cases": rows})
    # figure
    import matplotlib.pyplot as plt
    plots.style()
    fig, ax = plt.subplots(2, 1, figsize=(6.4, 4.2), sharex=True)
    cols = {"full GainShield": plots.BLUE, "monitor disabled": plots.RED, "fallback disabled": plots.ORANGE}
    styles = {"full GainShield": ("-", 1.5), "monitor disabled": ("-", 3.2), "fallback disabled": ((0, (3, 2)), 1.4)}
    for k in ["monitor disabled", "fallback disabled", "full GainShield"]:
        d = figs[k]
        ls, lw = styles[k]
        ax[0].plot(1e3 * d.t, d.v, color=cols[k], label=k + (" (identical trace)" if k == "fallback disabled" else ""),
                   lw=lw, ls=ls)
        ax[1].step(1e3 * d.t, d.Kp, color=cols[k], where="post", lw=lw, ls=ls)
    for s in (-1, 1):
        ax[0].axhline(800 + s * 40, color=plots.INK2, ls="--", lw=0.8)
        ax[0].axhline(800 + s * 80, color=plots.RED, ls=":", lw=0.8)
    ax[0].axvline(60, color=plots.INK2, lw=0.8)
    ax[0].text(61, 870, "unstable gains injected", fontsize=7, color=plots.INK2)
    ax[0].set_ylim(700, 900)
    ax[0].set_ylabel("V_dc [V]"); ax[1].set_ylabel("Kp [A/V]"); ax[1].set_xlabel("time [ms]")
    ax[0].legend(fontsize=7, loc="lower left", ncol=3)
    ax[0].set_title("Fault injection: monitor + fallback contain an unstable gain write", loc="left")
    plots.save(fig, FIGS / "fault_unstable_gains.png")
    pd.set_option("display.width", 250)
    print(out[["case", "detected", "response", "true_trip", "peak_dev_pct", "reason"]].to_string(index=False))
    print("injected gains spectral radius (nominal):", rho)


if __name__ == "__main__":
    main()
