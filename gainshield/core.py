"""GainShield orchestration: online tuning sessions and the deployed controller.

Layers (see docs/ARCHITECTURE.md):
  C  certificate (offline)        -> stability.certify.Certificate
  D  safe Bayesian optimisation   -> optimizer.safe_bo.SafeBayesOpt
  E  runtime safety supervisor    -> safety.supervisor.CandidateGate / RuntimeMonitor
  F  controller execution         -> controllers.pi.PIController (+ baseline fallback)
  G  audit                        -> audit.logger.AuditLogger
"""
from __future__ import annotations

from dataclasses import dataclass, field
import math
import time

import numpy as np

from .audit.logger import AuditLogger, AuditRecord
from .config import Config
from .controllers.baseline import baseline_gains
from .controllers.pi import PIController, PIGains
from .disturbances.scenarios import probe_scenario
from .evaluation.metrics import probe_cost, probe_metrics
from .optimizer.safe_bo import BOFlags, Proposal, SafeBayesOpt
from .plant.charger import PlantVariation
from .safety.supervisor import CandidateGate, GateFlags, RuntimeMonitor
from .simulation import ContextEstimate, Measurement, simulate
from .stability.certify import Certificate, local_certified, local_uncertainty


@dataclass
class GainShieldFlags:
    """All switches in one place (ablation study). Defaults = complete GainShield."""

    certified_region: bool = True    # B
    gp_uncertainty: bool = True      # C
    runtime_monitor: bool = True     # D
    context_aware: bool = True       # E
    fallback: bool = True            # F

    def bo(self) -> BOFlags:
        return BOFlags(self.certified_region, self.gp_uncertainty, self.context_aware)

    def gate(self) -> GateFlags:
        return GateFlags(self.certified_region, self.gp_uncertainty, True, self.context_aware)


# --------------------------------------------------------------------------- agents
class SupervisedPIAgent:
    """PI whose gains are managed by the supervisor; used for probes and deployment."""

    def __init__(self, cfg: Config, baseline: PIGains, audit: AuditLogger, flags: GainShieldFlags,
                 name: str = "gainshield") -> None:
        self.cfg = cfg
        self.name = name
        self.baseline = baseline
        self.audit = audit
        self.flags = flags
        lim = cfg.converter.I_grid_max_A
        self.pi = PIController(baseline, cfg.converter.Ts, -lim, lim)
        self.monitor = RuntimeMonitor(cfg, enabled=flags.runtime_monitor)
        self.state = "BASELINE"
        self.events: list[dict] = []
        self.aborted = False
        self.violation_unhandled = False
        self.rollbacks = 0

    def reset(self, ctx: ContextEstimate, u0: float, t0: float) -> None:
        self.pi.gains = self.baseline
        self.pi.reset(u0)
        self.monitor.reset()
        self.state = "BASELINE"
        self.aborted = False

    def apply(self, gains: PIGains, t: float, m: Measurement | None, ctx: ContextEstimate, state: str,
              event: str = "GAIN_APPLIED", reason: str = "", p: Proposal | None = None, rollback: bool = False) -> None:
        prev = self.pi.gains
        self.pi.set_gains(gains, bumpless=True)
        self.state = state
        self.audit.log(AuditRecord(
            event=event, t_sim_s=t, mode=ctx.mode, controller_state=state,
            v_meas_V=m.v if m else math.nan, i_meas_A=m.i if m else math.nan,
            Kp_prev=prev.Kp, Ki_prev=prev.Ki, Kp_proposed=gains.Kp, Ki_proposed=gains.Ki,
            Kp_active=gains.Kp, Ki_active=gains.Ki,
            gp_sigma_margin=max(p.sd_v, p.sd_i) if p else math.nan, gp_mu_cost=p.mu_J if p else math.nan,
            margin_v_lcb=p.lcb_v if p else math.nan, margin_i_lcb=p.lcb_i if p else math.nan,
            decision="ACCEPT", rollback=rollback, reason=reason, context=_ctx_dict(ctx)))

    def _on_monitor(self, ev, m: Measurement, ctx: ContextEstimate) -> None:
        self.events.append({"t": m.t, "kind": ev.kind, "detail": ev.detail, "gains": self.pi.gains.as_tuple()})
        if self.flags.fallback:
            if self.pi.gains != self.baseline or self.state not in ("BASELINE", "FALLBACK"):
                self.rollbacks += 1
                self.apply(self.baseline, m.t, m, ctx, "FALLBACK", event="ROLLBACK",
                           reason=f"runtime monitor: {ev.kind} ({ev.detail})", rollback=True)
            else:
                self.audit.log(AuditRecord(event="FALLBACK", t_sim_s=m.t, mode=ctx.mode, controller_state="FALLBACK",
                                           v_meas_V=m.v, i_meas_A=m.i, Kp_prev=self.pi.gains.Kp,
                                           Ki_prev=self.pi.gains.Ki, Kp_active=self.pi.gains.Kp,
                                           Ki_active=self.pi.gains.Ki, decision="HOLD_BASELINE",
                                           reason=f"runtime monitor: {ev.kind} ({ev.detail}) while baseline "
                                                  f"already active - alarm only, adaptation locked out",
                                           context=_ctx_dict(ctx)))
            self.state = "FALLBACK"
            self.aborted = True
        else:
            self.violation_unhandled = True
            self.audit.log(AuditRecord(event="FAULT", t_sim_s=m.t, mode=ctx.mode, controller_state="UNPROTECTED",
                                       v_meas_V=m.v, i_meas_A=m.i, Kp_active=self.pi.gains.Kp,
                                       Ki_active=self.pi.gains.Ki, decision="NONE",
                                       reason=f"{ev.kind} detected but fallback disabled (ablation)",
                                       context=_ctx_dict(ctx)))

    def control(self, m: Measurement, ctx: ContextEstimate) -> float:
        ev = self.monitor.check(m.v_ref - m.v, m.v, m.i)
        if ev is not None and not (self.state == "FALLBACK" and self.flags.fallback):
            self._on_monitor(ev, m, ctx)
        return self.pi.update(m.v_ref, m.v)

    def status(self) -> dict:
        return {"state": self.state, "Kp": self.pi.gains.Kp, "Ki": self.pi.gains.Ki}


