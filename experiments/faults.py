"""Fault-injection agents (simulation only - never connect to hardware)."""
from __future__ import annotations

import numpy as np
from dataclasses import replace

from gainshield.audit.logger import AuditRecord
from gainshield.controllers.pi import PIGains
from gainshield.core import GainShieldAgent, _ctx_dict
from gainshield.simulation import ContextEstimate, Measurement


class FaultInjectingAgent(GainShieldAgent):
    """GainShield agent with deliberately injected faults.

    gain_fault:   (t, PIGains) - gains forced into the PI BYPASSING the gate
                  (models a corrupted parameter write / optimizer software fault).
    sensor_fault: (t_start, t_end, kind, value) - kind 'offset' adds value [V]
                  to the voltage measurement, 'stuck' freezes it at value [V], 'stuck_noisy'
                  freezes the sensed quantity at value [V] but keeps 1 V rms ADC noise
                  (defeats a frozen-reading check; only the power-balance observer sees it).
    """

    def __init__(self, *a, gain_fault: tuple[float, PIGains] | None = None,
                 sensor_fault: tuple[float, float, str, float] | None = None, **kw) -> None:
        super().__init__(*a, **kw)
        self.gain_fault = gain_fault
        self.sensor_fault = sensor_fault
        self._gf_done = False
        self._rng = np.random.default_rng(123)

    def reset(self, ctx: ContextEstimate, u0: float, t0: float) -> None:
        super().reset(ctx, u0, t0)
        self._gf_done = False

    def control(self, m: Measurement, ctx: ContextEstimate) -> float:
        if self.sensor_fault and self.sensor_fault[0] <= m.t < self.sensor_fault[1]:
            _, _, kind, val = self.sensor_fault
            if kind == "offset":
                m = replace(m, v=m.v + val)
            elif kind == "stuck_noisy":
                m = replace(m, v=val + float(self._rng.normal(0.0, 1.0)))
            else:
                m = replace(m, v=val)
        if self.gain_fault and not self._gf_done and m.t >= self.gain_fault[0]:
            self._gf_done = True
            g: PIGains = self.gain_fault[1]
            prev = self.pi.gains
            self.pi.set_gains(g, bumpless=True)
            self.state = "ADAPTIVE"
            self.audit.log(AuditRecord(event="FAULT", t_sim_s=m.t, mode=ctx.mode, controller_state="ADAPTIVE",
                                       v_meas_V=m.v, i_meas_A=m.i, Kp_prev=prev.Kp, Ki_prev=prev.Ki,
                                       Kp_proposed=g.Kp, Ki_proposed=g.Ki, Kp_active=g.Kp, Ki_active=g.Ki,
                                       decision="INJECTED", reason="fault injection: gains written bypassing the gate",
                                       context=_ctx_dict(ctx)))
            # suppress context-triggered re-decisions so the fault persists until the monitor acts
            self.ctx_active = ctx
        return super().control(m, ctx)

    def _changed(self, ctx: ContextEstimate) -> bool:
        if self.gain_fault and self._gf_done and self.state == "ADAPTIVE":
            return False
        return super()._changed(ctx)
