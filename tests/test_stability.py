import numpy as np
import pytest

from gainshield.controllers.baseline import baseline_gains
from gainshield.controllers.pi import PIGains
from gainshield.disturbances.scenarios import Event, Scenario
from gainshield.plant.charger import PlantVariation
from gainshield.simulation import FixedPIAgent, simulate
from gainshield.stability.certify import (certify_point, local_certified, local_uncertainty,
                                          robust_stable_k_interval)
from gainshield.stability.linear_model import LinearPlant, k_interval, nominal_plant, spectral_radius


def test_zero_exclusion_matches_brute_force(cfg):
    rng = np.random.default_rng(0)
    Kp = np.exp(rng.uniform(np.log(0.2), np.log(12), 120))
    Ki = np.exp(rng.uniform(np.log(5), np.log(5000), 120))
    kmin, kmax = k_interval(cfg)
    for tau, d in [(0.3e-3, 1.0), (1e-3, 2.0)]:
        ze = robust_stable_k_interval(LinearPlant(1.0, tau, d, cfg.converter.Ts), Kp, Ki, kmin, kmax)
        bf = np.ones(len(Kp), bool)
        for k in np.linspace(kmin, kmax, 150):
            pl = LinearPlant(k, tau, d, cfg.converter.Ts)
            bf &= np.array([spectral_radius(pl, a, b) < 1 for a, b in zip(Kp, Ki)])
        assert np.array_equal(ze, bf)


def test_linear_model_predicts_nonlinear_instability(cfg):
    g = baseline_gains(cfg)
    pl = nominal_plant(cfg)
    ms = np.arange(1, 20, 0.05)
    m = ms[np.argmax([spectral_radius(pl, g.Kp * x, g.Ki * x) >= 1 for x in ms])]
    sc = Scenario("t", "", 0.12, 10e3, events=(Event(0.01, "vref", 801.0),), noise_scale=0.0)
    def decays(f):
        df = simulate(cfg, sc, FixedPIAgent(cfg, PIGains(g.Kp * m * f, g.Ki * m * f))).df
        e = (df.v - df.v_ref).abs().to_numpy()
        return e[1000:].max() < e[300:700].max()
    assert decays(0.97) and not decays(1.03)


def test_baseline_is_certified_and_unstable_gains_are_not(cfg):
    g = baseline_gains(cfg)
    assert certify_point(cfg, g.Kp, g.Ki)["certified"]
    bad = certify_point(cfg, 0.3, 1500.0)
    assert not bad["robust_stable"] and not bad["certified"]


def test_context_certificate_wider_than_global(cfg):
    """A weak grid / larger C admits gains the global certificate refuses."""
    ok_global = certify_point(cfg, 3.0, 300.0)["certified"]
    ls = local_uncertainty(cfg, 1.0, 0.8, cfg.plant.tau_i_nom_s, 1.5)
    ok_local, _ = local_certified(cfg, np.array([3.0]), np.array([300.0]), ls)
    assert not ok_global and ok_local[0]


def test_certificate_regions_nested(cert):
    assert not np.any(cert.certified & ~cert.robust_stable)
    assert not np.any(cert.robust_stable & ~cert.nominal)
    assert not np.any(cert.robust_stable & ~cert.screened)