class ProbeAgent(SupervisedPIAgent):
    """Applies a candidate (bumpless) at ``t_switch`` during a probe episode."""

    def __init__(self, *a, candidate: PIGains, proposal: Proposal | None, t_switch: float = 0.01, **kw) -> None:
        super().__init__(*a, **kw)
        self.candidate = candidate
        self.proposal = proposal
        self.t_switch = t_switch
        self.switched = False

    def reset(self, ctx: ContextEstimate, u0: float, t0: float) -> None:
        super().reset(ctx, u0, t0)
        self.switched = False

    def control(self, m: Measurement, ctx: ContextEstimate) -> float:
        if not self.switched and m.t >= self.t_switch:
            self.switched = True
            if self.candidate != self.baseline:
                self.apply(self.candidate, m.t, m, ctx, "PROBING", reason=f"probe {self.proposal.kind if self.proposal else ''}",
                           p=self.proposal)
            else:
                self.state = "PROBING"
        return super().control(m, ctx)


class GainShieldAgent(SupervisedPIAgent):
    """Deployed GainShield: context-scheduled safe gains + monitor + fallback."""

    def __init__(self, cfg: Config, shield: "GainShield", name: str = "gainshield",
                 lockout_s: float = 0.10, dwell_s: float = 0.005) -> None:
        super().__init__(cfg, shield.baseline, shield.audit, shield.flags, name)
        self.shield = shield
        self.lockout = int(round(lockout_s / cfg.converter.Ts))
        self.dwell = int(round(dwell_s / cfg.converter.Ts))
        self.decision_times_ms: list[float] = []

    def reset(self, ctx: ContextEstimate, u0: float, t0: float) -> None:
        super().reset(ctx, u0, t0)
        self.ctx_active = ctx
        self.pending = 0
        self.lock_until = -1
        self.k = 0
        self.audit.log(AuditRecord(event="SESSION_START", t_sim_s=0.0, mode=ctx.mode, controller_state="BASELINE",
                                   Kp_active=self.baseline.Kp, Ki_active=self.baseline.Ki,
                                   reason="controller start: baseline gains active", context=_ctx_dict(ctx)))
        self._decide(ctx, None, 0.0)

    def _changed(self, ctx: ContextEstimate) -> bool:
        a = self.ctx_active
        return (abs(ctx.vg_pu - a.vg_pu) > 0.05 or abs(ctx.p_load_W - a.p_load_W) > 3e3 or ctx.mode != a.mode)

    def _decide(self, ctx: ContextEstimate, m: Measurement | None, t: float) -> None:
        t1 = time.perf_counter()
        z = ctx.as_vector(self.cfg)
        p = self.shield.bo.recommend(z, self.shield.context_mask(ctx))
        dec = self.shield.gate.evaluate(p, ctx, self.pi.gains, self.baseline)
        self.decision_times_ms.append(1e3 * (time.perf_counter() - t1))
        self.ctx_active = ctx
        is_base = p.gains == self.baseline
        if dec.accept and p.gains != self.pi.gains:
            self.apply(p.gains, t, m, ctx, "BASELINE" if is_base else "ADAPTIVE",
                       reason=f"context-scheduled gains ({p.kind}, safe set {p.safe_set_size})", p=p)
        elif dec.accept:
            self.audit.log(AuditRecord(event="PROPOSAL", t_sim_s=t, mode=ctx.mode, controller_state=self.state,
                                       Kp_prev=self.pi.gains.Kp, Ki_prev=self.pi.gains.Ki,
                                       Kp_proposed=p.gains.Kp, Ki_proposed=p.gains.Ki, Kp_active=self.pi.gains.Kp,
                                       Ki_active=self.pi.gains.Ki, gp_mu_cost=p.mu_J,
                                       gp_sigma_margin=max(p.sd_v, p.sd_i), margin_v_lcb=p.lcb_v,
                                       margin_i_lcb=p.lcb_i, decision="KEEP",
                                       reason=f"recommended gains already active ({p.kind}, safe set {p.safe_set_size})",
                                       context=_ctx_dict(ctx)))
        elif not dec.accept:
            self.audit.log(AuditRecord(event="GAIN_REJECTED", t_sim_s=t, mode=ctx.mode, controller_state=self.state,
                                       Kp_prev=self.pi.gains.Kp, Ki_prev=self.pi.gains.Ki,
                                       Kp_proposed=p.gains.Kp, Ki_proposed=p.gains.Ki, Kp_active=self.pi.gains.Kp,
                                       Ki_active=self.pi.gains.Ki, gp_sigma_margin=max(p.sd_v, p.sd_i),
                                       margin_v_lcb=p.lcb_v, margin_i_lcb=p.lcb_i, decision="REJECT",
                                       reason=dec.reason, context=_ctx_dict(ctx)))
            if self.pi.gains != self.baseline:
                self.apply(self.baseline, t, m, ctx, "BASELINE", event="FALLBACK",
                           reason="recommended gains rejected -> baseline", rollback=True)

    def control(self, m: Measurement, ctx: ContextEstimate) -> float:
        self.k += 1
        if self.state == "FALLBACK" and self.k >= self.lock_until > 0:
            self.state = "BASELINE"
            self.monitor.reset()
            self._decide(ctx, m, m.t)
        elif self.state != "FALLBACK":
            if self._changed(ctx):
                self.pending += 1
                if self.pending >= self.dwell:
                    self.pending = 0
                    self.audit.log(AuditRecord(event="CONTEXT_CHANGE", t_sim_s=m.t, mode=ctx.mode,
                                               controller_state=self.state, v_meas_V=m.v, i_meas_A=m.i,
                                               Kp_active=self.pi.gains.Kp, Ki_active=self.pi.gains.Ki,
                                               reason="operating context changed", context=_ctx_dict(ctx)))
                    self._decide(ctx, m, m.t)
            else:
                self.pending = 0
        was = self.state
        u = super().control(m, ctx)
        if was != "FALLBACK" and self.state == "FALLBACK":
            self.lock_until = self.k + self.lockout
        return u


