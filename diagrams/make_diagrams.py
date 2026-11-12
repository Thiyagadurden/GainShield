"""Generate the six architecture diagrams (SVG + PNG) from code.

Run: python diagrams/make_diagrams.py
The Mermaid equivalents live in diagrams/*.mmd (rendered natively by GitHub).
Every block name here corresponds to a module in gainshield/ (see docs/ARCHITECTURE.md).
"""
from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch  # noqa: E402

OUT = Path(__file__).resolve().parent
INK, INK2 = "#0b0b0b", "#52514e"
FILL = {"plant": "#fdebe2", "model": "#f3f2ee", "cert": "#dbe8f8", "ai": "#d9f1e8", "safe": "#fde2e2",
        "ctrl": "#e8e4fa", "obs": "#fff3d6", "io": "#ffffff"}
EDGE = {"plant": "#eb6834", "model": "#8a887f", "cert": "#2a78d6", "ai": "#1baf7a", "safe": "#e34948",
        "ctrl": "#6250d6", "obs": "#c98500", "io": "#52514e"}


class D:
    def __init__(self, w: float, h: float, title: str = "") -> None:
        self.fig, self.ax = plt.subplots(figsize=(w, h))
        self.ax.set_xlim(0, w)
        self.ax.set_ylim(0, h)
        self.ax.axis("off")
        self.b: dict[str, tuple[float, float, float, float]] = {}
        if title:
            self.ax.text(0.15, h - 0.05, title, fontsize=12, weight="bold", color=INK, va="top")

    def box(self, key, x, y, w, h, text, kind="model", fs=8.5, bold_first=True):
        self.ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.02,rounding_size=0.08",
                                         fc=FILL[kind], ec=EDGE[kind], lw=1.4))
        lines = text.split("\n")
        if bold_first and len(lines) > 1:
            self.ax.text(x + w / 2, y + h - 0.12, lines[0], ha="center", va="top", fontsize=fs + 0.5, weight="bold", color=INK)
            self.ax.text(x + w / 2, y + h / 2 - 0.12, "\n".join(lines[1:]), ha="center", va="center", fontsize=fs - 0.8,
                         color=INK2, linespacing=1.25)
        else:
            self.ax.text(x + w / 2, y + h / 2, text, ha="center", va="center", fontsize=fs, color=INK,
                         weight="bold" if bold_first else "normal")
        self.b[key] = (x, y, w, h)

    def group(self, x, y, w, h, label, kind):
        self.ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.02,rounding_size=0.12",
                                         fc="none", ec=EDGE[kind], lw=1.0, ls=(0, (4, 3))))
        self.ax.text(x + 0.08, y + h - 0.06, label, fontsize=7.5, color=EDGE[kind], va="top", weight="bold")

    def _pt(self, key, side):
        x, y, w, h = self.b[key]
        return {"l": (x, y + h / 2), "r": (x + w, y + h / 2), "t": (x + w / 2, y + h), "b": (x + w / 2, y)}[side]

    def arrow(self, a, sa, b, sb, label="", color=INK2, rad=0.0, ls="-", lw=1.2, lpos=0.5, loff=(0, 0.08)):
        p1, p2 = self._pt(a, sa), self._pt(b, sb)
        self.ax.add_patch(FancyArrowPatch(p1, p2, arrowstyle="-|>", mutation_scale=11, color=color, lw=lw,
                                          connectionstyle=f"arc3,rad={rad}", linestyle=ls, shrinkA=2, shrinkB=2))
        if label:
            mx = p1[0] + lpos * (p2[0] - p1[0]) + loff[0]
            my = p1[1] + lpos * (p2[1] - p1[1]) + loff[1]
            self.ax.text(mx, my, label, fontsize=6.8, color=color, ha="center", va="bottom",
                         bbox=dict(fc="white", ec="none", pad=0.6, alpha=0.9))

    def path(self, pts, label="", color=INK2, ls="-", lw=1.2, li=0, loff=(0, 0.06)):
        """Orthogonal poly-line arrow through explicit waypoints; label on segment ``li``."""
        for (x1, y1), (x2, y2) in zip(pts[:-2], pts[1:-1]):
            self.ax.plot([x1, x2], [y1, y2], color=color, lw=lw, ls=ls, solid_capstyle="round")
        self.ax.add_patch(FancyArrowPatch(pts[-2], pts[-1], arrowstyle="-|>", mutation_scale=11, color=color, lw=lw,
                                          linestyle=ls, shrinkA=0, shrinkB=2))
        if label:
            (x1, y1), (x2, y2) = pts[li], pts[li + 1]
            self.ax.text((x1 + x2) / 2 + loff[0], (y1 + y2) / 2 + loff[1], label, fontsize=6.8, color=color,
                         ha="center", va="bottom", bbox=dict(fc="white", ec="none", pad=0.6, alpha=0.95))

    def save(self, name):
        for ext in ("svg", "png"):
            self.fig.savefig(OUT / f"{name}.{ext}", bbox_inches="tight", dpi=220)
        plt.close(self.fig)


