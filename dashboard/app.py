"""GainShield simulation dashboard (Streamlit).

Run:  streamlit run dashboard/app.py

Panels: Monitoring | AI optimiser | Safety | Experiments | Audit | Live tuning.
Every number shown is computed from a simulation executed in this session or
read from files in results/ produced by the experiment scripts.
"""
from __future__ import annotations

import math
import sys
from dataclasses import replace
from pathlib import Path

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from plotly.subplots import make_subplots

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "experiments"))

from common import MODEL_PATH, RESULTS, get_certificate, load_config, load_model  # noqa: E402
from gainshield.audit.logger import AuditLogger  # noqa: E402
from gainshield.controllers.baseline import baseline_gains  # noqa: E402
from gainshield.core import GainShield, TuningContext  # noqa: E402
from gainshield.disturbances.scenarios import standard_suite  # noqa: E402
from gainshield.evaluation.metrics import scenario_metrics  # noqa: E402
from gainshield.plant.charger import PlantVariation  # noqa: E402
from gainshield.simulation import ContextEstimate, FixedPIAgent, simulate  # noqa: E402
from gainshield.stability.certify import certify_point_context, local_uncertainty  # noqa: E402

BLUE, ORANGE, GREY, RED = "#2a78d6", "#eb6834", "#52514e", "#e34948"
st.set_page_config(page_title="GainShield", layout="wide")


@st.cache_resource(show_spinner="Loading configuration, certificate and trained model ...")
def resources():
    cfg = load_config()
    cert = get_certificate(cfg)
    audit = AuditLogger(run_id="dashboard")
    if MODEL_PATH.exists():
        gs = load_model(cfg, cert, audit=audit)
        trained = True
    else:
        gs = GainShield(cfg, cert, audit=audit)
        trained = False
    return cfg, cert, gs, trained


cfg, cert, gs, trained = resources()
base = baseline_gains(cfg)
Vref = cfg.plant.Vdc_ref_V

st.title("GainShield — safe PI gain tuning for a bidirectional EV-charger DC link")
st.caption("Averaged 30 kW / 800 V module, simulation only. All parameters are documented engineering assumptions "
           "(config/default.toml). " + ("Trained contextual GP model loaded." if trained else
                                         "No trained model found - run experiments/run_tuning.py; GainShield will stay on the baseline."))

# ----------------------------------------------------------------------------- sidebar: experiment panel
st.sidebar.header("Experiment")
suite = {s.name: s for s in standard_suite()}
name = st.sidebar.selectbox("Disturbance scenario", list(suite), index=2)
sc0 = suite[name]
st.sidebar.caption(sc0.description)
dur = st.sidebar.slider("Simulation duration [s]", 0.15, 0.60, float(sc0.duration_s), 0.05)
seed = st.sidebar.number_input("Random seed", 0, 10_000, 0)
noise = st.sidebar.slider("Sensor-noise scale", 0.0, 4.0, float(sc0.noise_scale), 0.5)
run_which = st.sidebar.radio("Run", ["Compare both", "Baseline only", "GainShield only"])
go_btn = st.sidebar.button("Run simulation", type="primary")
sc = replace(sc0, duration_s=dur, noise_scale=noise)

if go_btn or "runs" not in st.session_state:
    gs.audit.records.clear()
    runs = {}
    if run_which in ("Compare both", "Baseline only"):
        runs["baseline"] = simulate(cfg, sc, FixedPIAgent(cfg, base), seed=int(seed))
    if run_which in ("Compare both", "GainShield only"):
        ag = gs.agent()
        runs["gainshield"] = simulate(cfg, sc, ag, seed=int(seed))
        st.session_state["agent_events"] = ag.events
    st.session_state["runs"] = runs
    st.session_state["audit"] = list(gs.audit.records)
    st.session_state["scenario"] = sc
runs = st.session_state["runs"]
sc = st.session_state["scenario"]
colors = {"baseline": ORANGE, "gainshield": BLUE}

tabs = st.tabs(["Monitoring", "AI optimiser", "Safety", "Experiment results", "Audit log", "Live tuning"])

