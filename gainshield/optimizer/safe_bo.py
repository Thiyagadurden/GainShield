"""Contextual safe Bayesian optimisation of PI gains (SafeOpt-style).

Algorithm per iteration, for the current operating context z:

1. Candidate set X_c: log-spaced (Kp, Ki) grid restricted to the CERTIFIED
   region (Layer C), plus the baseline gains (the safe seed).
2. Three GPs over (gains, context): cost J, voltage margin m_v, current margin m_i.
3. Safe set   S = {x in X_c : mu_m(x,z) - beta*sd_m(x,z) >= h for m in (m_v, m_i)}
                 U {baseline}.
4. Maximisers M = {x in S : LCB_J(x) <= min_{x' in S} UCB_J(x')}.
   Expanders  G = {x in S : exists x' not in S with
                    UCB_m(x) - L * ||x - x'|| >= h for all margins}
   (Lipschitz form of Sui et al., ICML 2015; L estimated from the GP mean).
5. Proposal  x_next = argmax_{x in M u G} max(width_J/std_J, width_v, width_i).
6. After the episode, (x, z, J, m_v, m_i) is appended and the GPs refitted.

Recommendation for deployment at context z: argmin_{x in S} UCB_J(x, z)
(pessimistic in cost, safe in margins).

What this is NOT: the theoretical SafeOpt guarantee needs a known RKHS-norm
bound on the margin functions and a matching (larger) beta; neither is
verified here. GP safety predictions are therefore only ONE layer; the
certificate (Layer C) and the independent runtime monitor (Layer E) do not
rely on the GP.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import math

import numpy as np

from ..config import Config
from ..controllers.pi import PIGains
from ..stability.certify import Certificate
from .gp import GPModel


@dataclass
class BOFlags:
    """Switches used by the ablation study. Defaults = complete GainShield."""

    use_certified_region: bool = True
    use_uncertainty: bool = True
    use_context: bool = True


@dataclass
class Proposal:
    gains: PIGains
    kind: str                 # seed | init | maximizer | expander | recommend
    mu_J: float
    sd_J: float
    lcb_v: float
    lcb_i: float
    sd_v: float
    sd_i: float
    safe_set_size: int
    candidates: int
    extra: dict = field(default_factory=dict)


class SafeBayesOpt:
    def __init__(self, cfg: Config, certificate: Certificate, baseline: PIGains,
                 flags: BOFlags | None = None, seed: int | None = None) -> None:
        self.cfg = cfg
        self.cert = certificate
        self.baseline = baseline
        self.flags = flags or BOFlags()
        op = cfg.optimizer
        self.beta = op.beta if self.flags.use_uncertainty else 0.0
        self.h = op.safety_margin_min
        self.rng = np.random.default_rng(op.seed if seed is None else seed)
        self._lkp = (math.log(cfg.Kp_range[0]), math.log(cfg.Kp_range[1]))
        self._lki = (math.log(cfg.Ki_range[0]), math.log(cfg.Ki_range[1]))
        KP, KI = np.meshgrid(certificate.Kp, certificate.Ki)
        # candidate set = TIER-1 region (globally robustly stable); the context-dependent
        # tier-2 mask is applied per query via the ``mask`` argument.
        mask = certificate.robust_stable if self.flags.use_certified_region else np.ones_like(certificate.robust_stable)
        gk = np.c_[KP[mask], KI[mask]]
        self.cand_gains = np.vstack([gk, [baseline.Kp, baseline.Ki]])
        self.seed_index = len(self.cand_gains) - 1
        self.cand_u = self.encode_gains(self.cand_gains)
        gc = np.c_[KP[certificate.certified], KI[certificate.certified]]
        # globally certified subset (margins over the whole U) - used when context is unknown
        self.global_cert_mask = np.array([bool(np.any(np.all(np.isclose(gc, g), axis=1))) for g in self.cand_gains])
        self.global_cert_mask[self.seed_index] = True
        nd = 2 + 5
        # Cost GP: hyper-parameters fitted (bounded). Margin GPs: FIXED, a-priori
        # hyper-parameters (as assumed by SafeOpt) - short gain length-scales keep
        # the safe set expanding locally from the seed instead of extrapolating.
        ls_cost = np.array([0.2, 0.2, 0.3, 0.3, 0.3, 0.3, 0.3])
        ls_safe = np.array([0.15, 0.15, 0.6, 0.6, 0.6, 0.6, 0.6])
        self.gp_J = GPModel(nd, prior_mean=None, amplitude=0.5, ls_init=ls_cost, fixed_amplitude=False,
                            ls_bounds=(0.05, 1.0), seed=1)
        self.gp_v = GPModel(nd, prior_mean=0.0, amplitude=0.6, ls_init=ls_safe, noise=1e-3, optimize=False, seed=2)
        self.gp_i = GPModel(nd, prior_mean=0.0, amplitude=0.6, ls_init=ls_safe, noise=1e-3, optimize=False, seed=3)
        self.X: list[np.ndarray] = []
        self.yJ: list[float] = []
        self.yv: list[float] = []
        self.yi: list[float] = []
        self.history: list[dict] = []
        self.excluded = np.zeros(len(self.cand_gains), bool)

    def exclude(self, gains: PIGains) -> None:
        """Remove a candidate the supervisor rejected (avoids re-proposing it)."""
        d = np.abs(self.cand_gains[:, 0] - gains.Kp) + np.abs(self.cand_gains[:, 1] - gains.Ki)
        j = int(np.argmin(d))
        if j != self.seed_index:
            self.excluded[j] = True

    # ----------------------------------------------------------- encodings
    def encode_gains(self, g: np.ndarray) -> np.ndarray:
        g = np.atleast_2d(g)
        u1 = (np.log(g[:, 0]) - self._lkp[0]) / (self._lkp[1] - self._lkp[0])
        u2 = (np.log(g[:, 1]) - self._lki[0]) / (self._lki[1] - self._lki[0])
        return np.c_[u1, u2]

    def encode_context(self, z: np.ndarray) -> np.ndarray:
        z = np.asarray(z, float)
        if not self.flags.use_context:
            return np.ones_like(z)
        return z

    def _inputs(self, U: np.ndarray, z: np.ndarray) -> np.ndarray:
        zc = self.encode_context(z)
        return np.c_[U, np.repeat(zc[None, :], len(U), axis=0)]

    # ------------------------------------------------------------ data
    def add_observation(self, gains: PIGains, z: np.ndarray, J: float, m_v: float, m_i: float) -> None:
        u = self.encode_gains(np.array([[gains.Kp, gains.Ki]]))[0]
        self.X.append(np.r_[u, self.encode_context(z)])
        self.yJ.append(float(J))
        self.yv.append(float(np.clip(m_v, -1.0, 1.0)))
        self.yi.append(float(np.clip(m_i, -1.0, 1.0)))
        X = np.array(self.X)
        self.gp_J.fit(X, np.array(self.yJ))
        self.gp_v.fit(X, np.array(self.yv))
        self.gp_i.fit(X, np.array(self.yi))

    @property
    def n_obs(self) -> int:
        return len(self.X)

    # ------------------------------------------------------------ prediction
    def predict(self, z: np.ndarray, gains: np.ndarray | None = None) -> dict[str, np.ndarray]:
        G = self.cand_gains if gains is None else np.atleast_2d(gains)
        Xq = self._inputs(self.encode_gains(G), z)
        muJ, sdJ = self.gp_J.predict(Xq)
        muv, sdv = self.gp_v.predict(Xq)
        mui, sdi = self.gp_i.predict(Xq)
        return {"muJ": muJ, "sdJ": sdJ, "muv": muv, "sdv": sdv, "mui": mui, "sdi": sdi}

    def safe_mask(self, P: dict[str, np.ndarray], mask: np.ndarray | None = None) -> np.ndarray:
        b = self.beta
        S = (P["muv"] - b * P["sdv"] >= self.h) & (P["mui"] - b * P["sdi"] >= self.h)
        S = S.copy()
        if mask is not None:
            S &= mask
        S[self.seed_index] = True   # baseline is the certified safe seed
        return S

    # ------------------------------------------------------------ acquisition
    def _lipschitz(self, P: dict[str, np.ndarray]) -> float:
        """Crude Lipschitz estimate of the margin GP mean on the candidate set."""
        U = self.cand_u
        if len(U) < 3:
            return 1.0
        mu = np.minimum(P["muv"], P["mui"])
        idx = self.rng.choice(len(U), size=min(len(U), 300), replace=False)
        Us, ms = U[idx], mu[idx]
        d = np.linalg.norm(Us[:, None, :] - Us[None, :, :], axis=-1)
        dm = np.abs(ms[:, None] - ms[None, :])
        with np.errstate(divide="ignore", invalid="ignore"):
            r = np.where(d > 1e-9, dm / d, 0.0)
        return float(max(np.max(r), 0.5))

    def propose(self, z: np.ndarray, mask: np.ndarray | None = None) -> Proposal:
        P = self.predict(z)
        S = self.safe_mask(P, mask)
        b = self.beta if self.beta > 0 else 2.0   # exploration still uses confidence widths
        lcbJ = P["muJ"] - b * P["sdJ"]
        ucbJ = P["muJ"] + b * P["sdJ"]
        best_ucb = np.min(ucbJ[S])
        M = S & (lcbJ <= best_ucb)
        # expanders
        G = np.zeros_like(S)
        unsafe = ~S
        if mask is not None:
            unsafe &= mask   # only expand towards points that are allowed in this context
        if unsafe.any():
            L = self._lipschitz(P)
            ucb_m = np.minimum(P["muv"] + b * P["sdv"], P["mui"] + b * P["sdi"])
            Uu = self.cand_u[unsafe]
            for j in np.nonzero(S)[0]:
                d = np.min(np.linalg.norm(Uu - self.cand_u[j], axis=1))
                G[j] = ucb_m[j] - L * d >= self.h
        cand = (M | G) & ~self.excluded
        if not cand.any():
            cand = np.zeros_like(S)
            cand[self.seed_index] = True
        sJ = np.std(self.yJ) if len(self.yJ) > 1 else 1.0
        width = np.maximum.reduce([2 * b * P["sdJ"] / max(sJ, 1e-6), 2 * b * P["sdv"], 2 * b * P["sdi"]])
        width = np.where(cand, width, -np.inf)
        j = int(np.argmax(width))
        kind = "maximizer" if M[j] else "expander"
        return self._proposal(j, P, kind, int(S.sum()), extra={"n_M": int(M.sum()), "n_G": int(G.sum())})

    def recommend(self, z: np.ndarray, mask: np.ndarray | None = None, min_obs: int = 1) -> Proposal:
        """Gains to deploy at context z (pessimistic cost, safe margins)."""
        P = self.predict(z)
        S = self.safe_mask(P, mask)
        if self.n_obs < min_obs:
            return self._proposal(self.seed_index, P, "seed", int(S.sum()))
        b = self.beta if self.beta > 0 else 0.0
        ucbJ = np.where(S, P["muJ"] + b * P["sdJ"], np.inf)
        j = int(np.argmin(ucbJ))
        return self._proposal(j, P, "recommend", int(S.sum()))

    def initial_design(self, n: int) -> list[PIGains]:
        """Baseline + small log-space perturbations that are inside the candidate set."""
        out = [self.baseline]
        ub = self.encode_gains(np.array([[self.baseline.Kp, self.baseline.Ki]]))[0]
        d = np.linalg.norm(self.cand_u - ub, axis=1)
        d[~self.global_cert_mask] = np.inf
        near = np.argsort(d)[1: 1 + 12]
        if n > 1 and near.size:
            pick = self.rng.choice(near, size=min(n - 1, near.size), replace=False)
            out += [PIGains(*self.cand_gains[k]) for k in pick]
        return out

    def _proposal(self, j: int, P: dict[str, np.ndarray], kind: str, nS: int, extra: dict | None = None) -> Proposal:
        b = self.beta
        return Proposal(
            gains=PIGains(float(self.cand_gains[j, 0]), float(self.cand_gains[j, 1])), kind=kind,
            mu_J=float(P["muJ"][j]), sd_J=float(P["sdJ"][j]),
            lcb_v=float(P["muv"][j] - b * P["sdv"][j]), lcb_i=float(P["mui"][j] - b * P["sdi"][j]),
            sd_v=float(P["sdv"][j]), sd_i=float(P["sdi"][j]), safe_set_size=nS,
            candidates=len(self.cand_gains), extra=extra or {},
        )