def _ctx_dict(ctx: ContextEstimate) -> dict:
    return {"C_pu": ctx.C_pu, "tau_i_ms": 1e3 * ctx.tau_i_s, "delay_samples": ctx.delay_samples,
            "vg_pu": ctx.vg_pu, "p_load_kW": ctx.p_load_W / 1e3, "mode": ctx.mode}


# --------------------------------------------------------------------------- orchestrator
@dataclass
class TuningContext:
    name: str
    p_load_W: float
    vg_pu: float = 1.0
    variation: PlantVariation = field(default_factory=PlantVariation)


def default_training_contexts() -> list[TuningContext]:
    return [
        TuningContext("nominal_10kW", 10e3),
        TuningContext("C-20%_10kW", 10e3, variation=PlantVariation(C_pu=0.8)),
        TuningContext("C+20%_10kW", 10e3, variation=PlantVariation(C_pu=1.2)),
        TuningContext("sag0.85_20kW", 20e3, vg_pu=0.85),
        TuningContext("V2G_-12kW", -12e3),
        TuningContext("tau0.9ms_10kW", 10e3, variation=PlantVariation(tau_i_s=0.9e-3)),
        TuningContext("delay1.9_10kW", 10e3, variation=PlantVariation(delay_samples=1.9)),
        TuningContext("nominal_20kW", 20e3),
    ]


