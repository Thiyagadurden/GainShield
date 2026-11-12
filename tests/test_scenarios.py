import numpy as np

from gainshield.controllers.baseline import baseline_gains
from gainshield.disturbances.scenarios import scenario_by_name, standard_suite
from gainshield.simulation import FixedPIAgent, simulate


def test_suite_covers_required_classes():
    names = {s.name for s in standard_suite()}
    for n in ["load_increase", "load_decrease", "g2v_to_v2g", "v2g_to_g2v", "grid_sag", "sensor_noise",
              "cap_minus20", "cap_plus20", "inner_lag_slow", "delay_long", "combined"]:
        assert n in names


def test_reproducible_with_seed(cfg):
    sc = scenario_by_name("sensor_noise")
    a = simulate(cfg, sc, FixedPIAgent(cfg, baseline_gains(cfg)), seed=3).df
    b = simulate(cfg, sc, FixedPIAgent(cfg, baseline_gains(cfg)), seed=3).df
    c = simulate(cfg, sc, FixedPIAgent(cfg, baseline_gains(cfg)), seed=4).df
    assert np.array_equal(a.v.to_numpy(), b.v.to_numpy())
    assert not np.array_equal(a.v.to_numpy(), c.v.to_numpy())


def test_baseline_regulates_every_scenario(cfg):
    g = baseline_gains(cfg)
    for sc in standard_suite():
        df = simulate(cfg, sc, FixedPIAgent(cfg, g), seed=0).df
        assert abs(df.v.iloc[-200:].mean() - 800.0) < 2.0, sc.name
        assert (df.v - 800).abs().max() < 0.05 * 800, sc.name
