#!/usr/bin/env python3
"""Build dashboard.html from data/instantly_raw.json and data/kakiyo_snapshots.jsonl.

Usage: python3 scripts/generate_dashboard.py

Modeled on the "Daily Activity / Weekly Totals / Monthly Totals / Kakiyo
Snapshots (raw)" layout of the team's outreach tracking spreadsheet. Reads
the two data files, merges Instantly's true daily history with Kakiyo's
snapshot-diffed activity, and writes a self-contained dashboard.html at the
repo root. No third-party deps.
"""
import json
from collections import defaultdict
from datetime import date, timedelta
from html import escape
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
OUT_FILE = ROOT / "dashboard.html"

KAKIYO_FIELDS = ["prospects", "invitationsSent", "invitationsAccepted", "messagesSent", "prospectsAnswers", "qualified", "closed"]

SERIES = {
    "blue":   {"light": "#2a78d6", "dark": "#3987e5"},
    "orange": {"light": "#eb6834", "dark": "#d95926"},
    "aqua":   {"light": "#1baf7a", "dark": "#199e70"},
    "yellow": {"light": "#eda100", "dark": "#c98500"},
    "violet": {"light": "#4a3aa7", "dark": "#9085e9"},
    "red":    {"light": "#e34948", "dark": "#e66767"},
}
GOOD = {"light": "#006300", "dark": "#0ca30c"}
BAD = {"light": "#d03b3b", "dark": "#d03b3b"}

INSTANTLY_WEEKLY_METRICS = [("sent", "Sends", "blue"), ("opens", "Opens", "orange"), ("interested", "Interested", "aqua")]
KAKIYO_WEEKLY_METRICS = [("conn_sent", "Connections sent", "blue"), ("conn_accepted", "Connections accepted", "orange"), ("completing_goal", "Completing goal", "aqua")]


# --- date helpers ------------------------------------------------------
def week_start(d):
    return d - timedelta(days=d.weekday())


def week_label(ws):
    we = ws + timedelta(days=6)
    if ws.month == we.month:
        return f"{ws.strftime('%b %-d')}–{we.strftime('%-d')}"
    return f"{ws.strftime('%b %-d')}–{we.strftime('%b %-d')}"


def month_start(d):
    return d.replace(day=1)


def month_label(m):
    return m.strftime("%B %Y")


def daterange(start, end):
    d = start
    while d <= end:
        yield d
        d += timedelta(days=1)


def pct_change(cur, prev):
    if prev == 0:
        return None if cur == 0 else float("inf")
    return (cur - prev) / prev * 100


def fmt_delta(cur, prev):
    d = pct_change(cur, prev)
    if d is None:
        return "<span class='delta flat'>– flat</span>"
    if d == float("inf"):
        return "<span class='delta up'>▲ new</span>"
    arrow = "▲" if d >= 0 else "▼"
    cls = "up" if d >= 0 else "down"
    return f"<span class='delta {cls}'>{arrow} {abs(d):.0f}%</span>"


def fmt_pct(v):
    return f"{v:.1f}%"


def fmt_or_na(v, suffix=""):
    return "N/A" if v is None else f"{v:,}{suffix}"


# --- load data ------------------------------------------------------------
def load_instantly():
    raw = json.loads((DATA_DIR / "instantly_raw.json").read_text())
    by_date = defaultdict(lambda: defaultdict(int))
    for camp in raw["campaigns"]:
        for rec in camp["daily"]:
            d = rec["date"]
            by_date[d]["sent"] += rec.get("sent", 0)
            by_date[d]["opens"] += rec.get("unique_opened", 0)
            by_date[d]["replies"] += rec.get("unique_replies", 0)
            by_date[d]["interested"] += rec.get("opportunities", 0)
    return raw["fetched_at"], by_date


def load_funnel():
    path = DATA_DIR / "funnel.json"
    if not path.exists():
        return None
    return json.loads(path.read_text())


def load_kakiyo_snapshots():
    path = DATA_DIR / "kakiyo_snapshots.jsonl"
    if not path.exists():
        return []
    snaps = [json.loads(line) for line in path.read_text().splitlines() if line.strip()]
    snaps.sort(key=lambda s: s["date"])
    return snaps


def kakiyo_totals(snap):
    out = {}
    for f in KAKIYO_FIELDS:
        vals = [c[f] for c in snap["campaigns"] if f in c]
        out[f] = sum(vals) if vals else None
    return out


def kakiyo_daily_changes(snaps):
    """date -> {'baseline': bool, field: diff-or-None for each KAKIYO_FIELDS}."""
    out = {}
    prev_totals = None
    for snap in snaps:
        t = kakiyo_totals(snap)
        if prev_totals is None:
            out[snap["date"]] = {"baseline": True, "totals": t, **{f: None for f in KAKIYO_FIELDS}}
        else:
            diffs = {}
            for f in KAKIYO_FIELDS:
                diffs[f] = None if (t[f] is None or prev_totals[f] is None) else t[f] - prev_totals[f]
            out[snap["date"]] = {"baseline": False, "totals": t, **diffs}
        prev_totals = t
    return out


