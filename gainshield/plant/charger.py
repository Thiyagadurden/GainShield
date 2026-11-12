"""Averaged model of a bidirectional EV-charger DC link.

Topology represented (averaged, one module)::

    3-ph grid --(AFE: PWM rectifier/inverter, inner i_d loop)--> DC link C --(bidirectional DC-DC)--> battery

State vector x = [v_dc, i_d, p_dc]

* ``v_dc``  DC-link voltage [V]
* ``i_d``   AFE grid d-axis current, peak amplitude [A] (+ = power from grid)
* ``p_dc``  power drawn from the DC link by the DC-DC stage [W]
            (+ = G2V charging the battery, - = V2G discharging into the link)

Equations (power balance on the DC-link energy W = 1/2 C v^2)::

    C v dv/dt  = P_afe,dc - p_dc - v^2 / R_loss
    P_ac       = 1.5 * Vg_pk * i_d                    (dq power, unity PF, PLL locked)
    P_afe,dc   = eta * P_ac   if P_ac >= 0  (rectifying, G2V)
               = P_ac / eta   if P_ac <  0  (inverting,  V2G)
    tau_i  di_d/dt  = i_d*(t - T_d) - i_d             (closed inner current loop + delay)
    tau_dc dp_dc/dt = p_dem,slew(t) - p_dc            (DC-DC battery-power loop)

The DC-DC stage regulates battery power independently of v_dc, so seen from
the link it is a constant-power load (CPL) in G2V and a constant-power source
in V2G. The CPL's negative incremental resistance appears when the equation is
written in current form (i = p/v); in the power form above it is captured
exactly by the 1/(C v) factor.

Represented: DC-link energy dynamics, CPL behaviour, AFE inner-loop lag,
fractional control/PWM delay (sampled controller + ZOH), DC-DC lag and slew,
direction-dependent AFE losses, grid-voltage magnitude, current and power limits.

Omitted (documented in docs/MATHEMATICAL_MODEL.md): switching ripple,
AC-side filter dynamics and PLL dynamics, grid unbalance/harmonics, battery
voltage dynamics, thermal effects, DC-DC duty-cycle level dynamics.
"""
from __future__ import annotations

from dataclasses import dataclass
import math

import numpy as np

from ..config import Config


@dataclass
class PlantVariation:
    """Per-run deviation of the true plant from nominal (per-unit / absolute)."""

    C_pu: float = 1.0          # true C / C_nom
    tau_i_s: float | None = None   # None -> nominal
    delay_samples: float | None = None  # None -> nominal
    R_loss_ohm: float | None = None


