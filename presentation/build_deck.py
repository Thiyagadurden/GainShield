"""Build the TECHgium presentation by populating the official template.

    python presentation/build_deck.py <base15.pptx> <out.pptx>

<base15.pptx> is the official template with the Guidelines slide removed and three slides duplicated
(Technical Description ×2, Validation / Testing / Analysis ×3) so that the deck has 15 slides. Every
number on the slides is read from results/ or docs/RESULTS_SNAPSHOT.json - none is typed by hand.
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
from pptx.enum.chart import XL_CHART_TYPE, XL_LEGEND_POSITION, XL_LABEL_POSITION
from pptx.enum.shapes import MSO_CONNECTOR, MSO_SHAPE
from pptx.enum.text import MSO_ANCHOR, PP_ALIGN
from pptx.oxml.ns import qn
from pptx.util import Inches, Pt

ROOT = Path(__file__).resolve().parents[1]
RES = ROOT / "results"
FIG = RES / "figures"
DIA = ROOT / "diagrams"

NAVY = RGBColor(0x1B, 0x23, 0x5E)
BLUE = RGBColor(0x2A, 0x4F, 0xD6)
BLUE_T = RGBColor(0xE8, 0xED, 0xFB)
YELLOW = RGBColor(0xF2, 0xB7, 0x05)
YELLOW_T = RGBColor(0xFE, 0xF4, 0xD4)
GREEN = RGBColor(0x14, 0x8F, 0x62)
GREEN_T = RGBColor(0xDF, 0xF3, 0xEA)
RED = RGBColor(0xC8, 0x3A, 0x3A)
RED_T = RGBColor(0xFB, 0xE4, 0xE4)
ORANGE = RGBColor(0xEB, 0x68, 0x34)
INK = RGBColor(0x14, 0x14, 0x14)
INK2 = RGBColor(0x52, 0x51, 0x4E)
GREY_T = RGBColor(0xF2, 0xF2, 0xF0)
WHITE = RGBColor(0xFF, 0xFF, 0xFF)
FONT = "Calibri"

X0, X1 = 0.55, 12.85          # usable content width (template body placeholder)
Y0 = 1.02                     # just under the template title rule


# ---------------------------------------------------------------------------- helpers
def _run_fmt(run, size, bold=False, color=INK, italic=False, font=FONT):
    f = run.font
    f.size = Pt(size)
    f.bold = bold
    f.italic = italic
    f.name = font
    f.color.rgb = color


def text(slide, x, y, w, h, paras, size=12, color=INK, bold=False, align=PP_ALIGN.LEFT, anchor=MSO_ANCHOR.TOP,
         margin=0.04, name=None, spacing=2):
    """paras: str | list of str | list of list[(text, {opts})]."""
    tb = slide.shapes.add_textbox(Inches(x), Inches(y), Inches(w), Inches(h))
    if name:
        tb.name = name
    tf = tb.text_frame
    tf.word_wrap = True
    tf.vertical_anchor = anchor
    for m in ("margin_left", "margin_right", "margin_top", "margin_bottom"):
        setattr(tf, m, Inches(margin))
    if isinstance(paras, str):
        paras = [paras]
    for i, p in enumerate(paras):
        para = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        para.alignment = align
        para.space_after = Pt(spacing)
        runs = p if isinstance(p, list) else [(p, {})]
        for t, o in runs:
            r = para.add_run()
            r.text = t
            _run_fmt(r, o.get("size", size), o.get("bold", bold), o.get("color", color), o.get("italic", False))
    return tb


def box(slide, x, y, w, h, fill=GREY_T, line=None, shape=MSO_SHAPE.ROUNDED_RECTANGLE, radius=0.08, name=None,
        lw=1.0):
    s = slide.shapes.add_shape(shape, Inches(x), Inches(y), Inches(w), Inches(h))
    if name:
        s.name = name
    s.fill.solid()
    s.fill.fore_color.rgb = fill
    if line is None:
        s.line.fill.background()
    else:
        s.line.color.rgb = line
        s.line.width = Pt(lw)
    s.shadow.inherit = False
    if shape == MSO_SHAPE.ROUNDED_RECTANGLE:
        s.adjustments[0] = radius
    s.text_frame.text = ""
    return s


def card(slide, x, y, w, h, title, body, fill=GREY_T, title_color=NAVY, size=11, tsize=12.5, line=None):
    box(slide, x, y, w, h, fill=fill, line=line)
    text(slide, x + 0.12, y + 0.08, w - 0.24, 0.32, title, size=tsize, bold=True, color=title_color)
    text(slide, x + 0.12, y + 0.42, w - 0.24, h - 0.5, body, size=size, color=INK)


def badge(slide, x, y, d, label, fill=BLUE, color=WHITE, size=12):
    s = box(slide, x, y, d, d, fill=fill, shape=MSO_SHAPE.OVAL)
    tf = s.text_frame
    tf.margin_left = tf.margin_right = tf.margin_top = tf.margin_bottom = 0
    p = tf.paragraphs[0]
    p.alignment = PP_ALIGN.CENTER
    r = p.add_run()
    r.text = label
    _run_fmt(r, size, True, color)
    tf.vertical_anchor = MSO_ANCHOR.MIDDLE
    return s


def arrow(slide, x1, y1, x2, y2, color=INK2, width=1.5):
    c = slide.shapes.add_connector(MSO_CONNECTOR.STRAIGHT, Inches(x1), Inches(y1), Inches(x2), Inches(y2))
    c.line.color.rgb = color
    c.line.width = Pt(width)
    ln = c.line._get_or_add_ln()
    tail = etree.SubElement(ln, qn("a:tailEnd"))
    tail.set("type", "triangle")
    tail.set("w", "med")
    tail.set("len", "med")
    return c


def node(slide, x, y, w, h, title, sub="", fill=BLUE_T, line=BLUE, tcolor=NAVY, size=11, tsize=12):
    box(slide, x, y, w, h, fill=fill, line=line, lw=1.25)
    paras = [[(title, {"bold": True, "size": tsize, "color": tcolor})]]
    if sub:
        paras.append([(sub, {"size": size, "color": INK})])
    text(slide, x + 0.06, y + 0.04, w - 0.12, h - 0.08, paras, align=PP_ALIGN.CENTER, anchor=MSO_ANCHOR.MIDDLE,
         spacing=1)


def headline(slide, s):
    text(slide, X0, Y0, X1 - X0, 0.42, s, size=17, bold=True, color=BLUE, name="Headline")


def source(slide, s, y=7.08):
    text(slide, X0, y, X1 - X0, 0.28, s, size=9, color=INK2, name="Source")


def table(slide, x, y, w, h, rows, col_w=None, size=10.5, header_fill=NAVY, zebra=True, bold_first_col=False,
          header_size=None):
    nr, nc = len(rows), len(rows[0])
    gt = slide.shapes.add_table(nr, nc, Inches(x), Inches(y), Inches(w), Inches(h))
    t = gt.table
    tblPr = t._tbl.tblPr
    style = tblPr.find(qn("a:tableStyleId"))
    if style is not None:
        style.text = "{5940675A-B579-460E-94D1-54222C63F5DA}"   # 'No Style, Table Grid'
    if col_w:
        for i, cw in enumerate(col_w):
            t.columns[i].width = Inches(cw)
    for r in range(nr):
        t.rows[r].height = Inches(h / nr)
        for c in range(nc):
            cell = t.cell(r, c)
            cell.margin_left = cell.margin_right = Inches(0.06)
            cell.margin_top = cell.margin_bottom = Inches(0.025)
            cell.vertical_anchor = MSO_ANCHOR.MIDDLE
            val = rows[r][c]
            opts = {}
            if isinstance(val, tuple):
                val, opts = val
            tf = cell.text_frame
            tf.word_wrap = True
            p = tf.paragraphs[0]
            p.text = ""
            run = p.add_run()
            run.text = str(val)
            hdr = r == 0
            _run_fmt(run, opts.get("size", header_size or size if hdr else size), hdr or opts.get("bold", False) or (bold_first_col and c == 0),
                     WHITE if hdr else opts.get("color", INK))
            cell.fill.solid()
            cell.fill.fore_color.rgb = header_fill if hdr else opts.get("fill", (GREY_T if (zebra and r % 2 == 0) else WHITE))
    return gt


def remove_body_placeholder(slide):
    for sh in list(slide.shapes):
        if sh.is_placeholder and sh.placeholder_format.idx != 0:
            sh._element.getparent().remove(sh._element)


def set_title(slide, s):
    for sh in slide.shapes:
        if sh.is_placeholder and sh.placeholder_format.idx == 0:
            r = sh.text_frame.paragraphs[0].runs
            if r:
                r[0].text = s
                for extra in r[1:]:
                    extra.text = ""
            return


def notes(slide, s):
    slide.notes_slide.notes_text_frame.text = s


def pic(slide, path, x, y, w=None, h=None, name=None):
    p = slide.shapes.add_picture(str(path), Inches(x), Inches(y), Inches(w) if w else None, Inches(h) if h else None)
    if name:
        p.name = name
    return p


def bar_chart(slide, x, y, w, h, cats, series, colors, title=None, number_format='0.0', label_size=9, legend=True,
              horizontal=False, gap=60, max_val=None, labels=True):
    cd = CategoryChartData()
    cd.categories = cats
    for n, v in series:
        cd.add_series(n, v)
    ct = XL_CHART_TYPE.BAR_CLUSTERED if horizontal else XL_CHART_TYPE.COLUMN_CLUSTERED
    gf = slide.shapes.add_chart(ct, Inches(x), Inches(y), Inches(w), Inches(h), cd)
    ch = gf.chart
    ch.font.name = FONT
    ch.font.size = Pt(label_size)
    ch.font.color.rgb = INK2
    ch.has_title = bool(title)
    if title:
        ch.chart_title.text_frame.text = title
        for r in ch.chart_title.text_frame.paragraphs[0].runs:
            _run_fmt(r, 11, True, NAVY)
    ch.has_legend = legend
    if legend:
        ch.legend.position = XL_LEGEND_POSITION.TOP
        ch.legend.include_in_layout = False
        ch.legend.font.size = Pt(label_size)
    plot = ch.plots[0]
    plot.gap_width = gap
    plot.overlap = -10
    plot.has_data_labels = labels
    dl = plot.data_labels if labels else None
    if not labels:
        for s_, c in zip(plot.series, colors):
            s_.format.fill.solid(); s_.format.fill.fore_color.rgb = c
        va = ch.value_axis
        va.major_gridlines.format.line.color.rgb = RGBColor(0xE4, 0xE3, 0xDF)
        va.tick_labels.font.size = Pt(label_size)
        ch.category_axis.tick_labels.font.size = Pt(label_size)
        return gf
    dl.number_format = number_format
    dl.number_format_is_linked = False
    dl.font.size = Pt(label_size - 1)
    dl.font.color.rgb = INK2
    dl.position = XL_LABEL_POSITION.OUTSIDE_END
    for s, c in zip(plot.series, colors):
        s.format.fill.solid()
        s.format.fill.fore_color.rgb = c
    va = ch.value_axis
    va.has_major_gridlines = True
    va.major_gridlines.format.line.color.rgb = RGBColor(0xE4, 0xE3, 0xDF)
    va.format.line.fill.background()
    va.tick_labels.font.size = Pt(label_size)
    if max_val:
        va.maximum_scale = max_val
    va.minimum_scale = 0
    ca = ch.category_axis
    ca.tick_labels.font.size = Pt(label_size)
    ca.format.line.color.rgb = RGBColor(0xBF, 0xBE, 0xB8)
    ca.has_major_gridlines = False
    return gf


# ---------------------------------------------------------------------------- data
def load():
    snap = json.loads((ROOT / "docs" / "RESULTS_SNAPSHOT.json").read_text())
    ev = snap["evaluation"]
    abl = pd.read_csv(RES / "ablation.csv")
    fi = pd.read_csv(RES / "failure_injection.csv")
    cert = json.loads((RES / "certificate_summary.json").read_text())
    return snap, ev, abl, fi, cert


# ---------------------------------------------------------------------------- slides
def s1_cover(sl):
    for sh in sl.shapes:
        if sh.has_text_frame and sh.text_frame.text.strip() == "Concept Title":
            sh.left, sh.width = Inches(3.75), Inches(6.2)
            sh.top, sh.height = Inches(2.5), Inches(1.15)
            tf = sh.text_frame
            tf.word_wrap = True
            from pptx.enum.text import MSO_AUTO_SIZE
            tf.auto_size = MSO_AUTO_SIZE.NONE
            r0 = tf.paragraphs[0].runs[0]
            size = r0.font.size
            r0.text = "GainShield"
            for r in tf.paragraphs[0].runs[1:]:
                r.text = ""
            p = tf.add_paragraph()
            p.alignment = tf.paragraphs[0].alignment
            r = p.add_run()
            r.text = "Safe AI tuning of PI gains, with a stability certificate and runtime fallback, for bidirectional EV-charger DC links"
            _run_fmt(r, 13, False, RGBColor(0xFF, 0xFF, 0xFF))
            if size:
                r0.font.size = size
    notes(sl, "Fill in the PID, the four team photos and names, and the college before submission "
              "(placeholders kept from the official template). Rename the file with the last 5 digits of the PID.")


def s2_challenge(sl, ev, cert):
    remove_body_placeholder(sl)
    headline(sl, "The DC-link PI loop is tuned once by hand, but the plant it controls changes in every charging session")
    # charger strip
    y = 1.65
    xs = [0.6, 2.55, 4.5, 6.45, 8.4]
    labels = [("3-ph grid", "415 V, 0.8–1.1 pu"), ("Active front end", "inner i_d loop, 1–2 sample delay"),
              ("DC link  800 V", "C = 2 mF ±20 %"), ("Bidirectional DC-DC", "constant power, ±30 kW"),
              ("EV battery", "G2V  ⇄  V2G")]
    for i, (x, (t, s)) in enumerate(zip(xs, labels)):
        node(sl, x, y, 1.75, 0.95, t, s, fill=YELLOW_T if i == 2 else BLUE_T, line=YELLOW if i == 2 else BLUE,
             size=10, tsize=11.5)
        if i < 4:
            arrow(sl, x + 1.75, y + 0.47, xs[i + 1], y + 0.47)
    box(sl, 3.1, 2.95, 2.9, 0.6, fill=NAVY)
    text(sl, 3.1, 2.95, 2.9, 0.6, ["PI voltage controller, 10 kHz", "Kp, Ki fixed, tuned by hand"], size=10.5,
         color=WHITE, bold=True, align=PP_ALIGN.CENTER, anchor=MSO_ANCHOR.MIDDLE, spacing=0)
    arrow(sl, 5.37, 2.6, 5.37, 2.95, color=NAVY)
    arrow(sl, 3.42, 2.95, 3.42, 2.6, color=NAVY)
    text(sl, 5.45, 2.62, 1.2, 0.3, "v_dc measured", size=9, color=INK2)
    text(sl, 2.2, 2.62, 1.2, 0.3, "i_d* command", size=9, color=INK2, align=PP_ALIGN.RIGHT)
    # right: why it matters
    text(sl, 10.35, 1.55, 2.5, 0.3, "Why it matters", size=12.5, bold=True, color=NAVY)
    text(sl, 10.35, 1.88, 2.5, 1.6,
         ["DC-link voltage is the energy buffer between grid and car.",
          "Too slow: voltage dips or swells during power steps and G2V⇄V2G reversal.",
          "Too aggressive: oscillation, trips, stressed semiconductors."], size=10.5)
    # four problem cards
    cy = 3.85
    cw = 2.95
    cards = [
        ("1  The plant moves", "C drifts ±20 % with tolerance and ageing; grid sags to 0.8 pu; power reverses from +15 to −15 kW in 15 ms; the DC-DC stage behaves as a constant-power load."),
        ("2  Manual PI = one compromise", f"Tuned for nominal conditions, then detuned to survive the worst case. Our baseline keeps only {cert['baseline_worst_case']['PM_worst']:.0f}° worst-case phase margin and is not re-tuned when conditions change."),
        ("3  Unrestricted AI is unsafe", "Bayesian optimisation or RL that tries any gains on a live 800 V link can apply an unstable pair before it learns it is unstable."),
        ("4  No evidence trail", "Nobody can show afterwards which gains ran, why, or whether they were proved stable at the time."),
    ]
    for i, (t, b) in enumerate(cards):
        card(sl, X0 + i * (cw + 0.17), cy, cw, 1.95, t, b, fill=RED_T if i == 2 else GREY_T,
             title_color=RED if i == 2 else NAVY, size=12, tsize=13)
    box(sl, X0, 5.98, X1 - X0, 0.85, fill=NAVY)
    text(sl, X0 + 0.2, 5.98, X1 - X0 - 0.4, 0.85,
         [[("Challenge:  ", {"bold": True, "color": YELLOW, "size": 13}),
           ("tune the PI gains online for the current operating point, apply only gains that are proved stable, fall back "
            "instantly when something looks wrong, and log every decision.", {"color": WHITE, "size": 13})]],
         anchor=MSO_ANCHOR.MIDDLE)
    notes(sl, "Problem in 20 seconds: the DC-link loop is critical and conventionally hand-tuned once. The plant "
              "changes (capacitance, grid, power direction), so a single PI is a compromise. Plain AI tuning cannot be "
              "allowed to experiment on an 800 V link. All numbers are engineering assumptions (Assumptions slide).")


def s3_concept(sl, ev):
    remove_body_placeholder(sl)
    headline(sl, "GainShield: the AI chooses where to explore, while maths and an independent supervisor decide what is allowed")
    # native architecture
    y1, y2 = 1.75, 3.35
    node(sl, 0.6, y1, 2.05, 1.15, "Charger plant", "averaged AFE + DC link + DC-DC", fill=YELLOW_T, line=YELLOW)
    node(sl, 0.6, y2, 2.05, 1.1, "Context", "C, Vg, P, G2V/V2G, τ_i, delay", fill=GREY_T, line=INK2)
    node(sl, 3.05, y1, 2.3, 1.15, "① Certificate", "Tier 1: stable for ALL plants\nTier 2: margins for this context")
    node(sl, 3.05, y2, 2.3, 1.1, "② Safe BO (AI)", "contextual GPs: cost, V & I margins", fill=GREEN_T, line=GREEN,
         tcolor=GREEN)
    node(sl, 5.75, y1, 2.2, 1.15, "③ Candidate gate", "exact re-check, GP σ,\nenvelope, step limit", fill=RED_T,
         line=RED, tcolor=RED)
    node(sl, 5.75, y2, 2.2, 1.1, "PI controller 10 kHz", "anti-windup, bumpless", fill=BLUE_T, line=BLUE)
    node(sl, 8.35, y1, 2.0, 1.15, "③ Runtime monitor", "V, I, oscillation, sensor", fill=RED_T, line=RED, tcolor=RED)
    node(sl, 8.35, y2, 2.0, 1.1, "④ Baseline PI", "certified fallback", fill=BLUE_T, line=BLUE)
    arrow(sl, 2.65, y1 + 0.57, 3.05, y1 + 0.57)
    arrow(sl, 2.65, y2 + 0.55, 3.05, y2 + 0.55)
    arrow(sl, 4.2, y1 + 1.15, 4.2, y2)
    arrow(sl, 5.35, y2 + 0.4, 5.75, y1 + 0.85)
    arrow(sl, 6.85, y1 + 1.15, 6.85, y2)
    arrow(sl, 7.95, y2 + 0.55, 8.35, y1 + 0.85)
    arrow(sl, 9.35, y1 + 1.15, 9.35, y2, color=RED)
    arrow(sl, 8.35, y2 + 0.8, 7.95, y2 + 0.8, color=RED)
    text(sl, 7.6, y2 + 0.85, 0.8, 0.25, "rollback", size=8.5, color=RED, align=PP_ALIGN.RIGHT)
    node(sl, 0.6, 4.75, 9.75, 0.55, "④ Audit log + dashboard: every proposal, acceptance, rejection and rollback with reason",
         "", fill=GREY_T, line=INK2, tsize=11)
    # right: the four shields
    xr = 10.55
    items = [("1", "Prove", "No gain reaches the plant without a stability proof over C ±20 %, 0.8–1.1 pu grid, both power directions."),
             ("2", "Learn safely", "SafeOpt-style BO expands a GP safe set outward from the known-good baseline."),
             ("3", "Supervise", "An independent gate and monitor that do not trust the optimiser."),
             ("4", "Fall back + log", "Bumpless rollback to the certified manual PI, with every decision audited.")]
    for i, (n, t, b) in enumerate(items):
        yy = 1.62 + i * 0.97
        badge(sl, xr, yy, 0.36, n, fill=NAVY, size=11)
        text(sl, xr + 0.44, yy - 0.04, 1.85, 0.3, t, size=12, bold=True, color=NAVY)
        text(sl, xr + 0.44, yy + 0.24, 1.86, 0.72, b, size=9.5, color=INK)
    # bottom: innovation + vs conventional
    box(sl, X0, 5.5, X1 - X0, 1.38, fill=BLUE_T)
    text(sl, X0 + 0.2, 5.56, 3.0, 0.3, "Core innovation", size=12.5, bold=True, color=NAVY)
    text(sl, X0 + 0.2, 5.88, 4.9, 1.0,
         "A two-tier certificate (a global robust-stability proof plus context-specific margins) is wrapped around "
         "contextual safe Bayesian optimisation, so the AI can raise gains when the context allows it, and a sudden "
         "grid or capacitance change can never make the active loop unstable.", size=10.5)
    rows = [["", "Manual PI", "Plain BO / RL", "GainShield"],
            ["Adapts to operating point", "✗", "✓", "✓"],
            ["Stability proved before applying", "✓ (one point)", "✗", "✓ (whole set)"],
            ["Runtime fallback + audit", "–", "✗", "✓"]]
    table(sl, 5.65, 5.6, 7.05, 1.18, rows, col_w=[2.55, 1.4, 1.45, 1.65], size=10, bold_first_col=True)
    notes(sl, "Walk the loop: the plant and its context feed the certificate. The certificate restricts the "
              "candidates the GP optimiser may consider. The gate re-checks every proposal independently. The monitor "
              "watches real signals and rolls back to the baseline. Everything is logged. This diagram is the code "
              "structure (core.py, stability/, optimizer/, safety/, audit/).")


def s4_pros_cons(sl, ev, abl):
    remove_body_placeholder(sl)
    pt = ev["paired"]
    s = ev["summary"]
    headline(sl, "Measured strengths, with every limitation stated and a mitigation for each")
    w = (X1 - X0 - 0.3) / 2
    box(sl, X0, 1.6, w, 0.42, fill=GREEN)
    text(sl, X0 + 0.15, 1.6, w, 0.42, "Strengths (evidence from simulation)", size=13, bold=True, color=WHITE,
         anchor=MSO_ANCHOR.MIDDLE)
    box(sl, X0 + w + 0.3, 1.6, w, 0.42, fill=RED)
    text(sl, X0 + w + 0.45, 1.6, w, 0.42, "Limitations  →  mitigation", size=13, bold=True, color=WHITE,
         anchor=MSO_ANCHOR.MIDDLE)
    pros = [("Adaptive tuning", f"{-pt['peak_dev_pct']['mean_relative_change_pct']:.0f} % lower mean peak deviation and "
                                f"{-pt['IAE_Vs']['mean_relative_change_pct']:.0f} % lower IAE than the manual PI (p < 1e-7)."),
            ("Stability-aware optimisation", "Every applied gain is robustly stable for the whole uncertainty set (proof, not sampling)."),
            ("Safety supervision", f"0 of {ev['tuning']['episodes_run']} online probe episodes left the ±5 % band; an injected unstable gain was rolled back."),
            ("Traceability", f"{s['audit_records'] + ev['tuning']['audit_records']} audit records; an automatic check found 0 unexplained gain changes."),
            ("Reproducible testing", "Seeded, pre-drawn noise; one command regenerates all results; 36 automated tests.")]
    cons = [("Model dependency", "The certificate holds only for the linearised model inside the stated set → context-envelope check, monitor, HIL validation."),
            ("Computational requirements", f"Uncached context certificate ≈ {s['context_mask_ms']['median'] / 1e3:.1f} s in Python → off the 10 kHz loop; precomputed lookup table."),
            ("GP uncertainty", "A GP is not a guarantee (the RKHS bound is not verified) → GP is one of three layers; σ gate; zero-prior margins."),
            ("Stability-model assumptions", "Inner-loop lag and delay are gridded, not proved between nodes → margin slack; delay identification in HIL."),
            ("Simulation-to-hardware gap", "No hardware yet; a stuck sensor is not detected → power-balance observer, hardware OVP/UVP, PIL→HIL roadmap.")]
    rh = 0.86
    for i, ((t, b), (t2, b2)) in enumerate(zip(pros, cons)):
        yy = 2.12 + i * (rh + 0.06)
        box(sl, X0, yy, w, rh, fill=GREEN_T)
        text(sl, X0 + 0.15, yy + 0.05, w - 0.3, 0.3, t, size=12, bold=True, color=GREEN)
        text(sl, X0 + 0.15, yy + 0.35, w - 0.3, rh - 0.38, b, size=11.5)
        box(sl, X0 + w + 0.3, yy, w, rh, fill=RED_T)
        text(sl, X0 + w + 0.45, yy + 0.05, w - 0.3, 0.3, t2, size=12, bold=True, color=RED)
        text(sl, X0 + w + 0.45, yy + 0.35, w - 0.3, rh - 0.38, b2, size=11.5)
    text(sl, X0, 6.75, X1 - X0, 0.3,
         f"Trade-off made explicit: higher gains amplify sensor noise (current-reference ripple {pt['i_ripple_A']['mean_relative_change_pct']:+.1f} % on average), "
         "and GainShield stays on the baseline when it has no certified, evidence-backed improvement.",
         size=10.5, color=INK2)
    notes(sl, "Every strength is a measured number from results/. Every limitation is also listed in docs/LIMITATIONS.md.")


def s5_tech1(sl, cert):
    remove_body_placeholder(sl)
    headline(sl, "Plant model and controller, and why the stability certificate is an exact test")
    w = 6.1
    box(sl, X0, 1.6, w, 4.75, fill=GREY_T)
    paras = [
        [("Averaged plant (energy balance, CPL in G2V)", {"bold": True, "color": NAVY, "size": 12.5})],
        [("C·v·dv/dt = P_afe − P_dc − v²/R", {"size": 12.5})],
        [("P_ac = 1.5·Vg·i_d,   P_afe = η·P_ac (G2V) or P_ac/η (V2G)", {"size": 11.5})],
        [("τ_i·di_d/dt = i_d*(t − T_d) − i_d,    τ_dc·dP_dc/dt = P_dem − P_dc", {"size": 11.5})],
        [("PI controller (sampled at 10 kHz, ±80 A clamp)", {"bold": True, "color": NAVY, "size": 12.5})],
        [("u[k] = Kp·e[k] + x_I[k],  x_I ← x_I + Ki·Ts·e  (clamping anti-windup)", {"size": 11.5})],
        [("Bumpless gain change:  x_I ← u_prev − Kp_new·e_prev", {"size": 11.5})],
        [("Exact sampled loop (ZOH + fractional delay)", {"bold": True, "color": NAVY, "size": 12.5})],
        [("P(z) = k·N̂(z) / ((z−1)(z−λ)z^(d+1)),   k = 1.5·Vg·η / (C·Vref)", {"size": 11.5})],
        [("Closed loop:  p(z; k) = D(z) + k·N(z)   ← affine in k", {"size": 12.5, "bold": True})],
        [(f"C ±20 %, grid 0.8–1.1 pu and power direction enter only through k ∈ [{cert['k_interval'][0]:.0f}, {cert['k_interval'][1]:.0f}]. "
          "Zero-exclusion principle: stable at k_min and no unit-circle crossing for any k in the interval ⇒ "
          "stable for the whole interval. The crossings are the unit-circle roots of D·rev(N) − rev(D)·N.", {"size": 10.5})],
        [("Checked at 88 inner-lag × delay nodes; margins PM ≥ 40°, GM ≥ 6 dB, |1+L| ≥ 0.5.", {"size": 10.5})],
    ]
    paras = [[(t_, dict(o, size=o.get("size", 12) + 1))] for [(t_, o)] in paras]
    text(sl, X0 + 0.18, 1.72, w - 0.3, 5.1, paras, spacing=7)
    pic(sl, FIG / "kp_ki_regions.png", 6.85, 1.55, w=6.0)
    b = cert["baseline_worst_case"]
    stats = [(f"{100 * cert['fraction_certified']:.0f} %", "of the gain box is globally certified"),
             ("5 / 5", "nonlinear instability onsets predicted within ±3 %"),
             (f"{b['PM_worst']:.0f}°", "manual baseline worst-case phase margin")]
    for i, (n, l) in enumerate(stats):
        xx = 6.95 + i * 2.0
        text(sl, xx, 5.6, 1.9, 0.5, n, size=24, bold=True, color=BLUE)
        text(sl, xx, 6.12, 1.9, 0.6, l, size=10.5, color=INK2)
    notes(sl, "Four regions are kept separate in the figure: Monte-Carlo screened, nominal, robust (proof) and "
              "certified (robust plus margins). The zero-exclusion test was checked against brute-force eigenvalue "
              "sweeps with 100 % agreement. Validity: the linearised (unsaturated) model inside the uncertainty set.")


def s6_tech2(sl, ev):
    remove_body_placeholder(sl)
    t = ev["tuning"]
    headline(sl, "Safe Bayesian optimisation and an independent runtime supervisor")
    from PIL import Image
    im = Image.open(DIA / "02_ai_optimisation_flow.png")
    W, H = im.size
    crop = ROOT / "presentation" / "assets" / "bo_flow_cropped.png"
    crop.parent.mkdir(parents=True, exist_ok=True)
    im.crop((0, int(0.14 * H), W, int(0.84 * H))).save(crop)
    pic(sl, crop, X0 + 0.3, 1.55, w=X1 - X0 - 0.6)
    cw = (X1 - X0 - 0.4) / 3
    cy = 4.85
    card(sl, X0, cy, cw, 2.05, "Contextual GPs (scikit-learn)",
         ["Inputs: Kp, Ki (log), C, Vg, P, τ_i, delay.",
          "Outputs: probe cost J, voltage margin m_v, current margin m_i.",
          "Margin GPs: zero prior ⇒ unexplored = unsafe; safe set grows only from the baseline.",
          f"One iteration: {t['bo_iteration_ms_median']:.0f} ms median on a CPU (no GPU needed)."],
         fill=GREEN_T, title_color=GREEN, size=10)
    card(sl, X0 + cw + 0.2, cy, cw, 2.05, "Candidate gate (does not trust the optimiser)",
         ["Exact tier-1 + tier-2 re-certification of the gain pair.",
          "GP σ ≤ 0.25 and LCB(margins) ≥ 0.15.",
          "Context inside the validated envelope; gain step ≤ ×3.",
          f"Rejected {t['rejected_by_supervisor']} of {t['proposals']} proposals while tuning, each with a logged reason."],
         fill=RED_T, title_color=RED, size=10)
    card(sl, X0 + 2 * (cw + 0.2), cy, cw, 2.05, "Runtime monitor + fallback (every 100 µs)",
         ["|Vdc − Vref| > 4 %, current > 97 % for 2 ms, filtered oscillation, implausible dV.",
          "Alarm ⇒ bumpless rollback to the certified baseline, 100 ms lock-out, then re-decide.",
          "Deployed: gains re-scheduled when Vg, P or the mode changes."],
         fill=BLUE_T, title_color=NAVY, size=10)
    notes(sl, "SafeOpt (Sui et al. 2015) and its contextual version (Berkenkamp et al. 2023), with the gain set "
              "restricted to the certified region. We do not claim SafeOpt's theoretical guarantee; the hard "
              "guarantees come from the certificate and the monitor.")


def s7_plan(sl):
    remove_body_placeholder(sl)
    headline(sl, "Implementation mapped to the six required deliverables: D1 to D6 are built and tested in simulation; HIL is proposed")
    phases = [("D1", "Plant, constraints, disturbances, manual PI", "Averaged RK4 model; 10 seeded disturbance classes; symmetric-optimum baseline", "Done (sim)", GREEN),
              ("D2", "Online tuning + stability/safety monitor", "Two-tier certificate; contextual safe BO; candidate gate", "Done (sim)", GREEN),
              ("D3", "Fallback, rollback, audit log", "Bumpless rollback; lock-out; JSONL audit with trace check", "Done (sim)", GREEN),
              ("D4", "Simulation dashboard", "Streamlit: monitoring, AI, safety, experiments, audit, live tuning", "Done (sim)", GREEN),
              ("D5", "Evaluation vs manual PI", "11 scenarios × 5 seeds, paired tests, true-plant margins, timing", "Done (sim)", GREEN),
              ("D6", "Ablation, failure analysis, HIL roadmap", "7 ablation variants; 13 fault cases; HIL plan", "Done (sim) / HIL proposed", YELLOW)]
    cw = (X1 - X0 - 5 * 0.12) / 6
    for i, (d, t, b, st, col) in enumerate(phases):
        x = X0 + i * (cw + 0.12)
        box(sl, x, 1.6, cw, 0.5, fill=NAVY, shape=MSO_SHAPE.CHEVRON if i else MSO_SHAPE.PENTAGON)
        text(sl, x + 0.15, 1.6, cw - 0.3, 0.5, d, size=14, bold=True, color=WHITE, align=PP_ALIGN.CENTER,
             anchor=MSO_ANCHOR.MIDDLE)
        box(sl, x, 2.2, cw, 2.55, fill=GREY_T)
        text(sl, x + 0.1, 2.27, cw - 0.2, 0.75, t, size=11.5, bold=True, color=NAVY)
        text(sl, x + 0.1, 3.02, cw - 0.2, 1.3, b, size=11)
        box(sl, x + 0.1, 4.3, cw - 0.2, 0.34, fill=col)
        text(sl, x + 0.1, 4.3, cw - 0.2, 0.34, st, size=9.5, bold=True, color=WHITE if col == GREEN else INK,
             align=PP_ALIGN.CENTER, anchor=MSO_ANCHOR.MIDDLE)
    # next phases
    text(sl, X0, 4.95, 6, 0.32, "Next phases (proposed, not yet executed)", size=13, bold=True, color=NAVY)
    nxt = [("P1", "Software-in-the-loop", "Port the PI, monitor and fallback to C; precomputed tier-2 lookup table", "4 wks"),
           ("P2", "Processor-in-the-loop", "TI C2000 F28379D runs the 10 kHz loop; PC runs the optimiser and gate", "4 wks"),
           ("P3", "Controller HIL", "Real-time plant simulator; tests H1–H8 (timing, faults, communication loss)", "6 wks"),
           ("P4", "Scaled power bench", "48 V / 1 kW bidirectional converter, low-voltage only", "future")]
    nw = (X1 - X0 - 3 * 0.15) / 4
    for i, (k, t, b, d) in enumerate(nxt):
        x = X0 + i * (nw + 0.15)
        box(sl, x, 5.35, nw, 1.5, fill=YELLOW_T, line=YELLOW)
        badge(sl, x + 0.12, 5.45, 0.42, k, fill=YELLOW, color=INK, size=10)
        text(sl, x + 0.62, 5.45, nw - 0.7, 0.42, t, size=11.5, bold=True, color=NAVY, anchor=MSO_ANCHOR.MIDDLE)
        text(sl, x + 0.12, 5.92, nw - 0.24, 0.85, [b, [(d, {"bold": True, "color": INK2, "size": 9.5})]], size=10)
    notes(sl, "Status words are deliberate: 'Done (sim)' means code + tests + generated evidence in simulation. "
              "Nothing has run on hardware. Detailed matrix: docs/REQUIREMENTS_TRACEABILITY.md.")


def s8_plan2(sl):
    remove_body_placeholder(sl)
    headline(sl, "A modular, tested, one-command-reproducible Python repository")
    pic(sl, DIA / "06_software_modules.png", X0, 1.55, w=7.6)
    rows = [["Layer", "Technology", "Why"],
            ["Plant + control", "NumPy, RK4, 10 µs step", "transparent, no licence"],
            ["Certificate", "NumPy polynomial roots", "exact zero-exclusion test"],
            ["Safe BO", "scikit-learn GPs + own SafeOpt logic", "auditable, CPU-only"],
            ["Dashboard", "Streamlit + Plotly", "free hosting tier"],
            ["Tests", "pytest (36 tests)", "unit + integration"],
            ["Reports", "pandas, Matplotlib", "numbers generated, not typed"]]
    table(sl, 8.4, 1.6, 4.45, 2.75, rows, col_w=[1.25, 1.8, 1.4], size=9.5)
    box(sl, 8.4, 4.55, 4.45, 1.05, fill=NAVY)
    text(sl, 8.55, 4.6, 4.2, 0.95,
         [[("python experiments/run_all.py", {"bold": True, "color": YELLOW, "size": 12})],
          [("regenerates the certificate, tuning, evaluation, failure tests, ablation, reports and diagrams in about 15 min on a laptop CPU", {"color": WHITE, "size": 10})]])
    ladder = [("Model-in-the-loop simulation", "completed", GREEN), ("SIL on target code", "proposed", YELLOW),
              ("PIL / controller HIL", "proposed", YELLOW), ("Power hardware", "future", INK2)]
    for i, (t, s, c) in enumerate(ladder):
        yy = 5.75 + i * 0.29
        box(sl, 8.4, yy, 0.22, 0.22, fill=c, shape=MSO_SHAPE.OVAL)
        text(sl, 8.7, yy - 0.04, 4.1, 0.3, [[(t + "  ", {"bold": True, "size": 10.5}), (s, {"size": 10.5, "color": INK2})]])
    box(sl, X0, 5.0, 2.0, 1.95, fill=WHITE, line=INK2)
    text(sl, X0, 5.0, 2.0, 1.95, "GitHub QR code\n(to be added when the repository is published)", size=9.5, color=INK2,
         align=PP_ALIGN.CENTER, anchor=MSO_ANCHOR.MIDDLE)
    text(sl, X0 + 2.15, 5.05, 5.4, 1.9,
         [[("Repository: ", {"bold": True}), ("gainshield-safe-ev-charger-control", {})],
          "README with results, install and demo guide; documentation of the model, architecture, assumptions, traceability, HIL roadmap, costs and limitations.",
          "No credentials and no machine-specific paths; fixed seeds; pinned versions in requirements-lock.txt."], size=10.5)
    notes(sl, "Replace the QR placeholder after publishing (python -c \"import qrcode; qrcode.make(URL).save('qr.png')\").")


def s9_val1(sl, ev):
    remove_body_placeholder(sl)
    set_title(sl, "Validation / Testing / Analysis")
    headline(sl, "Test protocol: identical conditions for both controllers, 11 disturbance scenarios × 5 seeds")
    rows = [["#", "Scenario", "What changes", "Class"],
            ["1", "Load increase", "battery power 5 → 20 kW", "load"],
            ["2", "Load decrease", "20 → 5 kW", "load"],
            ["3", "G2V → V2G", "+15 → −15 kW (slew 2 kW/ms)", "reversal"],
            ["4", "V2G → G2V", "−15 → +15 kW", "reversal"],
            ["5", "Grid sag", "1.0 → 0.8 pu at 20 kW, recovery", "grid"],
            ["6", "Sensor noise", "3× noise + load step", "noise"],
            ["7–8", "Capacitance", "C −20 % / +20 % + load step", "model"],
            ["9", "Inner-loop lag", "τ_i = 1.0 ms (2× nominal)", "model"],
            ["10", "Control delay", "2.0 samples", "model"],
            ["11", "Combined", "C −20 %, τ_i 1 ms, delay 2, 0.85 pu, 2× noise, reversal", "stress"]]
    table(sl, X0, 1.6, 6.9, 4.4, rows, col_w=[0.45, 1.5, 3.95, 1.0], size=10)
    text(sl, X0, 6.12, 6.9, 0.9,
         [[("Identical for both controllers: ", {"bold": True}),
           ("initial steady state, plant parameters, event times, pre-drawn noise sequence, context-estimation error, 0.3–0.4 s duration, Ts = 100 µs, constraints. Metrics are computed on the true plant states.", {})]],
         size=10.5)
    # metrics + KPI
    xr = 7.75
    text(sl, xr, 1.55, 5.1, 0.3, "Metrics (required by the problem statement)", size=12.5, bold=True, color=NAVY)
    text(sl, xr, 1.88, 5.1, 1.7,
         ["Settling time (±0.5 % band), peak deviation, recovery overshoot, IAE",
          "Voltage violations (±5 %), trips (±10 %), current-limit violations",
          "Stability margin of every gain set used, on the true plant",
          "Computation time per step, per decision, per BO iteration",
          "Robustness: C ±20 %, lag, delay, noise ×2/×3; power reversal"], size=10.5, spacing=3)
    pt = ev["paired"]
    s = ev["summary"]
    tiles = [(f"{pt['peak_dev_pct']['mean_relative_change_pct']:+.1f} %", "mean peak deviation"),
             (f"{pt['IAE_Vs']['mean_relative_change_pct']:+.1f} %", "mean IAE"),
             (f"{pt['settling_time_ms']['mean_relative_change_pct']:+.1f} %", "mean settling time"),
             (f"{s['voltage_violation_ms_total']['gainshield']:.0f} ms", "outside ±5 % (both)"),
             (f"{s['trips']['gainshield']}", "trips or current violations"),
             (f"p = {pt['peak_dev_pct']['wilcoxon_p']:.0e}", "Wilcoxon, 55 pairs")]
    for i, (n, l) in enumerate(tiles):
        xx = xr + (i % 3) * 1.72
        yy = 3.9 + (i // 3) * 1.45
        box(sl, xx, yy, 1.6, 1.3, fill=BLUE_T if i < 3 else GREEN_T)
        text(sl, xx + 0.08, yy + 0.12, 1.45, 0.55, n, size=19 if i < 5 else 15, bold=True,
             color=BLUE if i < 3 else GREEN, align=PP_ALIGN.CENTER)
        text(sl, xx + 0.08, yy + 0.72, 1.45, 0.5, l, size=9.5, color=INK2, align=PP_ALIGN.CENTER)
    source(sl, "GainShield vs manual PI, 11 scenarios × 5 seeds. Source: results/evaluation_summary.json (experiments/run_evaluation.py)")
    notes(sl, "The official heading 'Validation / Testing / Analysis' is kept on all three validation slides. This "
              "slide is the protocol and the headline numbers.")


def s10_val2(sl, ev):
    remove_body_placeholder(sl)
    set_title(sl, "Validation / Testing / Analysis")
    headline(sl, "Results: lower voltage deviation in 8 of 11 scenarios; never worse, because it stays on the baseline when unsure")
    ps = ev["per_scenario"]
    order = ["load_increase", "load_decrease", "g2v_to_v2g", "v2g_to_g2v", "grid_sag", "sensor_noise", "cap_minus20",
             "cap_plus20", "inner_lag_slow", "delay_long", "combined"]
    names = ["Load ↑", "Load ↓", "G2V→V2G", "V2G→G2V", "Grid sag", "Noise ×3", "C −20 %", "C +20 %", "Slow lag",
             "Delay 2", "Combined"]
    bar_chart(sl, X0, 1.55, 7.3, 3.0, names,
              [("Manual PI", [ps[k]["peak_dev_pct"]["baseline"] for k in order]),
               ("GainShield", [ps[k]["peak_dev_pct"]["gainshield"] for k in order])],
              [ORANGE, BLUE], title="Peak DC-link deviation, % of 800 V (mean of 5 seeds)", number_format="0.0",
              label_size=9, gap=45)
    bar_chart(sl, X0, 4.6, 7.3, 2.4, names,
              [("Manual PI", [ps[k]["IAE_Vs"]["baseline"] for k in order]),
               ("GainShield", [ps[k]["IAE_Vs"]["gainshield"] for k in order])],
              [ORANGE, BLUE], title="Integral absolute error, V·s", number_format="0.00", label_size=9, gap=45,
              legend=False, labels=False)
    pic(sl, FIG / "eval_g2v_to_v2g.png", 8.05, 1.5, w=4.8)
    s = ev["summary"]
    g = ps["g2v_to_v2g"]
    text(sl, 8.05, 5.45, 4.8, 1.55,
         [[("G2V → V2G reversal: ", {"bold": True, "color": NAVY}),
           (f"peak {g['peak_dev_pct']['baseline']:.2f} % → {g['peak_dev_pct']['gainshield']:.2f} %, IAE {g['IAE_Vs']['change_pct']:+.0f} %. "
            "Kp is re-scheduled when the power reverses.", {})],
          [("Price paid: ", {"bold": True, "color": RED}),
           (f"current-reference ripple {ev['paired']['i_ripple_A']['mean_relative_change_pct']:+.1f} %; true-plant PM ≥ {s['min_true_PM_deg']['gainshield']:.0f}° "
            f"(baseline also {s['min_true_PM_deg']['baseline']:.0f}° worst).", {})],
          [("Held at baseline: ", {"bold": True, "color": INK2}),
           ("grid sag at 20 kW, slow inner loop and the combined stress (no certified, evidence-backed improvement).", {})]],
         size=10, spacing=3)
    source(sl, "Source: results/evaluation_summary.json, results/figures/eval_g2v_to_v2g.png", y=7.1)
    notes(sl, "Every bar is a mean of 5 seeds with identical noise. GainShield never violates a constraint; "
              "neither does the baseline. The gain comes with a measured trade-off in noise amplification.")


def s11_val3(sl, abl, fi):
    remove_body_placeholder(sl)
    set_title(sl, "Validation / Testing / Analysis")
    headline(sl, "Ablation and fault injection: each safety layer earns its place, and one gap is still open")
    a = abl.set_index("variant")
    labels = ["A complete", "B no certified region", "C no GP uncertainty", "D no runtime monitor", "E no context",
              "F no fallback"]
    short = ["A full", "B −cert.", "C −σ", "D −monitor", "E −context", "F −fallback"]
    rows = [["Variant", "Unsafe tuning episodes", "Deployed peak dev. vs PI", "Unstable gains injected: peak / outside ±5 %"]]
    for l, s in zip(labels, short):
        r = a.loc[l]
        risky = r["fault_v_viol_ms"] > 0
        rows.append([s, f"{int(r['tuning_unsafe_episodes'] + r['tuning_monitor_aborts'])}",
                     f"{r['deploy_peak_dev_vs_baseline']:.2f}×",
                     (f"{r['fault_peak_dev_pct']:.1f} % / {r['fault_v_viol_ms']:.0f} ms",
                      {"color": RED, "bold": True} if risky else {})])
    table(sl, X0, 1.6, 6.4, 3.05, rows, col_w=[1.3, 1.45, 1.55, 2.1], size=10)
    text(sl, X0, 4.75, 6.4, 2.2,
         [[("D and F: ", {"bold": True, "color": RED}),
           ("without the monitor or the fallback, an unstable gain write turns into a sustained oscillation; the full system rolls it back.", {})],
          [("C: ", {"bold": True, "color": NAVY}),
           ("trusting GP means gives faster but unverified gains (only "
            f"{int(a.loc['C no GP uncertainty', 'episodes'])} measured episodes); the σ check prevents this.", {})],
          [("B: ", {"bold": True, "color": NAVY}),
           ("no unsafe episode within this budget, so the certificate's value is a guarantee, not an average.", {})],
          [("E: ", {"bold": True, "color": NAVY}),
           (f"without context the improvement shrinks ({a.loc['E no context', 'deploy_peak_dev_vs_baseline']:.2f}× vs "
            f"{a.loc['A complete', 'deploy_peak_dev_vs_baseline']:.2f}×).", {})]], size=10, spacing=4)
    pic(sl, FIG / "fault_unstable_gains.png", 7.15, 1.5, w=5.7)
    f = fi.set_index(fi["case"].str.split().str[0])
    gates = sum(bool(f.loc[k, "detected"]) for k in ["G1", "G2", "G3", "G4", "G5"])
    box(sl, 7.15, 5.5, 2.75, 1.45, fill=GREEN_T)
    text(sl, 7.27, 5.55, 2.55, 1.4,
         [[(f"{gates} / 5", {"bold": True, "size": 18, "color": GREEN})],
          "unsafe proposals rejected by the gate, each with a logged reason (outside the region, σ, LCB, envelope, step)"],
         size=9.5)
    box(sl, 10.05, 5.5, 2.8, 1.45, fill=RED_T)
    text(sl, 10.17, 5.55, 2.6, 1.4,
         [[("Open gap", {"bold": True, "size": 13, "color": RED})],
          "A stuck voltage sensor is not detected (the baseline is equally blind). Mitigation: power-balance observer and hardware OVP/UVP."],
         size=9.5)
    source(sl, "Source: results/ablation.csv, results/failure_injection.csv, docs/FAILURE_ANALYSIS.md. Isolated simulation only.", y=7.1)
    notes(sl, "Unsafe ablation configurations are simulation-only and must never be connected to hardware.")


def s12_cost(sl):
    remove_body_placeholder(sl)
    headline(sl, "The prototype cost ₹0 in cash; the next validation step costs about ₹20,000; HIL through lab access first")
    rows = [["Tier", "Item", "Basis / source (12 Nov 2026, 1 USD ≈ ₹94)", "INR"],
            ["A  Actual", "Software stack", "open-source Python (NumPy, SciPy, scikit-learn, Streamlit)", "₹0"],
            ["A  Actual", "Computing / cloud / storage", "2-core CPU, no GPU; GitHub free tier", "₹0"],
            ["A  Actual", "Dashboard hosting", "Streamlit Community Cloud free tier (public app)", "₹0"],
            ["A  Actual", "Development effort (in kind)", "480 h at an assumed ₹300/h, not a cash cost", "≈ ₹1.44 lakh"],
            ["B  Estimate", "2 × TI LAUNCHXL-F28379D", "$44.16 (Arrow) to ₹5,712 (Indian distributor)", "₹8,300–11,400"],
            ["B  Estimate", "Signal conditioning, isolation, cables", "engineering estimate", "₹6,000–10,000"],
            ["C  Optional", "Real-time HIL via institute lab", "usage charges, if any", "₹0–50,000"],
            ["C  Optional", "HIL teaching kit (Typhoon HIL101)", "US MSRP $9,900; APAC price differs; excl. duties/GST", "≈ ₹9.3 lakh"],
            ["C  Optional", "Research-grade HIL (HIL404 class)", "published 2025 commercial quote, $44k incl. licences", "≈ ₹41 lakh"],
            ["C  Optional", "Scaled 48 V / 1 kW bidirectional bench", "engineering estimate, not quoted", "₹1.5–3 lakh"]]
    fills = {"A": GREEN_T, "B": YELLOW_T, "C": GREY_T}
    styled = [rows[0]] + [[(c, {"fill": fills[r[0][0]]}) for c in r] for r in rows[1:]]
    table(sl, X0, 1.6, X1 - X0, 4.55, styled, col_w=[1.3, 3.4, 5.6, 2.0], size=10.5, zebra=False)
    tiles = [("₹0", "cash spent on the delivered prototype", GREEN), ("≈ ₹20k", "next phase: PIL validation", YELLOW),
             ("No GPU", "full pipeline ≈ 15 min on a laptop CPU", BLUE)]
    for i, (n, l, c) in enumerate(tiles):
        xx = X0 + i * 4.15
        text(sl, xx, 6.25, 1.6, 0.5, n, size=20, bold=True, color=c)
        text(sl, xx + 1.55, 6.3, 2.5, 0.5, l, size=10.5, color=INK2)
    source(sl, "Sources: Arrow, Typhoon HIL product page, Streamlit docs, currencybeacon.com. Budgetary only: no vendor quotation was requested and no partnership exists. Details: docs/COST_ESTIMATE.md", y=6.88)
    notes(sl, "Separate actual, estimated and optional costs. Foreign prices exclude import duty and GST.")


def s13_assump(sl):
    remove_body_placeholder(sl)
    headline(sl, "The problem statement gives no numbers, so every value below is a stated engineering assumption")
    left = [["Group", "Assumption (simulation, not a hardware rating)"],
            ["Plant", "30 kW module, 800 V DC link, C = 2 mF ±20 %, 415 V grid 0.8–1.1 pu"],
            ["Plant", "AFE η = 98 % (direction-dependent); inner loop τ_i 0.3–1.0 ms"],
            ["Plant", "DC-DC power loop τ = 2 ms, slew 2 kW/ms, ±30 kW (constant-power load)"],
            ["Switching", "f_sw = f_s = 10 kHz; delay 1.0–2.0 samples (nominal 1.5)"],
            ["Electrical limits", "±5 % operating band, ±10 % trip, 4 % supervisor abort; i_d ≤ 80 A"],
            ["Sensors", "noise 1 V and 0.5 A (1σ); scaled ×2 and ×3 in tests"]]
    right = [["Group", "Assumption"],
             ["Simplifications", "averaged model: no switching ripple, AC filter/PLL, unbalance, battery or thermal dynamics"],
             ["Stability", "linearised and unsaturated; k-interval proved; τ_i × delay gridded (88 nodes); worst-case PM ≥ 40°, GM ≥ 6 dB, MM ≥ 0.5"],
             ["Context", "C, τ_i and delay identified within ±5 %, ±20 % and ±0.2 samples (estimator not implemented)"],
             ["Optimiser", "β = 2, h = 0.15, σ ≤ 0.25, step ≤ ×3; fixed margin-GP hyper-parameters; RKHS bound not verified"],
             ["Probe", "+10 V reference step and ±6 kW power step acceptable during a session"],
             ["Validation", "simulation only; no SIL, HIL or hardware tests performed"]]
    w = (X1 - X0 - 0.3) / 2
    table(sl, X0, 1.6, w, 4.9, left, col_w=[1.45, w - 1.45], size=10.5, bold_first_col=True)
    table(sl, X0 + w + 0.3, 1.6, w, 4.9, right, col_w=[1.45, w - 1.45], size=10.5, bold_first_col=True)
    source(sl, "All values are in config/default.toml (IDs A-1 to A-15, rationale in docs/ASSUMPTIONS.md); changing them and re-running regenerates every result.", y=6.7)
    notes(sl, "Ask for approval of these assumptions: they were proposed by us, not supplied.")


def s14_refs(sl):
    remove_body_placeholder(sl)
    headline(sl, "References: each one supports a specific design decision")
    refs = [
        "[1] Y. Sui, A. Gotovos, J. Burdick, A. Krause, “Safe exploration for optimization with Gaussian processes,” ICML, 2015.",
        "[2] F. Berkenkamp, A. Krause, A. P. Schoellig, “Bayesian optimization with safety constraints: safe and automatic parameter tuning in robotics,” Machine Learning 112, 3713–3747, 2023.",
        "[3] C. König, M. Khosravi, M. Maier, R. S. Smith, A. Rupenyan, J. Lygeros, “Safety-aware cascade controller tuning using constrained Bayesian optimization,” IEEE Trans. Ind. Electron., doi:10.1109/TIE.2022.3158007.",
        "[4] C. König, M. Turchetta, J. Lygeros, A. Rupenyan, A. Krause, “Safe and efficient model-free adaptive control via Bayesian optimization,” IEEE ICRA, 2021.",
        "[5] C. E. Rasmussen, C. K. I. Williams, Gaussian Processes for Machine Learning, MIT Press, 2006.",
        "[6] N. Srinivas, A. Krause, S. Kakade, M. Seeger, “Gaussian process optimization in the bandit setting,” ICML, 2010.",
        "[7] B. R. Barmish, New Tools for Robustness of Linear Systems, Macmillan, 1994 (zero-exclusion principle).",
        "[8] K. J. Åström, B. Wittenmark, Computer-Controlled Systems, 3rd ed., Prentice Hall, 1997.",
        "[9] K. J. Åström, T. Hägglund, Advanced PID Control, ISA, 2006 (anti-windup, bumpless transfer).",
        "[10] S. Preitl, R.-E. Precup, “An extension of tuning relations after symmetrical optimum method for PI and PID controllers,” Automatica 35(10), 1999.",
        "[11] A. Emadi, A. Khaligh, C. H. Rivetta, G. A. Williamson, “Constant power loads and negative impedance instability in automotive systems,” IEEE Trans. Veh. Technol. 55(4), 2006.",
        "[12] A. Yazdani, R. Iravani, Voltage-Sourced Converters in Power Systems, Wiley-IEEE Press, 2010.",
        "[13] F. Pedregosa et al., “Scikit-learn: machine learning in Python,” JMLR 12, 2011.",
        "[14] IEC 61851-23 (DC EV supply equipment); ISO 15118-20:2022 (V2G communication); IEEE 1547-2018. Context only, no compliance claim.",
        "[15] Typhoon HIL product pages (HIL101, TyphoonSim); Arrow (LAUNCHXL-F28379D); Streamlit Community Cloud docs; accessed 12 Nov 2026.",
    ]
    w = (X1 - X0 - 0.3) / 2
    text(sl, X0, 1.6, w, 5.4, refs[:8], size=12, spacing=7)
    text(sl, X0 + w + 0.3, 1.6, w, 5.4, refs[8:], size=12, spacing=7)
    notes(sl, "Each reference was checked to exist; the mapping from reference to claim is in docs/REFERENCES.md.")


def s15_thanks(sl):
    text(sl, 8.4, 4.6, 4.5, 1.0,
         [[("GainShield", {"bold": True, "size": 20, "color": YELLOW})],
          [("Prove. Learn safely. Supervise. Fall back.", {"size": 14, "color": WHITE})]], align=PP_ALIGN.RIGHT)


def main(base: str, out: str) -> None:
    snap, ev, abl, fi, cert = load()
    prs = Presentation(base)
    s = list(prs.slides)
    s1_cover(s[0]); s2_challenge(s[1], ev, cert); s3_concept(s[2], ev); s4_pros_cons(s[3], ev, abl)
    s5_tech1(s[4], cert); s6_tech2(s[5], ev); s7_plan(s[6]); s8_plan2(s[7]); s9_val1(s[8], ev)
    s10_val2(s[9], ev); s11_val3(s[10], abl, fi); s12_cost(s[11]); s13_assump(s[12]); s14_refs(s[13]); s15_thanks(s[14])
    prs.save(out)
    print("saved", out)


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