# --- merge into a unified daily table --------------------------------------
def build_daily_rows(instantly_by_date, kakiyo_changes):
    dates = set(instantly_by_date.keys()) | set(kakiyo_changes.keys())
    if not dates:
        return []
    lo = date.fromisoformat(min(dates))
    hi = date.fromisoformat(max(dates))
    rows = []
    for d in daterange(lo, hi):
        ds = d.isoformat()
        im = instantly_by_date.get(ds, {})
        sent, opens, replies, interested = im.get("sent", 0), im.get("opens", 0), im.get("replies", 0), im.get("interested", 0)
        open_rate = (opens / sent * 100) if sent else 0.0
        kc = kakiyo_changes.get(ds)
        rows.append({
            "date": ds, "sent": sent, "opens": opens, "open_rate": open_rate, "replies": replies, "interested": interested,
            "conn_sent": None if kc is None else (None if kc["baseline"] else kc["invitationsSent"]),
            "conn_accepted": None if kc is None else (None if kc["baseline"] else kc["invitationsAccepted"]),
            "replied": None if kc is None else (None if kc["baseline"] else kc["prospectsAnswers"]),
            "completing_goal": None if kc is None else (None if kc["baseline"] else kc["qualified"]),
            "kakiyo_note": "Baseline (first snapshot)" if (kc and kc["baseline"]) else None,
        })
    return rows


def aggregate_period(daily_rows, period_key_fn):
    periods = {}
    for row in daily_rows:
        d = date.fromisoformat(row["date"])
        key = period_key_fn(d)
        p = periods.setdefault(key, {"start": key, "sent": 0, "opens": 0, "replies": 0, "interested": 0,
                                      "conn_sent": 0, "conn_accepted": 0, "replied": 0, "completing_goal": 0})
        p["sent"] += row["sent"]
        p["opens"] += row["opens"]
        p["replies"] += row["replies"]
        p["interested"] += row["interested"]
        for f in ("conn_sent", "conn_accepted", "replied", "completing_goal"):
            if row[f] is not None:
                p[f] += row[f]
    for p in periods.values():
        p["open_rate"] = (p["opens"] / p["sent"] * 100) if p["sent"] else 0.0
    return periods


# --- rendering --------------------------------------------------------------
def rounded_top_path(x, y, w, h, r):
    if h <= 0:
        return ""
    r = min(r, w / 2, h)
    if r <= 0:
        return f"M{x},{y+h} L{x},{y} L{x+w},{y} L{x+w},{y+h} Z"
    return f"M{x},{y+h} L{x},{y+r} Q{x},{y} {x+r},{y} L{x+w-r},{y} Q{x+w},{y} {x+w},{y+r} L{x+w},{y+h} Z"


def bar_chart(periods_labeled, series, height=240, width=740):
    if not periods_labeled:
        return "<p class='empty'>No data yet.</p>"
    pad_l, pad_r, pad_t, pad_b = 44, 12, 16, 32
    plot_w = width - pad_l - pad_r
    plot_h = height - pad_t - pad_b
    max_val = 1
    for _, m in periods_labeled:
        for key, _, _ in series:
            max_val = max(max_val, m.get(key, 0))
    max_val *= 1.15

    def y_of(v):
        return pad_t + plot_h - (v / max_val * plot_h)

    grid = []
    for i in range(5):
        v = max_val / 4 * i
        y = y_of(v)
        grid.append(
            f"<line x1='{pad_l}' y1='{y:.1f}' x2='{width-pad_r}' y2='{y:.1f}' class='gridline'/>"
            f"<text x='{pad_l-8}' y='{y+4:.1f}' class='axis-label' text-anchor='end'>{round(v)}</text>"
        )

    group_w = plot_w / len(periods_labeled)
    bar_gap = 2
    n = len(series)
    bars_area = group_w * 0.72
    bar_w = max(4, (bars_area - bar_gap * (n - 1)) / n)

    bars, xlabels = [], []
    for wi, (label, metrics) in enumerate(periods_labeled):
        group_x = pad_l + wi * group_w + (group_w - (bar_w * n + bar_gap * (n - 1))) / 2
        for si, (key, slabel, color) in enumerate(series):
            v = metrics.get(key, 0)
            x = group_x + si * (bar_w + bar_gap)
            y = y_of(v)
            h = pad_t + plot_h - y
            path = rounded_top_path(x, y, bar_w, h, 4)
            if path:
                bars.append(f"<path d='{path}' fill='var(--series-{color})' class='bar'><title>{escape(label)} — {escape(slabel)}: {v:,}</title></path>")
        xlabels.append(f"<text x='{group_x + (bar_w*n + bar_gap*(n-1))/2:.1f}' y='{height-8}' class='axis-label' text-anchor='middle'>{escape(label)}</text>")

    baseline = f"<line x1='{pad_l}' y1='{pad_t+plot_h}' x2='{width-pad_r}' y2='{pad_t+plot_h}' class='baseline'/>"
    legend = "".join(f"<span class='legend-item'><i style='background:var(--series-{color})'></i>{escape(slabel)}</span>" for _, slabel, color in series)

    return (
        f"<div class='chart-wrap'><svg viewBox='0 0 {width} {height}' class='chart' role='img' aria-label='Weekly activity'>"
        f"{''.join(grid)}{baseline}{''.join(bars)}{''.join(xlabels)}</svg>"
        f"<div class='legend'>{legend}</div></div>"
    )


