"""Gaussian-process surrogate (thin wrapper over scikit-learn).

Kernel: s^2 * Matern(nu=2.5, ARD) + white noise. Hyper-parameters are fitted by
maximum marginal likelihood with bounded length-scales.

``prior_mean`` matters for safety: margin GPs use a ZERO prior mean on the
raw (un-normalised) margin, so an unexplored gain has mean 0 and a lower
confidence bound below the safety threshold -> it is NOT considered safe until
data nearby supports it. This is the mechanism that makes the safe set grow
outward from the known-safe baseline (as in SafeOpt).
"""
from __future__ import annotations

import warnings

import numpy as np
from sklearn.exceptions import ConvergenceWarning
from sklearn.gaussian_process import GaussianProcessRegressor
from sklearn.gaussian_process.kernels import ConstantKernel, Matern, WhiteKernel


class GPModel:
    def __init__(self, n_dims: int, prior_mean: float | None = 0.0, amplitude: float = 0.5,
                 ls_bounds: tuple[float, float] = (0.05, 5.0), noise: float = 1e-3, seed: int = 0,
                 ls_init: np.ndarray | None = None, fixed_amplitude: bool = True,
                 optimize: bool = True) -> None:
        self.n_dims = n_dims
        self.prior_mean = prior_mean
        ls0 = np.full(n_dims, 0.5) if ls_init is None else np.asarray(ls_init, float)
        amp_bounds = "fixed" if fixed_amplitude else (1e-3, 1e2)
        self.kernel = (ConstantKernel(amplitude ** 2, amp_bounds) * Matern(ls0, (ls_bounds,) * n_dims if n_dims > 1 else ls_bounds, nu=2.5)
                       + WhiteKernel(noise, (1e-6, 1e-1)))
        self.seed = seed
        self.optimize = optimize
        self.gp: GaussianProcessRegressor | None = None
        self._mean = 0.0

    def fit(self, X: np.ndarray, y: np.ndarray) -> "GPModel":
        X = np.asarray(X, float)
        y = np.asarray(y, float)
        if X.ndim != 2 or X.shape[1] != self.n_dims or len(X) != len(y):
            raise ValueError("bad GP training data shape")
        self._mean = float(np.mean(y)) if self.prior_mean is None else float(self.prior_mean)
        self.gp = GaussianProcessRegressor(self.kernel, normalize_y=False,
                                           n_restarts_optimizer=1 if self.optimize else 0,
                                           optimizer="fmin_l_bfgs_b" if self.optimize else None,
                                           random_state=self.seed)
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", ConvergenceWarning)
            self.gp.fit(X, y - self._mean)
        self.kernel = self.gp.kernel_   # warm start next fit
        return self

    def predict(self, X: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        X = np.atleast_2d(np.asarray(X, float))
        if self.gp is None:
            amp = float(np.sqrt(self.kernel.k1.k1.constant_value))
            return np.full(len(X), self._mean), np.full(len(X), amp)
        mu, sd = self.gp.predict(X, return_std=True)
        return mu + self._mean, sd

    @property
    def fitted_kernel(self) -> str:
        return str(self.kernel)
