"""Build the GainShield TECHgium deck on the official template (v2 design system).

    python presentation/deck_figures.py
    python presentation/build_deck.py presentation/template_base15.pptx presentation/29727.pptx

Design system
  palette   Ink navy 0F1E3D (structure, text) · Shield blue 1F4FBF (GainShield, primary) ·
            Steel 5B6B86 (secondary text) · Mist EEF2F8 (surfaces) · Hairline D5DBE5 ·
            Amber E9A100 (single accent: certified / key numbers) · semantic Safe 138A5E, Fault C23B3B
            (used only for safe/unsafe meaning). Manual-PI baseline is always neutral grey 9AA3B2.
  type      Calibri throughout. Claim line 17 pt bold navy · section label 10 pt bold amber caps ·
            body 12 pt · technical label 9.5 pt steel · stat 26-30 pt bold.
  grid      content x 0.55-12.75 in, top 1.62 in (under claim line), bottom 7.02 in.
Every number on the slides is read from results/ or docs/RESULTS_SNAPSHOT.json.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd
from lxml import etree
from pptx import Presentation
from pptx.chart.data import CategoryChartData
from pptx.dml.color import RGBColor
from pptx.enum.chart import XL_CHART_TYPE, XL_LABEL_POSITION, XL_LEGEND_POSITION, XL_TICK_LABEL_POSITION
from pptx.enum.shapes import MSO_CONNECTOR, MSO_SHAPE
from pptx.enum.text import MSO_ANCHOR, MSO_AUTO_SIZE, PP_ALIGN
from pptx.oxml.ns import qn
from pptx.util import Inches, Pt

ROOT = Path(__file__).resolve().parents[1]
RES = ROOT / "results"
ASSETS = ROOT / "presentation" / "assets"

PID = "TG0929727"
CONCEPT = ("GainShield: AI-Driven Safe Bayesian PI Gain Tuning with Stability Certification and Runtime "
           "Fallback for Bidirectional EV Charger DC-Link Control")
TEAM = [("Archana RG", "photo_archana_rg.jpg"), ("Thiyagarajan Gopalakrishnan", "photo_thiyagarajan_gopalakrishnan.jpg")]
REPO = "github.com/Thiyagadurden/GainShield"

NAVY = RGBColor(0x0F, 0x1E, 0x3D)
BLUE = RGBColor(0x1F, 0x4F, 0xBF)
BLUE2 = RGBColor(0x9D, 0xB4, 0xE0)
BLUE3 = RGBColor(0xDC, 0xE4, 0xF2)
STEEL = RGBColor(0x5B, 0x6B, 0x86)
MIST = RGBColor(0xEE, 0xF2, 0xF8)
PAPER = RGBColor(0xF6, 0xF7, 0xFA)
HAIR = RGBColor(0xD5, 0xDB, 0xE5)
AMBER = RGBColor(0xE9, 0xA1, 0x00)
AMBER_T = RGBColor(0xFD, 0xF3, 0xD9)
SAFE = RGBColor(0x13, 0x8A, 0x5E)
SAFE_T = RGBColor(0xE2, 0xF3, 0xEC)
FAULT = RGBColor(0xC2, 0x3B, 0x3B)
FAULT_T = RGBColor(0xF9, 0xE6, 0xE6)
BASE = RGBColor(0x9A, 0xA3, 0xB2)
WHITE = RGBColor(0xFF, 0xFF, 0xFF)
FONT = "Calibri"
X0, X1 = 0.55, 12.75


# =============================================================================== primitives
def _fmt(run, size, bold=False, color=NAVY, italic=False):
    f = run.font
    f.size, f.bold, f.italic, f.name = Pt(size), bold, italic, FONT
    f.color.rgb = color


def T(sl, x, y, w, h, paras, size=12, color=NAVY, bold=False, align=PP_ALIGN.LEFT, anchor=MSO_ANCHOR.TOP,
      after=3, line=None, name=None):
    """Text box. paras: str | [str | [(text, opts)]]"""
    tb = sl.shapes.add_textbox(Inches(x), Inches(y), Inches(w), Inches(h))
    if name:
        tb.name = name
    tf = tb.text_frame
    tf.word_wrap = True
    tf.auto_size = MSO_AUTO_SIZE.NONE
    tf.vertical_anchor = anchor
    tf.margin_left = tf.margin_right = tf.margin_top = tf.margin_bottom = 0
    for i, p in enumerate([paras] if isinstance(paras, str) else paras):
        para = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        para.alignment = align
        para.space_after = Pt(after)
        if line:
            para.line_spacing = line
        for t, o in (p if isinstance(p, list) else [(p, {})]):
            r = para.add_run()
            r.text = t
            _fmt(r, o.get("size", size), o.get("bold", bold), o.get("color", color), o.get("italic", False))
    return tb


def R(sl, x, y, w, h, fill=None, line=None, lw=1.0, shape=MSO_SHAPE.RECTANGLE, radius=0.06, dash=False, name=None):
    s = sl.shapes.add_shape(shape, Inches(x), Inches(y), Inches(w), Inches(h))
    if name:
        s.name = name
    if fill is None:
        s.fill.background()
    else:
        s.fill.solid()
        s.fill.fore_color.rgb = fill
    if line is None:
        s.line.fill.background()
    else:
        s.line.color.rgb = line
        s.line.width = Pt(lw)
        if dash:
            s.line.dash_style = 7  # dash
    s.shadow.inherit = False
    if shape == MSO_SHAPE.ROUNDED_RECTANGLE:
        s.adjustments[0] = radius
    return s


def L(sl, x1, y1, x2, y2, color=HAIR, w=0.75, arrow=False, dash=False, head="triangle"):
    c = sl.shapes.add_connector(MSO_CONNECTOR.STRAIGHT, Inches(x1), Inches(y1), Inches(x2), Inches(y2))
    c.line.color.rgb = color
    c.line.width = Pt(w)
    ln = c.line._get_or_add_ln()
    if dash:
        d = etree.SubElement(ln, qn("a:prstDash"))
        d.set("val", "dash")
    if arrow:
        t = etree.SubElement(ln, qn("a:tailEnd"))
        t.set("type", head)
        t.set("w", "med")
        t.set("len", "med")
    return c


def path(sl, pts, color=NAVY, w=1.25, dash=False):
    """Orthogonal multi-segment arrow through waypoints (inches)."""
    for i in range(len(pts) - 1):
        L(sl, *pts[i], *pts[i + 1], color=color, w=w, arrow=(i == len(pts) - 2), dash=dash)


def label(sl, x, y, w, s, color=STEEL, size=9.5, align=PP_ALIGN.LEFT, bold=False, h=0.24):
    return T(sl, x, y, w, h, s, size=size, color=color, align=align, bold=bold)


def claim(sl, s):
    T(sl, X0, 1.08, X1 - X0, 0.42, s, size=17, bold=True, color=NAVY, name="Claim")


def kicker(sl, x, y, w, s, color=AMBER, module=None):
    runs = [(s.upper(), {"bold": True, "color": color})]
    if module:
        runs.append(("   " + module, {"bold": False, "color": BLUE}))
    T(sl, x, y, w, 0.24, [runs], size=10)


def source(sl, s, y=7.08):
    T(sl, X0, y, X1 - X0, 0.22, s, size=8.5, color=STEEL, name="Source")


def comp(sl, x, y, w, h, title, sub="", fill=WHITE, line=NAVY, tcolor=NAVY, lw=1.0, tsize=11, ssize=9.5,
         align=PP_ALIGN.LEFT):
    """Component box: bold name + technical sub-label."""
    R(sl, x, y, w, h, fill=fill, line=line, lw=lw, shape=MSO_SHAPE.ROUNDED_RECTANGLE, radius=0.08)
    paras = [[(title, {"bold": True, "size": tsize, "color": tcolor})]]
    if sub:
        paras.append([(sub, {"size": ssize, "color": STEEL if fill in (WHITE, MIST, PAPER) else tcolor})])
    T(sl, x + 0.1, y + 0.05, w - 0.2, h - 0.1, paras, anchor=MSO_ANCHOR.MIDDLE, after=1, align=align)


def dot(sl, x, y, d, txt, fill=NAVY, color=WHITE, size=10):
    s = R(sl, x, y, d, d, fill=fill, shape=MSO_SHAPE.OVAL)
    tf = s.text_frame
    tf.margin_left = tf.margin_right = tf.margin_top = tf.margin_bottom = 0
    tf.vertical_anchor = MSO_ANCHOR.MIDDLE
    p = tf.paragraphs[0]
    p.alignment = PP_ALIGN.CENTER
    r = p.add_run()
    r.text = txt
    _fmt(r, size, True, color)
    return s


def chip(sl, x, y, w, txt, fill=MIST, color=NAVY, size=9.5, h=0.27):
    R(sl, x, y, w, h, fill=fill, shape=MSO_SHAPE.ROUNDED_RECTANGLE, radius=0.5)
    T(sl, x, y, w, h, txt, size=size, color=color, align=PP_ALIGN.CENTER, anchor=MSO_ANCHOR.MIDDLE, bold=True)


def stat(sl, x, y, w, num, lab, color=BLUE, nsize=28):
    T(sl, x, y, w, 0.55, num, size=nsize, bold=True, color=color)
    T(sl, x, y + 0.58, w, 0.5, lab, size=10, color=STEEL)


def pic(sl, f, x, y, w=None, h=None):
    return sl.shapes.add_picture(str(f), Inches(x), Inches(y), Inches(w) if w else None, Inches(h) if h else None)


def ledger(sl, x, y, w, rows, colw, size=10.5, rowh=0.36, header=True, bold_col0=True):
    """Hairline table drawn with text boxes and rules (editorial, no cell fills)."""
    yy = y
    for ri, row in enumerate(rows):
        hdr = header and ri == 0
        h = rowh if not isinstance(row[-1], tuple) else row[-1][1]
        cells = row if not isinstance(row[-1], tuple) else row[:-1]
        xx = x
        for ci, (c, cw) in enumerate(zip(cells, colw)):
            opts = {}
            if isinstance(c, dict):
                opts = c
                c = c["t"]
            T(sl, xx + 0.04, yy + 0.04, cw - 0.1, h - 0.06, c, size=opts.get("size", 9.5 if hdr else size),
              bold=hdr or opts.get("bold", bold_col0 and ci == 0), color=opts.get("color", STEEL if hdr else NAVY),
              anchor=MSO_ANCHOR.MIDDLE)
            xx += cw
        yy += h
        L(sl, x, yy, x + w, yy, color=NAVY if hdr else HAIR, w=1.0 if hdr else 0.6)
    return yy


def remove_body(sl):
    for sh in list(sl.shapes):
        if sh.is_placeholder and sh.placeholder_format.idx != 0:
            sh._element.getparent().remove(sh._element)


def set_title(sl, s):
    for sh in sl.shapes:
        if sh.is_placeholder and sh.placeholder_format.idx == 0:
            runs = sh.text_frame.paragraphs[0].runs
            runs[0].text = s
            for r in runs[1:]:
                r.text = ""


def notes(sl, s):
    sl.notes_slide.notes_text_frame.text = s


def hbar(sl, x, y, w, h, cats, series, colors, fmt='0.0"%"', size=10, legend=True, gap=40, overlap=0, point_colors=None,
         axis_max=None, axis_min=None, title=None):
    cd = CategoryChartData()
    cd.categories = cats
    for n, v in series:
        cd.add_series(n, v)
    gf = sl.shapes.add_chart(XL_CHART_TYPE.BAR_CLUSTERED, Inches(x), Inches(y), Inches(w), Inches(h), cd)
    ch = gf.chart
    ch.font.name, ch.font.size = FONT, Pt(size)
    ch.font.color.rgb = STEEL
    ch.has_title = bool(title)
    if title:
        ch.chart_title.text_frame.text = title
        for r in ch.chart_title.text_frame.paragraphs[0].runs:
            _fmt(r, 11, True, NAVY)
    ch.has_legend = legend
    if legend:
        ch.legend.position = XL_LEGEND_POSITION.TOP
        ch.legend.include_in_layout = False
        ch.legend.font.size = Pt(size)
    pl = ch.plots[0]
    pl.gap_width, pl.overlap = gap, overlap
    pl.has_data_labels = True
    dl = pl.data_labels
    dl.number_format, dl.number_format_is_linked = fmt, False
    dl.font.size = Pt(size - 0.5)
    dl.font.color.rgb = NAVY
    dl.position = XL_LABEL_POSITION.OUTSIDE_END
    for s_, c in zip(pl.series, colors):
        s_.format.fill.solid()
        s_.format.fill.fore_color.rgb = c
        s_.invert_if_negative = False
    if point_colors:
        for i, c in enumerate(point_colors):
            pt = pl.series[0].points[i]
            pt.format.fill.solid()
            pt.format.fill.fore_color.rgb = c
    va = ch.value_axis
    va.has_major_gridlines = False
    va.visible = False
    if axis_max is not None:
        va.maximum_scale = axis_max
    if axis_min is not None:
        va.minimum_scale = axis_min
    ca = ch.category_axis
    ca.reverse_order = True
    ca.tick_labels.font.size = Pt(size)
    ca.tick_labels.font.color.rgb = NAVY
    ca.format.line.color.rgb = HAIR
    ca.has_major_gridlines = False
    ca.tick_label_position = XL_TICK_LABEL_POSITION.LOW
    return gf


def sgn(v, d=1, unit=" %"):
    """Signed number with a true minus sign."""
    t = f"{abs(v):.{d}f}{unit}"
    return ("−" if v < 0 else "+") + t


# =============================================================================== data
NAMES = {"load_increase": "load step 5 → 20 kW", "load_decrease": "load step 20 → 5 kW", "g2v_to_v2g": "G2V → V2G reversal",
         "v2g_to_g2v": "V2G → G2V reversal", "grid_sag": "grid sag", "sensor_noise": "3× sensor noise",
         "cap_minus20": "C −20 %", "cap_plus20": "C +20 %", "inner_lag_slow": "slow inner loop",
         "delay_long": "2-sample delay", "combined": "combined stress"}


def headline(ev):
    """Measured headline figures: best case, mean where GainShield adapts, mean over all scenarios."""
    ps = ev["per_scenario"]
    ch = {k: v["peak_dev_pct"]["change_pct"] for k, v in ps.items()}
    ia = {k: v["IAE_Vs"]["change_pct"] for k, v in ps.items()}
    adapted = [k for k, c in ch.items() if c < -1.0]
    best = min(ch, key=ch.get)
    return {"best_key": best, "best_name": NAMES[best], "best": -ch[best], "best_iae": -min(ia.values()),
            "best_iae_name": NAMES[min(ia, key=ia.get)],
            "n_adapt": len(adapted), "n_all": len(ch),
            "adapt_mean": -sum(ch[k] for k in adapted) / max(len(adapted), 1),
            "adapt_iae": -sum(ia[k] for k in adapted) / max(len(adapted), 1),
            "all_mean": -ev["paired"]["peak_dev_pct"]["mean_relative_change_pct"],
            "all_iae": -ev["paired"]["IAE_Vs"]["mean_relative_change_pct"]}


def load():
    snap = json.loads((ROOT / "docs" / "RESULTS_SNAPSHOT.json").read_text())
    return (snap["evaluation"], pd.read_csv(RES / "ablation.csv"), pd.read_csv(RES / "failure_injection.csv"),
            json.loads((RES / "certificate_summary.json").read_text()))


# =============================================================================== slides
def s02_challenge(sl, ev):
    remove_body(sl)
    claim(sl, "The DC-link loop is tuned once by hand, but the plant it controls changes in every charging session")
    kicker(sl, X0, 1.68, 7.0, "Where the plant moves · averaged 30 kW / 800 V module")
    # ---- power path schematic
    bus = 2.95
    L(sl, 0.75, bus, 6.86, bus, color=NAVY, w=2.25)
    # grid source
    s = R(sl, 0.62, bus - 0.33, 0.66, 0.66, fill=WHITE, line=NAVY, lw=1.5, shape=MSO_SHAPE.OVAL)
    T(sl, 0.62, bus - 0.33, 0.66, 0.66, "3~", size=13, bold=True, align=PP_ALIGN.CENTER, anchor=MSO_ANCHOR.MIDDLE)
    blocks = [(1.85, "AFE", "PWM rectifier /\ninverter"), (5.05, "DC-DC", "battery power\nloop")]
    for x, t_, s_ in blocks:
        R(sl, x, bus - 0.42, 1.15, 0.84, fill=WHITE, line=NAVY, lw=1.5)
        T(sl, x, bus - 0.42, 1.15, 0.84, [[(t_, {"bold": True, "size": 12})], [(s_, {"size": 8.5, "color": STEEL})]],
          align=PP_ALIGN.CENTER, anchor=MSO_ANCHOR.MIDDLE, after=0)
    # capacitor symbol
    cx = 4.05
    L(sl, cx, bus, cx, bus + 0.3, color=NAVY, w=1.5)
    L(sl, cx - 0.28, bus + 0.3, cx + 0.28, bus + 0.3, color=NAVY, w=2.5)
    L(sl, cx - 0.28, bus + 0.42, cx + 0.28, bus + 0.42, color=NAVY, w=2.5)
    L(sl, cx, bus + 0.42, cx, bus + 0.62, color=NAVY, w=1.5)
    T(sl, cx - 0.75, bus - 0.62, 1.5, 0.45, [[("DC link", {"bold": True, "size": 11})], [("v_dc ≈ 800 V", {"size": 9, "color": STEEL})]],
      align=PP_ALIGN.CENTER, after=0)
    # battery
    R(sl, 6.85, bus - 0.36, 0.78, 0.72, fill=WHITE, line=NAVY, lw=1.5, shape=MSO_SHAPE.ROUNDED_RECTANGLE, radius=0.1)
    T(sl, 6.85, bus - 0.36, 0.78, 0.72, [[("EV", {"bold": True, "size": 12})], [("battery", {"size": 8.5, "color": STEEL})]],
      align=PP_ALIGN.CENTER, anchor=MSO_ANCHOR.MIDDLE, after=0)
    # power flow arrow
    L(sl, 1.95, 2.08, 6.9, 2.08, color=BLUE, w=1.5, arrow=True)
    L(sl, 6.9, 2.08, 1.95, 2.08, color=BLUE, w=1.5, arrow=True)
    T(sl, 3.1, 1.92, 2.6, 0.24, "G2V  ⇄  V2G   power flow", size=9.5, color=BLUE, bold=True, align=PP_ALIGN.CENTER)
    # control loop
    R(sl, 2.6, 4.05, 2.15, 0.6, fill=NAVY, shape=MSO_SHAPE.ROUNDED_RECTANGLE, radius=0.12)
    T(sl, 2.6, 4.05, 2.15, 0.6, [[("PI voltage controller", {"bold": True, "size": 11, "color": WHITE})],
                                 [("fixed Kp, Ki · 10 kHz", {"size": 9, "color": BLUE3})]],
      align=PP_ALIGN.CENTER, anchor=MSO_ANCHOR.MIDDLE, after=0)
    path(sl, [(cx, bus + 0.62), (cx, 4.05)], color=STEEL, w=1.0)
    label(sl, cx + 0.06, 3.62, 1.0, "v_dc measured", size=8.5)
    path(sl, [(2.6, 4.35), (2.42, 4.35), (2.42, bus + 0.42)], color=STEEL, w=1.0)
    label(sl, 1.35, 3.62, 1.0, "i_d* command", size=8.5, align=PP_ALIGN.RIGHT)
    # disturbance markers
    marks = [(0.84, 2.42, "1"), (2.3, 2.42, "2"), (3.38, 3.17, "3"), (6.15, 2.42, "4")]
    for x, y, n in marks:
        dot(sl, x, y, 0.27, n, fill=AMBER, color=NAVY, size=10)
    items = [("1", "Grid", "sags to 0.80 pu; rises to 1.10 pu"), ("2", "Inner loop", "lag 0.3–1.0 ms, delay 1–2 samples"),
             ("3", "Capacitor", "C ±20 % with tolerance and ageing"), ("4", "Load", "constant-power DC-DC; ±15 kW reversal")]
    for i, (n, t_, s_) in enumerate(items):
        x = X0 + (i % 2) * 3.6
        y = 4.95 + (i // 2) * 0.42
        dot(sl, x, y + 0.01, 0.24, n, fill=AMBER, color=NAVY, size=9)
        T(sl, x + 0.34, y, 3.2, 0.26, anchor=MSO_ANCHOR.MIDDLE, paras= [[(t_ + "  ", {"bold": True, "size": 11}), (s_, {"size": 10.5, "color": STEEL})]])
    # ---- evidence chart
    ps = ev["per_scenario"]
    kicker(sl, 8.3, 1.68, 4.45, "Evidence · one fixed PI, five conditions")
    cats = ["Load step 5→20 kW", "C −20 %", "Slow inner loop", "Power reversal", "Combined stress"]
    keys = ["load_increase", "cap_minus20", "inner_lag_slow", "g2v_to_v2g", "combined"]
    vals = [ps[k]["peak_dev_pct"]["baseline"] for k in keys]
    hbar(sl, 8.3, 1.98, 4.45, 2.75, cats, [("manual PI", vals)], [BASE], legend=False, gap=55, axis_max=4.2, fmt='0.0" %"',
         point_colors=[BASE, BASE, BASE, NAVY, NAVY])
    T(sl, 8.3, 4.78, 4.45, 0.6, "Peak DC-link deviation (% of 800 V) of the manually tuned PI, mean of 5 seeds. The same gains "
                                "give almost twice the deviation under reversal and combined stress.", size=9.5, color=STEEL)
    # ---- challenge band
    R(sl, X0, 5.9, X1 - X0, 1.1, fill=NAVY)
    T(sl, X0 + 0.25, 6.02, 2.0, 0.3, "THE CHALLENGE", size=10, bold=True, color=AMBER)
    T(sl, X0 + 0.25, 6.3, 2.4, 0.6, "Tune online, without ever experimenting blindly on 800 V", size=11.5, bold=True,
      color=WHITE)
    reqs = [("Adapt", "set Kp, Ki for the current grid, load, capacitance and power direction"),
            ("Prove", "apply only gains shown stable beforehand; unrestricted BO or RL could try an unstable pair"),
            ("Fall back · audit", "revert instantly to a known-good controller and log every decision")]
    for i, (t_, s_) in enumerate(reqs):
        x = 3.35 + i * 3.15
        L(sl, x - 0.15, 6.05, x - 0.15, 6.85, color=STEEL, w=0.75)
        T(sl, x, 6.02, 2.95, 0.95, [[(t_, {"bold": True, "size": 12, "color": AMBER})], [(s_, {"size": 10.5, "color": WHITE})]],
          after=2)
    notes(sl, "Numbered markers show where the plant varies. The chart is measured: the manually tuned baseline's peak "
              "deviation in five of the eleven test scenarios. All parameters are engineering assumptions.")


def s03_concept(sl, ev, cert):
    remove_body(sl)
    H = headline(ev)
    claim(sl, "GainShield nests the AI inside a stability proof, which conventional manual or AI tuning cannot offer")
    kicker(sl, X0, 1.68, 6.6, "The safety envelope in the Kp–Ki plane")
    rings = [(X0, 2.0, 6.75, 4.95, PAPER, HAIR, "Search box", "Kp 0.2–12 A/V × Ki 5–5000 A/(V·s) · 41 × 41 log grid", "configured bounds", NAVY),
             (X0 + 0.3, 2.62, 6.15, 4.15, BLUE3, None, "Tier 1 · robust stability", f"stable for every plant in the uncertainty set · {100 * cert['fraction_robust_stable']:.0f} % of grid", "proof, offline", NAVY),
             (X0 + 0.6, 3.24, 5.55, 3.35, BLUE2, None, "Tier 2 · context margins", "PM ≥ 40°, GM ≥ 6 dB, |1+L| ≥ 0.5 for the current context ± error", "proof + sweep, per context", NAVY),
             (X0 + 0.9, 3.86, 4.95, 2.55, BLUE, None, "GP safe set S", "lower confidence bound of V and I margins ≥ 0.15", "Gaussian processes, online", WHITE)]
    for x, y, w, h, f, ln, t_, s_, who, c in rings:
        R(sl, x, y, w, h, fill=f, line=ln, lw=0.75, shape=MSO_SHAPE.ROUNDED_RECTANGLE, radius=0.05)
        T(sl, x + 0.2, y + 0.1, w - 2.1, 0.5, [[(t_, {"bold": True, "size": 11.5, "color": c})],
                                              [(s_, {"size": 9, "color": c if c == WHITE else STEEL})]], after=0)
        T(sl, x + w - 1.95, y + 0.1, 1.8, 0.25, who, size=9, color=c if c == WHITE else STEEL, align=PP_ALIGN.RIGHT,
          bold=True)
    # inner: seed and deployed
    R(sl, X0 + 1.4, 4.75, 3.95, 1.45, fill=WHITE, shape=MSO_SHAPE.ROUNDED_RECTANGLE, radius=0.06)
    s = R(sl, X0 + 1.65, 5.03, 0.3, 0.3, fill=AMBER, shape=MSO_SHAPE.DIAMOND)
    T(sl, X0 + 2.08, 4.95, 3.2, 0.45, [[("Baseline seed", {"bold": True, "size": 11})],
                                      [("certified manual PI: always allowed, always the fallback", {"size": 9, "color": STEEL})]], after=0)
    R(sl, X0 + 1.65, 5.62, 0.3, 0.3, fill=BLUE, shape=MSO_SHAPE.STAR_5_POINT)
    T(sl, X0 + 2.08, 5.55, 3.2, 0.5, [[("Deployed gains", {"bold": True, "size": 11})],
                                     [("argmin over S of pessimistic cost, re-checked by the gate", {"size": 9, "color": STEEL})]], after=0)
    # right: advantages over conventional techniques (the GainShield column is highlighted)
    xr = 7.65
    kicker(sl, xr, 1.68, X1 - xr, "Advantages over conventional techniques")
    cw = [2.2, 0.92, 0.98, 1.0]
    xg = xr + sum(cw[:3])
    top, hh, rh = 1.98, 0.55, 0.43
    rows = [("Adapts to grid, load, capacitor", ("✗", "no"), ("✓", "yes"), "yes"),
            ("Proven stable before use", ("~", "one point"), ("✗", "no"), "whole set"),
            ("Safe while learning on the live loop", ("–", "n/a"), ("✗", "no"), "yes"),
            ("Falls back automatically", ("✗", "no"), ("✗", "no"), "yes"),
            ("Every gain change audited", ("✗", "no"), ("✗", "no"), "yes"),
            ("Peak voltage deviation (simulation)", ("", "reference"), ("", "not tested"), f"up to −{H['best']:.0f} %")]
    nrow = len(rows)
    R(sl, xg, top - 0.08, cw[3], hh + nrow * rh + 0.16, fill=BLUE, shape=MSO_SHAPE.ROUNDED_RECTANGLE, radius=0.06)
    for i, h_ in enumerate(["", "Manual PI", "Plain BO / RL", "GainShield"]):
        x = xr + sum(cw[:i])
        T(sl, x, top, cw[i], hh, h_, size=11, bold=True, color=WHITE if i == 3 else STEEL, align=PP_ALIGN.CENTER,
          anchor=MSO_ANCHOR.MIDDLE)
    L(sl, xr, top + hh, xg, top + hh, color=NAVY, w=1.0)
    for r, (crit, m, b_, g) in enumerate(rows):
        y = top + hh + r * rh
        T(sl, xr, y, cw[0] - 0.05, rh, crit, size=10.5, bold=True, color=NAVY, anchor=MSO_ANCHOR.MIDDLE)
        for j, (sym, word) in enumerate([m, b_]):
            x = xr + sum(cw[:j + 1])
            col = FAULT if sym == "✗" else (SAFE if sym == "✓" else STEEL)
            T(sl, x, y, cw[j + 1], rh, [[((sym + " ") if sym else "", {"bold": True, "color": col, "size": 11}),
                                         (word, {"size": 10, "color": STEEL})]], align=PP_ALIGN.CENTER,
              anchor=MSO_ANCHOR.MIDDLE)
        T(sl, xg, y, cw[3], rh, [[("✓ " if r < nrow - 1 else "", {"bold": True, "size": 11, "color": AMBER}),
                                  (g, {"bold": True, "size": 10.5, "color": WHITE})]], align=PP_ALIGN.CENTER,
          anchor=MSO_ANCHOR.MIDDLE)
        if r < nrow - 1:
            L(sl, xr, y + rh, xg, y + rh, color=HAIR, w=0.6)
    # three headline advantages
    yb = top + hh + nrow * rh + 0.32
    adv = [("Better regulation", f"up to {H['best']:.0f} % smaller voltage swings ({H['best_name']}); "
                                 f"{H['adapt_mean']:.0f} % on average where it adapts"),
           ("Safer than plain AI tuning", f"none of {ev['tuning']['episodes_run']} live learning trials left the ±5 % safe band"),
           ("Accountable", "every gain change is logged with its reason and can be replayed")]
    for i, (h_, b2) in enumerate(adv):
        y = yb + i * 0.5
        dot(sl, xr, y + 0.1, 0.26, str(i + 1), fill=AMBER, color=NAVY, size=9)
        T(sl, xr + 0.38, y, X1 - xr - 0.38, 0.46, [[(h_ + "  ", {"bold": True, "size": 12, "color": NAVY}),
                                                 (b2, {"size": 10.5, "color": STEEL})]], anchor=MSO_ANCHOR.MIDDLE)
    notes(sl, "Read the left diagram from outside in: configured box, tier-1 proof (offline), tier-2 context margins, "
              "GP safe set. The deployed gains are always inside all of them; the baseline is the seed and fallback.")


def s05_arch(sl):
    remove_body(sl)
    set_title(sl, "Technical Description")
    claim(sl, "System architecture: four layers separated by time-scale and by trust")
    lanes = [("OFFLINE", "once per configuration", 1.62, 2.6, PAPER),
             ("SUPERVISORY", "ms to s · decides gains", 2.66, 4.08, WHITE),
             ("REAL-TIME", "every 100 µs · 10 kHz", 4.14, 5.3, PAPER),
             ("PLANT", "simulated, averaged", 5.36, 6.62, WHITE)]
    for t_, s_, y0, y1, f in lanes:
        R(sl, X0, y0, X1 - X0, y1 - y0, fill=f, line=None)
        T(sl, X0 + 0.12, y0 + 0.1, 1.35, 0.6, [[(t_, {"bold": True, "size": 10, "color": NAVY})],
                                               [(s_, {"size": 8.5, "color": STEEL})]], after=0)
        L(sl, X0, y1, X1, y1, color=HAIR, w=0.6)
    # lane A
    comp(sl, 2.05, 1.75, 1.75, 0.7, "Parameters", "config/default.toml")
    comp(sl, 4.15, 1.75, 2.75, 0.7, "Tier-1 certificate", "stability/certify.py · zero-exclusion, 88 nodes")
    comp(sl, 7.25, 1.75, 1.85, 0.7, "certificate.npz", "regions + worst margins", fill=MIST, line=HAIR)
    path(sl, [(3.8, 2.1), (4.15, 2.1)])
    path(sl, [(6.9, 2.1), (7.25, 2.1)])
    # lane B
    yb, hb = 2.85, 0.9
    comp(sl, 2.05, yb, 1.6, hb, "Context", "C, Vg, P, mode,\nτ_i, delay (estimated)")
    comp(sl, 4.15, yb, 1.6, hb, "Tier-2 check", "local margins for\ncontext ± error")
    comp(sl, 6.25, yb, 1.95, hb, "SafeBayesOpt", "3 GPs (J, m_v, m_i)\nsafe set + acquisition", line=BLUE, lw=1.5, tcolor=BLUE)
    comp(sl, 8.75, yb, 1.75, hb, "CandidateGate", "exact re-certify · σ\nenvelope · step ≤ ×3", line=FAULT, lw=1.5, tcolor=FAULT)
    comp(sl, 11.0, yb, 1.6, hb, "AuditLogger", "append-only JSONL\n+ trace check", fill=AMBER_T, line=AMBER)
    ym = yb + hb / 2
    for a_, b_, lab in [(3.65, 4.15, "ctx"), (5.75, 6.25, "mask"), (8.2, 8.75, "Kp, Ki"), (10.5, 11.0, "log")]:
        path(sl, [(a_, ym), (b_, ym)])
        label(sl, a_, ym - 0.25, b_ - a_, lab, size=8.5, align=PP_ALIGN.CENTER)
    path(sl, [(8.15, 2.45), (8.15, 2.62), (7.25, 2.62), (7.25, yb)], color=STEEL, w=1.0)
    label(sl, 8.24, 2.42, 1.6, "Tier-1 candidates", size=8.5)
    # lane C
    yc, hc = 4.3, 0.85
    comp(sl, 6.25, yc, 1.95, hc, "Baseline gains", "certified manual PI\n(symmetric optimum)", fill=MIST, line=HAIR)
    comp(sl, 8.55, yc, 1.8, hc, "PIController", "anti-windup clamp\nbumpless set_gains()", line=NAVY, lw=1.5)
    comp(sl, 10.75, yc, 1.85, hc, "RuntimeMonitor", "|e| > 4 % · I hold\noscillation · dV/sample", line=FAULT, lw=1.5, tcolor=FAULT)
    path(sl, [(9.45, yb + hb), (9.45, yc)], color=BLUE, w=1.5)
    label(sl, 9.52, yb + hb + 0.06, 1.2, "accepted gains", size=8.5, color=BLUE)
    path(sl, [(8.2, yc + 0.6), (8.55, yc + 0.6)], color=FAULT, w=1.25)
    label(sl, 6.25, yc + hc + 0.02, 2.3, "fallback gains on rollback", size=8.5, color=FAULT)
    path(sl, [(10.75, yc + 0.25), (10.35, yc + 0.25)], color=FAULT, w=1.25)
    label(sl, 10.3, yc + 0.0, 0.5, "alarm", size=8.5, color=FAULT, align=PP_ALIGN.CENTER)
    path(sl, [(12.1, yc), (12.1, yb + hb)], color=AMBER, w=1.25)
    label(sl, 12.16, yb + hb + 0.06, 0.6, "events", size=8.5, color=AMBER)
    # lane D
    yd, hd = 5.52, 0.88
    comp(sl, 4.15, yd, 2.75, hd, "Disturbance suite", "disturbances/scenarios.py\n10 classes, seeded, pre-drawn noise")
    comp(sl, 7.25, yd, 5.35, hd, "ChargerPlant", "plant/charger.py · AFE + inner i_d loop + delay · DC link C·v·dv/dt = P_afe − P_dc − v²/R · "
                                                "constant-power DC-DC · RK4, 10 µs", line=AMBER, lw=1.5)
    path(sl, [(6.9, yd + hd / 2), (7.25, yd + hd / 2)])
    path(sl, [(9.0, yc + hc), (9.0, yd)], color=NAVY, w=1.5)
    label(sl, 9.07, yc + hc + 0.02, 1.0, "i_d* ≤ 80 A", size=8.5, color=NAVY)
    path(sl, [(11.4, yd), (11.4, yc + hc)], color=NAVY, w=1.5)
    label(sl, 11.47, yd - 0.22, 1.2, "v_dc, i_d (noisy)", size=8.5, color=NAVY)
    path(sl, [(7.6, yd + hd), (7.6, 6.52), (2.92, 6.52), (2.92, yb + hb)], color=STEEL, w=1.0, dash=True)
    label(sl, 3.02, 4.45, 2.2, "operating point →\ncontext estimate", size=8.5, h=0.4)
    # legend + note
    lx = X0
    for i, (c, t_) in enumerate([(NAVY, "signals / data"), (BLUE, "gain write"), (FAULT, "safety path"), (AMBER, "audit")]):
        L(sl, lx + i * 1.55, 6.84, lx + i * 1.55 + 0.35, 6.84, color=c, w=2)
        label(sl, lx + i * 1.55 + 0.42, 6.72, 1.1, t_, size=9)
    T(sl, 6.85, 6.7, X1 - 6.85, 0.36, "Implemented: all four layers run in one Python process (simulation). The lane split is the "
                                     "proposed PC / microcontroller deployment for HIL, not yet built.", size=9, color=STEEL)
    notes(sl, "Every box is a real class or module in the repository. The real-time lane is simulated in Python today.")


def s06_algo(sl, cert):
    remove_body(sl)
    set_title(sl, "Technical Description")
    claim(sl, "Two algorithms: an exact robust-stability test and a safe contextual Bayesian optimiser")
    # ---- left: certificate
    kicker(sl, X0, 1.68, 5.9, "A · Certificate", module="stability/linear_model.py · certify.py")
    k0, k1 = cert["k_interval"]
    steps = [("1", "Model the sampled charger loop exactly", "includes the 1–2 sample delay and inner-loop lag λ = e^(−Ts/τ_i):",
              "P(z) = k · N̂(z) / ((z − 1)(z − λ) z^(d+1))"),
             ("2", "Collapse all uncertainty into one gain k", f"C ±20 %, grid 0.8–1.1 pu and power direction enter only via k ∈ [{k0:.0f}, {k1:.0f}]:",
              "p(z; k) = D(z) + k · N(z)      affine in k"),
             ("3", "Test every gain pair over the whole k range", "if stable at k_min and no k in the range puts a root on "
                                          "|z| = 1, it is stable for all k. Crossings are found as the unit-circle roots of",
              "F(z) = D(z)·rev N(z) − rev D(z)·N(z)")]
    y = 2.0
    for n, t_, s_, eq in steps:
        dot(sl, X0, y + 0.03, 0.3, n, fill=NAVY, size=10)
        T(sl, X0 + 0.42, y, 5.45, 0.9, [[(t_, {"bold": True, "size": 11.5})], [(s_, {"size": 10, "color": STEEL})],
                                        [(eq, {"size": 11.5, "bold": True, "color": BLUE})]], after=1)
        y += 0.92 if n != "3" else 1.08
    pic(sl, ASSETS / "fig_regions.png", X0, 4.85, h=2.2)
    lx = X0 + 2.95
    for i, (c, t_) in enumerate([(RGBColor(0xF4, 0xF5, 0xF8), "unstable"), (BLUE3, "nominal only"),
                                 (BLUE2, f"Tier 1 robust · {100 * cert['fraction_robust_stable']:.0f} %"),
                                 (BLUE, f"globally certified · {100 * cert['fraction_certified']:.0f} %")]):
        R(sl, lx, 4.98 + i * 0.3, 0.22, 0.18, fill=c, line=HAIR, lw=0.5)
        label(sl, lx + 0.3, 4.93 + i * 0.3, 2.6, t_, size=9.5, color=NAVY)
    T(sl, lx, 6.2, 3.0, 0.85, [[("Verified: ", {"bold": True, "size": 9.5}),
                               ("100 % agreement with brute-force eigenvalue sweeps; predicts nonlinear instability onset "
                                "within ±3 % (5/5 cases).", {"size": 9.5, "color": STEEL})]])
    L(sl, 6.65, 1.72, 6.65, 7.0, color=HAIR, w=0.75)
    # ---- right: algorithm
    xr = 6.9
    kicker(sl, xr, 1.68, X1 - xr, "B · Safe contextual BO, one iteration", module="optimizer/safe_bo.py")
    R(sl, xr, 1.98, X1 - xr, 3.72, fill=PAPER, line=HAIR, lw=0.6)
    lines = [("z ← context estimate (C, Vg, P, τ_i, delay)", ""),
             ("X ← Tier-1 grid ∩ Tier-2(z) ∪ {baseline}", "candidates"),
             ("μ, σ ← GP_J, GP_v, GP_i at (X, z)", "Matern-5/2"),
             ("S ← { x : μ_m − β σ_m ≥ h  for m ∈ {v, i} }", "safe set"),
             ("M ← { x ∈ S : LCB_J(x) ≤ min_S UCB_J }", "maximisers"),
             ("G ← { x ∈ S : UCB_m(x) − L‖x − x′‖ ≥ h, x′ ∉ S }", "expanders"),
             ("x* ← argmax over M ∪ G of confidence width", ""),
             ("if Gate(x*) rejects: exclude x*, re-propose", "independent"),
             ("probe episode under RuntimeMonitor → J, m_v, m_i", "on plant"),
             ("refit the three GPs; write audit record", "")]
    for i, (code, tag) in enumerate(lines):
        yy = 2.1 + i * 0.355
        T(sl, xr + 0.12, yy, 0.3, 0.3, f"{i + 1}", size=9.5, color=STEEL, align=PP_ALIGN.RIGHT)
        T(sl, xr + 0.55, yy, 4.0, 0.3, code, size=11, color=NAVY, bold=i in (3, 7))
        if tag:
            T(sl, X1 - 1.15, yy + 0.02, 1.05, 0.3, tag, size=9, color=BLUE, align=PP_ALIGN.RIGHT)
    chips = ["β = 2", "h = 0.15", "σ_max = 0.25", "step ≤ ×3", "41 × 41 grid", "zero-prior GPs"]
    cx = xr
    for c in chips:
        w = 0.22 + 0.068 * len(c)
        chip(sl, cx, 5.82, w, c)
        cx += w + 0.08
    T(sl, xr, 6.22, X1 - xr, 0.85, [[("Probe cost  ", {"bold": True, "size": 10}),
                                     ("J = 0.35 IAE + 0.25 peak dev. + 0.10 overshoot + 0.10 settling + 0.20 ripple (each ÷ baseline). ",
                                      {"size": 10, "color": STEEL})],
                                    [("Follows SafeOpt [1] and its contextual form [2]; their theoretical guarantee is not claimed.",
                                      {"size": 9.5, "color": STEEL, "italic": True})]], after=2)
    notes(sl, "Left: why the certificate is exact in k. Right: the iteration exactly as implemented in SafeBayesOpt.propose "
              "and GainShield.tune_context.")


def s07_sequence(sl, fi):
    remove_body(sl)
    set_title(sl, "Technical Description")
    claim(sl, "Runtime sequence: every gain change is proposed, re-checked, applied bumplessly and logged")
    lanes = ["ChargerPlant", "RuntimeMonitor", "PIController", "GainShieldAgent", "SafeBayesOpt", "CandidateGate", "AuditLogger"]
    xs = [1.05 + i * 1.22 for i in range(7)]
    top, bot = 1.68, 6.95
    for x, n in zip(xs, lanes):
        hi = n in ("RuntimeMonitor", "CandidateGate")
        R(sl, x - 0.57, top, 1.14, 0.42, fill=NAVY if not hi else FAULT, shape=MSO_SHAPE.ROUNDED_RECTANGLE, radius=0.12)
        T(sl, x - 0.57, top, 1.14, 0.42, n, size=9, bold=True, color=WHITE, align=PP_ALIGN.CENTER, anchor=MSO_ANCHOR.MIDDLE)
        L(sl, x, top + 0.42, x, bot, color=HAIR, w=1.0, dash=True)
    X = dict(zip(lanes, xs))

    def msg(a, b, y, txt, color=NAVY, ret=False, w=1.25):
        L(sl, X[a], y, X[b], y, color=color, w=w, arrow=True, dash=ret)
        mid = (X[a] + X[b]) / 2
        T(sl, mid - 1.5, y - 0.24, 3.0, 0.22, txt, size=8.5, color=color, align=PP_ALIGN.CENTER)

    def note(a, y, txt, h=0.42, w=2.3, color=STEEL, fill=PAPER):
        R(sl, X[a] - w / 2, y, w, h, fill=fill, line=HAIR, lw=0.5)
        T(sl, X[a] - w / 2 + 0.06, y, w - 0.12, h, txt.split("\n"), size=8.5, color=color, anchor=MSO_ANCHOR.MIDDLE,
          align=PP_ALIGN.CENTER, after=0)

    note("GainShieldAgent", 2.28, "context change held 5 ms:\nΔVg > 0.05 pu · ΔP > 3 kW · mode", h=0.44, w=2.35)
    msg("GainShieldAgent", "SafeBayesOpt", 3.0, "recommend(z, Tier-2 mask)")
    msg("SafeBayesOpt", "GainShieldAgent", 3.3, "Kp, Ki, σ, LCB", ret=True)
    msg("GainShieldAgent", "CandidateGate", 3.65, "evaluate(proposal, context)", color=FAULT)
    note("CandidateGate", 3.78, "exact re-certify · σ ≤ 0.25\nLCB ≥ 0.15 · envelope · ×3", h=0.44, w=2.2, color=FAULT, fill=FAULT_T)
    msg("CandidateGate", "GainShieldAgent", 4.45, "accept / reject + reason", color=FAULT, ret=True)
    msg("GainShieldAgent", "PIController", 4.75, "set_gains(bumpless)", color=BLUE, w=1.5)
    msg("GainShieldAgent", "AuditLogger", 5.02, "GAIN_APPLIED / GAIN_REJECTED", color=AMBER)
    # loop frame
    R(sl, X["ChargerPlant"] - 0.45, 5.18, X["PIController"] - X["ChargerPlant"] + 0.9, 0.78, line=STEEL, lw=0.75)
    T(sl, X["ChargerPlant"] - 0.41, 5.2, 1.4, 0.2, "loop · every 100 µs", size=8.5, bold=True, color=STEEL)
    msg("PIController", "ChargerPlant", 5.58, "i_d*")
    msg("ChargerPlant", "RuntimeMonitor", 5.85, "v_dc, i_d")
    msg("RuntimeMonitor", "PIController", 6.3, "alarm → baseline gains", color=FAULT, w=1.5)
    msg("RuntimeMonitor", "AuditLogger", 6.72, "ROLLBACK + reason · adaptation locked out 100 ms", color=AMBER)
    # right panel: defense in depth
    xr = 9.45
    L(sl, xr - 0.15, 1.7, xr - 0.15, 7.0, color=HAIR, w=0.75)
    kicker(sl, xr, 1.68, X1 - xr, "Safety and integrity, in depth")
    f = fi.set_index(fi["case"].str.split().str[0])
    layers = [("Tier-1 proof", "a context change can never destabilise the active loop"),
              ("Exact re-check", f"out-of-set proposal rejected (test G1: {'yes' if f.loc['G1', 'detected'] else 'no'})"),
              ("GP σ and LCB", "extrapolation rejected (G2, G3)"),
              ("Envelope + step", "plant outside model, large jumps rejected (G4, G5)"),
              ("Monitor + fallback", "unstable gains reaching the plant rolled back (R1)"),
              ("Sensor plausibility", "stuck sensor caught; a power-balance estimate takes over (R5)"),
              ("Audit trace check", "every gain change explained by a record")]
    for i, (t_, s_) in enumerate(layers):
        y = 2.0 + i * 0.6
        T(sl, xr, y, X1 - xr, 0.62, [[(f"{i + 1}  ", {"bold": True, "size": 10.5, "color": AMBER}),
                                     (t_, {"bold": True, "size": 11})], [(s_, {"size": 9.5, "color": STEEL})]], after=0)
    R(sl, xr, 6.26, X1 - xr, 0.62, fill=SAFE_T)
    T(sl, xr + 0.12, 6.26, X1 - xr - 0.24, 0.62, anchor=MSO_ANCHOR.MIDDLE, paras= [[("Last line  ", {"bold": True, "size": 10, "color": SAFE}),
                                               ("independent hardware over/under-voltage trip behind every software layer "
                                                "(HIL roadmap).", {"size": 9.5, "color": NAVY})]])
    notes(sl, "Lifelines are the actual classes in core.py, optimizer/safe_bo.py, safety/supervisor.py, controllers/pi.py "
              "and audit/logger.py. The security mechanisms here are safety and integrity mechanisms: the system has no "
              "network interface, authentication or user data.")


def s08_plan(sl):
    remove_body(sl)
    set_title(sl, "Implementation Plan")
    claim(sl, "All six deliverables are implemented and tested in simulation; hardware-in-the-loop is the next phase")
    y = 2.95
    ms = [("D1", "Plant + baseline", "averaged model, 10 disturbance classes, manual PI"),
          ("D2", "Safe online tuning", "two-tier certificate, contextual safe BO, gate"),
          ("D3", "Fallback + audit", "bumpless rollback, lock-out, JSONL with trace check"),
          ("D4", "Dashboard", "Streamlit: 6 tabs incl. live tuning"),
          ("D5", "Evaluation", "11 scenarios × 5 seeds, paired tests, timing"),
          ("D6", "Ablation + faults", "7 variants, 14 fault cases, HIL plan"),
          ("P1", "SIL", "port PI + monitor to C; Tier-2 lookup table"),
          ("P2", "PIL", "TI C2000 F28379D runs the 10 kHz loop"),
          ("P3", "Controller HIL", "real-time plant, tests H1–H8"),
          ("P4", "Scaled bench", "48 V / 1 kW, low voltage only")]
    xs = [0.95 + i * 1.2 for i in range(10)]
    L(sl, xs[0], y, xs[5], y, color=NAVY, w=2.5)
    L(sl, xs[5], y, xs[9], y, color=AMBER, w=2.0, dash=True)
    R(sl, xs[0] - 0.3, 1.7, xs[5] - xs[0] + 0.6, 0.3, fill=SAFE_T)
    T(sl, xs[0] - 0.3, 1.7, xs[5] - xs[0] + 0.6, 0.3, "IMPLEMENTED AND TESTED IN SIMULATION", size=9.5, bold=True, color=SAFE,
      align=PP_ALIGN.CENTER, anchor=MSO_ANCHOR.MIDDLE)
    R(sl, xs[6] - 0.3, 1.7, xs[9] - xs[6] + 0.6, 0.3, fill=AMBER_T)
    T(sl, xs[6] - 0.3, 1.7, xs[9] - xs[6] + 0.6, 0.3, "PROPOSED · NOT YET EXECUTED", size=9.5, bold=True, color=NAVY,
      align=PP_ALIGN.CENTER, anchor=MSO_ANCHOR.MIDDLE)
    for i, (x, (k, t_, s_)) in enumerate(zip(xs, ms)):
        done = i < 6
        if done:
            dot(sl, x - 0.2, y - 0.2, 0.4, k, fill=NAVY, size=10)
        else:
            s = R(sl, x - 0.2, y - 0.2, 0.4, 0.4, fill=WHITE, line=AMBER, lw=1.75, shape=MSO_SHAPE.OVAL)
            T(sl, x - 0.2, y - 0.2, 0.4, 0.4, k, size=10, bold=True, color=NAVY, align=PP_ALIGN.CENTER, anchor=MSO_ANCHOR.MIDDLE)
        T(sl, x - 0.56, 2.15, 1.12, 0.5, t_, size=10.5, bold=True, color=NAVY, align=PP_ALIGN.CENTER, anchor=MSO_ANCHOR.BOTTOM)
        T(sl, x - 0.57, y + 0.32, 1.14, 0.9, s_, size=9, color=STEEL, align=PP_ALIGN.CENTER)
    # traceability
    kicker(sl, X0, 4.5, 9, "Requirement traceability", module="summary of docs/REQUIREMENTS_TRACEABILITY.md")
    G, A = ("Complete and tested (sim)", SAFE), ("Implemented, not fully validated", AMBER)
    rows = [["Deliverable", "Module", "Test", "Evidence", "Status"],
            ["D1 Plant, constraints, disturbances, baseline", "plant/, disturbances/, controllers/", "test_plant, test_scenarios", "energy balance, eval figures", G],
            ["D2 Safe online tuning + monitors", "stability/, optimizer/, safety/", "test_stability, _optimizer, _supervisor", "0 of 482 trials unsafe; stuck sensor caught", G],
            ["D3 Fallback, rollback, audit", "core.py, audit/logger.py", "test_integration, test_audit", "0 trace problems", G],
            ["D4 Dashboard", "dashboard/app.py", "headless AppTest", "6 tabs, no exceptions", G],
            ["D5 Evaluation", "experiments/run_evaluation.py", "55 paired runs", "evaluation_summary.json", G],
            ["D6 Ablation, failures, HIL roadmap", "run_ablation.py, run_failure_injection.py", "7 variants, 14 fault cases", "HIL_ROADMAP.md: 8 tests, costed", G]]
    colw = [3.05, 2.6, 2.05, 2.55, 1.95]
    yy = 4.8
    yy = ledger(sl, X0, yy, X1 - X0, [rows[0]], colw, rowh=0.3)
    for r in rows[1:]:
        st, c = r[4]
        ledger(sl, X0, yy, X1 - X0, [r[:4] + [""]], colw, size=9.5, rowh=0.355, header=False)
        chip(sl, X0 + sum(colw[:4]) + 0.02, yy + 0.05, 1.9, st, fill=SAFE_T if c == SAFE else AMBER_T,
             color=SAFE if c == SAFE else NAVY, size=8.5, h=0.25)
        yy += 0.355
    notes(sl, "Status words are deliberate. 'Complete and tested (sim)' never means hardware-validated.")


def s09_stack(sl, cert):
    remove_body(sl)
    set_title(sl, "Implementation Plan")
    claim(sl, "Implementation: a tested Python package, a reproducible pipeline and a live dashboard")
    # pipeline
    kicker(sl, X0, 1.68, 4.2, "One command reproduces every number")
    steps = [("run_certificate.py", "certificate.npz", f"≈ {cert['compute_seconds']:.0f} s"),
             ("run_tuning.py", "model.pkl · tuning_audit.jsonl", "13 contexts"),
             ("run_evaluation.py", "evaluation_summary.json", "55 pairs"),
             ("run_failure_injection.py", "failure_injection.csv", "14 cases"),
             ("run_ablation.py", "ablation.csv", "7 variants"),
             ("make_reports.py", "docs/*.md · RESULTS_SNAPSHOT.json", ""),
             ("build_deck.py", "this presentation", "")]
    for i, (a, b, c) in enumerate(steps):
        y = 2.02 + i * 0.6
        dot(sl, X0, y + 0.06, 0.26, str(i + 1), fill=NAVY, size=9)
        T(sl, X0 + 0.38, y, 3.85, 0.55, [[(a, {"bold": True, "size": 11}), ("   " + c, {"size": 9, "color": BLUE})],
                                         [("→ " + b, {"size": 9.5, "color": STEEL})]], after=0)
        if i < len(steps) - 1:
            L(sl, X0 + 0.13, y + 0.34, X0 + 0.13, y + 0.66, color=HAIR, w=1.0)
    T(sl, X0, 6.25, 4.2, 0.75, [[("python experiments/run_all.py", {"bold": True, "size": 11, "color": BLUE})],
                                [("≈ 30 min on a 2-core CPU; fixed seeds; no GPU, MATLAB or network.", {"size": 9.5, "color": STEEL})]])
    L(sl, 4.95, 1.72, 4.95, 7.0, color=HAIR, w=0.75)
    # stack
    xs_, ws = 5.2, 4.55
    kicker(sl, xs_, 1.68, ws, "Technology stack (as implemented)")
    stack = [("Frontend", "Streamlit + Plotly dashboard", "dashboard/app.py · monitoring, AI, safety, experiments, audit, live tuning", BLUE3),
             ("Experiments", "pandas · Matplotlib · SciPy stats", "experiments/ · reports generated, not typed", PAPER),
             ("Core package", "NumPy · scikit-learn", "gainshield/ · plant RK4, certificate, 3 GPs, supervisor, audit", BLUE3),
             ("Quality", "pytest · Streamlit AppTest", "40 unit + integration tests; dashboard tested headless", PAPER),
             ("Runtime", "Python ≥ 3.11 · CPU only", "pinned versions in requirements-lock.txt", PAPER)]
    for i, (a, b, c, f) in enumerate(stack):
        y = 2.02 + i * 0.86
        R(sl, xs_, y, ws, 0.78, fill=f)
        T(sl, xs_ + 0.15, y + 0.06, 1.2, 0.66, a.upper(), size=9, bold=True, color=STEEL, anchor=MSO_ANCHOR.MIDDLE)
        T(sl, xs_ + 1.35, y + 0.06, ws - 1.45, 0.68, [[(b, {"bold": True, "size": 11})], [(c, {"size": 9, "color": STEEL})]],
          anchor=MSO_ANCHOR.MIDDLE, after=0)
    T(sl, xs_, 6.4, ws, 0.6, "Why not PyTorch / BoTorch: the safe-set logic stays auditable line by line and runs on a CPU "
                             "in seconds, without a ~1 GB dependency.", size=9.5, color=STEEL)
    L(sl, 9.95, 1.72, 9.95, 7.0, color=HAIR, w=0.75)
    # resources
    xq = 10.2
    kicker(sl, xq, 1.68, X1 - xq, "Project resources")
    R(sl, xq, 2.02, 2.3, 2.3, fill=WHITE, line=HAIR, lw=0.75)
    pic(sl, ASSETS / "qr_github.png", xq + 0.08, 2.1, w=2.14, h=2.14)
    T(sl, xq, 4.42, X1 - xq, 0.5, [[("Scan: GitHub repository", {"bold": True, "size": 11})],
                                   [(REPO, {"size": 9.5, "color": BLUE})]], after=0)
    T(sl, xq, 5.05, X1 - xq, 1.9, ["README with results and quick start", "Model, architecture, assumptions",
                                   "Traceability, HIL roadmap, costs, limitations", "Generated results, figures, audit logs"],
      size=9.5, color=STEEL, after=4)
    notes(sl, "The QR code was supplied by the team and resolves through a qrfy.io short link; the printed URL is the "
              "repository itself.")


def s10_val(sl, ev):
    remove_body(sl)
    set_title(sl, "Validation / Testing / Analysis")
    pt, s, ps = ev["paired"], ev["summary"], ev["per_scenario"]
    H = headline(ev)
    claim(sl, f"Up to {H['best']:.0f} % smaller voltage swings: better in {H['n_adapt']} of {H['n_all']} scenarios and never worse")
    kicker(sl, X0, 1.68, 6.4, "Peak DC-link deviation, % of 800 V · mean of 5 seeds")
    order = ["load_increase", "load_decrease", "g2v_to_v2g", "v2g_to_g2v", "grid_sag", "sensor_noise", "cap_minus20",
             "cap_plus20", "inner_lag_slow", "delay_long", "combined"]
    names = ["Load 5 → 20 kW", "Load 20 → 5 kW", "G2V → V2G", "V2G → G2V", "Grid sag 0.8 pu", "Sensor noise ×3",
             "C −20 %", "C +20 %", "Inner lag 1 ms", "Delay 2 samples", "Combined stress"]
    hbar(sl, X0 - 0.1, 1.9, 6.55, 4.5, names,
         [("manual PI", [ps[k]["peak_dev_pct"]["baseline"] for k in order]),
          ("GainShield", [ps[k]["peak_dev_pct"]["gainshield"] for k in order])],
         [BASE, BLUE], fmt='0.00', size=9.5, gap=35, overlap=-5, axis_max=4.0)
    T(sl, X0, 6.42, 6.4, 0.6, [[("Protocol  ", {"bold": True, "size": 9.5}),
                                ("11 scenarios × 5 seeds; identical plant, events, pre-drawn noise and context error; Ts = 100 µs; "
                                 "metrics on true plant states. Sag, slow lag and combined: GainShield keeps the baseline.",
                                 {"size": 9.5, "color": STEEL})]])
    L(sl, 6.95, 1.72, 6.95, 7.0, color=HAIR, w=0.75)
    xr = 7.2
    kicker(sl, xr, 1.68, X1 - xr, "Power reversal +15 → −15 kW · seed 0")
    pic(sl, ASSETS / "fig_reversal.png", xr, 1.95, w=X1 - xr)
    g = ps["g2v_to_v2g"]["peak_dev_pct"]
    stats = [(f"−{H['best']:.0f} %", f"peak deviation,\n{H['best_name']}", BLUE),
             (f"−{H['adapt_mean']:.0f} %", f"average where it\nadapts ({H['n_adapt']}/{H['n_all']})", BLUE),
             (f"−{H['all_mean']:.0f} %", f"average over all\n{H['n_all']} scenarios", NAVY),
             ("0", "voltage, current or\ntrip violations", SAFE)]
    w = (X1 - xr) / 4
    for i, (n, l, c) in enumerate(stats):
        stat(sl, xr + i * w, 5.98, w - 0.1, n, l, color=c, nsize=22)
    source(sl, f"Source: results/evaluation_summary.json · Wilcoxon p = {pt['peak_dev_pct']['wilcoxon_p']:.1e} (peak deviation, 55 pairs) · "
               f"reversal peak {g['baseline']:.2f} % → {g['gainshield']:.2f} %", y=7.1)
    notes(sl, "Grey is always the manual PI, blue always GainShield.")


def s11_ablation(sl, abl, fi):
    remove_body(sl)
    set_title(sl, "Validation / Testing / Analysis")
    claim(sl, "Ablation and fault injection: removing a safety layer turns a contained fault into a sustained oscillation")
    kicker(sl, X0, 1.68, 6.3, "Remove one layer at a time · same seeds, same fault")
    a = abl.set_index("variant")
    rows = [["Variant", "Unsafe tuning\nepisodes", "Deployed peak\nvs manual PI", "Injected unstable gains:\npeak · time outside ±5 %"]]
    for v, s_ in [("A complete", "A  Complete GainShield"), ("B no certified region", "B  − certified region"),
                  ("C no GP uncertainty", "C  − GP uncertainty"), ("D no runtime monitor", "D  − runtime monitor"),
                  ("E no context", "E  − context"), ("F no fallback", "F  − fallback")]:
        r = a.loc[v]
        bad = r["fault_v_viol_ms"] > 0
        rows.append([s_, f"{int(r['tuning_unsafe_episodes'] + r['tuning_monitor_aborts'])}",
                     f"{r['deploy_peak_dev_vs_baseline']:.2f} ×",
                     {"t": f"{r['fault_peak_dev_pct']:.1f} % · {r['fault_v_viol_ms']:.0f} ms", "color": FAULT if bad else NAVY, "bold": bad}])
    ledger(sl, X0, 1.98, 6.3, [rows[0] + [("", 0.5)]], [2.1, 1.15, 1.3, 1.75], rowh=0.5)
    ledger(sl, X0, 2.48, 6.3, rows[1:], [2.1, 1.15, 1.3, 1.75], size=10.5, rowh=0.37, header=False)
    reads = [("D, F", "without the monitor or the fallback the fault persists as a limit cycle; with them it is rolled back.", FAULT),
             ("C", f"trusting GP means gives faster but unverified gains (only {int(a.loc['C no GP uncertainty', 'episodes'])} measured episodes).", NAVY),
             ("B", "no unsafe episode in this budget: the certificate's value is a guarantee, not an average.", NAVY),
             ("E", f"without context the gain shrinks ({a.loc['E no context', 'deploy_peak_dev_vs_baseline']:.2f} × vs {a.loc['A complete', 'deploy_peak_dev_vs_baseline']:.2f} ×).", NAVY)]
    for i, (k, t_, c) in enumerate(reads):
        T(sl, X0, 4.82 + i * 0.42, 6.3, 0.4, [[(k + "   ", {"bold": True, "size": 10.5, "color": c}), (t_, {"size": 10, "color": STEEL})]])
    L(sl, 7.1, 1.72, 7.1, 7.0, color=HAIR, w=0.75)
    xr = 7.35
    kicker(sl, xr, 1.68, X1 - xr, "Fault: unstable gains written behind the gate")
    pic(sl, ASSETS / "fig_fault.png", xr, 1.98, h=3.0)
    f = fi.set_index(fi["case"].str.split().str[0])
    gates = sum(bool(f.loc[k, "detected"]) for k in ["G1", "G2", "G3", "G4", "G5"])
    stat(sl, xr, 5.2, 1.6, f"{gates} / 5", "unsafe proposals\nrejected by the gate", color=SAFE)
    stat(sl, xr + 1.75, 5.2, 1.6, f"{f.loc['R1', 't_detect_ms'] - 60:.0f} ms", "injection to rollback\n(4 % abort band)", color=BLUE)
    R(sl, xr + 3.5, 5.15, X1 - xr - 3.5, 1.45, fill=SAFE_T)
    r5, r5x = f.loc["R5"], f.loc["R5-ref"]
    T(sl, xr + 3.62, 5.15, X1 - xr - 3.74, 1.45, anchor=MSO_ANCHOR.MIDDLE, paras= [[("Stuck sensor (R5): closed", {"bold": True, "size": 11, "color": SAFE})],
                                                 [(f"caught in {r5['t_detect_ms'] - 100:.1f} ms, voltage held within {r5['peak_dev_pct']:.1f} % "
                                                   f"on the observer estimate. Without the check: {r5x['peak_dev_pct']:.0f} % collapse, trip.",
                                                   {"size": 9.5})]], after=2)
    source(sl, "Source: results/ablation.csv, results/failure_injection.csv. Isolated simulation; unsafe variants are never for hardware.", y=7.1)
    notes(sl, "The 46 ms detection delay is a measured weakness: the oscillation grows until the 4 % abort band is hit.")


def s13_assume(sl):
    remove_body(sl)
    claim(sl, "No numbers were supplied, so every value is a stated, configurable engineering assumption")
    left = [("Plant", [("A-1/2", "30 kW module, 800 V DC link"), ("A-3", "C = 2 mF, ±20 %"), ("A-4", "415 V grid, 0.80–1.10 pu"),
                       ("A-6/7", "AFE η = 98 %; inner loop τ_i 0.3–1.0 ms"), ("A-8", "DC-DC τ = 2 ms, 2 kW/ms, ±30 kW")]),
            ("Limits", [("A-9/10", "10 kHz switching = sampling; delay 1.0–2.0 samples"), ("A-11/12", "i_d ≤ 80 A; ±5 % band, ±10 % trip, 4 % abort"),
                        ("A-14", "sensor noise 1 V, 0.5 A (1σ)")])]
    right = [("Stability", [("A-13", "worst case PM ≥ 40°, GM ≥ 6 dB, |1+L| ≥ 0.5"), ("model", "linearised, unsaturated; lag × delay gridded (88 nodes)")]),
             ("Optimiser", [("A-15", "context known within C ±5 %, τ_i ±20 %, delay ±0.2"), ("BO", "β = 2, h = 0.15, σ ≤ 0.25, step ≤ ×3; RKHS bound unverified"),
                            ("probe", "+10 V reference step and ±6 kW power step acceptable")]),
             ("Boundary", [("scope", "averaged model: no switching ripple, AC filter, PLL, battery, thermal"), ("tests", "simulation only: no SIL, HIL or hardware")])]
    w = (X1 - X0 - 0.5) / 2
    for ci, groups in enumerate([left, right]):
        x = X0 + ci * (w + 0.5)
        y = 1.72
        for g, items in groups:
            kicker(sl, x, y, w, g)
            y += 0.3
            for k, v in items:
                T(sl, x, y, 0.85, 0.43, k, size=10, bold=True, color=BLUE, anchor=MSO_ANCHOR.MIDDLE)
                T(sl, x + 0.9, y, w - 0.9, 0.43, v, size=12, color=NAVY, anchor=MSO_ANCHOR.MIDDLE)
                y += 0.43
                L(sl, x, y, x + w, y, color=HAIR, w=0.5)
            y += 0.18
    L(sl, X0 + w + 0.25, 1.75, X0 + w + 0.25, 6.6, color=HAIR, w=0.75)
    source(sl, "All values live in config/default.toml with rationale in docs/ASSUMPTIONS.md; changing them and running run_all.py regenerates every result.", y=6.85)
    notes(sl, "These assumptions were proposed by the team, not supplied by the problem statement.")


def s14_refs(sl):
    remove_body(sl)
    claim(sl, "References: each supports a specific design decision")
    groups = [("Safe Bayesian optimisation", [
        "[1] Y. Sui, A. Gotovos, J. Burdick, A. Krause, “Safe exploration for optimization with Gaussian processes,” ICML, 2015.",
        "[2] F. Berkenkamp, A. Krause, A. P. Schoellig, “Bayesian optimization with safety constraints,” Machine Learning 112, 2023.",
        "[3] C. König, M. Khosravi, M. Maier, R. S. Smith, A. Rupenyan, J. Lygeros, “Safety-aware cascade controller tuning using constrained Bayesian optimization,” IEEE Trans. Ind. Electron., doi:10.1109/TIE.2022.3158007.",
        "[4] C. König, M. Turchetta, J. Lygeros, A. Rupenyan, A. Krause, “Safe and efficient model-free adaptive control via Bayesian optimization,” IEEE ICRA, 2021.",
        "[5] C. E. Rasmussen, C. K. I. Williams, Gaussian Processes for Machine Learning, MIT Press, 2006.",
        "[6] N. Srinivas, A. Krause, S. Kakade, M. Seeger, “Gaussian process optimization in the bandit setting,” ICML, 2010."]),
        ("Control and robustness", [
            "[7] B. R. Barmish, New Tools for Robustness of Linear Systems, Macmillan, 1994.",
            "[8] K. J. Åström, B. Wittenmark, Computer-Controlled Systems, 3rd ed., 1997.",
            "[9] K. J. Åström, T. Hägglund, Advanced PID Control, ISA, 2006.",
            "[10] S. Preitl, R.-E. Precup, symmetrical optimum extension, Automatica 35(10), 1999."]),
        ("Power electronics", [
            "[11] A. Emadi et al., “Constant power loads and negative impedance instability,” IEEE Trans. Veh. Technol. 55(4), 2006.",
            "[12] A. Yazdani, R. Iravani, Voltage-Sourced Converters in Power Systems, Wiley-IEEE, 2010."]),
        ("Standards, software, sources", [
            "[13] F. Pedregosa et al., “Scikit-learn,” JMLR 12, 2011.",
            "[14] IEC 61851-23; ISO 15118-20:2022; IEEE 1547-2018 (context only, no compliance claim).",
            "[15] Typhoon HIL, Arrow and Streamlit pages, accessed 12 Nov 2026."])]
    w = (X1 - X0 - 0.5) / 2
    cols = [[groups[0]], [groups[1], groups[2], groups[3]]]
    for ci, gs in enumerate(cols):
        x = X0 + ci * (w + 0.5)
        y = 1.72
        for g, refs in gs:
            kicker(sl, x, y, w, g)
            y += 0.3
            for r in refs:
                n = -(-len(r) // 100)
                T(sl, x, y, w, 0.19 * n + 0.04, r, size=10.5, color=NAVY)
                y += 0.19 * n + 0.17
            y += 0.12
    L(sl, X0 + w + 0.25, 1.75, X0 + w + 0.25, 6.9, color=HAIR, w=0.75)
    notes(sl, "Mapping from each reference to the claim it supports: docs/REFERENCES.md.")


COLLEGE = "SRM Institute of Science and Technology, Kattankulathur"
CITY = "Chennai, Tamil Nadu"


def _alpha(shape, alpha_pct):
    """Set fill transparency on a solid-filled autoshape (alpha in percent opacity)."""
    clr = shape.fill._xPr.find(qn("a:solidFill"))[0]
    a = etree.SubElement(clr, qn("a:alpha"))
    a.set("val", str(int(alpha_pct * 1000)))


def s01_cover(sl):
    AX = 6.97                                   # centre axis of the template's title block
    for sh in list(sl.shapes):
        t = sh.text_frame.text.replace("\n", " ").strip() if sh.has_text_frame else ""
        if t.startswith("Author") or t.startswith("Name ") or t == "Concept Title" or t.startswith("College name"):
            sh._element.getparent().remove(sh._element)
        elif t.startswith("PID No"):
            sh.width = Inches(1.3)
            sh.text_frame.word_wrap = False
        elif t == "00000":
            sh.text_frame.paragraphs[0].runs[0].text = PID
            sh.left, sh.width = Inches(1.95), Inches(2.2)
            sh.text_frame.word_wrap = False
    # title block on the template's centre axis
    T(sl, AX - 3.2, 2.48, 6.4, 0.5, "GainShield", size=26, bold=True, color=AMBER, align=PP_ALIGN.CENTER,
      anchor=MSO_ANCHOR.MIDDLE)
    T(sl, AX - 2.6, 3.02, 5.2, 0.62, ["AI-Driven Safe Bayesian PI Gain Tuning with Stability Certification",
                                      "and Runtime Fallback for Bidirectional EV Charger DC-Link Control"],
      size=12, color=WHITE, align=PP_ALIGN.CENTER, after=0, line=1.1)
    # team plate: one dark panel separates the portraits from the background wave
    pw, ph, gap = 1.25, 1.56, 1.25
    plate_w = 2 * pw + gap + 2 * 0.6
    plate = R(sl, AX - plate_w / 2, 3.88, plate_w, 3.12, fill=RGBColor(0x07, 0x0D, 0x1F),
              shape=MSO_SHAPE.ROUNDED_RECTANGLE, radius=0.05)
    _alpha(plate, 82)
    for i, (name, f) in enumerate(TEAM):
        cx = AX + (i - 0.5) * (pw + gap)
        R(sl, cx - pw / 2 - 0.025, 4.03, pw + 0.05, ph + 0.05, fill=WHITE)
        pic(sl, ASSETS / f, cx - pw / 2, 4.055, w=pw, h=ph)
        T(sl, cx - 1.25, 5.7, 2.5, 0.3, name, size=12.5, bold=True, color=WHITE, align=PP_ALIGN.CENTER)
    L(sl, AX - 1.6, 6.12, AX + 1.6, 6.12, color=AMBER, w=0.75)
    T(sl, AX - 2.45, 6.24, 4.9, 0.62, [[(COLLEGE, {"bold": True, "size": 12, "color": AMBER})],
                                    [(CITY, {"size": 11, "color": WHITE})]], align=PP_ALIGN.CENTER, after=0)
    notes(sl, f"PID {PID}. Concept title exactly as registered. Team: Archana RG and Thiyagarajan Gopalakrishnan, "
              f"{COLLEGE}, {CITY}.")


def s04_pros(sl, ev):
    remove_body(sl)
    pt, t = ev["paired"], ev["tuning"]
    claim(sl, "Pros and cons in plain terms: what improves, what it costs, and how each risk is handled")
    w = (X1 - X0 - 0.5) / 2
    xl, xr = X0, X0 + w + 0.5
    peak = -pt["peak_dev_pct"]["mean_relative_change_pct"]
    H = headline(ev)
    ripple = pt["i_ripple_A"]["mean_relative_change_pct"]
    pros = [("Smaller voltage swings",
             f"When the load or power direction changes, the DC-link voltage swings up to {H['best']:.0f} % less "
             f"than with the hand-tuned controller ({H['adapt_mean']:.0f} % on average where it adapts, "
             f"{peak:.0f} % across all {H['n_all']} tests), and recovers sooner."),
            ("Never uses an unproven setting",
             "Every gain setting is checked mathematically for stability before it is applied, for all the "
             "capacitor, grid and power-direction conditions we model."),
            ("Learns safely while running",
             f"In {t['episodes_run']} live tuning trials, the voltage never left its ±5 % safe band."),
            ("Built-in safety net",
             "If the monitor sees anything abnormal, control switches straight back to the proven manual "
             "controller, without a jump in the output."),
            ("Every decision is recorded",
             "Each gain change is logged with its reason, so any result can be traced, audited and reproduced.")]
    cons = [("Slightly more electrical noise",
             f"Higher gains make the current command about {ripple:.0f} % noisier.",
             "noise is part of what the tuner minimises, within certified limits", "Handled now"),
            ("Only as good as the model",
             "The stability check assumes our model of the charger is accurate.",
             "a live monitor watches the real signals; hardware tests come next", "Handled now"),
            ("AI predictions can be wrong",
             "The learning model can be confident in conditions it has not tried yet.",
             "it is never trusted alone; uncertain suggestions are rejected", "Handled now"),
            ("Safety check is slow in Python",
             f"Checking a new operating condition takes about {ev['summary']['context_mask_ms']['median'] / 1e3:.1f} s.",
             "it runs outside the fast control loop; a lookup table will remove it", "Next step"),
            ("Not yet on real hardware",
             "Tested in simulation only; sensor checks are tuned on simulated noise.",
             "processor-in-the-loop on a TI board, then lab hardware tests", "Next step")]
    # headers
    for x, txt, c in [(xl, "PROS", SAFE), (xr, "CONS  ·  and how we handle each", AMBER)]:
        T(sl, x, 1.66, w, 0.3, txt, size=12, bold=True, color=c)
        L(sl, x, 2.0, x + w, 2.0, color=c, w=1.5)
    rh = 0.9
    for i, ((ph, pb), (ch, cb, cm, st)) in enumerate(zip(pros, cons)):
        y = 2.12 + i * rh
        dot(sl, xl, y + 0.04, 0.3, "✓", fill=SAFE, size=11)
        T(sl, xl + 0.45, y, w - 0.45, rh - 0.08, [[(ph, {"bold": True, "size": 13})], [(pb, {"size": 10.5, "color": STEEL})]],
          after=1)
        dot(sl, xr, y + 0.04, 0.3, "!", fill=AMBER, color=NAVY, size=12)
        T(sl, xr + 0.45, y, w - 1.75, 0.3, ch, size=13, bold=True)
        T(sl, xr + 0.45, y + 0.29, w - 0.45, 0.6, [[(cb, {"size": 10.5, "color": STEEL})],
                                                   [("How we handle it: ", {"size": 10.5, "bold": True, "color": NAVY}),
                                                    (cm, {"size": 10.5, "color": NAVY})]], after=0)
        now = st == "Handled now"
        chip(sl, X1 - 1.25, y + 0.02, 1.25, st, fill=SAFE_T if now else AMBER_T, color=SAFE if now else NAVY, size=9, h=0.26)
        if i < 4:
            L(sl, xl + 0.45, y + rh - 0.05, xl + w, y + rh - 0.05, color=HAIR, w=0.6)
            L(sl, xr + 0.45, y + rh - 0.05, X1, y + rh - 0.05, color=HAIR, w=0.6)
    L(sl, X0 + w + 0.25, 1.7, X0 + w + 0.25, 6.6, color=HAIR, w=0.75)
    source(sl, "All figures are from simulation: 11 test conditions × 5 runs, GainShield compared with the hand-tuned "
               "controller under identical conditions (results/evaluation_summary.json).", y=6.85)
    notes(sl, "Plain-language version. 'Handled now' means the safeguard is already implemented and tested in "
              "simulation; 'Next step' means it is planned.")

def s12_cost(sl, abl, ev):
    remove_body(sl)
    claim(sl, "Investment roadmap: about ₹20,000 takes GainShield onto real controller hardware")
    a = abl.set_index("variant")
    phases = [("1", "Processor-in-the-loop", "₹14–21k", "estimate",
               [("2 × TI LAUNCHXL-F28379D", "₹8.3–11.4k"), ("signal conditioning, isolation", "₹6–10k")],
               "10 kHz PI + monitor on a real MCU; measured delay and timing"),
              ("2", "Controller HIL · institute lab", "₹0–50k", "usage charges, if any",
               [("real-time plant simulator access", "₹0–50k")],
               "fault tests H1–H8, incl. sensor faults and comms loss"),
              ("3", "Scaled power bench", "₹1.5–3 L", "engineering estimate",
               [("48 V / 1 kW converter bench", "₹1.5–3 L")],
               "real switching, sensors and losses at safe voltage"),
              ("4", "Own HIL platform · optional", "₹9.3–41 L", "only if lab access is unavailable",
               [("Typhoon HIL101, MSRP $9,900", "≈ ₹9.3 L"), ("HIL404 class, quote $44k", "≈ ₹41 L")],
               "dedicated, repeatable HIL regression")]
    w = (X1 - X0 - 3 * 0.2) / 4
    y0 = 1.68
    for i, (n, t_, big, sub, items, unlock) in enumerate(phases):
        x = X0 + i * (w + 0.2)
        opt = n == "4"
        R(sl, x, y0, w, 1.42, fill=PAPER if opt else (BLUE3 if n == "1" else MIST))
        dot(sl, x + 0.18, y0 + 0.16, 0.32, n, fill=STEEL if opt else NAVY, size=10)
        T(sl, x + 0.6, y0 + 0.12, w - 0.75, 0.42, t_, size=11, bold=True, color=NAVY, anchor=MSO_ANCHOR.MIDDLE)
        T(sl, x + 0.18, y0 + 0.58, w - 0.3, 0.5, big, size=24, bold=True, color=STEEL if opt else BLUE)
        T(sl, x + 0.18, y0 + 1.07, w - 0.3, 0.28, sub, size=9.5, color=STEEL)
        y = y0 + 1.58
        for a_, v in items:
            T(sl, x, y, w - 0.95, 0.42, a_, size=10, color=NAVY)
            T(sl, x + w - 0.95, y, 0.95, 0.3, v, size=10, bold=True, align=PP_ALIGN.RIGHT)
            y += 0.44
            L(sl, x, y - 0.05, x + w, y - 0.05, color=HAIR, w=0.5)
        T(sl, x, 4.2, w, 0.62, [[("Unlocks", {"bold": True, "size": 10, "color": AMBER})],
                                  [(unlock, {"size": 10, "color": NAVY})]], after=0)
        if i < 3:
            L(sl, x + w + 0.02, y0 + 0.32, x + w + 0.18, y0 + 0.32, color=STEEL, w=1.0, arrow=True)
    # improvement headroom
    L(sl, X0, 4.92, X1, 4.92, color=HAIR, w=0.75)
    kicker(sl, X0, 5.02, 6, "Where the next improvement comes from")
    full = a.loc["A complete", "deploy_peak_dev_vs_baseline"]
    nosig = a.loc["C no GP uncertainty", "deploy_peak_dev_vs_baseline"]
    head = 100 * (full - nosig) / full
    pt = ev["paired"]
    H = headline(ev)
    items = [(f"−{H['best']:.0f} %", "best case today",
              f"peak deviation, {H['best_name']}; {sgn(pt['peak_dev_pct']['mean_relative_change_pct'])} mean over 55 paired runs"),
             (f"≈ {sgn(-head, 0)}", "further headroom observed",
              f"unverified GP-extrapolated gains reached {nosig:.2f}× vs {full:.2f}× deployed (ablation); more measured "
              "episodes per context can recover part of it safely"),
             (f"{ev['summary']['context_mask_ms']['median'] / 1e3:.1f} s", "decision latency to remove",
              "precomputed Tier-2 lookup table instead of the Python check"),
             (sgn(pt["i_ripple_A"]["mean_relative_change_pct"], 0), "noise penalty to win back",
              "current-command ripple vs manual PI; ripple-aware cost weighting or a notch filter")]
    cw = (X1 - X0 - 3 * 0.25) / 4
    for i, (n, h_, b_) in enumerate(items):
        x = X0 + i * (cw + 0.25)
        T(sl, x, 5.3, cw, 0.5, n, size=22, bold=True, color=BLUE if i < 2 else NAVY)
        T(sl, x, 5.8, cw, 0.95, [[(h_, {"bold": True, "size": 11})], [(b_, {"size": 9.5, "color": STEEL})]], after=1)
    source(sl, "Prices researched 12 Nov 2026, 1 USD ≈ ₹94 (Arrow, Typhoon HIL, Indian distributor listings); budgetary, no vendor quotation, "
               "no partnership; foreign prices exclude duties/GST. L = lakh. Headroom figures: results/ablation.csv (simulation).", y=6.82)
    notes(sl, "Future-focused: staged spending, each stage tied to what it unlocks. Headroom numbers are simulation "
              "observations, not promises: the 'no GP uncertainty' variant used gains without measured evidence.")


def s15_thanks(sl):
    RX = 12.8                                     # right edge shared by every element
    L(sl, RX - 2.6, 4.62, RX, 4.62, color=AMBER, w=1.0)
    T(sl, RX - 6.0, 4.76, 6.0, 0.42, "GainShield", size=20, bold=True, color=AMBER, align=PP_ALIGN.RIGHT)
    T(sl, RX - 6.0, 5.2, 6.0, 0.85, [[("Archana RG   ·   Thiyagarajan Gopalakrishnan", {"size": 12.5, "bold": True, "color": WHITE})],
                                     [(f"{COLLEGE}, {CITY}", {"size": 10.5, "color": BLUE3})],
                                     [(f"PID {PID}", {"size": 10.5, "color": BLUE3})]], align=PP_ALIGN.RIGHT, after=2)
    q = 1.15
    R(sl, RX - q - 0.04, 6.06, q + 0.08, q + 0.08, fill=WHITE)
    pic(sl, ASSETS / "qr_github.png", RX - q, 6.1, w=q, h=q)
    T(sl, RX - q - 3.4, 6.3, 3.2, 0.7, [[("Code, results and documentation", {"bold": True, "size": 10.5, "color": WHITE})],
                                        [(REPO, {"size": 10, "color": BLUE3})]], align=PP_ALIGN.RIGHT,
      anchor=MSO_ANCHOR.MIDDLE, after=1)


def main(base: str, out: str) -> None:
    ev, abl, fi, cert = load()
    prs = Presentation(base)
    s = list(prs.slides)
    s01_cover(s[0]); s02_challenge(s[1], ev); s03_concept(s[2], ev, cert); s04_pros(s[3], ev)
    s05_arch(s[4]); s06_algo(s[5], cert); s07_sequence(s[6], fi)
    s08_plan(s[7]); s09_stack(s[8], cert)
    s10_val(s[9], ev); s11_ablation(s[10], abl, fi)
    s12_cost(s[11], abl, ev); s13_assume(s[12]); s14_refs(s[13]); s15_thanks(s[14])
    prs.save(out)
    print("saved", out)


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
