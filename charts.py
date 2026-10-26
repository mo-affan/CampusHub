"""Small server-side SVG charts.

Drawn from real query results in Python, so they need no JavaScript library or
internet connection during a demo. Colours come from CSS classes (see
static/css/campushub.css), keeping them consistent with the rest of the UI.
"""
import math

from markupsafe import Markup, escape


def _nice_step(raw):
    if raw <= 0:
        return 1
    exp = 10 ** math.floor(math.log10(raw))
    for m in (1, 2, 2.5, 5, 10):
        if raw <= m * exp:
            return m * exp
    return 10 * exp


def _fmt(v):
    return str(int(v)) if float(v).is_integer() else f"{v:.1f}"


def stacked_columns(labels, series, height=230, width=700, highlight_index=None, aria="Column chart"):
    """labels: list[str]; series: list of {"name", "cls", "values"} stacked bottom-up."""
    n = len(labels)
    if n == 0:
        return Markup("")
    totals = [sum(float(s["values"][i] or 0) for s in series) for i in range(n)]
    step = _nice_step(max(totals + [1]) / 4)
    top = step * max(1, math.ceil(max(totals + [1]) / step))
    pl, pr, pt, pb = 34, 6, 12, 30
    cw, ch = width - pl - pr, height - pt - pb
    slot = cw / n
    bw = min(34, slot * 0.58)
    y = lambda v: pt + ch - (v / top) * ch  # noqa: E731
    parts = [f'<svg class="chart" viewBox="0 0 {width} {height}" role="img" aria-label="{escape(aria)}" '
             f'preserveAspectRatio="xMidYMid meet">']
    tick = 0.0
    while tick <= top + 1e-9:
        yy = y(tick)
        parts.append(f'<line class="grid" x1="{pl}" x2="{width - pr}" y1="{yy:.1f}" y2="{yy:.1f}"/>')
        parts.append(f'<text class="axis" x="{pl - 6}" y="{yy + 4:.1f}" text-anchor="end">{_fmt(tick)}</text>')
        tick += step
    for i, label in enumerate(labels):
        x = pl + slot * i + (slot - bw) / 2
        base = 0.0
        if highlight_index == i:
            parts.append(f'<rect class="col-highlight" x="{pl + slot * i + 2:.1f}" y="{pt}" '
                         f'width="{slot - 4:.1f}" height="{ch}" rx="6"/>')
        for s in series:
            v = float(s["values"][i] or 0)
            if v <= 0:
                continue
            y1, y0 = y(base + v), y(base)
            parts.append(f'<rect class="{s["cls"]}" x="{x:.1f}" y="{y1:.1f}" width="{bw:.1f}" '
                         f'height="{max(0.0, y0 - y1):.1f}" rx="3"><title>{escape(label)} · {escape(s["name"])}: '
                         f'{_fmt(v)}</title></rect>')
            base += v
        if totals[i] > 0:
            parts.append(f'<text class="value" x="{x + bw / 2:.1f}" y="{y(totals[i]) - 5:.1f}" '
                         f'text-anchor="middle">{_fmt(totals[i])}</text>')
        parts.append(f'<text class="axis" x="{x + bw / 2:.1f}" y="{height - 10}" text-anchor="middle">'
                     f'{escape(label)}</text>')
    parts.append("</svg>")
    return Markup("".join(parts))


def donut(segments, size=170, thickness=24, center_value=None, center_label=""):
    """segments: list of {"label", "value", "cls"}."""
    total = sum(float(s["value"] or 0) for s in segments)
    r = (size - thickness) / 2
    c = 2 * math.pi * r
    cx = cy = size / 2
    parts = [f'<svg class="donut" viewBox="0 0 {size} {size}" role="img" aria-label="{escape(center_label)} chart">',
             f'<circle class="donut-track" cx="{cx}" cy="{cy}" r="{r:.2f}" stroke-width="{thickness}" fill="none"/>']
    offset = 0.0
    if total > 0:
        for s in segments:
            v = float(s["value"] or 0)
            if v <= 0:
                continue
            length = v / total * c
            gap = 2 if len([x for x in segments if x["value"]]) > 1 else 0
            parts.append(f'<circle class="{s["cls"]}" cx="{cx}" cy="{cy}" r="{r:.2f}" fill="none" '
                         f'stroke-width="{thickness}" stroke-dasharray="{max(0.0, length - gap):.2f} {c:.2f}" '
                         f'stroke-dashoffset="{-offset:.2f}" transform="rotate(-90 {cx} {cy})">'
                         f'<title>{escape(s["label"])}: {_fmt(v)}</title></circle>')
            offset += length
    value = _fmt(total) if center_value is None else center_value
    parts.append(f'<text class="donut-value" x="{cx}" y="{cy + 2}" text-anchor="middle">{escape(value)}</text>')
    parts.append(f'<text class="donut-label" x="{cx}" y="{cy + 20}" text-anchor="middle">{escape(center_label)}</text>')
    parts.append("</svg>")
    return Markup("".join(parts))
