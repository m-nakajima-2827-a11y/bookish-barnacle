"""原稿JSONから提案書（.pptx）を生成する。

使い方:
    python build_deck.py <原稿.json> <出力.pptx>

デザインは references/design-rules.md（Noto Sans JP Medium／紺・金・緑の3色）に準拠。
原稿の構造は examples/sample-deck.json を参照。文字列中の **...** はアクセント色になる。
"""
import json
import re
import sys

from pptx import Presentation
from pptx.chart.data import CategoryChartData
from pptx.dml.color import RGBColor
from pptx.enum.chart import XL_CHART_TYPE, XL_LABEL_POSITION, XL_MARKER_STYLE
from pptx.enum.shapes import MSO_SHAPE
from pptx.enum.text import MSO_ANCHOR, PP_ALIGN
from pptx.oxml.ns import qn
from pptx.util import Inches, Pt

# Medium は独立したファミリー名で指定し、太字（擬似ボールド）は掛けない
FONT = "Noto Sans JP Medium"
BOLD = False

NAVY = RGBColor(0x1F, 0x3A, 0x5F)
GOLD = RGBColor(0x9A, 0x6F, 0x2E)
GREEN = RGBColor(0x25, 0x6B, 0x64)
INK = RGBColor(0x1A, 0x1A, 0x1A)
SUB = RGBColor(0x6B, 0x6B, 0x6B)
RULE = RGBColor(0xDC, 0xDC, 0xDC)
CARD = RGBColor(0xF5, 0xF5, 0xF2)
CREAM_CARD = RGBColor(0xF5, 0xEE, 0xDF)
TINTS = [CREAM_CARD, RGBColor(0xEA, 0xF0, 0xF7), RGBColor(0xE7, 0xF1, 0xEF)]
ACCENTS = [GOLD, NAVY, GREEN]
WHITE = RGBColor(0xFF, 0xFF, 0xFF)
CREAM = RGBColor(0xEA, 0xD9, 0xB8)
COVER_SUB = RGBColor(0xCB, 0xD5, 0xE6)
COVER_META = RGBColor(0xAE, 0xBB, 0xD2)
GRID = RGBColor(0xED, 0xED, 0xED)
AXIS = RGBColor(0x88, 0x88, 0x88)

W, H = 13.333, 7.5
ML = 0.6
CW = 12.1


def _font(run, size, color, bold=BOLD, spc=None):
    f = run.font
    f.name = FONT
    f.size = Pt(size)
    f.bold = bold
    f.color.rgb = color
    rpr = run._r.get_or_add_rPr()
    for tag in ("a:ea", "a:cs"):
        el = rpr.find(qn(tag))
        if el is None:
            el = rpr.makeelement(qn(tag), {})
            rpr.append(el)
        el.set("typeface", FONT)
    if spc:
        rpr.set("spc", str(spc))


def _runs(p, text, size, color, bold=BOLD, accent=GOLD, spc=None):
    """**...** をアクセント色の run に分けて追加する。"""
    for i, part in enumerate(re.split(r"\*\*(.+?)\*\*", text)):
        if part:
            r = p.add_run()
            r.text = part
            _font(r, size, accent if i % 2 else color, bold, spc)


def text(slide, x, y, w, h, lines, size, color=INK, bold=BOLD, align=PP_ALIGN.LEFT,
         anchor=MSO_ANCHOR.TOP, spacing=None, after=0, accent=GOLD, spc=None):
    box = slide.shapes.add_textbox(Inches(x), Inches(y), Inches(w), Inches(h))
    tf = box.text_frame
    tf.word_wrap = True
    tf.vertical_anchor = anchor
    tf.margin_left = tf.margin_right = tf.margin_top = tf.margin_bottom = 0
    for i, line in enumerate([lines] if isinstance(lines, str) else lines):
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        p.alignment = align
        if spacing:
            p.line_spacing = spacing
        p.space_after = Pt(after)
        segs = line if isinstance(line, list) else [(line, size, color)]
        for seg in segs:
            _runs(p, seg[0], seg[1], seg[2], bold, accent, spc)
    return box


