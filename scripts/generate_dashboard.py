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
    campaigns = []
    by_date = defaultdict(lambda: defaultdict(int))
    for camp in raw["campaigns"]:
        weekly = defaultdict(lambda: defaultdict(int))
        for rec in camp["daily"]:
            d = rec["date"]
            by_date[d]["sent"] += rec.get("sent", 0)
            by_date[d]["opens"] += rec.get("unique_opened", 0)
            by_date[d]["interested"] += rec.get("opportunities", 0)
            wk = week_start(date.fromisoformat(d)).isoformat()
            weekly[wk]["sent"] += rec.get("sent", 0)
            weekly[wk]["opens"] += rec.get("unique_opened", 0)
            weekly[wk]["replies"] += rec.get("unique_replies", 0)
        if camp["daily"]:
            campaigns.append({"id": camp["id"], "name": camp["name"], "status": camp["status"], "weekly": weekly})
    return raw["fetched_at"], campaigns, by_date


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
        sent, opens, interested = im.get("sent", 0), im.get("opens", 0), im.get("interested", 0)
        open_rate = (opens / sent * 100) if sent else 0.0
        kc = kakiyo_changes.get(ds)
        rows.append({
            "date": ds, "sent": sent, "opens": opens, "open_rate": open_rate, "interested": interested,
            "conn_sent": None if kc is None else (None if kc["baseline"] else kc["invitationsSent"]),
            "conn_accepted": None if kc is None else (None if kc["baseline"] else kc["invitationsAccepted"]),
            "completing_goal": None if kc is None else (None if kc["baseline"] else kc["qualified"]),
            "kakiyo_note": "Baseline (first snapshot)" if (kc and kc["baseline"]) else None,
        })
    return rows


def aggregate_period(daily_rows, period_key_fn):
    periods = {}
    for row in daily_rows:
        d = date.fromisoformat(row["date"])
        key = period_key_fn(d)
        p = periods.setdefault(key, {"start": key, "sent": 0, "opens": 0, "interested": 0, "conn_sent": 0, "conn_accepted": 0, "completing_goal": 0})
        p["sent"] += row["sent"]
        p["opens"] += row["opens"]
        p["interested"] += row["interested"]
        for f, col in (("conn_sent", "conn_sent"), ("conn_accepted", "conn_accepted"), ("completing_goal", "completing_goal")):
            if row[f] is not None:
                p[col] += row[f]
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


PERIOD_COLS = [("sent", "Sends"), ("opens", "Opens"), ("open_rate", "Open rate"), ("interested", "Interested"),
               ("conn_sent", "Connections sent"), ("conn_accepted", "Connections accepted"), ("completing_goal", "# Completing goal")]


def wow_tiles(cur, prev):
    fields = [("sent", "Sends"), ("opens", "Opens"), ("interested", "Interested"),
              ("conn_sent", "Connections sent"), ("conn_accepted", "Connections accepted"), ("completing_goal", "# Completing goal")]
    tiles = []
    for key, label in fields:
        cur_v = cur.get(key, 0)
        sub = fmt_delta(cur_v, prev.get(key, 0)) + " vs prior week" if prev else "<span class='delta flat'>no prior week yet</span>"
        tiles.append(f"<div class='tile'><div class='tile-label'>{escape(label)}</div><div class='tile-value'>{cur_v:,}</div><div class='tile-sub'>{sub}</div></div>")
    return f"<div class='tiles'>{''.join(tiles)}</div>"


def daily_activity_table(rows):
    body = []
    for r in rows:
        kakiyo_cells = (
            f"<td>{r['kakiyo_note']}</td><td>{r['kakiyo_note']}</td><td>{r['kakiyo_note']}</td>"
            if r["kakiyo_note"] else
            f"<td>{fmt_or_na(r['conn_sent'])}</td><td>{fmt_or_na(r['conn_accepted'])}</td><td>{fmt_or_na(r['completing_goal'])}</td>"
        )
        body.append(
            f"<tr><td class='rowhead'>{r['date']}</td><td>{r['sent']:,}</td><td>{r['opens']:,}</td>"
            f"<td>{fmt_pct(r['open_rate'])}</td><td>{r['interested']:,}</td>{kakiyo_cells}</tr>"
        )
    head = "<th>Date</th><th>Sends</th><th>Opens</th><th>Open rate</th><th>Interested</th><th>Conn. sent (daily)</th><th>Conn. accepted (daily)</th><th># Completing goal (daily)</th>"
    return f"<div class='table-wrap'><table><thead><tr>{head}</tr></thead><tbody>{''.join(body)}</tbody></table></div>"


def kakiyo_raw_table(snaps, changes):
    fields = [("prospects", "Prospects"), ("invitationsSent", "Conn. sent"), ("invitationsAccepted", "Conn. accepted"),
              ("messagesSent", "Messages sent"), ("prospectsAnswers", "Replies"), ("qualified", "Qualified")]
    head = "".join(f"<th>Cumulative {h}</th>" for _, h in fields) + "".join(f"<th>Δ {h}</th>" for _, h in fields)
    rows = []
    for snap in snaps:
        c = changes[snap["date"]]
        t = c["totals"]
        cum_cells = "".join(f"<td>{fmt_or_na(t.get(f))}</td>" for f, _ in fields)
        if c["baseline"]:
            delta_cells = f"<td colspan='{len(fields)}' class='mut'>Baseline (first snapshot)</td>"
        else:
            delta_cells = "".join(f"<td>{fmt_or_na(c.get(f))}</td>" for f, _ in fields)
        src = f" <span class='pill'>{escape(snap['source'])}</span>" if snap.get("source") else ""
        rows.append(f"<tr><td class='rowhead'>{snap['date']}{src}</td>{cum_cells}{delta_cells}</tr>")
    return f"<div class='table-wrap'><table><thead><tr><th>Snapshot date</th>{head}</tr></thead><tbody>{''.join(rows)}</tbody></table></div>"