def funnel_chart(stages, hue, split=None):
    """stages: [(label, value), ...] in funnel order (not required to be monotonic).
    hue: 'blue' or 'orange' — the categorical color this platform's funnel is drawn in.
    split: optional {'stage_index': i, 'good_label':..., 'good_value':..., 'bad_label':..., 'bad_value':...}
    to render a positive/negative breakdown bar under one stage."""
    if not stages:
        return "<p class='empty'>No data yet.</p>"
    values = [v for _, v in stages]
    max_v = max(values) or 1
    total = values[0] or 1
    n = len(stages)
    rows = []
    for i, (label, v) in enumerate(stages):
        width_pct = v / max_v * 100
        mix = round(55 * (n - 1 - i) / (n - 1)) if n > 1 else 0
        fill = f"color-mix(in oklab, var(--series-{hue}) {100 - mix}%, var(--surface) {mix}%)"
        of_total = v / total * 100
        if i == 0:
            meta = f"<b>{of_total:.0f}%</b> of total traffic"
        else:
            prev_v = values[i - 1] or 1
            retained = v / prev_v * 100
            meta = f"<b>{of_total:.0f}%</b> of total · <b>{retained:.0f}%</b> of prior stage"
        rows.append(
            "<div class='funnel-row'>"
            f"<div class='funnel-label'>{escape(label)}</div>"
            f"<div class='funnel-track'><div class='funnel-fill' style='width:{width_pct:.1f}%; background:{fill};'></div></div>"
            f"<div class='funnel-value'>{v:,}</div>"
            f"<div class='funnel-meta'>{meta}</div>"
            "</div>"
        )
        if split and split["stage_index"] == i:
            segs = split["segments"]  # [{'label':..., 'value':..., 'cls':'good'|'bad'|'unknown'}, ...]
            seg_total = sum(s["value"] for s in segs) or 1
            bar_html = "".join(
                f"<div class='seg {s['cls']}' style='width:{s['value']/seg_total*100:.1f}%'></div>" for s in segs
            )
            legend_html = "".join(
                f"<span class='legend-item'><i class='{s['cls']}'></i>{s['value']:,} {escape(s['label'])} ({s['value']/seg_total*100:.0f}%)</span>"
                for s in segs
            )
            rows.append(
                f"<div class='funnel-row'><div></div><div class='split-bar'>{bar_html}</div><div></div><div></div></div>"
                f"<div class='funnel-row'><div></div><div class='split-legend'>{legend_html}</div></div>"
            )
    return f"<div class='funnel'>{''.join(rows)}</div>"


def totals_table(periods, keys_labels, label_fn):
    """periods: sorted list of (key, dict). keys_labels: [(field, header)]."""
    head = "".join(f"<th>{h}</th>" for _, h in keys_labels)
    rows = []
    for i, (key, p) in enumerate(periods):
        cells = []
        for field, _ in keys_labels:
            if field == "open_rate":
                cells.append(f"<td>{fmt_pct(p['open_rate'])}</td>")
            else:
                cells.append(f"<td>{p.get(field, 0):,}</td>")
        rows.append(f"<tr><td class='rowhead'>{escape(label_fn(key))}</td>{''.join(cells)}</tr>")
    return f"<div class='table-wrap'><table><thead><tr><th>Period</th>{head}</tr></thead><tbody>{''.join(rows)}</tbody></table></div>"


INSTANTLY_PERIOD_COLS = [("sent", "Sends"), ("opens", "Opens"), ("open_rate", "Open rate"), ("interested", "Interested")]
KAKIYO_PERIOD_COLS = [("conn_sent", "Connections sent"), ("conn_accepted", "Connections accepted"), ("completing_goal", "# Completing goal")]


def instantly_daily_table(rows):
    body = []
    for r in rows:
        body.append(
            f"<tr><td class='rowhead'>{r['date']}</td><td>{r['sent']:,}</td><td>{r['opens']:,}</td>"
            f"<td>{fmt_pct(r['open_rate'])}</td><td>{r['interested']:,}</td></tr>"
        )
    head = "<th>Date</th><th>Sends</th><th>Opens</th><th>Open rate</th><th>Interested</th>"
    return f"<div class='table-wrap'><table><thead><tr>{head}</tr></thead><tbody>{''.join(body)}</tbody></table></div>"


def kakiyo_daily_table(rows):
    body = []
    for r in rows:
        if r["kakiyo_note"]:
            cells = f"<td colspan='3' class='mut'>{r['kakiyo_note']}</td>"
        else:
            cells = f"<td>{fmt_or_na(r['conn_sent'])}</td><td>{fmt_or_na(r['conn_accepted'])}</td><td>{fmt_or_na(r['completing_goal'])}</td>"
        body.append(f"<tr><td class='rowhead'>{r['date']}</td>{cells}</tr>")
    head = "<th>Date</th><th>Conn. sent (daily)</th><th>Conn. accepted (daily)</th><th># Completing goal (daily)</th>"
    return f"<div class='table-wrap'><table><thead><tr>{head}</tr></thead><tbody>{''.join(body)}</tbody></table></div>"


# Metric key can be a plain daily-row field name, or a 2-item list of field names to sum
# together (used by Overview to merge Instantly + Kakiyo into one number — see the footnote
# that ships next to it).
OVERVIEW_COMPARE_METRICS = [
    [["sent", "connSent"], "Sends", False],
    ["opens", "Opens", False],
    [["replies", "replied"], "Replies", False],
    ["interested", "Interested", False],
    ["connAccepted", "Connections accepted", False],
    ["completingGoal", "# Completing goal", False],
]
INSTANTLY_COMPARE_METRICS = [["sent", "Sends", False], ["opens", "Opens", False], ["openRate", "Open rate", True], ["replies", "Replies", False], ["interested", "Interested", False]]
KAKIYO_COMPARE_METRICS = [["connSent", "Connections sent", False], ["connAccepted", "Connections accepted", False], ["replied", "Replies", False], ["completingGoal", "# Completing goal", False]]


