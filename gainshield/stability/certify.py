"""Stability certification of PI gains over the plant uncertainty set.

Uncertainty set U (all from config):
    C       in [1 - C_tol, 1 + C_tol] * C_nom      (+/-20 %)
    vg      in Vg_range                            (0.80 ... 1.10 pu)
    eta     in {eta (G2V), 1/eta (V2G)}            (direction)
    tau_i   in tau_i_range_s                       (0.3 ... 1.0 ms)
    delay   in delay_range_samples                 (1.0 ... 2.0 samples)
C, vg and eta enter ONLY through the scalar k (see linear_model.py), giving
an interval [k_min, k_max].

Four regions are computed and kept distinct:

1. SCREENED   Monte-Carlo: stable (spectral radius < 1) for N random plants
              drawn from U. Evidence, not proof.
2. NOMINAL    Exactly stable for the nominal plant (roots of the
              characteristic polynomial inside the unit circle).
3. CERTIFIED  For every (tau_i, delay) node of a dense grid over U:
              (a) stable for ALL k in [k_min, k_max] - proved with the
                  zero-exclusion principle on the k-affine characteristic
                  polynomial p(z;k) = D(z) + k N(z): p is stable on the whole
                  segment iff it is stable at k_min and no k in the segment
                  places a root on |z| = 1. Unit-circle roots for some real k
                  occur only where Im{D(z) conj N(z)} = 0, i.e. at the
                  unit-circle roots of F(z) = D(z) rev(N)(z) - rev(D)(z) N(z),
                  which are found exactly (polynomial roots);
              (b) PM >= PM_min, GM >= GM_min, MM >= MM_min at k in
                  {k_min, k_nom, k_max} (numerical frequency sweep).
              Limitation: tau_i and delay are gridded, not proved between
              nodes; the margin requirements give slack to cover the gaps
              (verified by a refinement test). Valid for the linearised
              model only (small-signal, unsaturated).
4. VALIDATED  Empirical: nonlinear simulations over the disturbance suite
              produced no constraint violation (computed in experiments/).
"""
from __future__ import annotations

from dataclasses import dataclass, field
import math
import time

import numpy as np

from ..config import Config
from .linear_model import (LinearPlant, char_polys, default_w_grid, k_from_context, k_interval,
                           margins_from_loop, nominal_plant, pi_freq_response, plant_freq_response,
                           plant_polys)


# --------------------------------------------------------------------------- utils
def _batch_roots(coeffs: np.ndarray) -> np.ndarray:
    """Roots of many polynomials (rows, descending, leading coeff non-zero)."""
    c = coeffs / coeffs[:, :1]
    n = c.shape[1] - 1
    M = np.zeros((c.shape[0], n, n))
    M[:, 0, :] = -c[:, 1:]
    if n > 1:
        M[:, np.arange(1, n), np.arange(0, n - 1)] = 1.0
    return np.linalg.eigvals(M)


def _strip_leading(coeffs: np.ndarray, tol: float = 1e-14) -> np.ndarray:
    scale = np.max(np.abs(coeffs), axis=1, keepdims=True)
    nz = np.abs(coeffs) > tol * scale
    first = int(np.min(np.argmax(nz, axis=1)))
    return coeffs[:, first:]


