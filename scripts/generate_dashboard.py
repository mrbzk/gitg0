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
from datetime import date, datetime, timedelta
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


def uk_date(iso_str):
    """'YYYY-MM-DD' (or a full ISO timestamp) -> 'DD/MM/YYYY'."""
    if not iso_str:
        return iso_str
    try:
        d = datetime.fromisoformat(iso_str[:10])
    except ValueError:
        return iso_str
    return d.strftime("%d/%m/%Y")


def uk_datetime(iso_str):
    """Full ISO timestamp (e.g. '...Z') -> 'DD/MM/YYYY HH:MM UTC'."""
    if not iso_str:
        return iso_str
    try:
        d = datetime.fromisoformat(iso_str.replace("Z", "+00:00"))
    except ValueError:
        return iso_str
    return d.strftime("%d/%m/%Y %H:%M") + " UTC"


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
            "conn_sent": None if kc is None else (kc["totals"]["invitationsSent"] if kc["baseline"] else kc["invitationsSent"]),
            "conn_accepted": None if kc is None else (kc["totals"]["invitationsAccepted"] if kc["baseline"] else kc["invitationsAccepted"]),
            "replied": None if kc is None else (kc["totals"]["prospectsAnswers"] if kc["baseline"] else kc["prospectsAnswers"]),
            "completing_goal": None if kc is None else (kc["totals"]["qualified"] if kc["baseline"] else kc["qualified"]),
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