def global_compare_picker(min_date, max_date):
    return f"""
    <div id="global-compare">
      <div class="presets">
        <button type="button" data-preset="week">This week vs last week</button>
        <button type="button" data-preset="month">This month vs last month</button>
        <button type="button" data-preset="7d">Last 7 days vs previous 7 days</button>
        <button type="button" data-preset="30d">Last 30 days vs previous 30 days</button>
      </div>
      <div class="range-pickers">
        <div class="range-picker">
          <div class="rp-label"><i style="background:var(--series-blue)"></i>Period A</div>
          <div class="rp-fields">
            <input type="date" data-role="pa-start" min="{escape(min_date)}" max="{escape(max_date)}">
            <span>to</span>
            <input type="date" data-role="pa-end" min="{escape(min_date)}" max="{escape(max_date)}">
          </div>
        </div>
        <div class="range-picker">
          <div class="rp-label"><i style="background:var(--series-yellow)"></i>Period B</div>
          <div class="rp-fields">
            <input type="date" data-role="pb-start" min="{escape(min_date)}" max="{escape(max_date)}">
            <span>to</span>
            <input type="date" data-role="pb-end" min="{escape(min_date)}" max="{escape(max_date)}">
          </div>
        </div>
      </div>
      <p class="note" data-role="range-note"></p>
    </div>
    """


def compare_output(metrics, needs_kakiyo):
    metrics_json = escape(json.dumps(metrics))
    return f'<div class="compare-output" data-metrics=\'{metrics_json}\' data-needs-kakiyo="{"1" if needs_kakiyo else "0"}"></div>'


