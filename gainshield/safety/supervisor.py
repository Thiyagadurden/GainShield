"""Independent runtime safety supervisor (Layer E).

Two parts, deliberately independent of the optimizer's internal decisions:

``CandidateGate``   decides whether proposed gains may be applied. It
                    RE-COMPUTES the stability certificate for the exact gain
                    pair (it does not trust the optimizer's grid), checks GP
                    confidence, the operating-context envelope and a gain
                    step limit.

``RuntimeMonitor``  watches measured signals every control period and
                    requests a rollback to the baseline when the voltage
                    leaves the abort band, the current stays near its limit,
                    a sustained oscillation is detected, or a sensor reading
                    is physically implausible.

Neither part claims safety outside the modelled uncertainty set: the context
envelope check exists precisely to refuse adaptation when the plant is
believed to be outside the set the certificate covers.
"""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
import math

from ..config import Config
from ..controllers.pi import PIGains
from ..optimizer.safe_bo import Proposal
from ..simulation import ContextEstimate
from ..stability.certify import certify_point, certify_point_context, local_uncertainty


@dataclass
class GateFlags:
    check_certificate: bool = True
    check_uncertainty: bool = True
    check_context: bool = True
    context_certificate: bool = True   # tier-2 (context-conditioned) vs global margins only


@dataclass
class Decision:
    accept: bool
    reasons: list[str] = field(default_factory=list)
    checks: dict = field(default_factory=dict)

    @property
    def reason(self) -> str:
        return "; ".join(self.reasons) if self.reasons else "all checks passed"


class CandidateGate:
    def __init__(self, cfg: Config, flags: GateFlags | None = None, max_step_factor: float = 3.0) -> None:
        self.cfg = cfg
        self.flags = flags or GateFlags()
        self.max_step = math.log(max_step_factor)
        self._cache: dict[tuple[float, float], dict] = {}

    def certificate(self, g: PIGains, ctx: ContextEstimate | None = None) -> dict:
        if self.flags.context_certificate and ctx is not None:
            key = (round(g.Kp, 9), round(g.Ki, 9), round(ctx.C_pu, 3), round(ctx.vg_pu, 3),
                   round(ctx.tau_i_s, 6), round(ctx.delay_samples, 3))
            if key not in self._cache:
                ls = local_uncertainty(self.cfg, ctx.C_pu, ctx.vg_pu, ctx.tau_i_s, ctx.delay_samples)
                self._cache[key] = certify_point_context(self.cfg, g.Kp, g.Ki, ls)
            return self._cache[key]
        key = (round(g.Kp, 9), round(g.Ki, 9))
        if key not in self._cache:
            self._cache[key] = certify_point(self.cfg, g.Kp, g.Ki)
        return self._cache[key]

    def context_ok(self, ctx: ContextEstimate) -> tuple[bool, str]:
        env = self.cfg.supervisor.context_envelope
        vals = {"C_pu": ctx.C_pu, "Vg_pu": ctx.vg_pu, "tau_i_ms": 1e3 * ctx.tau_i_s, "delay_samples": ctx.delay_samples}
        bad = [f"{k}={v:.3g} outside {env[k]}" for k, v in vals.items() if k in env and not (env[k][0] <= v <= env[k][1])]
        if abs(ctx.p_load_W) > self.cfg.converter.P_dcdc_max_W:
            bad.append("load power beyond rating")
        return (not bad), "; ".join(bad)

    def evaluate(self, p: Proposal, ctx: ContextEstimate, active: PIGains, baseline: PIGains) -> Decision:
        reasons: list[str] = []
        checks: dict = {}
        g = p.gains
        is_baseline = math.isclose(g.Kp, baseline.Kp) and math.isclose(g.Ki, baseline.Ki)
        if self.flags.check_certificate and not is_baseline:
            c = self.certificate(g, ctx)
            checks["certificate"] = c
            if not c["certified"]:
                reasons.append(f"not certified (robust_stable={c['robust_stable']}, PM={c['PM_worst']:.1f} deg, "
                               f"GM={c['GM_worst']:.1f} dB, MM={c['MM_worst']:.2f})")
        if self.flags.check_uncertainty and not is_baseline:
            op = self.cfg.optimizer
            checks["gp"] = {"lcb_v": p.lcb_v, "lcb_i": p.lcb_i, "sd_v": p.sd_v, "sd_i": p.sd_i}
            if max(p.sd_v, p.sd_i) > op.sigma_max_accept:
                reasons.append(f"GP margin uncertainty {max(p.sd_v, p.sd_i):.2f} > {op.sigma_max_accept}")
            if min(p.lcb_v, p.lcb_i) < op.safety_margin_min:
                reasons.append(f"GP margin lower bound {min(p.lcb_v, p.lcb_i):.2f} < {op.safety_margin_min}")
        if self.flags.check_context:
            ok, why = self.context_ok(ctx)
            checks["context_ok"] = ok
            if not ok:
                reasons.append("context outside validated envelope: " + why)
        step = max(abs(math.log(g.Kp / active.Kp)), abs(math.log(g.Ki / active.Ki)))
        checks["log_step"] = step
        if step > self.max_step and not is_baseline:
            reasons.append(f"gain step x{math.exp(step):.2f} exceeds limit x{math.exp(self.max_step):.1f}")
        return Decision(not reasons, reasons, checks)