def overall():
    d = D(13.1, 7.3, "GainShield - overall system architecture")
    d.group(0.2, 4.55, 4.0, 2.0, "A/B  ELECTRICAL PLANT + MODEL", "plant")
    d.box("plant", 0.35, 4.7, 3.7, 1.55, "Bidirectional charger (averaged)\nAFE + inner i_d loop + delay\nDC link C·v·dv/dt = P_afe - P_dc - P_loss\nDC-DC stage (CPL in G2V / source in V2G)", "plant")
    d.box("dist", 0.35, 2.85, 3.7, 1.25, "Disturbance suite\nload steps, G2V<->V2G, grid sag,\nnoise, C ±20 %, lag, delay, combined", "model")
    d.box("ctx", 0.35, 0.6, 3.7, 1.7, "Operating context estimate\nC, Vg, P_load, mode, tau_i, delay\n+ bounded estimation error", "model")
    d.group(4.55, 4.55, 3.9, 2.0, "C  OFFLINE STABILITY CERTIFICATE", "cert")
    d.box("cert", 4.7, 4.7, 3.6, 1.55, "Two-tier certificate\nT1: robust stability for ALL plants in U\n(zero-exclusion proof over k-interval)\nT2: PM/GM/MM for current context set", "cert")
    d.group(4.55, 0.45, 3.9, 3.75, "D  SAFE BAYESIAN OPTIMISATION", "ai")
    d.box("gp", 4.7, 2.55, 3.6, 1.35, "Contextual GPs\ncost J, voltage margin m_v,\ncurrent margin m_i  (gains + context)", "ai")
    d.box("acq", 4.7, 0.6, 3.6, 1.55, "SafeOpt-style acquisition\nsafe set S = LCB(m) >= h  within T1∩T2\nmaximisers ∪ expanders -> candidate", "ai")
    d.group(8.85, 2.4, 3.95, 4.15, "E/F  RUNTIME SUPERVISOR + CONTROLLER", "safe")
    d.box("gate", 9.0, 4.95, 3.65, 1.3, "Candidate gate (independent)\nre-certify exact gains, GP sigma & LCB,\ncontext envelope, gain-step limit", "safe")
    d.box("pi", 9.0, 3.55, 3.65, 1.1, "PI controller  10 kHz\nanti-windup, saturation, bumpless", "ctrl")
    d.box("mon", 9.0, 2.55, 3.65, 0.8, "Runtime monitor\nV band, I limit, oscillation, sensor", "safe", fs=8)
    d.box("base", 9.0, 0.6, 1.7, 1.45, "Baseline PI\n(fixed, certified)\nfallback", "ctrl", fs=8)
    d.box("audit", 10.9, 0.6, 1.75, 1.45, "G  Audit + KPIs\nJSONL log\ndashboard", "obs", fs=8)
    d.arrow("plant", "r", "cert", "l", "linearised model")
    d.arrow("cert", "b", "gp", "t", "allowed gain set")
    d.arrow("gp", "b", "acq", "t", "mu, sigma")
    d.path([(8.3, 1.2), (8.68, 1.2), (8.68, 5.6), (9.0, 5.6)], "proposal (Kp, Ki, context)", li=1, loff=(-0.02, 0))
    d.arrow("gate", "b", "pi", "t", "accepted (bumpless)")
    d.path([(12.65, 4.1), (12.9, 4.1), (12.9, 6.85), (2.2, 6.85), (2.2, 6.25)],
           "i_d* reference to AFE  |  measured v_dc, i_d back to supervisor", li=2)
    d.path([(9.85, 2.55), (9.85, 2.05)], color=EDGE["safe"])
    d.ax.text(9.2, 2.2, "rollback", fontsize=6.8, color=EDGE["safe"], ha="right")
    d.path([(11.8, 2.55), (11.8, 2.05)], color=EDGE["obs"])
    d.ax.text(11.9, 2.2, "events", fontsize=6.8, color=EDGE["obs"])
    d.arrow("dist", "t", "plant", "b", "")
    d.path([(4.05, 1.2), (4.7, 1.2)], "context z", loff=(-0.05, 0.02))
    d.path([(0.35, 5.0), (0.12, 5.0), (0.12, 1.45), (0.35, 1.45)], ls="--", label="")
    d.ax.text(0.2, 0.15, "Hard guarantees come from C (math) and E (independent monitor). The GP in D only decides WHERE to explore "
                         "inside the certified set.", fontsize=7.5, color=INK2, style="italic")
    d.save("01_system_architecture")