CSS_TEMPLATE = """
:root { color-scheme: light; }
* { box-sizing: border-box; }
body { margin: 0; font-family: system-ui, -apple-system, "Segoe UI", sans-serif; background: var(--page); color: var(--ink-1); }
.viz-root {
  --page: #f9f9f7; --surface: #fcfcfb; --ink-1:#0b0b0b; --ink-2:#52514e; --ink-mut:#898781;
  --grid:#e1e0d9; --baseline:#c3c2b7; --border: rgba(11,11,11,0.10);
  --good: GOOD_L; --bad: BAD_L;
  --series-blue: BLUE_L; --series-orange: ORANGE_L; --series-aqua: AQUA_L;
  --series-yellow: YELLOW_L; --series-violet: VIOLET_L; --series-red: RED_L;
}
@media (prefers-color-scheme: dark) {
  :root:where(:not([data-theme="light"])) .viz-root {
    --page: #0d0d0d; --surface: #1a1a19; --ink-1:#ffffff; --ink-2:#c3c2b7; --ink-mut:#898781;
    --grid:#2c2c2a; --baseline:#383835; --border: rgba(255,255,255,0.10);
    --good: GOOD_D; --bad: BAD_D;
    --series-blue: BLUE_D; --series-orange: ORANGE_D; --series-aqua: AQUA_D;
    --series-yellow: YELLOW_D; --series-violet: VIOLET_D; --series-red: RED_D;
  }
}
:root[data-theme="dark"] .viz-root {
  --page: #0d0d0d; --surface: #1a1a19; --ink-1:#ffffff; --ink-2:#c3c2b7; --ink-mut:#898781;
  --grid:#2c2c2a; --baseline:#383835; --border: rgba(255,255,255,0.10);
  --good: GOOD_D; --bad: BAD_D;
  --series-blue: BLUE_D; --series-orange: ORANGE_D; --series-aqua: AQUA_D;
  --series-yellow: YELLOW_D; --series-violet: VIOLET_D; --series-red: RED_D;
}
.wrap { max-width: 1100px; margin: 0 auto; padding: 32px 20px 80px; }
h1 { font-size: 1.6rem; margin: 0 0 4px; }
.sub { color: var(--ink-2); margin: 0 0 32px; font-size: 0.95rem; }
h2 { font-size: 1.15rem; margin: 0 0 4px; display:flex; align-items:center; gap:8px; }
h3 { font-size: 0.95rem; margin: 24px 0 4px; color: var(--ink-2); }
h2 .dot { width:10px; height:10px; border-radius:50%; display:inline-block; }
section { background: var(--surface); border: 1px solid var(--border); border-radius: 12px; padding: 24px; margin-bottom: 24px; }
.tiles { display: grid; grid-template-columns: repeat(auto-fit, minmax(140px, 1fr)); gap: 14px; margin: 16px 0; }
.tile { padding: 14px 16px; border: 1px solid var(--border); border-radius: 10px; }
.tile-label { font-size: 0.78rem; color: var(--ink-mut); margin-bottom: 6px; }
.tile-value { font-size: 1.5rem; font-variant-numeric: tabular-nums; }
.tile-sub { font-size: 0.76rem; color: var(--ink-2); margin-top: 4px; }
.delta { font-weight: 600; }
.delta.up { color: var(--good); }
.delta.down { color: var(--bad); }
.delta.flat { color: var(--ink-mut); font-weight: 400; }
.note { font-size: 0.85rem; color: var(--ink-2); margin: 8px 0 0; }
.chart-wrap { margin-top: 16px; }
.chart { width: 100%; height: auto; }
.gridline { stroke: var(--grid); stroke-width: 1; }
.baseline { stroke: var(--baseline); stroke-width: 1; }
.axis-label { fill: var(--ink-mut); font-size: 11px; }
.bar { transition: opacity .1s; }
.bar:hover { opacity: 0.8; }
.legend { display: flex; gap: 16px; flex-wrap: wrap; margin-top: 8px; font-size: 0.8rem; color: var(--ink-2); }
.legend-item { display: inline-flex; align-items: center; gap: 6px; }
.legend-item i { width: 10px; height: 10px; border-radius: 2px; display: inline-block; }
.table-wrap { overflow-x: auto; margin-top: 12px; max-height: 420px; overflow-y: auto; }
table { border-collapse: collapse; width: 100%; font-size: 0.8rem; }
th, td { text-align: left; padding: 7px 10px; border-bottom: 1px solid var(--border); white-space: nowrap; }
th { color: var(--ink-mut); font-weight: 600; font-size: 0.72rem; text-transform: uppercase; letter-spacing: .02em;
  position: sticky; top: 0; background: var(--surface); }
.rowhead { font-weight: 600; }
.pill { display: inline-block; margin-left: 8px; font-size: 0.65rem; font-weight: 500; color: var(--ink-mut);
  border: 1px solid var(--border); border-radius: 999px; padding: 1px 7px; text-transform: uppercase; }
.mut { color: var(--ink-mut); }
.empty { color: var(--ink-mut); font-size: 0.9rem; }
footer { color: var(--ink-mut); font-size: 0.8rem; text-align: center; margin-top: 8px; }

.presets { display: flex; flex-wrap: wrap; gap: 8px; margin: 16px 0; }
.presets button { font: inherit; font-size: 0.8rem; background: var(--surface); color: var(--ink-1);
  border: 1px solid var(--border); border-radius: 999px; padding: 6px 14px; cursor: pointer; }
.presets button:hover { background: var(--grid); }
.presets button.active { background: var(--series-blue); color: #fff; border-color: var(--series-blue); }
.range-pickers { display: grid; grid-template-columns: repeat(auto-fit, minmax(260px, 1fr)); gap: 16px; margin-bottom: 8px; }
.range-picker { border: 1px solid var(--border); border-radius: 10px; padding: 12px 14px; }
.range-picker .rp-label { display:flex; align-items:center; gap:6px; font-size: 0.8rem; font-weight: 600; margin-bottom: 8px; }
.range-picker .rp-label i { width:10px; height:10px; border-radius: 2px; display:inline-block; }
.range-picker .rp-fields { display: flex; align-items: center; gap: 8px; font-size: 0.82rem; }
.range-picker input[type="date"] { font: inherit; font-size: 0.82rem; background: var(--page); color: var(--ink-1);
  border: 1px solid var(--border); border-radius: 6px; padding: 5px 8px; }
.compare-table td.pa { border-left: 3px solid var(--series-blue); }
.compare-table td.pb { border-left: 3px solid var(--series-yellow); }

.funnel { display: flex; flex-direction: column; gap: 14px; margin-top: 12px; }
.funnel-row { display: grid; grid-template-columns: 160px 1fr 70px 210px; align-items: center; gap: 12px; }
.funnel-label { font-size: 0.85rem; font-weight: 600; }
.funnel-track { background: var(--grid); border-radius: 6px; height: 28px; overflow: hidden; }
.funnel-fill { height: 100%; border-radius: 6px 0 0 6px; min-width: 3px; }
.funnel-value { font-size: 0.95rem; font-weight: 700; font-variant-numeric: tabular-nums; text-align: right; }
.funnel-meta { font-size: 0.75rem; color: var(--ink-2); }
.funnel-meta b { color: var(--ink-1); font-variant-numeric: tabular-nums; }
.split-bar { grid-column: 2 / 3; display: flex; height: 10px; border-radius: 5px; overflow: hidden; background: var(--grid); }
.split-bar .seg { height: 100%; min-width: 2px; }
.split-bar .seg.good { background: var(--good); }
.split-bar .seg.bad { background: var(--bad); }
.split-bar .seg.unknown { background: var(--ink-mut); }
.split-legend { grid-column: 2 / 5; display: flex; gap: 16px; font-size: 0.75rem; color: var(--ink-2); }
.split-legend .legend-item i { width: 9px; height: 9px; border-radius: 2px; }
.split-legend .legend-item i.good { background: var(--good); }
.split-legend .legend-item i.bad { background: var(--bad); }
.split-legend .legend-item i.unknown { background: var(--ink-mut); }
@media (max-width: 640px) {
  .funnel-row { grid-template-columns: 1fr; gap: 4px; }
  .funnel-value, .funnel-meta { text-align: left; }
  .split-bar, .split-legend { grid-column: auto; }
}

.tabs { display: flex; gap: 4px; margin: 0 0 20px; border-bottom: 1px solid var(--border); }
.tabs button { font: inherit; font-size: 0.95rem; font-weight: 600; background: none; color: var(--ink-mut);
  border: none; border-bottom: 2px solid transparent; padding: 10px 6px; margin-right: 20px; cursor: pointer;
  display: flex; align-items: center; gap: 8px; }
.tabs button .dot { width:10px; height:10px; border-radius:50%; display:inline-block; }
.tabs button:hover { color: var(--ink-1); }
.tabs button.active { color: var(--ink-1); border-bottom-color: var(--ink-1); }
.tab-panel { display: none; }
.tab-panel.active { display: block; }
"""