def _flat(sh):
    """テーマ由来の影・効果を外す（p:style を削除）。"""
    st = sh._element.find(qn("p:style"))
    if st is not None:
        sh._element.remove(st)


def card(slide, x, y, w, h, fill=CARD):
    sh = slide.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE,
                                Inches(x), Inches(y), Inches(w), Inches(h))
    sh.adjustments[0] = 0.0235
    sh.fill.solid()
    sh.fill.fore_color.rgb = fill
    sh.line.color.rgb = RULE
    sh.line.width = Pt(1)
    _flat(sh)
    return sh


def badge(slide, x, y, d, label, color):
    sh = slide.shapes.add_shape(MSO_SHAPE.OVAL, Inches(x), Inches(y), Inches(d), Inches(d))
    sh.fill.solid()
    sh.fill.fore_color.rgb = color
    sh.line.fill.background()
    _flat(sh)
    tf = sh.text_frame
    tf.margin_left = tf.margin_right = tf.margin_top = tf.margin_bottom = 0
    tf.vertical_anchor = MSO_ANCHOR.MIDDLE
    p = tf.paragraphs[0]
    p.alignment = PP_ALIGN.CENTER
    _runs(p, label, 20, WHITE)


def navy_bg(slide):
    fill = slide.background.fill
    fill.solid()
    fill.fore_color.rgb = NAVY


def header(slide, label, title, lead=None):
    text(slide, ML, 0.50, 8.0, 0.30, label, 11, GOLD, spc=300)
    text(slide, ML, 0.85, 12.0, 0.80, title, 29)
    if lead:
        text(slide, ML, 1.70, CW, 0.95, lead, 20, spacing=1.2)


def footer(slide, d, page):
    m = d["meta"]
    text(slide, ML, 7.05, 8.0, 0.30, m.get("footer") or f'{m.get("project", "")}｜{m["title"]}', 9, SUB)
    text(slide, 12.4, 7.05, 0.5, 0.30, str(page), 9, SUB, align=PP_ALIGN.RIGHT)


def fit(t, width, max_pt, min_pt):
    """1行に収まる級数（全角1em・半角0.55emで概算）。"""
    em = sum(0.6 if ord(ch) < 0x2E80 else 1.0 for ch in t) or 1
    return max(min_pt, min(max_pt, int(width * 72 / em * 0.85)))


def section_label(no, name):
    return f"{no:02d} ─ {name}"


def slide_cover(prs, d):
    s = prs.slides.add_slide(prs.slide_layouts[6])
    navy_bg(s)
    m = d["meta"]
    if m.get("client"):
        text(s, 0.71, 0.60, 8.0, 0.40, [[(m["client"] + " ", 16, COVER_META), ("御中", 14, COVER_META)]], 16)
    if m.get("project"):
        text(s, 0.67, 1.82, 11.0, 0.40, m["project"], 22, CREAM, spc=200)
    lines = [[(m["title"], 46, WHITE)]]
    if m.get("title_accent"):
        lines.append([(m["title_accent"], 46, CREAM)])
    text(s, ML, 2.51, 12.0, 2.0, lines, 46, spacing=1.05)
    sub = [x for x in [m.get("subtitle"), f'{m.get("date", "")}　{m.get("author", "")}'.strip("　")] if x]
    text(s, ML, 4.91, 11.0, 1.0, sub, 16, COVER_SUB, spacing=1.2)