def bar_chart(periods_labeled, series, height=240, width=740, scrollable=False):
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

    wrap_class = "chart-wrap wide" if scrollable else "chart-wrap"
    svg_style = f" style='width:{width}px'" if scrollable else ""
    return (
        f"<div class='{wrap_class}'><svg viewBox='0 0 {width} {height}' class='chart'{svg_style} role='img' aria-label='Activity'>"
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


def active_conversations_tile(fk):
    if "active_conversations" not in fk:
        return "<p class='empty'>No active-conversation data recorded yet.</p>"
    days = fk.get("active_conversations_window_days", 3)
    fetched = fk.get("active_conversations_fetched_at", "")
    return (
        "<div class='tiles'><div class='tile'>"
        f"<div class='tile-label'>Active conversations (last {days} days)</div>"
        f"<div class='tile-value'>{fk['active_conversations']:,}</div>"
        "<div class='tile-sub'>Replied or qualified, with their last message inside the window</div>"
        "</div></div>"
        f"<p class='note'>As of {escape(uk_datetime(fetched))}.</p>"
    )


def info_icon(text):
    return (
        "<span class='info-wrap'>"
        "<button type='button' class='info-icon' aria-label='About this section'>i</button>"
        f"<span class='info-tip' role='tooltip'>{escape(text)}</span>"
        "</span>"
    )


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
            f"<tr><td class='rowhead'>{uk_date(r['date'])}</td><td>{r['sent']:,}</td><td>{r['opens']:,}</td>"
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
        body.append(f"<tr><td class='rowhead'>{uk_date(r['date'])}</td>{cells}</tr>")
    head = "<th>Date</th><th>Conn. sent (daily)</th><th>Conn. accepted (daily)</th><th># Completing goal (daily)</th>"
    return f"<div class='table-wrap'><table><thead><tr>{head}</tr></thead><tbody>{''.join(body)}</tbody></table></div>"


def granularity_section(weekly_chart, weekly_table, monthly_chart, monthly_table, daily_chart, daily_table, note=""):
    return f"""
    <div class="granularity-group">
      <div class="granularity-switch">
        <label>View: <select data-role="granularity-select">
          <option value="weekly" selected>Weekly totals</option>
          <option value="monthly">Monthly totals</option>
          <option value="daily">Daily activity</option>
        </select></label>
      </div>
      {note}
      <div class="granularity-panel active" data-granularity="weekly">
        {weekly_chart}
        {weekly_table}
      </div>
      <div class="granularity-panel" data-granularity="monthly">
        {monthly_chart}
        {monthly_table}
      </div>
      <div class="granularity-panel" data-granularity="daily">
        {daily_chart}
        {daily_table}
      </div>
    </div>
    """


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
      <label class="compare-toggle">
        <input type="checkbox" data-role="compare-toggle">
        Compare to a previous period
      </label>
      <div class="presets" data-role="presets-single">
        <button type="button" data-preset="this-week">This week</button>
        <button type="button" data-preset="this-month">This month</button>
        <button type="button" data-preset="last-7d">Last 7 days</button>
        <button type="button" data-preset="last-30d">Last 30 days</button>
        <button type="button" data-preset="custom">Custom</button>
      </div>
      <div class="presets" data-role="presets-compare">
        <button type="button" data-preset="week">This week vs last week</button>
        <button type="button" data-preset="month">This month vs last month</button>
        <button type="button" data-preset="7d">Last 7 days vs previous 7 days</button>
        <button type="button" data-preset="30d">Last 30 days vs previous 30 days</button>
      </div>
      <div class="range-pickers">
        <div class="range-picker">
          <div class="rp-label"><i style="background:var(--series-blue)"></i><span data-role="pa-title">Period</span></div>
          <div class="rp-fields">
            <input type="date" data-role="pa-start" min="{escape(min_date)}" max="{escape(max_date)}">
            <span>to</span>
            <input type="date" data-role="pa-end" min="{escape(min_date)}" max="{escape(max_date)}">
          </div>
        </div>
        <div class="range-picker" data-role="pb-picker">
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
html, body { margin: 0; min-height: 100%; }
body { font-family: 'Inter', system-ui, -apple-system, "Segoe UI", sans-serif; }
.viz-root {
  display: block; min-height: 100vh; background: var(--page); color: var(--ink-1);
  font-family: inherit;
  --gittgo-navy: #16222f; --gittgo-navy-2: #1d2f42; --gittgo-lime: #b6e23a; --gittgo-lime-2: #cdf05e;
  --gittgo-cream: #f7f6f1; --gittgo-coral: #ff6b57;
  --page: var(--gittgo-cream); --surface: #ffffff; --ink-1: var(--gittgo-navy); --ink-2:#5b6a76; --ink-mut:#8a97a1;
  --grid:#e4e2da; --baseline:#c9c6ba; --border: rgba(22,34,47,0.14);
  --good: GOOD_L; --bad: BAD_L;
  --series-blue: BLUE_L; --series-orange: ORANGE_L; --series-aqua: AQUA_L;
  --series-yellow: YELLOW_L; --series-violet: VIOLET_L; --series-red: RED_L;
}
@media (prefers-color-scheme: dark) {
  :root:where(:not([data-theme="light"])) { color-scheme: dark; }
  :root:where(:not([data-theme="light"])) .viz-root {
    --page: var(--gittgo-navy); --surface: var(--gittgo-navy-2); --ink-1: var(--gittgo-cream); --ink-2: rgba(247,246,241,.72); --ink-mut: rgba(247,246,241,.55);
    --grid: rgba(247,246,241,.12); --baseline: rgba(247,246,241,.22); --border: rgba(247,246,241,0.14);
    --good: GOOD_D; --bad: BAD_D;
    --series-blue: BLUE_D; --series-orange: ORANGE_D; --series-aqua: AQUA_D;
    --series-yellow: YELLOW_D; --series-violet: VIOLET_D; --series-red: RED_D;
  }
}
:root[data-theme="dark"] { color-scheme: dark; }
:root[data-theme="dark"] .viz-root {
  --page: var(--gittgo-navy); --surface: var(--gittgo-navy-2); --ink-1: var(--gittgo-cream); --ink-2: rgba(247,246,241,.72); --ink-mut: rgba(247,246,241,.55);
  --grid: rgba(247,246,241,.12); --baseline: rgba(247,246,241,.22); --border: rgba(247,246,241,0.14);
  --good: GOOD_D; --bad: BAD_D;
  --series-blue: BLUE_D; --series-orange: ORANGE_D; --series-aqua: AQUA_D;
  --series-yellow: YELLOW_D; --series-violet: VIOLET_D; --series-red: RED_D;
}
.wrap { max-width: 1100px; margin: 0 auto; padding: 32px 20px 80px; }
h1, h2, h3 { font-family: 'Poppins', 'Inter', sans-serif; font-weight: 800; letter-spacing: -0.01em; }
h1 { font-size: 1.7rem; margin: 0 0 4px; }
.sub { color: var(--ink-2); margin: 0 0 32px; font-size: 0.95rem; }
.page-header { display: flex; align-items: center; gap: 18px; }
.brand-logo { flex-shrink: 0; }
.brand-mark { display: inline-block; font-family: 'Poppins', 'Inter', sans-serif; font-weight: 800; font-size: 1.05rem;
  color: var(--gittgo-lime); background: var(--gittgo-navy); border: 2px solid var(--gittgo-lime);
  border-radius: 11px; padding: 6px 16px; line-height: 1.2; letter-spacing: -0.01em; }
.page-header-text { min-width: 0; }
@media (max-width: 640px) {
  .page-header { flex-direction: column; align-items: flex-start; gap: 12px; }
}
h2 { font-size: 1.15rem; margin: 0 0 4px; display:flex; align-items:center; gap:8px; }
h3 { font-size: 0.95rem; margin: 24px 0 4px; color: var(--ink-2); font-weight: 700; }
h2 .dot { width:10px; height:10px; border-radius:50%; display:inline-block; }
section { background: var(--surface); border: 1px solid var(--border); border-radius: 18px; padding: 24px; margin-bottom: 24px; }
.collapsible > summary { cursor: pointer; list-style: none; display: flex; align-items: center; gap: 8px; }
.collapsible > summary::-webkit-details-marker { display: none; }
.collapsible > summary h2 { margin: 0; }
.collapsible > summary .chevron { display: inline-block; font-size: 0.75rem; color: var(--ink-mut);
  transition: transform .15s ease; }
.collapsible:not([open]) > summary .chevron { transform: rotate(-90deg); }
.collapsible:not([open]) > summary { margin-bottom: 0; }
.collapsible-body { margin-top: 16px; }
.tiles { display: grid; grid-template-columns: repeat(auto-fit, minmax(140px, 1fr)); gap: 14px; margin: 16px 0; }
.tile { padding: 14px 16px; border: 1px solid var(--border); border-radius: 14px; }
.tile-label { font-size: 0.78rem; color: var(--ink-mut); margin-bottom: 6px; }
.tile-value { font-family: 'Poppins', 'Inter', sans-serif; font-weight: 800; font-size: 1.5rem; font-variant-numeric: tabular-nums; }
.tile-sub { font-size: 0.76rem; color: var(--ink-2); margin-top: 4px; }
.delta { font-weight: 600; }
.delta.up { color: var(--good); }
.delta.down { color: var(--bad); }
.delta.flat { color: var(--ink-mut); font-weight: 400; }
.note { font-size: 0.85rem; color: var(--ink-2); margin: 8px 0 0; }
.chart-wrap { margin-top: 16px; }
.chart-wrap.wide { overflow-x: auto; }
.chart { width: 100%; height: auto; }
.gridline { stroke: var(--grid); stroke-width: 1; }
.baseline { stroke: var(--baseline); stroke-width: 1; }
.axis-label { fill: var(--ink-mut); font-size: 11px; }
.bar { transition: opacity .1s; }
.bar:hover { opacity: 0.8; }
.legend { display: flex; gap: 16px; flex-wrap: wrap; margin-top: 8px; font-size: 0.8rem; color: var(--ink-2); }
.legend-item { display: inline-flex; align-items: center; gap: 6px; }
.legend-item i { width: 10px; height: 10px; border-radius: 2px; display: inline-block; }
.table-wrap { overflow-x: auto; margin-top: 12px; }
table { border-collapse: collapse; width: 100%; font-size: 0.8rem; }
th, td { text-align: left; padding: 7px 10px; border-bottom: 1px solid var(--border); white-space: nowrap; }
th { color: var(--ink-mut); font-weight: 600; font-size: 0.72rem; text-transform: uppercase; letter-spacing: .02em;
  background: var(--surface); }
.rowhead { font-weight: 600; }
.pagination-bar { display: flex; flex-wrap: wrap; align-items: center; justify-content: space-between; gap: 10px;
  margin-top: 10px; padding-top: 10px; border-top: 1px solid var(--border); font-size: 0.78rem; color: var(--ink-2); }
.pagination-size { display: flex; align-items: center; gap: 6px; }
.pagination-size select { font: inherit; font-size: 0.78rem; background: var(--page); color: var(--ink-1);
  border: 1px solid var(--border); border-radius: 999px; padding: 4px 10px; }
.pagination-nav { display: flex; align-items: center; gap: 8px; }
.pagination-nav button { font: inherit; font-family: 'Poppins', 'Inter', sans-serif; font-weight: 600; font-size: 0.78rem;
  background: var(--surface); color: var(--ink-1);
  border: 1px solid var(--border); border-radius: 999px; padding: 4px 12px; cursor: pointer; }
.pagination-nav button:hover:not(:disabled) { background: var(--grid); }
.pagination-nav button:disabled { opacity: 0.4; cursor: default; }
.pagination-page { font-variant-numeric: tabular-nums; min-width: 44px; text-align: center; }
.pill { display: inline-block; margin-left: 8px; font-size: 0.65rem; font-weight: 500; color: var(--ink-mut);
  border: 1px solid var(--border); border-radius: 999px; padding: 1px 7px; text-transform: uppercase; }
.mut { color: var(--ink-mut); }
.empty { color: var(--ink-mut); font-size: 0.9rem; }
footer { color: var(--ink-mut); font-size: 0.8rem; text-align: center; margin-top: 8px; }

.info-wrap { position: relative; display: inline-flex; }
.info-icon { width: 17px; height: 17px; border-radius: 50%; border: 1px solid var(--border); background: var(--surface);
  color: var(--ink-mut); font-size: 11px; font-weight: 700; font-style: italic; font-family: Georgia, "Times New Roman", serif;
  line-height: 1; cursor: pointer; display: inline-flex; align-items: center; justify-content: center; padding: 0; }
.info-icon:hover, .info-icon:focus-visible { color: var(--gittgo-navy); border-color: var(--gittgo-lime); background: var(--gittgo-lime); }
.info-tip { position: absolute; top: calc(100% + 8px); left: 0; z-index: 30; width: 270px; max-width: 75vw;
  background: var(--surface); color: var(--ink-2); border: 1px solid var(--border); border-radius: 8px;
  padding: 10px 12px; font-size: 0.78rem; font-weight: 400; line-height: 1.45; box-shadow: 0 6px 20px rgba(0,0,0,0.14);
  opacity: 0; pointer-events: none; transform: translateY(-4px); transition: opacity .12s ease, transform .12s ease; }
.info-wrap:hover .info-tip, .info-wrap.open .info-tip { opacity: 1; pointer-events: auto; transform: translateY(0); }
@media (hover: none) {
  .info-wrap:hover .info-tip { opacity: 0; pointer-events: none; }
  .info-wrap.open .info-tip { opacity: 1; pointer-events: auto; }
}

.compare-toggle { display: flex; align-items: center; gap: 8px; font-size: 0.85rem; font-weight: 600;
  color: var(--ink-1); margin-bottom: 10px; cursor: pointer; user-select: none; }
.compare-toggle input { width: 16px; height: 16px; cursor: pointer; accent-color: var(--gittgo-lime); }
.presets { display: flex; flex-wrap: wrap; gap: 8px; margin: 16px 0; }
.presets button { font: inherit; font-family: 'Poppins', 'Inter', sans-serif; font-weight: 700; font-size: 0.78rem;
  background: var(--surface); color: var(--ink-1);
  border: 1px solid var(--border); border-radius: 999px; padding: 7px 15px; cursor: pointer; transition: transform .1s ease; }
.presets button:hover { background: var(--grid); }
.presets button:active { transform: translateY(1px); }
.presets button.active { background: var(--gittgo-lime); color: var(--gittgo-navy); border-color: var(--gittgo-lime); }
[data-role="presets-compare"] { display: none; }
[data-role="pb-picker"] { display: none; }
#global-compare.compare-mode [data-role="presets-single"] { display: none; }
#global-compare.compare-mode [data-role="presets-compare"] { display: flex; }
#global-compare.compare-mode [data-role="pb-picker"] { display: block; }
.range-pickers { display: grid; grid-template-columns: repeat(auto-fit, minmax(260px, 1fr)); gap: 16px; margin-bottom: 8px; }
.range-picker { border: 1px solid var(--border); border-radius: 10px; padding: 12px 14px; }
.range-picker .rp-label { display:flex; align-items:center; gap:6px; font-size: 0.8rem; font-weight: 600; margin-bottom: 8px; }
.range-picker .rp-label i { width:10px; height:10px; border-radius: 2px; display:inline-block; }
.range-picker .rp-fields { display: flex; align-items: center; gap: 8px; font-size: 0.82rem; }
.range-picker input[type="date"] { font: inherit; font-size: 0.82rem; background: var(--page); color: var(--ink-1);
  border: 1px solid var(--border); border-radius: 6px; padding: 5px 8px; }
.compare-table td.pa { border-left: 3px solid var(--series-blue); }
.compare-table td.pb { border-left: 3px solid var(--series-yellow); }
.pace { color: var(--ink-mut); font-size: 0.82em; font-weight: 400; }

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
.tabs button { font: inherit; font-family: 'Poppins', 'Inter', sans-serif; font-size: 0.95rem; font-weight: 700;
  background: none; color: var(--ink-mut);
  border: none; border-bottom: 2px solid transparent; padding: 10px 6px; margin-right: 20px; cursor: pointer;
  display: flex; align-items: center; gap: 8px; }
.tabs button .dot { width:10px; height:10px; border-radius:50%; display:inline-block; }
.tabs button:hover { color: var(--ink-1); }
.tabs button.active { color: var(--ink-1); border-bottom-color: var(--gittgo-lime); }
.tab-panel { display: none; }
.tab-panel.active { display: block; }

.granularity-switch { margin: 12px 0 4px; font-size: 0.85rem; color: var(--ink-2); }
.granularity-switch select { font: inherit; font-family: 'Poppins', 'Inter', sans-serif; font-size: 0.85rem; font-weight: 600; background: var(--page);
  color: var(--ink-1); border: 1px solid var(--border); border-radius: 999px; padding: 5px 12px; cursor: pointer; }
.granularity-panel { display: none; }
.granularity-panel.active { display: block; }
"""


COMPARE_JS = """
(function () {
  var dataEl = document.getElementById('daily-data');
  if (!dataEl) return;
  var DAILY = JSON.parse(dataEl.textContent);

  function isoDate(d) { return d.toISOString().slice(0, 10); }
  function fmtDateUK(iso) { var p = iso.split('-'); return p[2] + '/' + p[1] + '/' + p[0]; }
  function parseISO(s) { var p = s.split('-').map(Number); return new Date(Date.UTC(p[0], p[1] - 1, p[2])); }
  function addDays(d, n) { var r = new Date(d); r.setUTCDate(r.getUTCDate() + n); return r; }
  function weekStartOf(d) { var day = (d.getUTCDay() + 6) % 7; return addDays(d, -day); }
  function monthStartOf(d) { return new Date(Date.UTC(d.getUTCFullYear(), d.getUTCMonth(), 1)); }
  function monthEndOf(d) { return new Date(Date.UTC(d.getUTCFullYear(), d.getUTCMonth() + 1, 0)); }

  var lastDate = DAILY.length ? parseISO(DAILY[DAILY.length - 1].date) : new Date();

  function sumRange(start, end) {
    var sent = 0, opens = 0, replies = 0, interested = 0, connSent = 0, connAccepted = 0, replied = 0, completingGoal = 0, hasKakiyo = false, days = 0;
    var instantlyDays = 0, kakiyoDays = 0, activeDays = 0;
    for (var i = 0; i < DAILY.length; i++) {
      var r = DAILY[i];
      if (r.date < start || r.date > end) continue;
      days++;
      var iActive = r.sent > 0;
      var kActive = r.conn_sent !== null && r.conn_sent > 0;
      if (iActive) instantlyDays++;
      if (kActive) kakiyoDays++;
      if (iActive || kActive) activeDays++;
      sent += r.sent; opens += r.opens; replies += r.replies; interested += r.interested;
      if (r.conn_sent !== null) { connSent += r.conn_sent; hasKakiyo = true; }
      if (r.conn_accepted !== null) { connAccepted += r.conn_accepted; hasKakiyo = true; }
      if (r.replied !== null) { replied += r.replied; hasKakiyo = true; }
      if (r.completing_goal !== null) { completingGoal += r.completing_goal; hasKakiyo = true; }
    }
    var openRate = sent ? (opens / sent * 100) : 0;
    return { sent: sent, opens: opens, openRate: openRate, replies: replies, interested: interested, connSent: connSent,
      connAccepted: connAccepted, replied: replied, completingGoal: completingGoal, hasKakiyo: hasKakiyo, days: days,
      instantlyDays: instantlyDays, kakiyoDays: kakiyoDays, activeDays: activeDays };
  }

  // Sends/replies/etc pace off the days a platform actually sent something, not the
  // calendar span — a 7-day range with a weekends-off schedule might only have 5 active days.
  var KAKIYO_KEYS = ['connSent', 'connAccepted', 'replied', 'completingGoal'];
  function activeDaysFor(period, keyOrArr) {
    if (Array.isArray(keyOrArr)) return period.activeDays;
    return KAKIYO_KEYS.indexOf(keyOrArr) !== -1 ? period.kakiyoDays : period.instantlyDays;
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
  var compareToggle = picker.querySelector('[data-role="compare-toggle"]');
  var paStart = picker.querySelector('[data-role="pa-start"]'), paEnd = picker.querySelector('[data-role="pa-end"]');
  var pbStart = picker.querySelector('[data-role="pb-start"]'), pbEnd = picker.querySelector('[data-role="pb-end"]');
  var paTitle = picker.querySelector('[data-role="pa-title"]');
  var rangeNote = picker.querySelector('[data-role="range-note"]');
  var singleButtons = picker.querySelectorAll('[data-role="presets-single"] button');
  var compareButtons = picker.querySelectorAll('[data-role="presets-compare"] button');
  var outputs = document.querySelectorAll('.compare-output');
  var lastDateStr = DAILY.length ? DAILY[DAILY.length - 1].date : '';

  function isCompareMode() { return compareToggle.checked; }
  function clearActive(buttons) { for (var i = 0; i < buttons.length; i++) buttons[i].classList.remove('active'); }

  function renderCompare(out, a, b) {
    var metrics = JSON.parse(out.getAttribute('data-metrics'));
    var needsKakiyo = out.getAttribute('data-needs-kakiyo') === '1';
    var rows = '';
    for (var i = 0; i < metrics.length; i++) {
      var key = metrics[i][0], label = metrics[i][1], isPct = metrics[i][2];
      var av = getVal(a, key), bv = getVal(b, key);
      var avFmt = isPct ? fmtPct(av) : fmtNum(av);
      var bvFmt = isPct ? fmtPct(bv) : fmtNum(bv);
      var deltaA = av, deltaB = bv;
      if (!isPct) {
        var aActive = activeDaysFor(a, key), bActive = activeDaysFor(b, key);
        var aRate = aActive > 0 ? av / aActive : 0;
        var bRate = bActive > 0 ? bv / bActive : 0;
        avFmt += " <span class='pace'>(" + aRate.toFixed(1) + "/active day)</span>";
        bvFmt += " <span class='pace'>(" + bRate.toFixed(1) + "/active day)</span>";
        if (aActive > 0 && bActive > 0) { deltaA = aRate; deltaB = bRate; }
      }
      rows += '<tr><td class="rowhead">' + label + '</td><td class="pa">' + avFmt + '</td><td class="pb">' + bvFmt + '</td><td>' + fmtDelta(deltaA, deltaB) + '</td></tr>';
    }
    var note = (needsKakiyo && !a.hasKakiyo && !b.hasKakiyo)
      ? "<p class='note'>No Kakiyo snapshot activity fell inside either range — those columns will read 0.</p>" : '';
    var paceNote = "<p class='note'>Numbers in brackets are the daily pace — value ÷ the days that platform actually " +
      "sent something (not every day gets sends, e.g. weekends). The % change compares that pace, not the raw totals, " +
      "for every row above.</p>";
    out.innerHTML =
      '<div class="table-wrap compare-table"><table>' +
      '<thead><tr><th>Metric</th><th>Period A (' + fmtDateUK(paStart.value) + ' to ' + fmtDateUK(paEnd.value) + ', ' + a.days + 'd)</th>' +
      '<th>Period B (' + fmtDateUK(pbStart.value) + ' to ' + fmtDateUK(pbEnd.value) + ', ' + b.days + 'd)</th><th>A vs B</th></tr></thead>' +
      '<tbody>' + rows + '</tbody></table></div>' + paceNote + note;
  }

  function renderSingle(out, a) {
    var metrics = JSON.parse(out.getAttribute('data-metrics'));
    var needsKakiyo = out.getAttribute('data-needs-kakiyo') === '1';
    var rows = '';
    for (var i = 0; i < metrics.length; i++) {
      var key = metrics[i][0], label = metrics[i][1], isPct = metrics[i][2];
      var av = getVal(a, key);
      var avFmt = isPct ? fmtPct(av) : fmtNum(av);
      rows += '<tr><td class="rowhead">' + label + '</td><td>' + avFmt + '</td></tr>';
    }
    var note = (needsKakiyo && !a.hasKakiyo)
      ? "<p class='note'>No Kakiyo snapshot activity fell inside this range — those rows will read 0.</p>" : '';
    out.innerHTML =
      '<div class="table-wrap compare-table"><table>' +
      '<thead><tr><th>Metric</th><th>' + fmtDateUK(paStart.value) + ' to ' + fmtDateUK(paEnd.value) + ' (' + a.days + 'd)</th></tr></thead>' +
      '<tbody>' + rows + '</tbody></table></div>' + note;
  }

  function renderAll() {
    if (!paStart.value || !paEnd.value) return;
    if (isCompareMode()) {
      if (!pbStart.value || !pbEnd.value) return;
      var a = sumRange(paStart.value, paEnd.value);
      var b = sumRange(pbStart.value, pbEnd.value);
      for (var i = 0; i < outputs.length; i++) renderCompare(outputs[i], a, b);
      var beyond = lastDateStr && (paEnd.value > lastDateStr || pbEnd.value > lastDateStr);
      rangeNote.textContent = beyond
        ? 'One of the selected ranges extends past ' + fmtDateUK(lastDateStr) + ', the most recent day loaded — those days will read as 0 until the dashboard is refreshed.'
        : '';
    } else {
      var a2 = sumRange(paStart.value, paEnd.value);
      for (var j = 0; j < outputs.length; j++) renderSingle(outputs[j], a2);
      var beyond2 = lastDateStr && paEnd.value > lastDateStr;
      rangeNote.textContent = beyond2
        ? 'The selected range extends past ' + fmtDateUK(lastDateStr) + ', the most recent day loaded — those days will read as 0 until the dashboard is refreshed.'
        : '';
    }
  }

  function setSinglePreset(name) {
    var aStart, aEnd;
    if (name === 'this-week') { aStart = weekStartOf(lastDate); aEnd = addDays(aStart, 6); }
    else if (name === 'this-month') { aStart = monthStartOf(lastDate); aEnd = monthEndOf(lastDate); }
    else if (name === 'last-7d') { aEnd = lastDate; aStart = addDays(aEnd, -6); }
    else if (name === 'last-30d') { aEnd = lastDate; aStart = addDays(aEnd, -29); }
    else if (name === 'custom') {
      clearActive(singleButtons);
      var btn = picker.querySelector('[data-preset="custom"]');
      if (btn) btn.classList.add('active');
      return;
    } else {
      return;
    }
    paStart.value = isoDate(aStart); paEnd.value = isoDate(aEnd);
    clearActive(singleButtons);
    for (var i = 0; i < singleButtons.length; i++) {
      singleButtons[i].classList.toggle('active', singleButtons[i].getAttribute('data-preset') === name);
    }
    renderAll();
  }

  function setComparePreset(name) {
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
    clearActive(compareButtons);
    for (var i = 0; i < compareButtons.length; i++) {
      compareButtons[i].classList.toggle('active', compareButtons[i].getAttribute('data-preset') === name);
    }
    renderAll();
  }

  function applyMode() {
    var compare = isCompareMode();
    picker.classList.toggle('compare-mode', compare);
    if (paTitle) paTitle.textContent = compare ? 'Period A' : 'Period';
    if (compare && (!pbStart.value || !pbEnd.value)) {
      setComparePreset('week');
    } else {
      renderAll();
    }
  }

  for (var i = 0; i < singleButtons.length; i++) {
    singleButtons[i].addEventListener('click', function (e) { setSinglePreset(e.currentTarget.getAttribute('data-preset')); });
  }
  for (var i = 0; i < compareButtons.length; i++) {
    compareButtons[i].addEventListener('click', function (e) { setComparePreset(e.currentTarget.getAttribute('data-preset')); });
  }
  [paStart, paEnd].forEach(function (el) {
    el.addEventListener('change', function () { clearActive(singleButtons); clearActive(compareButtons); renderAll(); });
  });
  [pbStart, pbEnd].forEach(function (el) {
    el.addEventListener('change', function () { clearActive(compareButtons); renderAll(); });
  });
  compareToggle.addEventListener('change', applyMode);

  if (DAILY.length) {
    setSinglePreset('this-week');
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

GRANULARITY_JS = """
(function () {
  document.querySelectorAll('.granularity-group').forEach(function (group) {
    var select = group.querySelector('[data-role="granularity-select"]');
    var panels = group.querySelectorAll('.granularity-panel');
    if (!select) return;
    function activate(val) {
      panels.forEach(function (p) { p.classList.toggle('active', p.getAttribute('data-granularity') === val); });
    }
    select.addEventListener('change', function () { activate(select.value); });
    activate(select.value);
  });
})();
"""

INFO_JS = """
(function () {
  function closeAll() {
    document.querySelectorAll('.info-wrap.open').forEach(function (w) { w.classList.remove('open'); });
  }
  document.querySelectorAll('.info-icon').forEach(function (btn) {
    btn.addEventListener('click', function (e) {
      e.stopPropagation();
      e.preventDefault(); // don't let a click here toggle an ancestor <details>
      var wrap = btn.closest('.info-wrap');
      var wasOpen = wrap.classList.contains('open');
      closeAll();
      if (!wasOpen) wrap.classList.add('open');
    });
  });
  document.addEventListener('click', closeAll);
  document.addEventListener('keydown', function (e) { if (e.key === 'Escape') closeAll(); });
})();
"""

PAGINATION_JS = """
(function () {
  var PAGE_SIZES = [10, 25, 50, 100];
  function init(wrap) {
    var table = wrap.querySelector('table');
    var tbody = table && table.querySelector('tbody');
    if (!tbody) return;
    var rows = Array.prototype.slice.call(tbody.children);
    if (rows.length <= PAGE_SIZES[0]) return;

    var bar = document.createElement('div');
    bar.className = 'pagination-bar';

    var sizeWrap = document.createElement('label');
    sizeWrap.className = 'pagination-size';
    sizeWrap.appendChild(document.createTextNode('Show '));
    var select = document.createElement('select');
    PAGE_SIZES.filter(function (n) { return n < rows.length; }).concat([rows.length]).forEach(function (n) {
      var opt = document.createElement('option');
      opt.value = n === rows.length ? 'all' : String(n);
      opt.textContent = n === rows.length ? 'All (' + n + ')' : String(n);
      select.appendChild(opt);
    });
    sizeWrap.appendChild(select);
    sizeWrap.appendChild(document.createTextNode(' at a time'));

    var info = document.createElement('span');
    info.className = 'pagination-info';

    var prevBtn = document.createElement('button');
    prevBtn.type = 'button';
    prevBtn.textContent = 'Prev';
    var pageLabel = document.createElement('span');
    pageLabel.className = 'pagination-page';
    var nextBtn = document.createElement('button');
    nextBtn.type = 'button';
    nextBtn.textContent = 'Next';
    var nav = document.createElement('span');
    nav.className = 'pagination-nav';
    nav.appendChild(prevBtn);
    nav.appendChild(pageLabel);
    nav.appendChild(nextBtn);

    bar.appendChild(sizeWrap);
    bar.appendChild(info);
    bar.appendChild(nav);
    wrap.appendChild(bar);

    var page = 0;
    function pageSize() { return select.value === 'all' ? rows.length : parseInt(select.value, 10); }
    function totalPages() { return Math.max(1, Math.ceil(rows.length / pageSize())); }
    function render() {
      var size = pageSize();
      var total = totalPages();
      if (page >= total) page = total - 1;
      if (page < 0) page = 0;
      var start = page * size;
      var end = Math.min(start + size, rows.length);
      rows.forEach(function (r, i) { r.style.display = (i >= start && i < end) ? '' : 'none'; });
      info.textContent = 'Showing ' + (start + 1) + '\\u2013' + end + ' of ' + rows.length;
      pageLabel.textContent = (page + 1) + ' / ' + total;
      prevBtn.disabled = page === 0;
      nextBtn.disabled = page >= total - 1;
    }
    select.addEventListener('change', function () { page = 0; render(); });
    prevBtn.addEventListener('click', function () { page--; render(); });
    nextBtn.addEventListener('click', function () { page++; render(); });
    page = totalPages() - 1;
    render();
  }
  document.querySelectorAll('.table-wrap').forEach(function (wrap) {
    if (wrap.classList.contains('compare-table')) return;
    init(wrap);
  });
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
    monthly_chart_periods = [(month_label(k), p) for k, p in monthly_sorted]
    daily_chart_periods = [
        (uk_date(r["date"]), {
            "sent": r["sent"], "opens": r["opens"], "interested": r["interested"],
            "conn_sent": r["conn_sent"] or 0, "conn_accepted": r["conn_accepted"] or 0,
            "completing_goal": r["completing_goal"] or 0,
        })
        for r in daily_rows
    ]
    daily_chart_width = max(740, len(daily_chart_periods) * 50 + 60)

    instantly_weekly_table = totals_table(weekly_sorted, INSTANTLY_PERIOD_COLS, lambda k: week_label(k))
    kakiyo_weekly_table = totals_table(weekly_sorted, KAKIYO_PERIOD_COLS, lambda k: week_label(k))
    instantly_monthly_table = totals_table(monthly_sorted, INSTANTLY_PERIOD_COLS, lambda k: month_label(k))
    kakiyo_monthly_table = totals_table(monthly_sorted, KAKIYO_PERIOD_COLS, lambda k: month_label(k))

    instantly_chart = bar_chart(weekly_chart_periods, INSTANTLY_WEEKLY_METRICS)
    instantly_chart_monthly = bar_chart(monthly_chart_periods, INSTANTLY_WEEKLY_METRICS)
    instantly_chart_daily = bar_chart(daily_chart_periods, INSTANTLY_WEEKLY_METRICS, width=daily_chart_width, scrollable=True)

    if kakiyo_has_history:
        kakiyo_chart = bar_chart(weekly_chart_periods, KAKIYO_WEEKLY_METRICS)
        kakiyo_chart_monthly = bar_chart(monthly_chart_periods, KAKIYO_WEEKLY_METRICS)
        kakiyo_chart_daily = bar_chart(daily_chart_periods, KAKIYO_WEEKLY_METRICS, width=daily_chart_width, scrollable=True)
    else:
        no_history_msg = "<p class='empty'>Not enough Kakiyo snapshots yet to chart change over time — need at least 2.</p>"
        kakiyo_chart = kakiyo_chart_monthly = kakiyo_chart_daily = no_history_msg

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
            f"interested yet — not counted as negative. Snapshot as of {escape(uk_datetime(funnel['fetched_at']))}. "
            "\"Sales\" is currently sourced from Instantly's own Closed/Won "
            "status — a firmer source for this number is still being worked out.</p>"
        )
        kakiyo_funnel = funnel_chart(
            [("Connections sent", fk["connections_sent"]), ("Connections accepted", fk["connections_accepted"]),
             ("Contacts replied", fk["contacts_replied"]), ("Contacts qualified", fk["contacts_qualified"]),
             ("Sales", fk["conversions"])],
            "orange",
        )
        kakiyo_funnel += (
            f"<p class='note'>Snapshot as of {escape(uk_datetime(funnel['fetched_at']))}. "
            "\"Sales\" is currently sourced from Kakiyo's own closed-deal status — a firmer source for this number "
            "is still being worked out.</p>"
        )
        kakiyo_active_conversations = active_conversations_tile(fk)
    else:
        instantly_funnel = kakiyo_funnel = "<p class='empty'>No funnel data recorded yet.</p>"
        kakiyo_active_conversations = "<p class='empty'>No active-conversation data recorded yet.</p>"

    kakiyo_note = (
        "<p class='note'>Kakiyo only gives us a running total, not a day-by-day history. So each refresh saves a "
        "dated snapshot of those totals, and this dashboard works out day/week/month activity by comparing each "
        "snapshot to the one before it. The 30/07/2026 baseline came from the team's existing tracking spreadsheet; "
        "everything after that is pulled live. Because there's no earlier snapshot to compare that first one against, "
        "its whole running total (80 connections sent, 15 accepted, 1 qualified) shows up as a single day's/week's "
        "activity on 30/07/2026 below, whichever view you're looking at. Periods before snapshot tracking began "
        "show 0 for Kakiyo columns because no snapshot existed yet, not because activity was zero.</p>"
    )

    instantly_granularity = granularity_section(
        instantly_chart, instantly_weekly_table,
        instantly_chart_monthly, instantly_monthly_table,
        instantly_chart_daily, instantly_daily,
    )
    kakiyo_granularity = granularity_section(
        kakiyo_chart, kakiyo_weekly_table,
        kakiyo_chart_monthly, kakiyo_monthly_table,
        kakiyo_chart_daily, kakiyo_daily,
        note=kakiyo_note,
    )

    html_out = f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="theme-color" content="#16222f">
<title>Outreach Activity Dashboard</title>
<style>{build_css()}</style>
</head>
<body>
<div class="viz-root">
<div class="wrap">
  <div class="page-header">
    <span class="brand-logo"><span class="brand-mark">gittgo</span></span>
    <div class="page-header-text">
      <h1>Outreach Activity Dashboard</h1>
      <p class="sub">Week-over-week activity across Kakiyo (LinkedIn) and Instantly (Email) campaigns. Data fetched {escape(uk_datetime(fetched_at))}.</p>
    </div>
  </div>

  <section>
    <h2>Compare periods {info_icon("Pick a date range (or use a preset) to see totals for that period. Tick the Compare box to line it up against a second range instead. This is the one control for the whole page — it drives the Overview below and each platform tab's own Selected period numbers, all at once. If Period A and B had a different number of days with actual sending activity (e.g. an in-progress week vs a full one, or weekends with no sends), the A vs B change compares daily pace over those active days, not raw totals.")}</h2>
    <p class="sub" style="margin-bottom:12px;">All {len(daily_rows)} loaded days ({escape(uk_date(min_date))} to {escape(uk_date(max_date))}) are available to look at. Pick a range or use a preset below; tick "Compare to a previous period" to see it side by side with another range. This controls every metric below: the overview and each platform's own totals.</p>
    {global_picker}
  </section>

  <section>
    <details class="collapsible" open>
      <summary><span class="chevron">▾</span><h2>Overview {info_icon("Cross-platform totals for the two periods picked above. Sends and Replies each combine both platforms into one number — see the note under the table for how.")}</h2></summary>
      <div class="collapsible-body">
        {overview_output}
        {overview_footnote}
      </div>
    </details>
  </section>

  <div class="tabs">
    <button type="button" data-tab="instantly"><span class="dot" style="background:var(--series-blue)"></span>Instantly (email)</button>
    <button type="button" data-tab="kakiyo"><span class="dot" style="background:var(--series-orange)"></span>Kakiyo (LinkedIn)</button>
  </div>

  <div class="tab-panel" data-tab="instantly">
    <section>
      <h2>Selected period {info_icon("Instantly's own metrics for the same two periods chosen in Compare periods above, with a % change between them.")}</h2>
      {instantly_output}
    </section>

    <section>
      <h2>Funnel {info_icon("A cumulative, all-time view of Instantly's pipeline — Total unique contacts through Sales — independent of the date picker above. Each bar shows its share of total traffic and its share of the stage before it.")}</h2>
      {instantly_funnel}
    </section>

    <section>
      <h2>Activity over time {info_icon("Every day, week, or month of loaded data, charted and tabled — pick which one with the dropdown below. This is a full history view and isn't affected by the date picker above.")}</h2>
      {instantly_granularity}
    </section>
  </div>

  <div class="tab-panel" data-tab="kakiyo">
    <section>
      <h2>Selected period {info_icon("Kakiyo's own metrics for the same two periods chosen in Compare periods above, with a % change between them.")}</h2>
      {kakiyo_output}
    </section>

    <section>
      <h2>Active conversations {info_icon("A live count, not tied to the date picker above: prospects who've replied or been qualified and whose most recent message was within the window — i.e. someone you could follow up with right now.")}</h2>
      {kakiyo_active_conversations}
    </section>

    <section>
      <h2>Funnel {info_icon("A cumulative, all-time view of Kakiyo's pipeline — Connections sent through Sales — independent of the date picker above. Each bar shows its share of total traffic and its share of the stage before it.")}</h2>
      {kakiyo_funnel}
    </section>

    <section>
      <h2>Activity over time {info_icon("Every day, week, or month of loaded data, charted and tabled — pick which one with the dropdown below. Reconstructed from daily snapshots of Kakiyo's running totals, not a native history feed — see the note below. Not affected by the date picker above.")}</h2>
      {kakiyo_granularity}
    </section>
  </div>

  <footer>Regenerate with <code>python3 scripts/generate_dashboard.py</code> after refreshing data/. See README.md.</footer>
</div>
</div>
<script id="daily-data" type="application/json">{daily_rows_json}</script>
<script>{COMPARE_JS}</script>
<script>{TABS_JS}</script>
<script>{GRANULARITY_JS}</script>
<script>{INFO_JS}</script>
<script>{PAGINATION_JS}</script>
</body>
</html>
"""
    OUT_FILE.write_text(html_out)
    print(f"Wrote {OUT_FILE}")


if __name__ == "__main__":
    main()