def campaign_breakdown_table(campaigns, weeks):
    thead = "".join(f"<th>{escape(week_label(date.fromisoformat(wk)))}</th>" for wk in weeks)
    rows = []
    status_names = {1: "Active", 2: "Paused", 0: "Draft", 3: "Completed"}
    for camp in campaigns:
        cells = []
        for wk in weeks:
            m = camp["weekly"].get(wk, {})
            cells.append(f"<td>{m.get('sent',0)} sent / {m.get('opens',0)} opens / {m.get('replies',0)} replies</td>")
        rows.append(f"<tr><td class='rowhead'>{escape(camp['name'])}<span class='pill'>{status_names.get(camp['status'], camp['status'])}</span></td>{''.join(cells)}</tr>")
    return f"<div class='table-wrap'><table><thead><tr><th>Campaign</th>{thead}</tr></thead><tbody>{''.join(rows)}</tbody></table></div>"


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
    fetched_at, campaigns, instantly_by_date = load_instantly()
    kakiyo_snaps = load_kakiyo_snapshots()
    kakiyo_changes = kakiyo_daily_changes(kakiyo_snaps)

    daily_rows = build_daily_rows(instantly_by_date, kakiyo_changes)
    weekly = aggregate_period(daily_rows, week_start)
    monthly = aggregate_period(daily_rows, month_start)

    weekly_sorted = sorted(weekly.items())
    monthly_sorted = sorted(monthly.items())

    kakiyo_has_history = sum(1 for s in kakiyo_snaps if not kakiyo_changes[s["date"]]["baseline"]) > 0

    # headline: this week vs prior week
    if weekly_sorted:
        cur_wk_key, cur_wk = weekly_sorted[-1]
        prev_wk = weekly_sorted[-2][1] if len(weekly_sorted) > 1 else None
        today = date.today()
        in_progress = cur_wk_key == week_start(today) and (today - cur_wk_key).days < 6
        headline = wow_tiles(cur_wk, prev_wk)
        if in_progress:
            headline += f"<p class='note'>Week of {escape(week_label(cur_wk_key))} is still in progress — totals will grow before it's comparable to a full week.</p>"
    else:
        headline = "<p class='empty'>No data yet.</p>"

    weekly_chart_periods = [(week_label(k), p) for k, p in weekly_sorted]
    weekly_table = totals_table(weekly_sorted, PERIOD_COLS, lambda k: f"{week_label(k)} ({k.isoformat()} start)")
    monthly_table = totals_table(monthly_sorted, PERIOD_COLS, lambda k: month_label(k))

    instantly_chart = bar_chart(weekly_chart_periods, INSTANTLY_WEEKLY_METRICS)
    kakiyo_chart = bar_chart(weekly_chart_periods, KAKIYO_WEEKLY_METRICS) if kakiyo_has_history else (
        "<p class='empty'>Not enough Kakiyo snapshots yet to chart week-over-week change — need at least 2.</p>"
    )

    daily_table = daily_activity_table(daily_rows)
    kakiyo_raw = kakiyo_raw_table(kakiyo_snaps, kakiyo_changes) if kakiyo_snaps else "<p class='empty'>No Kakiyo snapshots recorded yet.</p>"

    recent_weeks = [wk for wk, _ in weekly_sorted[-6:]]
    campaign_table = campaign_breakdown_table(campaigns, [wk.isoformat() for wk in recent_weeks]) if campaigns else ""

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
    <h2>This week vs. prior week</h2>
    {headline}
  </section>

  <section>
    <h2>Weekly totals</h2>
    <h3><span class="dot" style="background:var(--series-blue)"></span>Instantly (email)</h3>
    {instantly_chart}
    <h3><span class="dot" style="background:var(--series-orange)"></span>Kakiyo (LinkedIn)</h3>
    {kakiyo_chart}
    {kakiyo_note}
    {weekly_table}
  </section>

  <section>
    <h2>Monthly totals</h2>
    {monthly_table}
  </section>

  <section>
    <h2>Daily activity</h2>
    {daily_table}
  </section>

  <section>
    <h2>Instantly — by campaign (last 6 weeks)</h2>
    {campaign_table if campaign_table else "<p class='empty'>No campaign data.</p>"}
  </section>

  <section>
    <h2>Kakiyo snapshots (raw)</h2>
    {kakiyo_raw}
  </section>

  <footer>Regenerate with <code>python3 scripts/generate_dashboard.py</code> after refreshing data/. See README.md.</footer>
</div>
</div>
</body>
</html>
"""
    OUT_FILE.write_text(html_out)
    print(f"Wrote {OUT_FILE}")


if __name__ == "__main__":
    main()