# ----------------------------------------------------------------------------- monitoring
with tabs[0]:
    last = runs.get("gainshield") or runs.get("baseline")
    d = last.df
    c = st.columns(5)
    c[0].metric("DC-link reference", f"{d.v_ref.iloc[-1]:.0f} V")
    c[1].metric("DC-link voltage", f"{d.v.iloc[-1]:.1f} V", f"{d.v.iloc[-1] - d.v_ref.iloc[-1]:+.1f} V")
    c[2].metric("Grid current i_d", f"{d.i_d.iloc[-1]:.1f} A")
    c[3].metric("Battery power", f"{d.p_dc.iloc[-1] / 1e3:.1f} kW")
    c[4].metric("Mode", "G2V" if d.p_dem.iloc[-1] > 0 else ("V2G" if d.p_dem.iloc[-1] < 0 else "IDLE"))
    fig = make_subplots(rows=4, cols=1, shared_xaxes=True, vertical_spacing=0.04,
                        subplot_titles=("DC-link voltage [V]", "Grid d-axis current [A]", "Power [kW]", "Kp [A/V]"))
    for k, r in runs.items():
        t = 1e3 * r.df.t
        fig.add_trace(go.Scatter(x=t, y=r.df.v, name=f"{k} V_dc", line=dict(color=colors[k], width=1.6)), 1, 1)
        fig.add_trace(go.Scatter(x=t, y=r.df.i_d, name=f"{k} i_d", line=dict(color=colors[k], width=1.4), showlegend=False), 2, 1)
        fig.add_trace(go.Scatter(x=t, y=r.df.P_ac / 1e3, name=f"{k} P_grid", line=dict(color=colors[k], width=1.4), showlegend=False), 3, 1)
        fig.add_trace(go.Scatter(x=t, y=r.df.Kp, name=f"{k} Kp", line=dict(color=colors[k], width=1.4, shape="hv"), showlegend=False), 4, 1)
    t = 1e3 * d.t
    fig.add_trace(go.Scatter(x=t, y=d.v_ref, name="V_ref", line=dict(color=GREY, width=1, dash="dot")), 1, 1)
    fig.add_trace(go.Scatter(x=t, y=d.p_dem / 1e3, name="battery demand", line=dict(color=GREY, width=1, dash="dot")), 3, 1)
    band = cfg.constraints.V_band_op * Vref
    for s in (-1, 1):
        fig.add_hline(Vref + s * band, line=dict(color=GREY, dash="dash", width=1), row=1, col=1)
        fig.add_hline(s * cfg.converter.I_grid_max_A, line=dict(color=GREY, dash="dash", width=1), row=2, col=1)
    fig.update_layout(height=780, hovermode="x unified", margin=dict(l=10, r=10, t=30, b=10), legend=dict(orientation="h"))
    fig.update_xaxes(title_text="time [ms]", row=4, col=1)
    st.plotly_chart(fig, width="stretch")

