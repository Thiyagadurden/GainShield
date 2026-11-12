import pytest

from gainshield.controllers.baseline import baseline_gains, symmetric_optimum
from gainshield.controllers.pi import PIController, PIGains


def test_gains_validation():
    with pytest.raises(ValueError):
        PIGains(-1.0, 1.0)


def test_anti_windup_limits_integrator():
    pi = PIController(PIGains(1.0, 1000.0), 1e-4, -10.0, 10.0)
    for _ in range(10000):
        u = pi.update(100.0, 0.0)
    assert u == 10.0 and pi.saturated
    assert pi.x_i <= 10.0
    # recovers immediately when the error reverses (no wind-up delay)
    u = pi.update(-5.0, 0.0)
    assert u < 10.0


def test_bumpless_transfer_output_continuous():
    pi = PIController(PIGains(1.0, 100.0), 1e-4, -80.0, 80.0)
    for _ in range(50):
        pi.update(810.0, 800.0)
    u_before = pi.u_prev
    pi.set_gains(PIGains(3.0, 400.0), bumpless=True)
    u_after = pi.update(810.0, 800.0)
    # change in output is only the new integral increment
    assert abs(u_after - u_before) <= 400.0 * 1e-4 * 10.0 + 1e-9


def test_non_bumpless_jumps():
    pi = PIController(PIGains(1.0, 100.0), 1e-4, -80.0, 80.0)
    for _ in range(50):
        pi.update(810.0, 800.0)
    u_before = pi.u_prev
    pi.set_gains(PIGains(3.0, 400.0), bumpless=False)
    assert abs(pi.update(810.0, 800.0) - u_before) > 15.0


def test_symmetric_optimum_scaling(cfg):
    g = baseline_gains(cfg)
    g2 = symmetric_optimum(cfg, C_pu=2.0)
    assert g2.Kp == pytest.approx(2 * g.Kp)
    assert g2.Ki == pytest.approx(2 * g.Ki)