def ai_flow():
    d = D(12.5, 4.2, "Safe Bayesian optimisation - one tuning iteration")
    y = 1.5
    steps = [("s1", "1  Context z\nC, Vg, P, mode,\ntau_i, delay", "model"),
             ("s2", "2  Candidates\nT1 grid ∩ T2(z)\n+ baseline seed", "cert"),
             ("s3", "3  GP predict\nmu/sigma of J,\nm_v, m_i", "ai"),
             ("s4", "4  Safe set S\nmu - beta·sigma\n>= h (both)", "ai"),
             ("s5", "5  Acquire\nmax width over\nM ∪ G in S", "ai"),
             ("s6", "6  Gate\nexact re-certify,\nsigma, step, ctx", "safe"),
             ("s7", "7  Probe episode\non plant under\nruntime monitor", "plant"),
             ("s8", "8  Update GPs\n(J, m_v, m_i)\n+ audit record", "obs")]
    for i, (k, t, kind) in enumerate(steps):
        d.box(k, 0.2 + i * 1.55, y, 1.35, 1.5, t, kind, fs=8)
    for i in range(len(steps) - 1):
        d.arrow(steps[i][0], "r", steps[i + 1][0], "l")
    x5 = 0.2 + 4 * 1.55 + 0.675
    x6 = 0.2 + 5 * 1.55 + 0.675
    d.path([(x6, y), (x6, y - 0.45), (x5, y - 0.45), (x5, y)], "rejected -> exclude, re-propose", color=EDGE["safe"], li=1,
           loff=(0, -0.32))
    d.arrow("s8", "t", "s3", "t", "next iteration", rad=0.25, lpos=0.5, loff=(0, 0.35))
    d.ax.text(0.2, 0.25, "Recommendation for deployment: argmin over S of (mu_J + beta·sigma_J) - pessimistic in cost, safe in margins. "
                         "beta = 2, h = 0.15 (config).", fontsize=7.5, color=INK2, style="italic")
    d.save("02_ai_optimisation_flow")


