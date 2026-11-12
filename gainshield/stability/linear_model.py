"""Exact discrete-time small-signal model of the sampled DC-link loop.

Continuous small-signal plant about (Vref, P0), lossless (R -> inf, see note)::

    dv/dt   = k * i_d                 k = 1.5 * Vg_pk * vg_pu * eta / (C * Vref)
    di_d/dt = (u(t - T_d) - i_d) / tau_i

The controller output u[k] is held (ZOH) and applied after a total delay
T_d = d * Ts, d = dI + f, 0 <= f < 1 (computation + PWM). Exact ZOH
discretisation with fractional input delay (Astrom & Wittenmark, Computer
Controlled Systems, sec. 2.3) gives::

    x[k+1] = Phi x[k] + G0 u[k-dI] + G1 u[k-dI-1]

and the pulse transfer function from u to v::

    P(z) = k * N_hat(z) / ((z - 1)(z - lam) z^(dI+1)),   lam = exp(-Ts/tau_i)

Every v-related entry of Phi, G0, G1 is proportional to k, so the closed-loop
characteristic polynomial with the PI controller C(z) = Kp + Ki Ts/(z-1) is
AFFINE in k::

    p(z; k) = D(z) + k * N(z)
    D(z) = (z-1)^2 (z-lam) z^(dI+1)
    N(z) = N_hat(z) * (Kp (z-1) + Ki Ts)

This structure is what makes the robust certificate in ``certify.py`` exact
over the whole capacitance / grid-voltage / efficiency interval.

Note on losses: the lumped loss term adds a pole at -2/(C R) ~ -0.05 rad/s
(stabilising, negligible). It is omitted here so that the k-affine structure
holds; tests check that results with losses included agree.
"""
from __future__ import annotations

from dataclasses import dataclass
import math

import numpy as np

from ..config import Config


@dataclass(frozen=True)
class LinearPlant:
    k: float          # integrator gain [V/(A s)]
    tau_i: float      # inner-loop time constant [s]
    delay: float      # total delay in samples
    Ts: float

    @property
    def dI(self) -> int:
        return int(math.floor(self.delay + 1e-12))

    @property
    def frac(self) -> float:
        return self.delay - self.dI


def k_from_context(cfg: Config, C_pu: float, vg_pu: float, eta: float | None = None) -> float:
    p = cfg.plant
    eta = p.eta_afe if eta is None else eta
    return 1.5 * p.Vg_peak_phase_V * vg_pu * eta / (p.C_nom_F * C_pu * p.Vdc_ref_V)


def k_interval(cfg: Config, C_pu_range: tuple[float, float] | None = None,
               vg_range: tuple[float, float] | None = None) -> tuple[float, float]:
    """Interval of k over the uncertainty set (eta in [eta, 1/eta] covers both directions)."""
    p = cfg.plant
    Cr = C_pu_range or (1 - p.C_tol, 1 + p.C_tol)
    Vr = vg_range or p.Vg_range
    kmin = k_from_context(cfg, Cr[1], Vr[0], p.eta_afe)
    # in V2G the AFE power seen from the DC side is P_ac/eta -> gain 1/eta
    kmax = k_from_context(cfg, Cr[0], Vr[1], 1.0 / p.eta_afe)
    return kmin, kmax


def _int_eAsB(k: float, alpha: float, h: float) -> np.ndarray:
    """int_0^h exp(A s) B ds for A=[[0,k],[0,-alpha]], B=[0,alpha]."""
    if h <= 0:
        return np.zeros(2)
    e = math.exp(-alpha * h)
    return np.array([k * (h - (1 - e) / alpha), 1 - e])


def discretize(pl: LinearPlant) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    alpha = 1.0 / pl.tau_i
    Ts, f = pl.Ts, pl.frac
    def Phi(h: float) -> np.ndarray:
        e = math.exp(-alpha * h)
        return np.array([[1.0, pl.k * (1 - e) / alpha], [0.0, e]])
    tau_p = f * Ts
    G0 = _int_eAsB(pl.k, alpha, Ts - tau_p)
    G1 = Phi(Ts - tau_p) @ _int_eAsB(pl.k, alpha, tau_p)
    return Phi(Ts), G0, G1


def plant_polys(pl: LinearPlant) -> tuple[np.ndarray, np.ndarray]:
    """Return (num, den) of P(z) in descending powers of z (num includes k)."""
    Phi, G0, G1 = discretize(pl)
    lam = Phi[1, 1]
    phi12 = Phi[0, 1]
    # c (zI-Phi)^-1 (G0 z + G1) * z^-(dI+1)
    num = np.polyadd(np.polymul([1.0, -lam], [G0[0], G1[0]]), phi12 * np.array([G0[1], G1[1]]))
    den = np.polymul(np.polymul([1.0, -1.0], [1.0, -lam]), np.r_[1.0, np.zeros(pl.dI + 1)])
    return num, den