class ChargerPlant:
    """Averaged bidirectional charger, integrated with fixed-step RK4.

    The controller runs at ``Ts``; the plant is integrated with ``substeps``
    RK4 sub-steps per control period so that fractional control delays are
    represented at a resolution of ``Ts / substeps``.
    """

    def __init__(self, cfg: Config, variation: PlantVariation | None = None) -> None:
        self.cfg = cfg
        var = variation or PlantVariation()
        p, c = cfg.plant, cfg.converter
        self.C = p.C_nom_F * var.C_pu
        self.tau_i = var.tau_i_s if var.tau_i_s is not None else p.tau_i_nom_s
        self.delay_samples = var.delay_samples if var.delay_samples is not None else c.delay_nom_samples
        self.R = var.R_loss_ohm if var.R_loss_ohm is not None else p.R_loss_ohm
        self.eta = p.eta_afe
        self.tau_dc = p.tau_dcdc_s
        self.slew = p.dcdc_slew_W_per_s
        self.Vg_pk_nom = p.Vg_peak_phase_V
        self.Ts = c.Ts
        self.n_sub = c.substeps
        self.h = self.Ts / self.n_sub
        self.I_max = c.I_grid_max_A
        self.P_dc_max = c.P_dcdc_max_W
        if self.C <= 0 or self.tau_i <= 0 or self.delay_samples < 0:
            raise ValueError("non-physical plant parameters")
        # delay in sub-steps (fractional delay resolved to the sub-step grid)
        self.delay_sub = int(round(self.delay_samples * self.n_sub))
        self.x = np.zeros(3)
        self.vg_pu = 1.0
        self.p_dem = 0.0          # DC-DC demanded battery power (after limits)
        self.p_dem_slewed = 0.0
        self._cmd_hist: list[float] = []   # i_d* per sub-step (for delay line)
        self.t = 0.0

    # ------------------------------------------------------------------ setup
    def equilibrium(self, v: float, p_load: float, vg_pu: float = 1.0) -> np.ndarray:
        """Steady state for a given DC voltage, battery power and grid voltage."""
        p_need = p_load + v * v / self.R
        vgpk = self.Vg_pk_nom * vg_pu
        p_ac = p_need / self.eta if p_need >= 0 else p_need * self.eta
        i_d = p_ac / (1.5 * vgpk)
        return np.array([v, i_d, p_load])

    def reset(self, v0: float, p_load0: float, vg_pu: float = 1.0) -> np.ndarray:
        self.vg_pu = vg_pu
        self.x = self.equilibrium(v0, p_load0, vg_pu)
        self.p_dem = self.p_dem_slewed = float(np.clip(p_load0, -self.P_dc_max, self.P_dc_max))
        hist_len = self.delay_sub + self.n_sub + 2
        self._cmd_hist = [float(self.x[1])] * hist_len
        self.t = 0.0
        return self.x.copy()

    # --------------------------------------------------------------- dynamics
    def afe_dc_power(self, i_d: float) -> float:
        p_ac = 1.5 * self.Vg_pk_nom * self.vg_pu * i_d
        return self.eta * p_ac if p_ac >= 0 else p_ac / self.eta

    def _f(self, x: np.ndarray, i_cmd: float, p_ref: float) -> np.ndarray:
        v, i_d, p_dc = x
        v_safe = max(v, 1.0)  # avoid division by zero in pathological runs
        dv = (self.afe_dc_power(i_d) - p_dc - v * v / self.R) / (self.C * v_safe)
        di = (i_cmd - i_d) / self.tau_i
        dp = (p_ref - p_dc) / self.tau_dc
        return np.array([dv, di, dp])

    def set_load_demand(self, p_dem: float) -> None:
        self.p_dem = float(np.clip(p_dem, -self.P_dc_max, self.P_dc_max))

    def set_grid_voltage(self, vg_pu: float) -> None:
        self.vg_pu = float(vg_pu)

    def step(self, i_cmd: float) -> np.ndarray:
        """Advance one control period with the (already saturated) command i_d*.

        The command enters a delay line, so the AFE sees it ``delay_samples``
        control periods later (zero-order hold between controller updates).
        """
        i_cmd = float(np.clip(i_cmd, -self.I_max, self.I_max))
        h = self.h
        for _ in range(self.n_sub):
            self._cmd_hist.append(i_cmd)
            applied = self._cmd_hist[-1 - self.delay_sub]
            # DC-DC slew limiting of the battery-power demand
            dmax = self.slew * h
            self.p_dem_slewed += float(np.clip(self.p_dem - self.p_dem_slewed, -dmax, dmax))
            pr = self.p_dem_slewed
            x = self.x
            k1 = self._f(x, applied, pr)
            k2 = self._f(x + 0.5 * h * k1, applied, pr)
            k3 = self._f(x + 0.5 * h * k2, applied, pr)
            k4 = self._f(x + h * k3, applied, pr)
            self.x = x + (h / 6.0) * (k1 + 2 * k2 + 2 * k3 + k4)
            self.t += h
        # bound history length
        if len(self._cmd_hist) > 4 * (self.delay_sub + self.n_sub + 2):
            self._cmd_hist = self._cmd_hist[-(self.delay_sub + self.n_sub + 2):]
        return self.x.copy()

    # ------------------------------------------------------------ diagnostics
    def energy(self) -> float:
        return 0.5 * self.C * self.x[0] ** 2

    def power_terms(self) -> dict[str, float]:
        v, i_d, p_dc = self.x
        return {
            "P_ac": 1.5 * self.Vg_pk_nom * self.vg_pu * i_d,
            "P_afe_dc": self.afe_dc_power(i_d),
            "P_dc": p_dc,
            "P_loss": v * v / self.R,
        }

    @property
    def loop_gain_k(self) -> float:
        """Small-signal integrator gain k = dv/dt per A of i_d (1/(F)·W/V)."""
        return 1.5 * self.Vg_pk_nom * self.vg_pu * self.eta / (self.C * self.x[0] if self.x[0] > 0 else 1.0)


def mode_of(p_load: float) -> str:
    """Operating mode label from battery-side power sign."""
    if abs(p_load) < 1.0:
        return "IDLE"
    return "G2V" if p_load > 0 else "V2G"


def rated_check(cfg: Config) -> dict[str, float]:
    """Quick sanity numbers used by tests and docs."""
    p = cfg.plant
    I_rated = p.P_rated_W / (1.5 * p.Vg_peak_phase_V)
    return {
        "Vg_peak_phase_V": p.Vg_peak_phase_V,
        "I_d_at_rated_A": I_rated,
        "I_headroom_frac": cfg.converter.I_grid_max_A / I_rated,
        "stored_energy_J": 0.5 * p.C_nom_F * p.Vdc_ref_V ** 2,
        "energy_ms_at_rated": 1e3 * 0.5 * p.C_nom_F * p.Vdc_ref_V ** 2 / p.P_rated_W,
        "sqrt3": math.sqrt(3),
    }
