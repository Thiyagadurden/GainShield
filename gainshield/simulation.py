"""Closed-loop simulation harness shared by every controller.

Controllers implement the ``Agent`` protocol. The harness owns the plant,
noise generator and event schedule, so two agents run on the same scenario
and seed see bit-identical disturbances and noise sequences.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Protocol

import numpy as np
import pandas as pd

from .config import Config
from .controllers.pi import PIController, PIGains
from .disturbances.scenarios import Scenario
from .plant.charger import ChargerPlant, mode_of


@dataclass
class Measurement:
    t: float
    v_ref: float
    v: float          # measured DC voltage (noisy)
    i: float          # measured grid d-current (noisy)
    p_load: float     # DC-DC power demand (known by the charger controller)
    vg_pu: float      # measured grid voltage magnitude (noisy)


@dataclass
class ContextEstimate:
    """Operating context as the controller believes it to be."""

    C_pu: float
    tau_i_s: float
    delay_samples: float
    vg_pu: float
    p_load_W: float

    @property
    def mode(self) -> str:
        return mode_of(self.p_load_W)

    def as_vector(self, cfg: Config) -> np.ndarray:
        """Normalised context features for the GP."""
        return np.array([
            self.C_pu,
            self.vg_pu,
            self.p_load_W / cfg.plant.P_rated_W,
            self.tau_i_s / cfg.plant.tau_i_nom_s,
            self.delay_samples / cfg.converter.delay_nom_samples,
        ])


class Agent(Protocol):
    name: str

    def reset(self, ctx: ContextEstimate, u0: float, t0: float) -> None: ...

    def control(self, m: Measurement, ctx: ContextEstimate) -> float: ...

    def status(self) -> dict: ...


class FixedPIAgent:
    """Manually tuned PI with fixed gains (the baseline)."""

    def __init__(self, cfg: Config, gains: PIGains, name: str = "baseline") -> None:
        self.cfg = cfg
        self.name = name
        lim = cfg.converter.I_grid_max_A
        self.pi = PIController(gains, cfg.converter.Ts, -lim, lim)

    def reset(self, ctx: ContextEstimate, u0: float, t0: float) -> None:
        self.pi.reset(u0)

    def control(self, m: Measurement, ctx: ContextEstimate) -> float:
        return self.pi.update(m.v_ref, m.v)

    def status(self) -> dict:
        return {"state": "BASELINE", "Kp": self.pi.gains.Kp, "Ki": self.pi.gains.Ki}


@dataclass
class SimResult:
    scenario: Scenario
    agent: str
    df: pd.DataFrame
    compute_us_per_step: float
    true_params: dict = field(default_factory=dict)


def simulate(cfg: Config, scenario: Scenario, agent: Agent, seed: int = 0,
             ctx_error: dict | None = None, record_every: int = 1) -> SimResult:
    """Run ``agent`` on ``scenario``.

    ``ctx_error`` holds multiplicative/additive estimation errors applied to the
    true plant parameters to produce the context the agent sees (identical for
    all agents for a given seed).
    """
    rng = np.random.default_rng(seed)
    plant = ChargerPlant(cfg, scenario.variation)
    v_ref = cfg.plant.Vdc_ref_V
    plant.reset(v_ref, scenario.p_load0_W, scenario.vg0_pu)
    Ts = cfg.converter.Ts
    n = int(round(scenario.duration_s / Ts))
    sv = cfg.noise.v_sigma_V * scenario.noise_scale
    si = cfg.noise.i_sigma_A * scenario.noise_scale
    # pre-draw all noise so every agent sees the same sequence
    nv = rng.normal(0.0, sv, n)
    ni = rng.normal(0.0, si, n)
    ng = rng.normal(0.0, 0.005 * scenario.noise_scale, n)
    err = ctx_error or {}
    C_est = plant.C / cfg.plant.C_nom_F * (1.0 + err.get("C", 0.0))
    tau_est = plant.tau_i * (1.0 + err.get("tau", 0.0))
    d_est = plant.delay_samples + err.get("delay", 0.0)

    events = sorted(scenario.events, key=lambda e: e.t)
    ev_idx = 0
    p_load = scenario.p_load0_W
    vg = scenario.vg0_pu
    vg_filt = vg
    ctx = ContextEstimate(C_est, tau_est, d_est, vg, p_load)
    agent.reset(ctx, float(plant.x[1]), 0.0)

    rows = np.zeros((n, 12))
    statuses: list[str] = []
    gains_hist = np.zeros((n, 2))
    t_comp = 0.0
    a_lp = Ts / (2e-3 + Ts)  # 2 ms grid-voltage measurement filter
    for k in range(n):
        t = k * Ts
        while ev_idx < len(events) and events[ev_idx].t <= t + 1e-12:
            e = events[ev_idx]
            if e.kind == "p_load":
                p_load = e.value
                plant.set_load_demand(p_load)
            elif e.kind == "vg":
                vg = e.value
                plant.set_grid_voltage(vg)
            elif e.kind == "vref":
                v_ref = e.value
            ev_idx += 1
        vg_filt += a_lp * (vg + ng[k] - vg_filt)
        x = plant.x
        m = Measurement(t, v_ref, x[0] + nv[k], x[1] + ni[k], p_load, vg_filt)
        ctx = ContextEstimate(C_est, tau_est, d_est, vg_filt, p_load)
        t1 = time.perf_counter()
        u = agent.control(m, ctx)
        t_comp += time.perf_counter() - t1
        st = agent.status()
        statuses.append(st.get("state", ""))
        gains_hist[k] = (st.get("Kp", np.nan), st.get("Ki", np.nan))
        pt = plant.power_terms()
        rows[k] = (t, v_ref, x[0], m.v, x[1], u, x[2], p_load, vg, pt["P_ac"], pt["P_afe_dc"], plant.energy())
        plant.step(u)
        if not np.isfinite(plant.x).all() or plant.x[0] <= 0:
            rows = rows[: k + 1]
            gains_hist = gains_hist[: k + 1]
            break
    df = pd.DataFrame(rows, columns=["t", "v_ref", "v", "v_meas", "i_d", "i_cmd", "p_dc", "p_dem",
                                     "vg_pu", "P_ac", "P_afe_dc", "W_J"])
    df["Kp"] = gains_hist[:, 0]
    df["Ki"] = gains_hist[:, 1]
    df["state"] = statuses[: len(df)]
    if record_every > 1:
        df = df.iloc[::record_every].reset_index(drop=True)
    return SimResult(scenario, agent.name, df, 1e6 * t_comp / max(len(statuses), 1),
                     {"C_F": plant.C, "tau_i_s": plant.tau_i, "delay_samples": plant.delay_samples})