class GainShield:
    def __init__(self, cfg: Config, certificate: Certificate, flags: GainShieldFlags | None = None,
                 audit: AuditLogger | None = None, seed: int | None = None) -> None:
        self.cfg = cfg
        self.cert = certificate
        self.flags = flags or GainShieldFlags()
        self.baseline = baseline_gains(cfg)
        self.audit = audit or AuditLogger()
        self.bo = SafeBayesOpt(cfg, certificate, self.baseline, self.flags.bo(), seed=seed)
        self.gate = CandidateGate(cfg, self.flags.gate())
        self.scales = self._cost_scales()
        self.episodes: list[dict] = []
        self.bo_times_ms: list[float] = []
        self._mask_cache: dict[tuple, np.ndarray] = {}
        self.mask_times_ms: list[float] = []

    def context_mask(self, ctx: ContextEstimate) -> np.ndarray | None:
        """Allowed candidates for this context (tier-2 certificate), cached per context bin."""
        if not self.flags.certified_region:
            return None
        if not self.flags.context_aware:
            return self.bo.global_cert_mask
        key = (round(ctx.C_pu, 2), round(ctx.vg_pu, 2), round(ctx.tau_i_s * 1e5) / 1e5, round(ctx.delay_samples / 0.05) * 0.05)
        if key not in self._mask_cache:
            t0 = time.perf_counter()
            ls = local_uncertainty(self.cfg, *key)
            ok, _ = local_certified(self.cfg, self.bo.cand_gains[:, 0], self.bo.cand_gains[:, 1], ls)
            ok[self.bo.seed_index] = True
            self._mask_cache[key] = ok
            self.mask_times_ms.append(1e3 * (time.perf_counter() - t0))
        return self._mask_cache[key]

    def _cost_scales(self) -> dict[str, float]:
        """Cost normalisation from the baseline probe at nominal context (fixed seed)."""
        sc = probe_scenario(10e3, 1.0, PlantVariation())
        r = simulate(self.cfg, sc, SupervisedPIAgent(self.cfg, self.baseline, AuditLogger(), GainShieldFlags()), seed=12345)
        pm = probe_metrics(self.cfg, r.df)
        return {k: max(abs(pm[k]), 1e-6) if np.isfinite(pm[k]) else 1.0 for k in ("IAE_Vs", "peak_load_dev_V", "overshoot_pct", "settling_ms", "ripple_A")} | {
            "overshoot_pct": max(pm["overshoot_pct"], 5.0)}

    def context_estimate(self, tc: TuningContext, rng: np.random.Generator) -> tuple[ContextEstimate, dict]:
        """Context the tuner believes (true parameters + identification error)."""
        p, c = self.cfg.plant, self.cfg.converter
        v = tc.variation
        err = {"C": float(rng.normal(0, 0.015)), "tau": float(rng.normal(0, 0.05)), "delay": float(rng.normal(0, 0.05))}
        C_true = v.C_pu
        tau_true = v.tau_i_s if v.tau_i_s is not None else p.tau_i_nom_s
        d_true = v.delay_samples if v.delay_samples is not None else c.delay_nom_samples
        ctx = ContextEstimate(C_true * (1 + err["C"]), tau_true * (1 + err["tau"]), d_true + err["delay"], tc.vg_pu, tc.p_load_W)
        return ctx, err

    def run_episode(self, gains: PIGains, proposal: Proposal | None, tc: TuningContext, ctx: ContextEstimate,
                    err: dict, seed: int) -> dict:
        sc = probe_scenario(tc.p_load_W, tc.vg_pu, tc.variation)
        agent = ProbeAgent(self.cfg, self.baseline, self.audit, self.flags, candidate=gains, proposal=proposal,
                           name="probe")
        r = simulate(self.cfg, sc, agent, seed=seed, ctx_error=err)
        pm = probe_metrics(self.cfg, r.df, aborted=agent.aborted)
        # true constraint record (independent of the monitor): band violation on the true plant
        e = (r.df["v"] - r.df["v_ref"]).abs()
        pm["true_v_viol"] = float((e > self.cfg.constraints.V_band_op * self.cfg.plant.Vdc_ref_V).any())
        pm["true_trip"] = float((e > self.cfg.constraints.V_band_trip * self.cfg.plant.Vdc_ref_V).any())
        pm["max_dev_V"] = float(e.max())
        pm["J"] = probe_cost(pm, self.scales)
        pm["monitor_events"] = [ev["kind"] for ev in agent.events]
        pm["unhandled"] = agent.violation_unhandled
        return {"pm": pm, "df": r.df}

    def tune_context(self, tc: TuningContext, n_iters: int | None = None, seed: int = 0,
                     callback=None) -> list[dict]:
        rng = np.random.default_rng(seed)
        ctx, err = self.context_estimate(tc, rng)
        z = ctx.as_vector(self.cfg)
        cmask = self.context_mask(ctx)
        n_iters = n_iters or self.cfg.optimizer.iters_per_context
        self.audit.log(AuditRecord(event="SESSION_START", mode=ctx.mode, controller_state="BASELINE",
                                   Kp_active=self.baseline.Kp, Ki_active=self.baseline.Ki,
                                   reason=f"tuning session {tc.name}", context=_ctx_dict(ctx)))
        plan: list[tuple[PIGains, Proposal | None, str]] = []
        if self.bo.n_obs == 0:
            plan = [(g, None, "init") for g in self.bo.initial_design(self.cfg.optimizer.n_init)]
        else:
            plan = [(self.baseline, None, "seed")]   # always re-measure the seed in a new context
        out = []
        it = 0
        while it < n_iters + len(plan):
            t0 = time.perf_counter()
            if it < len(plan):
                g, p, kind = plan[it]
                if p is None:
                    p = self.bo.predict(z, np.array([[g.Kp, g.Ki]]))
                    p = Proposal(g, kind, float(p["muJ"][0]), float(p["sdJ"][0]),
                                 float(p["muv"][0] - self.bo.beta * p["sdv"][0]),
                                 float(p["mui"][0] - self.bo.beta * p["sdi"][0]),
                                 float(p["sdv"][0]), float(p["sdi"][0]), 0, len(self.bo.cand_gains))
            else:
                p = self.bo.propose(z, cmask)
                g, kind = p.gains, p.kind
            t_prop = time.perf_counter() - t0
            dec = self.gate.evaluate(p, ctx, self.baseline, self.baseline)
            if kind in ("init", "seed"):
                # initial design is next to the certified seed; only the certificate/context are binding
                dec.reasons = [r for r in dec.reasons if not r.startswith("GP ")]
                dec.accept = not dec.reasons
            self.audit.log(AuditRecord(event="PROPOSAL", mode=ctx.mode, controller_state="BASELINE",
                                       Kp_prev=self.baseline.Kp, Ki_prev=self.baseline.Ki,
                                       Kp_proposed=g.Kp, Ki_proposed=g.Ki, Kp_active=self.baseline.Kp,
                                       Ki_active=self.baseline.Ki, gp_sigma_margin=max(p.sd_v, p.sd_i),
                                       gp_mu_cost=p.mu_J, margin_v_lcb=p.lcb_v, margin_i_lcb=p.lcb_i,
                                       decision="ACCEPT" if dec.accept else "REJECT", reason=dec.reason,
                                       context=_ctx_dict(ctx), extra={"kind": kind, "iteration": it,
                                                                       "safe_set": p.safe_set_size}))
            rec = {"context": tc.name, "iter": it, "kind": kind, "Kp": g.Kp, "Ki": g.Ki, "accepted": dec.accept,
                   "reason": dec.reason, "mu_J": p.mu_J, "sd_J": p.sd_J, "lcb_v": p.lcb_v, "sd_v": p.sd_v,
                   "safe_set": p.safe_set_size, "t_propose_ms": 1e3 * t_prop}
            if dec.accept:
                ep = self.run_episode(g, p, tc, ctx, err, seed=seed * 1000 + it)
                pm = ep["pm"]
                t1 = time.perf_counter()
                self.bo.add_observation(g, z, pm["J"], pm["m_v"], pm["m_i"])
                rec["t_fit_ms"] = 1e3 * (time.perf_counter() - t1)
                rec.update({k: v for k, v in pm.items() if not isinstance(v, list)})
                rec["monitor_events"] = ",".join(pm["monitor_events"])
                self.audit.log(AuditRecord(event="EPISODE_RESULT", mode=ctx.mode, controller_state="BASELINE",
                                           Kp_prev=g.Kp, Ki_prev=g.Ki,
                                           Kp_active=self.baseline.Kp, Ki_active=self.baseline.Ki, gp_mu_cost=p.mu_J,
                                           decision="ROLLED_BACK" if pm["aborted"] else "COMPLETED",
                                           rollback=bool(pm["aborted"]),
                                           reason=f"J={pm['J']:.3f} m_v={pm['m_v']:.2f} m_i={pm['m_i']:.2f}; probe ended, gains revert to baseline",
                                           context=_ctx_dict(ctx)))
                if callback:
                    callback(rec, ep)
            else:
                self.bo.history.append({"rejected": (g.Kp, g.Ki)})
                self.bo.exclude(g)
                rec["t_fit_ms"] = 0.0
                self.audit.log(AuditRecord(event="GAIN_REJECTED", mode=ctx.mode, controller_state="BASELINE",
                                           Kp_prev=self.baseline.Kp, Ki_prev=self.baseline.Ki,
                                           Kp_proposed=g.Kp, Ki_proposed=g.Ki, Kp_active=self.baseline.Kp,
                                           Ki_active=self.baseline.Ki, gp_sigma_margin=max(p.sd_v, p.sd_i),
                                           margin_v_lcb=p.lcb_v, margin_i_lcb=p.lcb_i, decision="REJECT",
                                           reason=dec.reason, context=_ctx_dict(ctx)))
            self.bo_times_ms.append(rec["t_propose_ms"] + rec["t_fit_ms"])
            out.append(rec)
            self.episodes.append(rec)
            it += 1
        recm = self.bo.recommend(z, cmask)
        self.audit.log(AuditRecord(event="SESSION_END", mode=ctx.mode, controller_state="ADAPTIVE",
                                   Kp_active=recm.gains.Kp, Ki_active=recm.gains.Ki, gp_mu_cost=recm.mu_J,
                                   reason=f"recommended gains for {tc.name}", context=_ctx_dict(ctx)))
        return out

    def agent(self, name: str = "gainshield") -> GainShieldAgent:
        return GainShieldAgent(self.cfg, self, name=name)