COMPARE_JS = """
(function () {
  var dataEl = document.getElementById('daily-data');
  if (!dataEl) return;
  var DAILY = JSON.parse(dataEl.textContent);

  function isoDate(d) { return d.toISOString().slice(0, 10); }
  function parseISO(s) { var p = s.split('-').map(Number); return new Date(Date.UTC(p[0], p[1] - 1, p[2])); }
  function addDays(d, n) { var r = new Date(d); r.setUTCDate(r.getUTCDate() + n); return r; }
  function weekStartOf(d) { var day = (d.getUTCDay() + 6) % 7; return addDays(d, -day); }
  function monthStartOf(d) { return new Date(Date.UTC(d.getUTCFullYear(), d.getUTCMonth(), 1)); }
  function monthEndOf(d) { return new Date(Date.UTC(d.getUTCFullYear(), d.getUTCMonth() + 1, 0)); }

  var lastDate = DAILY.length ? parseISO(DAILY[DAILY.length - 1].date) : new Date();

  function sumRange(start, end) {
    var sent = 0, opens = 0, replies = 0, interested = 0, connSent = 0, connAccepted = 0, replied = 0, completingGoal = 0, hasKakiyo = false, days = 0;
    for (var i = 0; i < DAILY.length; i++) {
      var r = DAILY[i];
      if (r.date < start || r.date > end) continue;
      days++;
      sent += r.sent; opens += r.opens; replies += r.replies; interested += r.interested;
      if (r.conn_sent !== null) { connSent += r.conn_sent; hasKakiyo = true; }
      if (r.conn_accepted !== null) { connAccepted += r.conn_accepted; hasKakiyo = true; }
      if (r.replied !== null) { replied += r.replied; hasKakiyo = true; }
      if (r.completing_goal !== null) { completingGoal += r.completing_goal; hasKakiyo = true; }
    }
    var openRate = sent ? (opens / sent * 100) : 0;
    return { sent: sent, opens: opens, openRate: openRate, replies: replies, interested: interested, connSent: connSent,
      connAccepted: connAccepted, replied: replied, completingGoal: completingGoal, hasKakiyo: hasKakiyo, days: days };
  }

  function fmtDelta(cur, prev) {
    if (prev === 0) {
      if (cur === 0) return "<span class='delta flat'>– flat</span>";
      return "<span class='delta up'>▲ new</span>";
    }
    var d = (cur - prev) / prev * 100;
    var arrow = d >= 0 ? '▲' : '▼';
    var cls = d >= 0 ? 'up' : 'down';
    return "<span class='delta " + cls + "'>" + arrow + ' ' + Math.abs(d).toFixed(0) + "%</span>";
  }

  function fmtPct(v) { return v.toFixed(1) + '%'; }
  function fmtNum(v) { return v.toLocaleString(); }

  // A metric key is either a plain field name, or an array of field names to sum
  // together (Overview merges Instantly + Kakiyo fields into one number this way).
  function getVal(obj, keyOrArr) {
    if (Array.isArray(keyOrArr)) {
      var s = 0;
      for (var i = 0; i < keyOrArr.length; i++) s += (obj[keyOrArr[i]] || 0);
      return s;
    }
    return obj[keyOrArr] || 0;
  }

  var picker = document.getElementById('global-compare');
  if (!picker) return;
  var paStart = picker.querySelector('[data-role="pa-start"]'), paEnd = picker.querySelector('[data-role="pa-end"]');
  var pbStart = picker.querySelector('[data-role="pb-start"]'), pbEnd = picker.querySelector('[data-role="pb-end"]');
  var rangeNote = picker.querySelector('[data-role="range-note"]');
  var presetButtons = picker.querySelectorAll('.presets button');
  var outputs = document.querySelectorAll('.compare-output');
  var lastDateStr = DAILY.length ? DAILY[DAILY.length - 1].date : '';

  function renderOne(out, a, b) {
    var metrics = JSON.parse(out.getAttribute('data-metrics'));
    var needsKakiyo = out.getAttribute('data-needs-kakiyo') === '1';
    var rows = '';
    for (var i = 0; i < metrics.length; i++) {
      var key = metrics[i][0], label = metrics[i][1], isPct = metrics[i][2];
      var av = getVal(a, key), bv = getVal(b, key);
      var avFmt = isPct ? fmtPct(av) : fmtNum(av);
      var bvFmt = isPct ? fmtPct(bv) : fmtNum(bv);
      rows += '<tr><td class="rowhead">' + label + '</td><td class="pa">' + avFmt + '</td><td class="pb">' + bvFmt + '</td><td>' + fmtDelta(av, bv) + '</td></tr>';
    }
    var note = (needsKakiyo && !a.hasKakiyo && !b.hasKakiyo)
      ? "<p class='note'>No Kakiyo snapshot activity fell inside either range — those columns will read 0.</p>" : '';
    out.innerHTML =
      '<div class="table-wrap compare-table"><table>' +
      '<thead><tr><th>Metric</th><th>Period A (' + paStart.value + ' to ' + paEnd.value + ', ' + a.days + 'd)</th>' +
      '<th>Period B (' + pbStart.value + ' to ' + pbEnd.value + ', ' + b.days + 'd)</th><th>A vs B</th></tr></thead>' +
      '<tbody>' + rows + '</tbody></table></div>' + note;
  }

  function renderAll() {
    if (!paStart.value || !paEnd.value || !pbStart.value || !pbEnd.value) return;
    var a = sumRange(paStart.value, paEnd.value);
    var b = sumRange(pbStart.value, pbEnd.value);
    for (var i = 0; i < outputs.length; i++) renderOne(outputs[i], a, b);
    var beyond = lastDateStr && (paEnd.value > lastDateStr || pbEnd.value > lastDateStr);
    rangeNote.textContent = beyond
      ? 'One of the selected ranges extends past ' + lastDateStr + ', the most recent day loaded — those days will read as 0 until the dashboard is refreshed.'
      : '';
  }

  function setPreset(name) {
    var aStart, aEnd, bStart, bEnd;
    if (name === 'week') {
      aStart = weekStartOf(lastDate); aEnd = addDays(aStart, 6);
      bStart = addDays(aStart, -7); bEnd = addDays(bStart, 6);
    } else if (name === 'month') {
      aStart = monthStartOf(lastDate); aEnd = monthEndOf(lastDate);
      var prevAnchor = addDays(aStart, -1);
      bStart = monthStartOf(prevAnchor); bEnd = monthEndOf(prevAnchor);
    } else if (name === '7d') {
      aEnd = lastDate; aStart = addDays(aEnd, -6);
      bEnd = addDays(aStart, -1); bStart = addDays(bEnd, -6);
    } else if (name === '30d') {
      aEnd = lastDate; aStart = addDays(aEnd, -29);
      bEnd = addDays(aStart, -1); bStart = addDays(bEnd, -29);
    } else {
      return;
    }
    paStart.value = isoDate(aStart); paEnd.value = isoDate(aEnd);
    pbStart.value = isoDate(bStart); pbEnd.value = isoDate(bEnd);
    for (var i = 0; i < presetButtons.length; i++) {
      presetButtons[i].classList.toggle('active', presetButtons[i].getAttribute('data-preset') === name);
    }
    renderAll();
  }

  for (var i = 0; i < presetButtons.length; i++) {
    presetButtons[i].addEventListener('click', function (e) { setPreset(e.currentTarget.getAttribute('data-preset')); });
  }
  [paStart, paEnd, pbStart, pbEnd].forEach(function (el) {
    el.addEventListener('change', function () {
      for (var i = 0; i < presetButtons.length; i++) presetButtons[i].classList.remove('active');
      renderAll();
    });
  });

  if (DAILY.length) {
    setPreset('week');
  } else {
    for (var j = 0; j < outputs.length; j++) outputs[j].innerHTML = "<p class='empty'>No data loaded.</p>";
  }
})();
"""