def slide_overview(prs, d, no, page):
    s = prs.slides.add_slide(prs.slide_layouts[6])
    o = d["overview"]
    header(s, section_label(no, "SUMMARY"), o["title"], o["core"])
    props = o["proposals"][:5]
    n = len(props)
    gap = 0.15
    cw = (CW + 0.12 - gap * (n - 1)) / n
    for i, p in enumerate(props):
        x = ML + 0.06 + i * (cw + gap)
        y = 3.05
        color = ACCENTS[i % 3]
        rows = [("優先度", p["priority"]), ("期間", p["period"]), ("KPI", p["kpi"])]
        if n <= 3:  # 横並び: 番号＋タイトル、項目は1行ずつ
            card(s, x, y, cw, 2.75)
            badge(s, x + 0.17, y + 0.40, 0.59, str(i + 1), color)
            text(s, x + 0.85, y + 0.32, cw - 0.95, 0.80, p["title"], fit(p["title"], cw - 1.0, 24, 18),
                 color, anchor=MSO_ANCHOR.MIDDLE, spacing=1.05)
            for k, (lab, val) in enumerate(rows):
                yy = y + 1.35 + k * 0.42
                text(s, x + 0.34, yy + 0.05, 0.9, 0.3, lab, 11, color, spc=300)
                text(s, x + 1.25, yy, cw - 1.45, 0.4, val, 16)
        else:  # 4〜5件: 番号の下にタイトル、項目はラベルと値を縦積み
            card(s, x, y, cw, 3.7)
            badge(s, x + 0.2, y + 0.25, 0.59, str(i + 1), color)
            text(s, x + 0.2, y + 0.95, cw - 0.4, 0.75, p["title"], fit(p["title"], (cw - 0.4) * 2, 20, 16),
                 color, spacing=1.05)
            for k, (lab, val) in enumerate(rows):
                yy = y + 1.95 + k * 0.58
                text(s, x + 0.2, yy, cw - 0.4, 0.25, lab, 11, color, spc=300)
                text(s, x + 0.2, yy + 0.22, cw - 0.4, 0.35, val, 15)
    footer(s, d, page)


def bullets(items, numbered=False):
    return [f"{i}. {t}" if numbered else f"・{t}" for i, t in enumerate(items[:2], 1)]


