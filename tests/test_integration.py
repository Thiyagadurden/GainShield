"""End-to-end: tuning session, deployment and fault rollback (coarse certificate for speed)."""
import numpy as np

from faults import FaultInjectingAgent
from gainshield.audit.logger import AuditLogger, verify_gain_trace
from gainshield.controllers.pi import PIGains
from gainshield.core import GainShield, default_training_contexts
from gainshield.disturbances.scenarios import Event, Scenario, scenario_by_name
from gainshield.simulation import simulate


def test_tuning_deploy_and_fault(cfg, cert):
    audit = AuditLogger(run_id="it")
    gs = GainShield(cfg, cert, audit=audit)
    hist = gs.tune_context(default_training_contexts()[0], n_iters=4, seed=1)
    acc = [h for h in hist if h["accepted"]]
    assert len(acc) >= 3
    assert all(h["true_v_viol"] == 0 for h in acc)
    assert all(h["aborted"] == 0 for h in acc)
    r = simulate(cfg, scenario_by_name("load_increase"), gs.agent(), seed=0)
    assert (r.df.v - 800).abs().max() < 40
    # unstable gains written behind the gate's back -> monitor + rollback
    sc = Scenario("s", "", 0.25, 10e3, events=(Event(0.05, "p_load", 10e3),))
    ag = FaultInjectingAgent(cfg, gs, gain_fault=(0.06, PIGains(0.3, 1500.0)))
    r = simulate(cfg, sc, ag, seed=0)
    assert ag.rollbacks >= 1
    assert abs(r.df.v.iloc[-1] - 800) < 5
    assert (r.df.v - 800).abs().max() < 0.10 * 800
    assert verify_gain_trace(audit.records) == []