# ----------------------------------------------------------------------------- AI panel
with tabs[1]:
    r = runs.get("gainshield")
    ctx = ContextEstimate(sc.variation.C_pu, sc.variation.tau_i_s or cfg.plant.tau_i_nom_s,
                          sc.variation.delay_samples or cfg.converter.delay_nom_samples,
                          float(r.df.vg_pu.iloc[-1]) if r is not None else sc.vg0_pu,
                          float(r.df.p_dem.iloc[-1]) if r is not None else sc.p_load0_W)
    z = ctx.as_vector(cfg)
    mask = gs.context_mask(ctx)
    rec = gs.bo.recommend(z, mask)
    P = gs.bo.predict(z)
    S = gs.bo.safe_mask(P, mask)
    c = st.columns(6)
    c[0].metric("Active Kp", f"{r.df.Kp.iloc[-1]:.3f}" if r is not None else "-")
    c[1].metric("Active Ki", f"{r.df.Ki.iloc[-1]:.1f}" if r is not None else "-")
    c[2].metric("Recommended Kp / Ki", f"{rec.gains.Kp:.2f} / {rec.gains.Ki:.0f}")
    c[3].metric("GP predicted cost J", f"{rec.mu_J:.3f}", help="1.0 ~ baseline at nominal context")
    c[4].metric("GP cost std", f"{rec.sd_J:.3f}")
    c[5].metric("Observations / safe set", f"{gs.bo.n_obs} / {int(S.sum())}")
    G = gs.bo.cand_gains
    f2 = go.Figure()
    f2.add_trace(go.Scatter(x=G[:, 0], y=G[:, 1], mode="markers", name="candidates (tier-1 region)",
                            marker=dict(symbol="square", size=9, color=P["muJ"], colorscale="Blues_r",
                                        colorbar=dict(title="GP mean J"), line=dict(width=0)),
                            text=[f"J={a:.3f}±{b:.3f}<br>m_v LCB={c_:.2f}" for a, b, c_ in
                                  zip(P["muJ"], P["sdJ"], P["muv"] - gs.bo.beta * P["sdv"])], hoverinfo="text+x+y"))
    notok = ~mask if mask is not None else np.zeros(len(G), bool)
    f2.add_trace(go.Scatter(x=G[notok, 0], y=G[notok, 1], mode="markers", name="not certified for this context",
                            marker=dict(symbol="x", size=6, color=GREY)))
    f2.add_trace(go.Scatter(x=G[S, 0], y=G[S, 1], mode="markers", name="GP-safe & certified",
                            marker=dict(symbol="square-open", size=11, color="#1baf7a", line=dict(width=1.5))))
    f2.add_trace(go.Scatter(x=[base.Kp], y=[base.Ki], mode="markers", name="baseline",
                            marker=dict(symbol="diamond", size=13, color=ORANGE, line=dict(color="white", width=1))))
    f2.add_trace(go.Scatter(x=[rec.gains.Kp], y=[rec.gains.Ki], mode="markers", name="recommended",
                            marker=dict(symbol="star", size=16, color="#1baf7a", line=dict(color="white", width=1))))
    f2.update_xaxes(type="log", title="Kp [A/V]")
    f2.update_yaxes(type="log", title="Ki [A/(V s)]")
    f2.update_layout(height=520, title=f"GP cost and safe set at the current context (C={ctx.C_pu:.2f} pu, "
                                       f"Vg={ctx.vg_pu:.2f} pu, P={ctx.p_load_W / 1e3:.0f} kW)")
    st.plotly_chart(f2, width="stretch")
    hist_p = RESULTS / "tuning_history.csv"
    if hist_p.exists():
        h = pd.read_csv(hist_p)
        st.subheader("Tuning iterations (from results/tuning_history.csv)")
        f3 = make_subplots(rows=1, cols=2, subplot_titles=("Gains per iteration", "Probe cost J"))
        acc = h.accepted.astype(bool)
        f3.add_trace(go.Scatter(x=h.index[acc], y=h.Kp[acc], mode="markers", name="Kp accepted", marker=dict(color=BLUE)), 1, 1)
        f3.add_trace(go.Scatter(x=h.index[~acc], y=h.Kp[~acc], mode="markers", name="Kp rejected", marker=dict(color=RED, symbol="x")), 1, 1)
        f3.add_trace(go.Scatter(x=h.index[acc], y=h.J[acc], mode="markers", name="J", marker=dict(color=BLUE)), 1, 2)
        f3.add_hline(1.0, line=dict(color=ORANGE, dash="dash"), row=1, col=2)
        f3.update_layout(height=320)
        st.plotly_chart(f3, width="stretch")

# ----------------------------------------------------------------------------- safety panel
with tabs[2]:
    c = st.columns(4)
    c[0].metric("Voltage operating band", f"±{cfg.constraints.V_band_op * 100:.0f} % ({cfg.constraints.V_band_op * Vref:.0f} V)")
    c[1].metric("Supervisor abort band", f"±{cfg.supervisor.V_abort_frac * 100:.0f} %")
    c[2].metric("Trip band", f"±{cfg.constraints.V_band_trip * 100:.0f} %")
    c[3].metric("Current limit", f"{cfg.converter.I_grid_max_A:.0f} A")
    rows = []
    for k, rr in runs.items():
        m = scenario_metrics(cfg, rr.df, sc.first_event_t)
        kp, ki = float(rr.df.Kp.iloc[-1]), float(rr.df.Ki.iloc[-1])
        ls = local_uncertainty(cfg, ctx.C_pu, ctx.vg_pu, ctx.tau_i_s, ctx.delay_samples)
        cp = certify_point_context(cfg, kp, ki, ls)
        rows.append({"controller": k, "active Kp": kp, "active Ki": ki,
                     "tier-1 robust stability (global proof)": cp["robust_stable"],
                     "tier-2 margins (this context)": cp["margins_ok"], "worst PM [deg]": round(cp["PM_worst"], 1),
                     "worst GM [dB]": round(cp["GM_worst"], 1), "worst MM": round(cp["MM_worst"], 2),
                     "voltage margin": round(m["v_margin"], 3), "current margin": round(m["i_margin"], 3),
                     "time outside ±5 % [ms]": m["v_viol_ms"], "trip": bool(m["v_trip"])})
    st.dataframe(pd.DataFrame(rows), width="stretch")
    ev = st.session_state.get("agent_events", [])
    st.write("**Runtime monitor events (GainShield run):**", "none" if not ev else "")
    if ev:
        st.dataframe(pd.DataFrame(ev), width="stretch")
    rb = [a for a in st.session_state["audit"] if a["event"] in ("ROLLBACK", "FALLBACK", "GAIN_REJECTED")]
    st.write(f"**Rollback / rejection records in this run:** {len(rb)}")
    if rb:
        st.dataframe(pd.DataFrame(rb)[["t_sim_s", "event", "Kp_prev", "Kp_active", "reason"]], width="stretch")
    if (RESULTS / "figures" / "kp_ki_regions.png").exists():
        st.image(str(RESULTS / "figures" / "kp_ki_regions.png"), caption="Offline certificate: four regions kept distinct",
                 width=640)

