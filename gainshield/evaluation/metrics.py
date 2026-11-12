"""Performance and constraint metrics (computed on the TRUE plant signals).

Definitions (documented in docs/EVALUATION_REPORT.md):

* settling_time_ms  time from the first disturbance until |v - Vref| enters and
                    stays inside +/- settle_band_frac * Vref (4 V at 800 V).
                    NaN if it never settles inside the run.
* peak_dev_pct      max |v - Vref| after the first disturbance, % of Vref.
                    (For a disturbance-rejection test this is the 'overshoot'
                    of the regulated voltage away from its set-point.)
* recovery_os_pct   classical overshoot of the recovery: largest excursion on
                    the opposite side of Vref, as % of the peak deviation.
* IAE_Vs            integral of |v - Vref| dt after the first disturbance [V s].
* v_viol_ms         time outside the +/-5 % operating band [ms]; v_trip = ever
                    outside +/-10 %.
* i_viol_ms         time with |i_d| > 95 % of the current limit [ms].
* i_ripple_A        std of the controller output in the last 30 ms
                    (sensor-noise amplification into the current reference).
"""
from __future__ import annotations

import math

import numpy as np
import pandas as pd

from ..config import Config


def settling_time(t: np.ndarray, err: np.ndarray, t0: float, band: float) -> float:
    m = t >= t0
    tt, ee = t[m], np.abs(err[m])
    if tt.size == 0:
        return math.nan
    outside = np.nonzero(ee > band)[0]
    if outside.size == 0:
        return 0.0
    last = outside[-1]
    if last >= tt.size - 1:
        return math.nan
    return float(tt[last + 1] - t0)


def scenario_metrics(cfg: Config, df: pd.DataFrame, t0: float) -> dict[str, float]:
    Vref = cfg.plant.Vdc_ref_V
    t = df["t"].to_numpy()
    v = df["v"].to_numpy()
    vr = df["v_ref"].to_numpy()
    e = v - vr
    dt = t[1] - t[0] if t.size > 1 else cfg.converter.Ts
    m = t >= t0
    em = e[m]
    if em.size == 0:
        raise ValueError("disturbance time beyond simulation end")
    peak_i = int(np.argmax(np.abs(em)))
    peak = float(em[peak_i])
    after = em[peak_i:]
    opp = after[np.sign(after) == -np.sign(peak)] if peak != 0 else np.array([])
    rec_os = float(100 * np.max(np.abs(opp)) / abs(peak)) if opp.size and peak != 0 else 0.0
    band_op = cfg.constraints.V_band_op * Vref
    band_trip = cfg.constraints.V_band_trip * Vref
    I_thr = cfg.constraints.I_margin_frac * cfg.converter.I_grid_max_A
    i = df["i_d"].to_numpy()
    u = df["i_cmd"].to_numpy()
    tail = t >= t[-1] - 0.03
    return {
        "settling_time_ms": 1e3 * settling_time(t, e, t0, cfg.constraints.settle_band_frac * Vref),
        "peak_dev_pct": 100 * abs(peak) / Vref,
        "recovery_os_pct": rec_os,
        "IAE_Vs": float(np.sum(np.abs(em)) * dt),
        "v_viol_ms": float(1e3 * np.sum(np.abs(e) > band_op) * dt),
        "v_trip": float(np.any(np.abs(e) > band_trip)),
        "i_viol_ms": float(1e3 * np.sum(np.abs(i) > I_thr) * dt),
        "i_peak_A": float(np.max(np.abs(i))),
        "i_ripple_A": float(np.std(u[tail])),
        "v_margin": float((band_op - np.max(np.abs(e))) / band_op),
        "i_margin": float((I_thr - np.max(np.abs(i))) / I_thr),
    }


def probe_metrics(cfg: Config, df: pd.DataFrame, t_ref: float = 0.02, t_load: float = 0.09,
                  ref_step_V: float = 10.0, aborted: bool = False) -> dict[str, float]:
    """Metrics of a tuning-probe episode (see disturbances.probe_scenario)."""
    t = df["t"].to_numpy()
    e = (df["v"] - df["v_ref"]).to_numpy()
    dt = t[1] - t[0]
    seg1 = (t >= t_ref) & (t < t_load)
    e1 = e[seg1]
    # overshoot of the +10 V reference step: v - 810 > 0 after the step
    os_pct = float(100 * max(0.0, np.max(e1)) / ref_step_V) if e1.size else math.nan
    ts_ref = settling_time(t[seg1], e1, t_ref, 0.1 * ref_step_V) if e1.size else math.nan
    m = t >= t_ref
    iae = float(np.sum(np.abs(e[m])) * dt)
    u = df["i_cmd"].to_numpy()
    quiet = (t >= t_load - 0.025) & (t < t_load)
    ripple = float(np.std(u[quiet])) if np.any(quiet) else math.nan
    Vref = cfg.plant.Vdc_ref_V
    V_abort = cfg.supervisor.V_abort_frac * Vref
    I_thr = cfg.constraints.I_margin_frac * cfg.converter.I_grid_max_A
    seg2 = t >= t_load
    peak_load = float(np.max(np.abs(e[seg2]))) if np.any(seg2) else math.nan
    return {
        "IAE_Vs": iae,
        "overshoot_pct": os_pct,
        "settling_ms": 1e3 * ts_ref if not math.isnan(ts_ref) else math.nan,
        "ripple_A": ripple,
        "peak_load_dev_V": peak_load,
        # normalised safety margins (>= 0 means inside the supervisor abort limits)
        "m_v": float((V_abort - np.max(np.abs(e))) / V_abort),
        "m_i": float((I_thr - np.max(np.abs(df["i_d"].to_numpy()))) / I_thr),
        "aborted": float(aborted),
    }


# reference scales so that the cost is dimensionless (baseline at nominal ~ 1.0)
# Design choice (documented): disturbance rejection dominates for a DC link,
# ripple (sensor-noise amplification into the current reference) is the
# counter-weight that stops the optimiser from simply maximising Kp.
COST_WEIGHTS = {"IAE_Vs": 0.35, "peak_load_dev_V": 0.25, "overshoot_pct": 0.10, "settling_ms": 0.10, "ripple_A": 0.20}


def probe_cost(pm: dict[str, float], scales: dict[str, float]) -> float:
    """Scalar cost J (lower is better). Aborted / unsettled episodes are penalised."""
    J = 0.0
    for k, w in COST_WEIGHTS.items():
        val = pm[k]
        if not np.isfinite(val):
            val = 3.0 * scales[k]
        J += w * val / scales[k]
    if pm.get("aborted", 0.0) > 0:
        J = max(J, 3.0)
    return float(J)
