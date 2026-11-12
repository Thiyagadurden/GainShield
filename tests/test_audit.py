import json

import pytest

from gainshield.audit.logger import AuditLogger, AuditRecord, verify_gain_trace


def test_jsonl_roundtrip_and_schema(tmp_path):
    p = tmp_path / "a.jsonl"
    log = AuditLogger(p, run_id="t")
    log.log(AuditRecord("SESSION_START", Kp_active=1.0, Ki_active=10.0))
    log.log(AuditRecord("GAIN_APPLIED", t_sim_s=0.1, Kp_prev=1.0, Ki_prev=10.0, Kp_proposed=2.0, Ki_proposed=20.0,
                        Kp_active=2.0, Ki_active=20.0, decision="ACCEPT", reason="test"))
    log.log(AuditRecord("ROLLBACK", t_sim_s=0.2, Kp_prev=2.0, Ki_prev=20.0, Kp_active=1.0, Ki_active=10.0,
                        rollback=True, reason="monitor"))
    recs = AuditLogger.read(p)
    assert [r["seq"] for r in recs] == [0, 1, 2]
    for k in ("t_sim_s", "mode", "v_meas_V", "i_meas_A", "Kp_prev", "Kp_proposed", "Kp_active",
              "gp_sigma_margin", "margin_v_lcb", "decision", "rollback", "reason"):
        assert k in recs[1]
    assert verify_gain_trace(recs) == []
    json.dumps(recs)


def test_trace_detects_unexplained_change():
    recs = [{"seq": 0, "event": "GAIN_APPLIED", "Kp_prev": 1.0, "Ki_prev": 1.0, "Kp_active": 2.0, "Ki_active": 2.0},
            {"seq": 1, "event": "GAIN_APPLIED", "Kp_prev": 3.0, "Ki_prev": 3.0, "Kp_active": 4.0, "Ki_active": 4.0}]
    assert verify_gain_trace(recs)


def test_unknown_event_rejected():
    with pytest.raises(ValueError):
        AuditRecord("NOPE")
