"""Configuration loading.

All numerical parameters live in ``config/default.toml``. This module turns the
TOML file into typed, frozen dataclasses so the rest of the code never reads
magic numbers. Every value is an engineering assumption (see docs/ASSUMPTIONS.md).
"""
from __future__ import annotations

import math
import tomllib
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG = REPO_ROOT / "config" / "default.toml"


@dataclass(frozen=True)
class PlantParams:
    P_rated_W: float
    Vdc_ref_V: float
    C_nom_F: float
    C_tol: float
    Vg_ll_rms_V: float
    Vg_range: tuple[float, float]
    R_loss_ohm: float
    eta_afe: float
    tau_i_nom_s: float
    tau_i_range_s: tuple[float, float]
    tau_dcdc_s: float
    dcdc_slew_W_per_s: float

    @property
    def Vg_peak_phase_V(self) -> float:
        """Peak phase voltage at 1.0 pu (amplitude-invariant dq frame)."""
        return self.Vg_ll_rms_V * math.sqrt(2.0 / 3.0)


@dataclass(frozen=True)
class ConverterParams:
    f_sw_Hz: float
    f_s_Hz: float
    delay_nom_samples: float
    delay_range_samples: tuple[float, float]
    substeps: int
    I_grid_max_A: float
    P_dcdc_max_W: float

    @property
    def Ts(self) -> float:
        return 1.0 / self.f_s_Hz


@dataclass(frozen=True)
class Constraints:
    V_band_op: float
    V_band_trip: float
    I_margin_frac: float
    settle_band_frac: float
    PM_min_deg: float
    GM_min_dB: float
    MM_min: float


@dataclass(frozen=True)
class OptimizerParams:
    beta: float
    n_grid: int
    n_init: int
    iters_per_context: int
    safety_margin_min: float
    sigma_max_accept: float
    seed: int


@dataclass(frozen=True)
class SupervisorParams:
    V_abort_frac: float
    I_abort_frac: float
    I_abort_hold_s: float
    osc_window_s: float
    osc_rms_V: float
    context_envelope: dict[str, tuple[float, float]]


@dataclass(frozen=True)
class NoiseParams:
    v_sigma_V: float
    i_sigma_A: float


@dataclass(frozen=True)
class ContextErrorBounds:
    C_err: float
    vg_err: float
    tau_err: float
    delay_err: float


@dataclass(frozen=True)
class Config:
    plant: PlantParams
    converter: ConverterParams
    constraints: Constraints
    so_a: float
    Kp_range: tuple[float, float]
    Ki_range: tuple[float, float]
    optimizer: OptimizerParams
    supervisor: SupervisorParams
    noise: NoiseParams
    ctx_err: ContextErrorBounds
    raw: dict[str, Any] = field(default_factory=dict, compare=False, repr=False)

    def with_optimizer(self, **kw: Any) -> "Config":
        return replace(self, optimizer=replace(self.optimizer, **kw))

    def with_supervisor(self, **kw: Any) -> "Config":
        return replace(self, supervisor=replace(self.supervisor, **kw))


def _tup(x: Any) -> tuple[float, float]:
    if not (isinstance(x, (list, tuple)) and len(x) == 2):
        raise ValueError(f"expected a 2-element range, got {x!r}")
    lo, hi = float(x[0]), float(x[1])
    if lo > hi:
        raise ValueError(f"range lower bound {lo} exceeds upper bound {hi}")
    return lo, hi


def load_config(path: str | Path | None = None) -> Config:
    """Load and validate a GainShield TOML configuration."""
    p = Path(path) if path is not None else DEFAULT_CONFIG
    with open(p, "rb") as fh:
        raw = tomllib.load(fh)
    pl = dict(raw["plant"])
    for k in ("Vg_range", "tau_i_range_s"):
        pl[k] = _tup(pl[k])
    cv = dict(raw["converter"])
    cv["delay_range_samples"] = _tup(cv["delay_range_samples"])
    cv["substeps"] = int(cv["substeps"])
    sup = dict(raw["supervisor"])
    sup["context_envelope"] = {k: _tup(v) for k, v in sup["context_envelope"].items()}
    cfg = Config(
        plant=PlantParams(**pl),
        converter=ConverterParams(**cv),
        constraints=Constraints(**raw["constraints"]),
        so_a=float(raw["baseline"]["so_a"]),
        Kp_range=_tup(raw["gains_box"]["Kp_range"]),
        Ki_range=_tup(raw["gains_box"]["Ki_range"]),
        optimizer=OptimizerParams(**raw["optimizer"]),
        supervisor=SupervisorParams(**sup),
        noise=NoiseParams(**raw["noise"]),
        ctx_err=ContextErrorBounds(**raw["context_estimation"]),
        raw=raw,
    )
    _validate(cfg)
    return cfg


def _validate(cfg: Config) -> None:
    p, c = cfg.plant, cfg.converter
    checks = {
        "C_nom_F > 0": p.C_nom_F > 0,
        "0 < eta_afe <= 1": 0 < p.eta_afe <= 1,
        "tau_i range contains nominal": p.tau_i_range_s[0] <= p.tau_i_nom_s <= p.tau_i_range_s[1],
        "delay range contains nominal": c.delay_range_samples[0] <= c.delay_nom_samples <= c.delay_range_samples[1],
        "substeps >= 2": c.substeps >= 2,
        "trip band wider than operating band": cfg.constraints.V_band_trip > cfg.constraints.V_band_op,
        "abort band inside operating band": cfg.supervisor.V_abort_frac < cfg.constraints.V_band_op,
        "rated grid current can carry rated power": 1.5 * p.Vg_peak_phase_V * c.I_grid_max_A > p.P_rated_W,
    }
    bad = [k for k, ok in checks.items() if not ok]
    if bad:
        raise ValueError("invalid configuration: " + "; ".join(bad))