def slide_proposal(prs, d, p, idx, no, page):
    s = prs.slides.add_slide(prs.slide_layouts[6])
    header(s, section_label(no, f"PROPOSAL {idx:02d}"), p["title"], p["core"])
    gx, gy, gw, gh = ML, 2.65, 8.25, 4.2
    gap = 0.15
    cw, ch = (gw - gap) / 2, (gh - gap) / 2
    cells = [("課題", "WHY", p["why"], False), ("解決策", "WHAT", p["what"], False),
             ("効果", "ROI", p["roi"], False), ("動き", "NEXT", p["next"], True)]
    for i, (ja, en, items, num) in enumerate(cells):
        x = gx + (i % 2) * (cw + gap)
        y = gy + (i // 2) * (ch + gap)
        color = ACCENTS[i % 3] if i < 3 else NAVY
        card(s, x, y, cw, ch)
        text(s, x + 0.25, y + 0.15, cw - 0.4, 0.30, en, 11, color, spc=300)
        text(s, x + 0.25, y + 0.36, cw - 0.4, 0.45, ja, 21, color)
        text(s, x + 0.25, y + 0.85, cw - 0.45, ch - 0.95, bullets(items, num), 14, spacing=1.15, after=4)
    rx = gx + gw + 0.25
    rw = ML + CW - rx
    if p.get("chart"):
        chart(s, rx, gy, rw, gh, p["chart"])
    elif p.get("metric"):
        metric(s, rx, gy, rw, gh, p["metric"])
    footer(s, d, page)


def metric(slide, x, y, w, h, m):
    card(slide, x, y, w, h, CREAM_CARD)
    value = [(m["value"], 38, GOLD)]
    if m.get("unit"):
        value.append((" " + m["unit"], 14, GOLD))
    text(slide, x + 0.2, y + 0.9, w - 0.4, 0.9, [value], 38, align=PP_ALIGN.CENTER,
         anchor=MSO_ANCHOR.BOTTOM)
    text(slide, x + 0.2, y + 1.9, w - 0.4, 0.8, m["label"], 16, align=PP_ALIGN.CENTER, spacing=1.05)
    if m.get("sub"):
        text(slide, x + 0.2, y + 2.6, w - 0.4, 0.7, m["sub"], 14, GREEN, align=PP_ALIGN.CENTER, spacing=1.1)
    if m.get("note"):
        text(slide, x + 0.2, y + h - 0.55, w - 0.4, 0.4, m["note"], 10.5, SUB, align=PP_ALIGN.CENTER)


def chart(slide, x, y, w, h, c):
    if c.get("title"):
        text(slide, x, y, w, 0.35, c["title"], 14, NAVY)
    data = CategoryChartData()
    data.categories = c["categories"]
    data.add_series("", c["values"])
    line = c.get("type") == "line"
    kind = XL_CHART_TYPE.LINE_MARKERS if line else XL_CHART_TYPE.COLUMN_CLUSTERED
    ch = slide.shapes.add_chart(kind, Inches(x), Inches(y + 0.4), Inches(w),
                                Inches(h - 0.85), data).chart
    ch.has_legend = False
    ch.has_title = False
    ch.font.name = FONT
    ch.font.size = Pt(11)
    ch.font.bold = BOLD
    ch.font.color.rgb = AXIS
    va, ca = ch.value_axis, ch.category_axis
    va.has_major_gridlines = line
    if line:
        va.major_gridlines.format.line.color.rgb = GRID
    va.format.line.fill.background()
    va.visible = line
    ca.format.line.color.rgb = AXIS
    plot = ch.plots[0]
    plot.has_data_labels = True
    dl = plot.data_labels
    unit = c.get("unit", "")
    dec = any(isinstance(v, float) and not float(v).is_integer() for v in c["values"])
    dl.number_format = ('0.0' if dec else '0') + (f'"{unit}"' if unit else "")
    dl.number_format_is_linked = False
    dl.font.size = Pt(11)
    dl.font.bold = BOLD
    dl.font.color.rgb = INK
    ser = plot.series[0]
    if line:
        ser.smooth = False
        ser.format.line.color.rgb = GOLD
        ser.format.line.width = Pt(3)
        ser.marker.style = XL_MARKER_STYLE.CIRCLE
        ser.marker.size = 7
        ser.marker.format.fill.solid()
        ser.marker.format.fill.fore_color.rgb = GOLD
        ser.marker.format.line.color.rgb = GOLD
        dl.position = XL_LABEL_POSITION.ABOVE
    else:
        plot.gap_width = 80
        dl.position = XL_LABEL_POSITION.OUTSIDE_END
        hi = c.get("highlight", len(c["values"]) - 1)
        for i in range(len(c["values"])):
            pt = ser.points[i]
            pt.format.fill.solid()
            pt.format.fill.fore_color.rgb = GOLD if i == hi else RULE
    if c.get("note"):
        text(slide, x, y + h - 0.35, w, 0.3, c["note"], 11, SUB)


def slide_next(prs, d, no, page):
    s = prs.slides.add_slide(prs.slide_layouts[6])
    na = d["next_actions"][:5]
    header(s, section_label(no, "NEXT ACTION"), d.get("next_title", "次の動き"), d.get("next_lead"))
    n = len(na)
    arrow = 0.43
    bw = (CW - arrow * (n - 1)) / n
    y = 3.0
    for i, a in enumerate(na):
        x = ML + i * (bw + arrow)
        color = ACCENTS[i % 3]
        box = s.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, Inches(x), Inches(y), Inches(bw), Inches(0.9))
        box.adjustments[0] = 0.08
        box.fill.solid()
        box.fill.fore_color.rgb = color
        box.line.color.rgb = color
        box.line.width = Pt(1.5)
        _flat(box)
        text(s, x + 0.07, y + 0.05, bw - 0.14, 0.8, f'{"①②③④⑤"[i]} {a["step"]}', 15, WHITE,
             align=PP_ALIGN.CENTER, anchor=MSO_ANCHOR.MIDDLE, spacing=1.05)
        if i < n - 1:
            text(s, x + bw, y, arrow, 0.9, "→", 18, SUB, align=PP_ALIGN.CENTER, anchor=MSO_ANCHOR.MIDDLE)
        card(s, x, y + 1.1, bw, 1.25)
        for k, (lab, val) in enumerate([("担当", a.get("owner", "")), ("期限", a.get("due", ""))]):
            yy = y + 1.3 + k * 0.45
            text(s, x + 0.25, yy + 0.04, 0.7, 0.3, lab, 11, color, spc=300)
            text(s, x + 0.95, yy, bw - 1.15, 0.4, val, 16)
    if d.get("next_note"):
        text(s, ML + 0.19, 6.24, 11.5, 0.47, d["next_note"], 17, NAVY)
    footer(s, d, page)