TABS_JS = """
(function () {
  var tabButtons = document.querySelectorAll('.tabs button');
  var panels = document.querySelectorAll('.tab-panel');
  function activate(name) {
    for (var i = 0; i < tabButtons.length; i++) {
      tabButtons[i].classList.toggle('active', tabButtons[i].getAttribute('data-tab') === name);
    }
    for (var j = 0; j < panels.length; j++) {
      panels[j].classList.toggle('active', panels[j].getAttribute('data-tab') === name);
    }
  }
  for (var i = 0; i < tabButtons.length; i++) {
    tabButtons[i].addEventListener('click', function (e) { activate(e.currentTarget.getAttribute('data-tab')); });
  }
  if (tabButtons.length) activate(tabButtons[0].getAttribute('data-tab'));
})();
"""


def build_css():
    subs = {
        "GOOD_L": GOOD["light"], "GOOD_D": GOOD["dark"], "BAD_L": BAD["light"], "BAD_D": BAD["dark"],
        "BLUE_L": SERIES["blue"]["light"], "BLUE_D": SERIES["blue"]["dark"],
        "ORANGE_L": SERIES["orange"]["light"], "ORANGE_D": SERIES["orange"]["dark"],
        "AQUA_L": SERIES["aqua"]["light"], "AQUA_D": SERIES["aqua"]["dark"],
        "YELLOW_L": SERIES["yellow"]["light"], "YELLOW_D": SERIES["yellow"]["dark"],
        "VIOLET_L": SERIES["violet"]["light"], "VIOLET_D": SERIES["violet"]["dark"],
        "RED_L": SERIES["red"]["light"], "RED_D": SERIES["red"]["dark"],
    }
    css = CSS_TEMPLATE
    for k, v in subs.items():
        css = css.replace(k, v)
    return css