def safety_flow():
    d = D(12.5, 5.6, "Runtime safety and fallback")
    d.box("prop", 0.3, 3.9, 2.2, 1.0, "Recommended / proposed\ngains (Kp, Ki)", "ai", fs=8, bold_first=False)
    checks = [("c1", "Tier-1 robust\nstability (proof)?"), ("c2", "Tier-2 margins for\ncontext set?"),
              ("c3", "GP sigma <= 0.25 and\nLCB(m) >= 0.15?"), ("c4", "Context inside\nenvelope? step <= x3?")]
    for i, (k, t) in enumerate(checks):
        d.box(k, 2.85 + i * 2.0, 3.9, 1.8, 1.0, t, "safe", fs=7.6, bold_first=False)
    d.box("apply", 11.0, 3.9, 1.3, 1.0, "Apply\n(bumpless)", "ctrl", fs=8, bold_first=False)
    d.arrow("prop", "r", "c1", "l")
    for a, b in [("c1", "c2"), ("c2", "c3"), ("c3", "c4"), ("c4", "apply")]:
        d.arrow(a, "r", b, "l", "yes", color=EDGE["ai"], lpos=0.45)
    d.box("rej", 3.0, 2.0, 5.6, 0.9, "REJECT: keep active gains (or baseline)\n+ log GAIN_REJECTED with reason", "safe", fs=8, bold_first=False)
    for k in ("c1", "c2", "c3", "c4"):
        d.arrow(k, "b", "rej", "t", "", color=EDGE["safe"], ls="--")
    d.box("mon", 9.1, 1.9, 3.2, 1.1, "Every 100 us: |e| > 32 V?  |i| > 77.6 A for 2 ms?\noscillation (filtered)?  implausible dv?", "safe", fs=7.5, bold_first=False)
    d.arrow("apply", "b", "mon", "t", "running", lpos=0.4)
    d.box("rb", 3.8, 0.3, 5.0, 0.95, "ROLLBACK to certified baseline PI (bumpless)\nlock out adaptation 100 ms, log reason", "ctrl", fs=8, bold_first=False)
    d.arrow("mon", "b", "rb", "r", "alarm", color=EDGE["safe"], rad=-0.2)
    d.box("re", 0.3, 0.3, 3.0, 0.95, "After lock-out: re-decide\nfor the current context", "model", fs=8, bold_first=False)
    d.arrow("rb", "l", "re", "r", "")
    d.arrow("re", "t", "prop", "b", "", rad=-0.2)
    d.save("03_runtime_safety_fallback")


def electrical():
    d = D(12.5, 5.0, "Electrical block diagram (averaged model) and signals")
    d.box("grid", 0.2, 1.7, 1.6, 1.3, "3-ph grid\n415 V LL\n0.80-1.10 pu", "io", fs=8)
    d.box("afe", 2.3, 1.5, 2.3, 1.7, "Active front end\nPWM rectifier/inverter\ninner i_d loop tau_i\n+ delay 1-2 samples", "plant", fs=8)
    d.box("link", 5.1, 1.5, 1.9, 1.7, "DC link\nC = 2 mF ±20 %\n800 V ref\nR_loss", "plant", fs=8)
    d.box("dcdc", 7.5, 1.5, 2.3, 1.7, "Bidirectional DC-DC\nbattery power loop\ntau 2 ms, slew 2 kW/ms\n±30 kW", "plant", fs=8)
    d.box("bat", 10.3, 1.7, 1.9, 1.3, "EV battery\nG2V: +P\nV2G: -P", "io", fs=8)
    d.arrow("grid", "r", "afe", "l", "P_ac = 1.5·Vg·i_d")
    d.arrow("afe", "r", "link", "l", "P_afe")
    d.arrow("link", "r", "dcdc", "l", "P_dc")
    d.arrow("dcdc", "r", "bat", "l", "")
    d.box("ctl", 3.4, 3.55, 5.8, 0.65, "GainShield voltage controller (PI, 10 kHz)  ->  i_d*  saturated ±80 A", "ctrl", fs=8, bold_first=False)
    d.arrow("link", "t", "ctl", "b", "v_dc (noisy)", lpos=0.5)
    d.arrow("ctl", "l", "afe", "t", "i_d*", rad=0.3)
    d.ax.text(0.2, 0.6, "Sign convention: P_dc > 0 = G2V (energy leaves the link to the battery); P_dc < 0 = V2G. "
                        "AFE losses: P_afe = eta·P_ac (rectifying), P_ac/eta (inverting), eta = 0.98.\n"
                        "Omitted: switching ripple, AC filter and PLL dynamics, unbalance/harmonics, battery voltage dynamics, thermal effects.",
              fontsize=7.5, color=INK2)
    d.save("04_electrical_block_diagram")