# ----------------------------------------------------------------------------- experiment results
with tabs[3]:
    if len(runs) == 2:
        mb = scenario_metrics(cfg, runs["baseline"].df, sc.first_event_t)
        mg = scenario_metrics(cfg, runs["gainshield"].df, sc.first_event_t)
        tbl = pd.DataFrame({"baseline": mb, "gainshield": mg})
        tbl["change %"] = 100 * (tbl.gainshield - tbl.baseline) / tbl.baseline.replace(0, np.nan)
        st.subheader(f"This run: {sc.name}, seed {seed}")
        st.dataframe(tbl.style.format("{:.3f}"), width="stretch")
    else:
        st.info("Select 'Compare both' to see a side-by-side metrics table for this run.")
    p = RESULTS / "evaluation_summary.csv"
    if p.exists():
        st.subheader("Full evaluation (results/evaluation_summary.csv, 5 seeds per scenario)")
        st.dataframe(pd.read_csv(p), width="stretch")
    p = RESULTS / "ablation.csv"
    if p.exists():
        st.subheader("Ablation study (results/ablation.csv)")
        st.dataframe(pd.read_csv(p), width="stretch")

# ----------------------------------------------------------------------------- audit panel
with tabs[4]:
    a = pd.json_normalize(st.session_state["audit"])
    if len(a):
        st.subheader("Decisions in this run")
        cols = [c_ for c_ in ["seq", "t_sim_s", "event", "controller_state", "mode", "Kp_prev", "Ki_prev",
                              "Kp_proposed", "Ki_proposed", "Kp_active", "Ki_active", "gp_sigma_margin",
                              "margin_v_lcb", "decision", "rollback", "reason"] if c_ in a.columns]
        st.dataframe(a[cols], width="stretch", height=360)
        r = runs.get("gainshield")
        if r is not None:
            st.subheader("Controller state history")
            stt = r.df[["t", "state"]].copy()
            stt["chg"] = stt.state != stt.state.shift()
            st.dataframe(stt[stt.chg][["t", "state"]].rename(columns={"t": "t [s]"}), width="stretch")
        st.download_button("Download audit (JSONL)", "\n".join(pd.Series(st.session_state["audit"]).map(lambda x: __import__("json").dumps(x))),
                           file_name="gainshield_audit.jsonl")
    for f in ["tuning_audit.jsonl", "evaluation_audit.jsonl", "failure_audit.jsonl"]:
        if (RESULTS / "audit" / f).exists():
            st.caption(f"Stored log: results/audit/{f}")

# ----------------------------------------------------------------------------- live tuning
with tabs[5]:
    st.write("Run a short **online safe-tuning session** on a fresh optimiser (does not modify the loaded model). "
             "Every candidate passes the certificate, GP-confidence, context and step checks; every probe runs "
             "under the runtime monitor.")
    c = st.columns(4)
    lp = c[0].slider("Battery power [kW]", -25, 25, 10)
    vg = c[1].slider("Grid voltage [pu]", 0.80, 1.10, 1.0, 0.01)
    Cp = c[2].slider("True capacitance [pu]", 0.80, 1.20, 1.0, 0.05)
    n = c[3].slider("Iterations", 3, 20, 8)
    if st.button("Start tuning session"):
        fresh = GainShield(cfg, cert, audit=AuditLogger(run_id="live"))
        prog = st.progress(0.0)
        box = st.empty()
        rows = []

        def cb(rec, ep):
            rows.append(rec)
            prog.progress(min(1.0, len(rows) / (n + cfg.optimizer.n_init)))
            box.dataframe(pd.DataFrame(rows)[["iter", "kind", "Kp", "Ki", "accepted", "J", "m_v", "m_i", "safe_set"]])
        hist = fresh.tune_context(TuningContext("live", lp * 1e3, vg, PlantVariation(C_pu=Cp)), n_iters=n, seed=int(seed), callback=cb)
        h = pd.DataFrame(hist)
        st.success(f"{int(h.accepted.sum())} episodes run, {int((~h.accepted).sum())} proposals rejected, "
                   f"{int(h.get('aborted', pd.Series(dtype=float)).fillna(0).sum())} rolled back by the monitor.")
        st.dataframe(h, width="stretch")