def _gain_polys(pl_unit: LinearPlant, Kp: np.ndarray, Ki: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """D (shared) and N rows (one per gain pair) for a unit-k plant."""
    D1, N1 = char_polys(pl_unit, 1.0, 0.0)        # N for Kp=1, Ki=0
    _, N2 = char_polys(pl_unit, 0.0, 1.0)         # N for Kp=0, Ki=1
    N = Kp[:, None] * N1[None, :] + Ki[:, None] * N2[None, :]
    return D1, N


def robust_stable_k_interval(pl_unit: LinearPlant, Kp: np.ndarray, Ki: np.ndarray,
                             kmin: float, kmax: float, tol_circle: float = 1e-5) -> np.ndarray:
    """Exact (zero-exclusion) robust stability over k in [kmin, kmax] for each gain pair."""
    Kp = np.atleast_1d(np.asarray(Kp, float))
    Ki = np.atleast_1d(np.asarray(Ki, float))
    D, N = _gain_polys(pl_unit, Kp, Ki)
    n = len(D)
    # (a) stability at kmin
    P = D[None, :] + kmin * N
    r = _batch_roots(_strip_leading(P))
    stable_at_kmin = np.max(np.abs(r), axis=1) < 1.0 - 1e-12
    # (b) no unit-circle crossing for k in [kmin, kmax]
    revD = D[::-1]
    revN = N[:, ::-1]
    ok = stable_at_kmin.copy()
    for i in np.nonzero(stable_at_kmin)[0]:
        F = np.polysub(np.polymul(D, revN[i]), np.polymul(revD, N[i]))
        F = np.trim_zeros(np.where(np.abs(F) > 1e-13 * np.max(np.abs(F)), F, 0.0), "f")
        if F.size < 2:
            continue
        zs = np.roots(F)
        zs = zs[np.abs(np.abs(zs) - 1.0) < tol_circle]
        if zs.size == 0:
            continue
        Dz = np.polyval(D, zs)
        Nz = np.polyval(N[i], zs)
        with np.errstate(divide="ignore", invalid="ignore"):
            kstar = -Dz / Nz
        real = np.abs(kstar.imag) <= 1e-6 * np.maximum(1.0, np.abs(kstar.real))
        hit = real & (kstar.real >= kmin * (1 - 1e-9)) & (kstar.real <= kmax * (1 + 1e-9))
        if np.any(hit):
            ok[i] = False
    # consistency: the other end of the segment must be stable as well
    ok_kmax = np.max(np.abs(_batch_roots(_strip_leading(D[None, :] + kmax * N))), axis=1) < 1.0 - 1e-12
    return ok & ok_kmax


@dataclass
class Certificate:
    Kp: np.ndarray            # (n,) log grid
    Ki: np.ndarray            # (m,)
    screened: np.ndarray      # (m, n) bool, Ki on rows
    nominal: np.ndarray
    robust_stable: np.ndarray
    certified: np.ndarray
    PM_worst: np.ndarray
    GM_worst: np.ndarray
    MM_worst: np.ndarray
    rho_nominal: np.ndarray
    meta: dict = field(default_factory=dict)

    def contains(self, Kp: float, Ki: float) -> bool:
        """Grid lookup (nearest node in log space). Use ``certify_point`` for exact checks."""
        i = int(np.argmin(np.abs(np.log(self.Ki) - math.log(Ki))))
        j = int(np.argmin(np.abs(np.log(self.Kp) - math.log(Kp))))
        return bool(self.certified[i, j])

    def save(self, path: str) -> None:
        np.savez_compressed(path, Kp=self.Kp, Ki=self.Ki, screened=self.screened, nominal=self.nominal,
                            robust_stable=self.robust_stable, certified=self.certified,
                            PM_worst=self.PM_worst, GM_worst=self.GM_worst, MM_worst=self.MM_worst,
                            rho_nominal=self.rho_nominal, meta=np.array([repr(self.meta)]))

    @staticmethod
    def load(path: str) -> "Certificate":
        z = np.load(path, allow_pickle=False)
        return Certificate(z["Kp"], z["Ki"], z["screened"], z["nominal"], z["robust_stable"], z["certified"],
                           z["PM_worst"], z["GM_worst"], z["MM_worst"], z["rho_nominal"],
                           {"repr": str(z["meta"][0])})


def uncertainty_nodes(cfg: Config, n_tau: int = 8, delay_step: float = 0.1) -> list[tuple[float, float]]:
    t0, t1 = cfg.plant.tau_i_range_s
    d0, d1 = cfg.converter.delay_range_samples
    taus = np.linspace(t0, t1, n_tau)
    ds = np.round(np.arange(d0, d1 + 1e-9, delay_step), 6)
    return [(float(t), float(d)) for t in taus for d in ds]


def margin_nodes(cfg: Config, n_tau: int = 4, n_delay: int = 5) -> list[tuple[float, float]]:
    t0, t1 = cfg.plant.tau_i_range_s
    d0, d1 = cfg.converter.delay_range_samples
    return [(float(t), float(d)) for t in np.linspace(t0, t1, n_tau) for d in np.linspace(d0, d1, n_delay)]


def worst_margins(cfg: Config, Kp: np.ndarray, Ki: np.ndarray, nodes: list[tuple[float, float]] | None = None,
                  k_values: tuple[float, ...] | None = None, n_w: int = 700) -> dict[str, np.ndarray]:
    Ts = cfg.converter.Ts
    kmin, kmax = k_interval(cfg)
    knom = k_from_context(cfg, 1.0, 1.0)
    ks = k_values or (kmin, knom, kmax)
    nodes = nodes or margin_nodes(cfg)
    w = default_w_grid(Ts, n_w)
    C = pi_freq_response(Kp, Ki, w, Ts)
    PM = np.full(len(Kp), np.inf)
    GM = np.full(len(Kp), np.inf)
    MM = np.full(len(Kp), np.inf)
    for tau, d in nodes:
        for k in ks:
            P = plant_freq_response(LinearPlant(k, tau, d, Ts), w)
            m = margins_from_loop(C * P[None, :], w)
            PM = np.minimum(PM, m["PM"])
            GM = np.minimum(GM, m["GM"])
            MM = np.minimum(MM, m["MM"])
    return {"PM": PM, "GM": GM, "MM": MM}


def robust_stable_all_nodes(cfg: Config, Kp: np.ndarray, Ki: np.ndarray,
                            nodes: list[tuple[float, float]] | None = None) -> np.ndarray:
    kmin, kmax = k_interval(cfg)
    ok = np.ones(len(Kp), bool)
    for tau, d in nodes or uncertainty_nodes(cfg):
        idx = np.nonzero(ok)[0]
        if idx.size == 0:
            break
        pl1 = LinearPlant(1.0, tau, d, cfg.converter.Ts)
        ok[idx] = robust_stable_k_interval(pl1, Kp[idx], Ki[idx], kmin, kmax)
    return ok


def certify_point(cfg: Config, Kp: float, Ki: float) -> dict:
    """Exact independent re-check of one gain pair (used by the runtime supervisor)."""
    Kp_a, Ki_a = np.array([Kp]), np.array([Ki])
    rs = bool(robust_stable_all_nodes(cfg, Kp_a, Ki_a)[0])
    m = worst_margins(cfg, Kp_a, Ki_a)
    c = cfg.constraints
    margins_ok = bool(m["PM"][0] >= c.PM_min_deg and m["GM"][0] >= c.GM_min_dB and m["MM"][0] >= c.MM_min)
    return {"robust_stable": rs, "margins_ok": margins_ok, "certified": rs and margins_ok,
            "PM_worst": float(m["PM"][0]), "GM_worst": float(m["GM"][0]), "MM_worst": float(m["MM"][0])}


def screen_monte_carlo(cfg: Config, Kp: np.ndarray, Ki: np.ndarray, n_samples: int = 200, seed: int = 0) -> np.ndarray:
    rng = np.random.default_rng(seed)
    p, c = cfg.plant, cfg.converter
    ok = np.ones(len(Kp), bool)
    for _ in range(n_samples):
        C_pu = rng.uniform(1 - p.C_tol, 1 + p.C_tol)
        vg = rng.uniform(*p.Vg_range)
        eta = p.eta_afe if rng.random() < 0.5 else 1 / p.eta_afe
        tau = rng.uniform(*p.tau_i_range_s)
        d = rng.uniform(*c.delay_range_samples)
        pl1 = LinearPlant(1.0, tau, d, c.Ts)
        k = k_from_context(cfg, C_pu, vg, eta)
        D, N = _gain_polys(pl1, Kp, Ki)
        r = _batch_roots(_strip_leading(D[None, :] + k * N))
        ok &= np.max(np.abs(r), axis=1) < 1.0
    return ok


def gain_grid(cfg: Config, n: int | None = None) -> tuple[np.ndarray, np.ndarray]:
    n = n or cfg.optimizer.n_grid
    Kp = np.logspace(math.log10(cfg.Kp_range[0]), math.log10(cfg.Kp_range[1]), n)
    Ki = np.logspace(math.log10(cfg.Ki_range[0]), math.log10(cfg.Ki_range[1]), n)
    return Kp, Ki


def compute_certificate(cfg: Config, n: int | None = None, mc_samples: int = 200, verbose: bool = False) -> Certificate:
    t0 = time.perf_counter()
    Kp, Ki = gain_grid(cfg, n)
    KP, KI = np.meshgrid(Kp, Ki)          # rows: Ki, cols: Kp
    kp, ki = KP.ravel(), KI.ravel()
    Ts = cfg.converter.Ts
    pn = nominal_plant(cfg)
    D, N = _gain_polys(LinearPlant(1.0, pn.tau_i, pn.delay, Ts), kp, ki)
    rho = np.max(np.abs(_batch_roots(_strip_leading(D[None, :] + pn.k * N))), axis=1)
    nominal = rho < 1.0
    screened = screen_monte_carlo(cfg, kp, ki, mc_samples)
    rs = robust_stable_all_nodes(cfg, kp, ki)
    m = worst_margins(cfg, kp, ki)
    c = cfg.constraints
    cert = rs & (m["PM"] >= c.PM_min_deg) & (m["GM"] >= c.GM_min_dB) & (m["MM"] >= c.MM_min)
    shp = KP.shape
    kmin, kmax = k_interval(cfg)
    meta = {"k_interval": (kmin, kmax), "k_nom": pn.k, "n_uncertainty_nodes": len(uncertainty_nodes(cfg)),
            "n_margin_nodes": len(margin_nodes(cfg)), "mc_samples": mc_samples,
            "seconds": time.perf_counter() - t0}
    if verbose:
        print(meta)
    return Certificate(Kp, Ki, screened.reshape(shp), nominal.reshape(shp), rs.reshape(shp), cert.reshape(shp),
                       m["PM"].reshape(shp), m["GM"].reshape(shp), m["MM"].reshape(shp), rho.reshape(shp), meta)


# --------------------------------------------------------------------------- tier 2
# Context-conditioned margin certificate.
#
# Tier 1 (above, GLOBAL):  robust stability for EVERY plant in U. A gain that
#   passes tier 1 cannot be destabilised by any context change inside U, so a
#   sudden grid sag or capacitance drift never makes the active loop unstable
#   while the supervisor is still reacting.
# Tier 2 (LOCAL): stability + PM/GM/MM requirements for the subset of U that is
#   consistent with the CURRENT context estimate and its error bounds
#   (config [context_estimation]). Tier 2 is what lets GainShield use higher
#   gains when, e.g., the grid is weak or C is high, while tier 1 keeps the
#   worst case stable.
@dataclass(frozen=True)
class LocalSet:
    kmin: float
    kmax: float
    tau_lo: float
    tau_hi: float
    d_lo: float
    d_hi: float

    def nodes(self) -> list[tuple[float, float]]:
        dm = 0.5 * (self.d_lo + self.d_hi)
        return [(t, d) for t in (self.tau_lo, self.tau_hi) for d in (self.d_lo, dm, self.d_hi)]


def local_uncertainty(cfg: Config, C_pu: float, vg_pu: float, tau_i_s: float, delay: float) -> LocalSet:
    e, p = cfg.ctx_err, cfg.plant
    kmin = k_from_context(cfg, C_pu * (1 + e.C_err), vg_pu * (1 - e.vg_err), p.eta_afe)
    kmax = k_from_context(cfg, C_pu * (1 - e.C_err), vg_pu * (1 + e.vg_err), 1.0 / p.eta_afe)
    return LocalSet(kmin, kmax, tau_i_s * (1 - e.tau_err), tau_i_s * (1 + e.tau_err),
                    max(0.0, delay - e.delay_err), delay + e.delay_err)


def local_certified(cfg: Config, Kp: np.ndarray, Ki: np.ndarray, ls: LocalSet) -> tuple[np.ndarray, dict]:
    """Tier-2 check for many gain pairs: local robust stability (proof) + local margins."""
    Kp = np.atleast_1d(np.asarray(Kp, float))
    Ki = np.atleast_1d(np.asarray(Ki, float))
    ok = np.ones(len(Kp), bool)
    for tau, d in ls.nodes():
        idx = np.nonzero(ok)[0]
        if idx.size == 0:
            break
        ok[idx] = robust_stable_k_interval(LinearPlant(1.0, tau, d, cfg.converter.Ts), Kp[idx], Ki[idx], ls.kmin, ls.kmax)
    m = worst_margins(cfg, Kp, Ki, nodes=ls.nodes(), k_values=(ls.kmin, 0.5 * (ls.kmin + ls.kmax), ls.kmax), n_w=600)
    c = cfg.constraints
    ok &= (m["PM"] >= c.PM_min_deg) & (m["GM"] >= c.GM_min_dB) & (m["MM"] >= c.MM_min)
    return ok, m


def certify_point_context(cfg: Config, Kp: float, Ki: float, ls: LocalSet) -> dict:
    """Exact two-tier re-check of one gain pair (runtime supervisor)."""
    t1 = bool(robust_stable_all_nodes(cfg, np.array([Kp]), np.array([Ki]))[0])
    ok2, m = local_certified(cfg, np.array([Kp]), np.array([Ki]), ls)
    return {"robust_stable": t1, "margins_ok": bool(ok2[0]), "certified": t1 and bool(ok2[0]),
            "PM_worst": float(m["PM"][0]), "GM_worst": float(m["GM"][0]), "MM_worst": float(m["MM"][0]),
            "tier": "global-stability + local-margins"}