def dataflow():
    d = D(12.5, 4.6, "Data flow (files and objects)")
    d.box("cfg", 0.2, 3.0, 2.2, 1.0, "config/default.toml\nall parameters (A-1..A-15)", "io", fs=8)
    d.box("cert", 3.0, 3.0, 2.5, 1.0, "run_certificate.py\n-> certificate.npz", "cert", fs=8)
    d.box("tune", 6.1, 3.0, 2.5, 1.0, "run_tuning.py\n-> gainshield_model.pkl", "ai", fs=8)
    d.box("eval", 9.2, 3.0, 3.0, 1.0, "run_evaluation.py / ablation /\nfailure_injection -> CSV, JSON, PNG", "obs", fs=8)
    d.box("audit", 6.1, 1.2, 2.5, 1.0, "results/audit/*.jsonl\nevery gain decision", "obs", fs=8)
    d.box("dash", 9.2, 1.2, 3.0, 1.0, "dashboard/app.py (Streamlit)\nlive runs + stored results", "obs", fs=8)
    d.box("ppt", 3.0, 1.2, 2.5, 1.0, "docs/ + slides\n(numbers copied from results/)", "model", fs=8)
    d.arrow("cfg", "r", "cert", "l")
    d.arrow("cert", "r", "tune", "l")
    d.arrow("tune", "r", "eval", "l")
    d.arrow("tune", "b", "audit", "t")
    d.arrow("eval", "b", "dash", "t")
    d.arrow("audit", "r", "dash", "l")
    d.arrow("audit", "l", "ppt", "r", "evidence")
    d.ax.text(0.2, 0.4, "Reproducible: fixed seeds; noise sequences pre-drawn per (scenario, seed) so every controller sees identical disturbances.",
              fontsize=7.5, color=INK2, style="italic")
    d.save("05_data_flow")


def modules():
    d = D(12.5, 5.0, "Software modules (package gainshield/)")
    mods = [("config.py", "typed TOML config", "io"), ("plant/charger.py", "averaged plant, RK4", "plant"),
            ("controllers/pi.py\nbaseline.py", "PI, anti-windup,\nsymmetric optimum", "ctrl"),
            ("disturbances/\nscenarios.py", "seeded suite", "model"), ("simulation.py", "closed-loop harness", "model"),
            ("stability/\nlinear_model.py", "exact ZOH + delay", "cert"), ("stability/\ncertify.py", "T1/T2 certificate", "cert"),
            ("optimizer/gp.py\nsafe_bo.py", "GPs, SafeOpt-style", "ai"), ("safety/\nsupervisor.py", "gate + monitor", "safe"),
            ("audit/logger.py", "JSONL audit", "obs"), ("evaluation/\nmetrics.py plots.py", "KPIs, figures", "obs"),
            ("core.py", "orchestration,\nagents, sessions", "ctrl")]
    for i, (a, b, k) in enumerate(mods):
        r, c = divmod(i, 6)
        d.box(f"m{i}", 0.2 + c * 2.05, 2.6 - r * 1.7, 1.85, 1.35, f"{a}\n{b}", k, fs=7.6)
    d.ax.text(0.2, 0.3, "Outside the package: experiments/ (reproducible scripts), dashboard/ (Streamlit), tests/ (pytest, 36 tests), "
                        "diagrams/, docs/.", fontsize=7.5, color=INK2)
    d.save("06_software_modules")


if __name__ == "__main__":
    overall(); ai_flow(); safety_flow(); electrical(); dataflow(); modules()
    print("diagrams written to", OUT)
