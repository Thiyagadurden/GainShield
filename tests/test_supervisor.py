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