@dataclass
class MonitorEvent:
    kind: str     # V_ABORT | I_ABORT | OSCILLATION | SENSOR_FAULT | SENSOR_STUCK | POWER_BALANCE
    detail: str


class RuntimeMonitor:
    """Per-sample monitor. Call ``check`` every control period."""

    def __init__(self, cfg: Config, enabled: bool = True) -> None:
        s = cfg.supervisor
        self.enabled = enabled
        self.Ts = cfg.converter.Ts
        Vref = cfg.plant.Vdc_ref_V
        self.V_abort = s.V_abort_frac * Vref
        self.I_abort = s.I_abort_frac * cfg.converter.I_grid_max_A
        self.I_hold = int(round(s.I_abort_hold_s / self.Ts))
        self.win = int(round(3 * s.osc_window_s / self.Ts))
        self.osc_rms = s.osc_rms_V
        self.hyst = 4.0                      # V, hysteresis for oscillation crossings
        # oscillation detection runs on a low-pass filtered error (tau 0.5 ms) so that
        # sensor noise does not produce crossings (found during evaluation: with
        # 2x noise the unfiltered detector raised false alarms on the baseline)
        self.a_lp = self.Ts / (0.5e-3 + self.Ts)
        # max physically possible |dv| per sample (+ margin): P_max / (C_min * V) * Ts * 4
        C_min = cfg.plant.C_nom_F * (1 - cfg.plant.C_tol)
        self.dv_max = 4 * 1.5 * cfg.plant.Vg_peak_phase_V * cfg.converter.I_grid_max_A * 1.2 / (C_min * Vref) * self.Ts + 15.0
        # ---- sensor plausibility (closes failure case R5, stuck voltage sensor) -------------
        # (a) frozen-reading check: with A-14 sensor noise (1 V rms) a live ADC never returns
        #     the same value for 2 ms; a stuck one does.
        self.frozen_n = int(round(s.frozen_window_s / self.Ts))
        self.frozen_tol = s.frozen_range_V
        # (b) power-balance observer (analytical redundancy): predicts v_dc from the energy
        #     balance C v dv/dt = P_afe(i_meas, vg_meas) - p_dcdc - v^2/R using only signals the
        #     controller already has (measured grid current and voltage, the DC-DC power demand
        #     and its nominal dynamics). A residual |v_meas - v_hat| that persists means the
        #     voltage sensor or the plant model is wrong -> alarm.
        p = cfg.plant
        self.C_nom, self.R, self.eta = p.C_nom_F, p.R_loss_ohm, p.eta_afe
        self.Vg_pk, self.tau_dc, self.slew = p.Vg_peak_phase_V, p.tau_dcdc_s, p.dcdc_slew_W_per_s
        self.a_dc = 1.0 - math.exp(-self.Ts / self.tau_dc)
        self.L_obs = self.Ts / s.observer_tau_s           # output-injection gain (healthy sensor)
        self.a_res = self.Ts / (0.5e-3 + self.Ts)        # residual low-pass, 0.5 ms
        self.res_th = s.residual_threshold_V
        self.res_n = int(round(s.residual_hold_s / self.Ts))
        self.reset()

    def reset(self) -> None:
        """Full reset (new session): detectors, observer and the sensor-fault latch."""
        self.reset_detectors()
        self.v_win: deque[float] = deque(maxlen=self.frozen_n)
        self.v_hat: float | None = None
        self.inj: deque[float] = deque(maxlen=int(round(0.03 / self.Ts)))  # last 30 ms of output injection
        self.p_s = self.p_hat = 0.0
        self.r_f = 0.0
        self.r_count = 0
        self.max_abs_residual = 0.0
        self.sensor_failed = False      # latched: feedback switched to the observer estimate

    def reset_detectors(self) -> None:
        """Reset the transient detectors only (end of a lock-out). The observer keeps running
        and a sensor-fault latch is NOT cleared: a failed sensor needs service, not a timer."""
        self.i_count = 0
        self.e_hist: deque[float] = deque(maxlen=self.win)
        self.cross: deque[int] = deque()
        self.side = 0
        self.k = 0
        self.v_prev: float | None = None
        self.e_f = 0.0

    # ------------------------------------------------------------ power-balance observer
    def _afe_dc(self, i_d: float, vg_pu: float) -> float:
        p_ac = 1.5 * self.Vg_pk * vg_pu * i_d
        return self.eta * p_ac if p_ac >= 0 else p_ac / self.eta

    def observe(self, v_meas: float, i_meas: float, p_load: float, vg_pu: float, C_pu: float) -> float:
        """Advance the observer one sample; returns the residual v_meas - v_hat (before update).
        After a sensor fault the output injection is switched off, so v_hat runs open-loop on
        the energy balance and serves as a virtual voltage sensor."""
        if self.v_hat is None:
            self.v_hat, self.p_s, self.p_hat = v_meas, p_load, p_load
        r = v_meas - self.v_hat
        dmax = self.slew * self.Ts
        self.p_s += max(-dmax, min(dmax, p_load - self.p_s))
        self.p_hat += self.a_dc * (self.p_s - self.p_hat)
        v = max(self.v_hat, 1.0)
        dv = (self._afe_dc(i_meas, vg_pu) - self.p_hat - v * v / self.R) / (self.C_nom * C_pu * v)
        inj = 0.0 if self.sensor_failed else self.L_obs * r
        self.inj.append(inj)
        self.v_hat += self.Ts * dv + inj
        return r

    def _declare_sensor_fault(self) -> None:
        """Latch the fault and undo the last 30 ms of output injection: once the sensor is wrong,
        the injection has been pulling v_hat towards the wrong reading."""
        self.sensor_failed = True
        self.v_hat -= sum(self.inj)
        self.inj.clear()

    def check(self, e: float, v_meas: float, i_meas: float, p_load: float | None = None,
              vg_pu: float | None = None, C_pu: float | None = None) -> MonitorEvent | None:
        self.k += 1
        if not self.enabled:
            return None
        if p_load is not None and not self.sensor_failed:
            r = self.observe(v_meas, i_meas, p_load, vg_pu if vg_pu is not None else 1.0,
                             C_pu if C_pu is not None else 1.0)
            self.r_f += self.a_res * (r - self.r_f)
            self.max_abs_residual = max(self.max_abs_residual, abs(self.r_f))
            self.v_win.append(v_meas)
            if len(self.v_win) == self.frozen_n and max(self.v_win) - min(self.v_win) < self.frozen_tol:
                self._declare_sensor_fault()
                return MonitorEvent("SENSOR_STUCK", f"v_meas range {max(self.v_win) - min(self.v_win):.3f} V over "
                                                    f"{self.frozen_n} samples (frozen reading)")
            self.r_count = self.r_count + 1 if abs(self.r_f) > self.res_th else 0
            if self.r_count >= self.res_n:
                self._declare_sensor_fault()
                return MonitorEvent("POWER_BALANCE", f"|v_meas - v_hat| = {abs(self.r_f):.1f} V > "
                                                     f"{self.res_th:.1f} V for {self.r_count} samples")
        elif p_load is not None:
            self.observe(v_meas, i_meas, p_load, vg_pu if vg_pu is not None else 1.0,
                         C_pu if C_pu is not None else 1.0)
        if self.v_prev is not None and abs(v_meas - self.v_prev) > self.dv_max:
            jump = abs(v_meas - self.v_prev)
            self.v_prev = v_meas
            return MonitorEvent("SENSOR_FAULT", f"|dv|={jump:.1f} V/sample > {self.dv_max:.1f} V implausible")
        self.v_prev = v_meas
        if abs(e) > self.V_abort:
            return MonitorEvent("V_ABORT", f"|Vdc-Vref|={abs(e):.1f} V > {self.V_abort:.1f} V")
        self.i_count = self.i_count + 1 if abs(i_meas) > self.I_abort else 0
        if self.i_count > self.I_hold:
            return MonitorEvent("I_ABORT", f"|i_d|>{self.I_abort:.1f} A for {self.i_count} samples")
        # sustained oscillation: >= 4 hysteresis crossings in the window and RMS above threshold
        self.e_f += self.a_lp * (e - self.e_f)
        ef = self.e_f
        self.e_hist.append(ef)
        new_side = 1 if ef > self.hyst else (-1 if ef < -self.hyst else self.side)
        if new_side != self.side and self.side != 0:
            self.cross.append(self.k)
        self.side = new_side
        while self.cross and self.cross[0] < self.k - self.win:
            self.cross.popleft()
        if len(self.cross) >= 4 and len(self.e_hist) == self.win:
            rms = math.sqrt(sum(x * x for x in self.e_hist) / self.win)
            if rms > self.osc_rms:
                return MonitorEvent("OSCILLATION", f"{len(self.cross)} crossings, RMS {rms:.1f} V")
        return None
