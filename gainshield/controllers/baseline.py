"""Manual baseline tuning (documented procedure).

Procedure (what an engineer would do by hand, made reproducible):

1. Linearise the DC link around Vref with the AFE inner loop and delay lumped
   into one small time constant:  G(s) = k / s * 1 / (T_sum s + 1),
   k = 1.5 * Vg_pk * eta / (C * Vref),  T_sum = tau_i + T_d + Ts/2 (ZOH).
2. Apply the symmetric-optimum rule (Kessler 1958; Preitl & Precup 1999):
       crossover   w_c = 1 / (a * T_sum)
       Kp          = w_c / k
       Ti          = a^2 * T_sum,   Ki = Kp / Ti
   with a = 3.5 (more conservative than the textbook a = 2 to keep margin
   against +/-20 % C and longer inner-loop lag) using NOMINAL parameters.
3. Verify on the nominal plant: phase margin, load-step response.

The resulting gains are FIXED and remain available as the fallback controller.
"""
from __future__ import annotations

from ..config import Config
from .pi import PIGains


def lumped_time_constant(cfg: Config, tau_i: float | None = None, delay_samples: float | None = None) -> float:
    Ts = cfg.converter.Ts
    tau = cfg.plant.tau_i_nom_s if tau_i is None else tau_i
    d = cfg.converter.delay_nom_samples if delay_samples is None else delay_samples
    return tau + d * Ts + 0.5 * Ts


def plant_integrator_gain(cfg: Config, C_pu: float = 1.0, vg_pu: float = 1.0) -> float:
    p = cfg.plant
    return 1.5 * p.Vg_peak_phase_V * vg_pu * p.eta_afe / (p.C_nom_F * C_pu * p.Vdc_ref_V)


def symmetric_optimum(cfg: Config, a: float | None = None, C_pu: float = 1.0, vg_pu: float = 1.0,
                      tau_i: float | None = None, delay_samples: float | None = None) -> PIGains:
    a = cfg.so_a if a is None else a
    if a <= 1:
        raise ValueError("symmetric optimum requires a > 1")
    T = lumped_time_constant(cfg, tau_i, delay_samples)
    k = plant_integrator_gain(cfg, C_pu, vg_pu)
    wc = 1.0 / (a * T)
    Kp = wc / k
    Ki = Kp / (a * a * T)
    return PIGains(Kp=Kp, Ki=Ki)


def baseline_gains(cfg: Config) -> PIGains:
    """The fixed manually-tuned baseline used throughout (nominal parameters)."""
    return symmetric_optimum(cfg)