def char_polys(pl: LinearPlant, Kp: float, Ki: float) -> tuple[np.ndarray, np.ndarray]:
    """Return (D, N) with closed-loop characteristic polynomial p = D + N (k included in N).

    D(z) = den_P(z) * (z - 1);  N(z) = num_P(z) * (Kp (z-1) + Ki Ts).
    """
    num, den = plant_polys(pl)
    D = np.polymul(den, [1.0, -1.0])
    N = np.polymul(num, [Kp, -Kp + Ki * pl.Ts])
    n = max(len(D), len(N))
    return np.r_[np.zeros(n - len(D)), D], np.r_[np.zeros(n - len(N)), N]


def closed_loop_poles(pl: LinearPlant, Kp: float, Ki: float) -> np.ndarray:
    D, N = char_polys(pl, Kp, Ki)
    p = np.trim_zeros(D + N, "f")
    return np.roots(p)


def spectral_radius(pl: LinearPlant, Kp: float, Ki: float) -> float:
    return float(np.max(np.abs(closed_loop_poles(pl, Kp, Ki))))


def plant_freq_response(pl: LinearPlant, w: np.ndarray) -> np.ndarray:
    num, den = plant_polys(pl)
    z = np.exp(1j * w * pl.Ts)
    return np.polyval(num, z) / np.polyval(den, z)


def pi_freq_response(Kp: np.ndarray | float, Ki: np.ndarray | float, w: np.ndarray, Ts: float) -> np.ndarray:
    z = np.exp(1j * w * Ts)
    Kp = np.asarray(Kp, dtype=float)[..., None]
    Ki = np.asarray(Ki, dtype=float)[..., None]
    return Kp + Ki * Ts / (z - 1.0)


def default_w_grid(Ts: float, n: int = 1500) -> np.ndarray:
    return np.logspace(0.5, math.log10(0.999 * math.pi / Ts), n)


def margins_from_loop(L: np.ndarray, w: np.ndarray) -> dict[str, np.ndarray]:
    """Vectorised PM/GM/MM from loop frequency response L (..., n_w).

    PM  [deg]: min over gain-crossover frequencies of 180 + angle(L).
    GM  [dB]:  upper gain margin, min over phase-crossovers (-180 mod 360) with |L|<1.
    MM  [-]:   modulus (disk) margin min |1 + L| (inverse of peak sensitivity).
    wc  [rad/s]: first gain-crossover frequency (bandwidth proxy).
    """
    L = np.atleast_2d(L)
    mag = np.abs(L)
    ph = np.unwrap(np.angle(L), axis=-1)
    ph_deg = np.degrees(ph)
    lm = np.log(np.maximum(mag, 1e-300))
    # gain crossovers: sign change of log|L|
    s = np.sign(lm)
    cross = (s[:, :-1] > 0) & (s[:, 1:] <= 0)
    PM = np.full(L.shape[0], np.inf)
    wc = np.full(L.shape[0], np.nan)
    rows, cols = np.nonzero(cross)
    if rows.size:
        t = lm[rows, cols] / (lm[rows, cols] - lm[rows, cols + 1])
        phc = ph_deg[rows, cols] + t * (ph_deg[rows, cols + 1] - ph_deg[rows, cols])
        pm = ((phc + 180.0) + 180.0) % 360.0 - 180.0
        np.minimum.at(PM, rows, pm)
        wcs = w[cols] + t * (w[cols + 1] - w[cols])
        first = np.full(L.shape[0], np.inf)
        np.minimum.at(first, rows, wcs)
        wc = np.where(np.isfinite(first), first, np.nan)
    # phase crossovers of -180 + 360 m
    q = np.floor((ph_deg + 180.0) / 360.0)
    pc = q[:, :-1] != q[:, 1:]
    GM = np.full(L.shape[0], np.inf)
    rows, cols = np.nonzero(pc)
    if rows.size:
        m = mag[rows, cols]
        ok = m < 1.0
        gm = -20 * np.log10(np.maximum(m, 1e-300))
        gm = np.where(ok, gm, np.inf)
        np.minimum.at(GM, rows, gm)
    MM = np.min(np.abs(1.0 + L), axis=-1)
    return {"PM": PM, "GM": GM, "MM": MM, "wc": wc}


def nominal_plant(cfg: Config, C_pu: float = 1.0, vg_pu: float = 1.0, tau_i: float | None = None,
                  delay: float | None = None) -> LinearPlant:
    return LinearPlant(
        k=k_from_context(cfg, C_pu, vg_pu),
        tau_i=cfg.plant.tau_i_nom_s if tau_i is None else tau_i,
        delay=cfg.converter.delay_nom_samples if delay is None else delay,
        Ts=cfg.converter.Ts,
    )


def loop_margins(cfg: Config, pl: LinearPlant, Kp: float, Ki: float) -> dict[str, float]:
    w = default_w_grid(pl.Ts)
    L = plant_freq_response(pl, w) * pi_freq_response(Kp, Ki, w, pl.Ts)
    m = margins_from_loop(L, w)
    out = {k: float(v[0]) for k, v in m.items()}
    out["rho"] = spectral_radius(pl, Kp, Ki)
    return out