def slide_appendix(prs, d, ap, no, page):
    s = prs.slides.add_slide(prs.slide_layouts[6])
    header(s, section_label(no, "APPENDIX"), ap["title"])
    head, *rows = ap["rows"]
    widths = ap.get("widths") or [CW / len(head)] * len(head)
    row_h = 0.4
    gt = s.shapes.add_table(len(rows) + 1, len(head), Inches(ML), Inches(1.7),
                            Inches(sum(widths)), Inches(row_h * (len(rows) + 1)))
    tbl = gt.table
    tbl.first_row = False
    tbl.horz_banding = False
    for j, w in enumerate(widths):
        tbl.columns[j].width = Inches(w)
    for i, row in enumerate([head] + rows):
        tbl.rows[i].height = Inches(row_h)
        for j, v in enumerate(row):
            cell = tbl.cell(i, j)
            cell.fill.solid()
            cell.fill.fore_color.rgb = NAVY if i == 0 else WHITE
            cell.vertical_anchor = MSO_ANCHOR.MIDDLE
            cell.margin_left = cell.margin_right = Inches(0.1)
            tf = cell.text_frame
            tf.word_wrap = True
            p = tf.paragraphs[0]
            p.alignment = PP_ALIGN.CENTER if i == 0 else PP_ALIGN.LEFT
            _runs(p, v, 12 if i == 0 else 11, WHITE if i == 0 else INK)
            tcPr = cell._tc.get_or_add_tcPr()
            for k, tag in enumerate(("a:lnL", "a:lnR", "a:lnT", "a:lnB")):
                ln = tcPr.makeelement(qn(tag), {"w": "6350"})
                sf = ln.makeelement(qn("a:solidFill"), {})
                sf.append(sf.makeelement(qn("a:srgbClr"), {"val": "DCDCDC"}))
                ln.append(sf)
                tcPr.insert(k, ln)  # 罫線は塗りより前に置く（スキーマ順）
    if ap.get("note"):
        text(s, ML, 6.75, CW, 0.3, ap["note"], 9, SUB)
    footer(s, d, page)


def slide_closing(prs, d):
    c = d["closing"]
    s = prs.slides.add_slide(prs.slide_layouts[6])
    navy_bg(s)
    text(s, ML, 1.64, 12.0, 0.40, c.get("label") or d["meta"].get("project", ""), 22, CREAM, spc=200)
    lines = [[(c["message"], 46, WHITE)]]
    if c.get("message_accent"):
        lines.append([(c["message_accent"], 46, CREAM)])
    text(s, 0.62, 2.52, 12.0, 2.52, lines, 46, spacing=1.05)


def build(d, out):
    prs = Presentation()
    prs.slide_width, prs.slide_height = Inches(W), Inches(H)
    slide_cover(prs, d)
    page, no = 1, 0
    page += 1; no += 1
    slide_overview(prs, d, no, page)
    for idx, p in enumerate(d["proposals"][:5], 1):
        page += 1; no += 1
        slide_proposal(prs, d, p, idx, no, page)
    if d.get("next_actions"):
        page += 1; no += 1
        slide_next(prs, d, no, page)
    for ap in d.get("appendix", []):
        page += 1; no += 1
        slide_appendix(prs, d, ap, no, page)
    if d.get("closing"):
        page += 1
        slide_closing(prs, d)
    prs.save(out)
    return page


if __name__ == "__main__":
    if len(sys.argv) != 3:
        sys.exit("usage: python build_deck.py <deck.json> <out.pptx>")
    with open(sys.argv[1], encoding="utf-8") as f:
        deck = json.load(f)
    n = len(deck.get("proposals", []))
    if not 3 <= n <= 5:
        sys.exit(f"提案は3〜5点にしてください（現在 {n} 点）")
    pages = build(deck, sys.argv[2])
    print(f"saved {sys.argv[2]} ({pages} slides)")