def main():
    fetched_at, instantly_by_date = load_instantly()
    kakiyo_snaps = load_kakiyo_snapshots()
    kakiyo_changes = kakiyo_daily_changes(kakiyo_snaps)

    daily_rows = build_daily_rows(instantly_by_date, kakiyo_changes)
    weekly = aggregate_period(daily_rows, week_start)
    monthly = aggregate_period(daily_rows, month_start)

    weekly_sorted = sorted(weekly.items())
    monthly_sorted = sorted(monthly.items())

    kakiyo_has_history = sum(1 for s in kakiyo_snaps if not kakiyo_changes[s["date"]]["baseline"]) > 0

    min_date = daily_rows[0]["date"] if daily_rows else ""
    max_date = daily_rows[-1]["date"] if daily_rows else ""
    daily_rows_json = json.dumps(daily_rows).replace("</", "<\\/")

    global_picker = global_compare_picker(min_date, max_date)
    overview_output = compare_output(OVERVIEW_COMPARE_METRICS, True)
    instantly_output = compare_output(INSTANTLY_COMPARE_METRICS, False)
    kakiyo_output = compare_output(KAKIYO_COMPARE_METRICS, True)
    overview_footnote = (
        "<p class='note'>\"Sends\" combines Instantly's emails sent and Kakiyo's connection requests sent — both "
        "are the first outreach touch on their platform, so they're counted as the same step here. \"Replies\" "
        "combines both platforms' reply counts the same way.</p>"
    )

    weekly_chart_periods = [(week_label(k), p) for k, p in weekly_sorted]
    instantly_weekly_table = totals_table(weekly_sorted, INSTANTLY_PERIOD_COLS, lambda k: f"{week_label(k)} ({k.isoformat()} start)")
    kakiyo_weekly_table = totals_table(weekly_sorted, KAKIYO_PERIOD_COLS, lambda k: f"{week_label(k)} ({k.isoformat()} start)")
    instantly_monthly_table = totals_table(monthly_sorted, INSTANTLY_PERIOD_COLS, lambda k: month_label(k))
    kakiyo_monthly_table = totals_table(monthly_sorted, KAKIYO_PERIOD_COLS, lambda k: month_label(k))

    instantly_chart = bar_chart(weekly_chart_periods, INSTANTLY_WEEKLY_METRICS)
    kakiyo_chart = bar_chart(weekly_chart_periods, KAKIYO_WEEKLY_METRICS) if kakiyo_has_history else (
        "<p class='empty'>Not enough Kakiyo snapshots yet to chart week-over-week change — need at least 2.</p>"
    )

    instantly_daily = instantly_daily_table(daily_rows)
    kakiyo_daily = kakiyo_daily_table(daily_rows)

    funnel = load_funnel()
    if funnel:
        fi, fk = funnel["instantly"], funnel["kakiyo"]
        instantly_funnel = funnel_chart(
            [("Total unique contacts", fi["total_unique_contacts"]), ("Emails sent", fi["emails_sent"]),
             ("Emails replied", fi["emails_replied"]), ("Sales", fi["conversions"])],
            "blue",
            split={"stage_index": 2, "segments": [
                {"label": "positive", "value": fi["emails_replied_positive"], "cls": "good"},
                {"label": "negative", "value": fi["emails_replied_negative"], "cls": "bad"},
                {"label": "unknown", "value": fi["emails_replied_unknown"], "cls": "unknown"},
            ]},
        )
        instantly_funnel += (
            "<p class='note'>Emails sent can exceed total unique contacts because each contact receives multiple "
            "steps in a sequence. \"Unknown\" replies are ones Instantly hasn't been marked interested or not "
            f"interested yet — not counted as negative. Snapshot as of {escape(funnel['fetched_at'])} "
            f"({escape(fi.get('source',''))}). \"Sales\" is currently sourced from Instantly's own Closed/Won "
            "status — a firmer source for this number is still being worked out.</p>"
        )
        kakiyo_funnel = funnel_chart(
            [("Connections sent", fk["connections_sent"]), ("Connections accepted", fk["connections_accepted"]),
             ("Contacts replied", fk["contacts_replied"]), ("Contacts qualified", fk["contacts_qualified"]),
             ("Sales", fk["conversions"])],
            "orange",
        )
        kakiyo_funnel += (
            f"<p class='note'>Snapshot as of {escape(funnel['fetched_at'])} ({escape(fk.get('source',''))}). "
            "\"Sales\" is currently sourced from Kakiyo's own `closed` status — a firmer source for this number "
            "is still being worked out.</p>"
        )
    else:
        instantly_funnel = kakiyo_funnel = "<p class='empty'>No funnel data recorded yet — see data/funnel.json.</p>"

    kakiyo_note = (
        "<p class='note'>Kakiyo's API only exposes running totals, not a historical daily feed. Each refresh appends a "
        "dated snapshot, and this dashboard diffs consecutive snapshots to build day/week/month activity — the "
        "2026-07-30 baseline came from the team's existing tracking spreadsheet; everything after is pulled live. "
        "Weeks/months before snapshot tracking began show 0 for Kakiyo columns because no snapshot existed yet, not "
        "because activity was zero.</p>"
    )

    html_out = f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Outreach Activity Dashboard</title>
<style>{build_css()}</style>
</head>
<body>
<div class="viz-root">
<div class="wrap">
  <h1>Outreach Activity Dashboard</h1>
  <p class="sub">Week-over-week activity across Kakiyo (LinkedIn) and Instantly (Email) campaigns. Data fetched {escape(fetched_at)}.</p>

  <section>
    <h2>Compare periods</h2>
    <p class="sub" style="margin-bottom:12px;">All {len(daily_rows)} loaded days ({escape(min_date)} to {escape(max_date)}) are available to compare — pick any two ranges, or use a preset. This controls every metric below: the overview and each platform's own totals.</p>
    {global_picker}
  </section>

  <section>
    <h2>Overview</h2>
    {overview_output}
    {overview_footnote}
  </section>

  <div class="tabs">
    <button type="button" data-tab="instantly"><span class="dot" style="background:var(--series-blue)"></span>Instantly (email)</button>
    <button type="button" data-tab="kakiyo"><span class="dot" style="background:var(--series-orange)"></span>Kakiyo (LinkedIn)</button>
  </div>

  <div class="tab-panel" data-tab="instantly">
    <section>
      <h2>Selected period</h2>
      {instantly_output}
    </section>

    <section>
      <h2>Funnel</h2>
      {instantly_funnel}
    </section>

    <section>
      <h2>Weekly totals</h2>
      {instantly_chart}
      {instantly_weekly_table}
    </section>

    <section>
      <h2>Monthly totals</h2>
      {instantly_monthly_table}
    </section>

    <section>
      <h2>Daily activity</h2>
      {instantly_daily}
    </section>
  </div>

  <div class="tab-panel" data-tab="kakiyo">
    <section>
      <h2>Selected period</h2>
      {kakiyo_output}
    </section>

    <section>
      <h2>Funnel</h2>
      {kakiyo_funnel}
    </section>

    <section>
      <h2>Weekly totals</h2>
      {kakiyo_chart}
      {kakiyo_note}
      {kakiyo_weekly_table}
    </section>

    <section>
      <h2>Monthly totals</h2>
      {kakiyo_monthly_table}
    </section>

    <section>
      <h2>Daily activity</h2>
      {kakiyo_daily}
    </section>
  </div>

  <footer>Regenerate with <code>python3 scripts/generate_dashboard.py</code> after refreshing data/. See README.md.</footer>
</div>
</div>
<script id="daily-data" type="application/json">{daily_rows_json}</script>
<script>{COMPARE_JS}</script>
<script>{TABS_JS}</script>
</body>
</html>
"""
    OUT_FILE.write_text(html_out)
    print(f"Wrote {OUT_FILE}")


if __name__ == "__main__":
    main()
