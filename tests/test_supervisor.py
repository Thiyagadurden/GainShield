import math

from gainshield.controllers.baseline import baseline_gains
from gainshield.controllers.pi import PIGains
from gainshield.optimizer.safe_bo import Proposal
from gainshield.safety.supervisor import CandidateGate, RuntimeMonitor
from gainshield.simulation import ContextEstimate


def _p(g, sd=0.05, lcb=0.5):
    return Proposal(g, "t", 1.0, 0.1, lcb, lcb, sd, sd, 1, 1)


def _ctx(cfg, C=1.0):
    return ContextEstimate(C, cfg.plant.tau_i_nom_s, 1.5, 1.0, 10e3)


def test_gate_rejects_and_accepts(cfg):
    gate = CandidateGate(cfg)
    b = baseline_gains(cfg)
    assert not gate.evaluate(_p(PIGains(0.3, 1500.0)), _ctx(cfg), b, b).accept
    assert not gate.evaluate(_p(PIGains(1.5, 180.0), sd=0.5), _ctx(cfg), b, b).accept
    assert not gate.evaluate(_p(PIGains(1.5, 180.0), lcb=0.0), _ctx(cfg), b, b).accept
    assert not gate.evaluate(_p(PIGains(1.5, 180.0)), _ctx(cfg, C=0.5), b, b).accept
    assert gate.evaluate(_p(PIGains(1.5, 180.0)), _ctx(cfg), b, b).accept
    assert gate.evaluate(_p(b), _ctx(cfg), b, b).accept


def test_monitor_voltage_abort(cfg):
    m = RuntimeMonitor(cfg)
    assert m.check(10.0, 790.0, 10.0) is None
    ev = m.check(40.0, 760.0, 10.0)
    assert ev is not None and ev.kind in ("V_ABORT", "SENSOR_FAULT")


def test_monitor_sensor_fault(cfg):
    m = RuntimeMonitor(cfg)
    m.check(0.0, 800.0, 0.0)
    assert m.check(0.0, 870.0, 0.0).kind == "SENSOR_FAULT"


def test_monitor_detects_sustained_oscillation(cfg):
    m = RuntimeMonitor(cfg)
    ev = None
    for k in range(4000):
        e = 15.0 * math.sin(2 * math.pi * 150 * k * cfg.converter.Ts)
        ev = ev or m.check(e, 800 - e, 0.0)
    assert ev is not None and ev.kind == "OSCILLATION"


def test_monitor_disabled(cfg):
    m = RuntimeMonitor(cfg, enabled=False)
    assert m.check(100.0, 700.0, 100.0) is None


# ---- sensor plausibility (closes failure case R5) -------------------------------------------
def _plant_run(cfg, sensor, n=3000, step_k=1500):
    """Closed loop with the baseline PI on the real plant model; ``sensor(k, v_true, rng)`` gives the
    voltage reading. Returns the monitor and the true voltage at the end."""
    import numpy as np
    from gainshield.controllers.pi import PIController
    from gainshield.plant.charger import ChargerPlant
    rng = np.random.default_rng(0)
    plant = ChargerPlant(cfg)
    plant.reset(800.0, 10e3)
    pi = PIController(baseline_gains(cfg), cfg.converter.Ts, -80.0, 80.0)
    pi.reset(float(plant.x[1]))
    mon = RuntimeMonitor(cfg)
    first = None
    for k in range(n):
        if k == step_k:
            plant.set_load_demand(20e3)
        v_meas = sensor(k, plant.x[0], rng)
        i_meas = plant.x[1] + rng.normal(0, 0.5)
        ev = mon.check(800.0 - v_meas, v_meas, i_meas, plant.p_dem, 1.0, 1.0)
        first = first or ev
        v_fb = mon.v_hat if mon.sensor_failed else v_meas
        plant.step(pi.update(800.0, v_fb))
    return mon, first, plant.x[0]


def test_healthy_sensor_raises_no_sensor_alarm(cfg):
    mon, ev, v = _plant_run(cfg, lambda k, v, rng: v + rng.normal(0, 3.0))   # 3x A-14 noise
    assert ev is None and not mon.sensor_failed
    assert mon.max_abs_residual < 0.5 * cfg.supervisor.residual_threshold_V


def test_frozen_sensor_detected_and_virtual_sensor_holds_voltage(cfg):
    mon, ev, v = _plant_run(cfg, lambda k, v, rng: v + rng.normal(0, 1.0) if k < 1000 else 800.0)
    assert ev is not None and ev.kind == "SENSOR_STUCK"
    assert abs(v - 800.0) < 0.04 * 800.0       # load step after the fault: no collapse


def test_noisy_stuck_sensor_caught_by_power_balance(cfg):
    mon, ev, v = _plant_run(cfg, lambda k, v, rng: v + rng.normal(0, 1.0) if k < 1000 else 800.0 + rng.normal(0, 1.0))
    assert ev is not None and ev.kind == "POWER_BALANCE"
    assert abs(v - 800.0) < 0.04 * 800.0


def test_sensor_fault_latch_survives_detector_reset(cfg):
    mon, ev, v = _plant_run(cfg, lambda k, v, rng: 800.0 if k >= 1000 else v + rng.normal(0, 1.0), n=1100)
    assert mon.sensor_failed
    mon.reset_detectors()
    assert mon.sensor_failed
