#!/usr/bin/env python3
"""Build dashboard.html from data/instantly_raw.json and data/kakiyo_snapshots.jsonl.

Usage: python3 scripts/generate_dashboard.py
Reads the two data files, aggregates activity into ISO (Mon-Sun) weeks, and
writes a self-contained dashboard.html at the repo root. No third-party deps.
"""
import json
from collections import defaultdict
from datetime import date, timedelta
from html import escape
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
OUT_FILE = ROOT / "dashboard.html"

# --- palette (validated default from the dataviz skill) ---------------------
SERIES = {
    "blue":    {"light": "#2a78d6", "dark": "#3987e5"},
    "orange":  {"light": "#eb6834", "dark": "#d95926"},
    "aqua":    {"light": "#1baf7a", "dark": "#199e70"},
    "yellow":  {"light": "#eda100", "dark": "#c98500"},
    "violet":  {"light": "#4a3aa7", "dark": "#9085e9"},
    "red":     {"light": "#e34948", "dark": "#e66767"},
}
GOOD = {"light": "#006300", "dark": "#0ca30c"}
BAD = {"light": "#d03b3b", "dark": "#d03b3b"}

INSTANTLY_METRICS = [
    ("sent", "Sent", "blue"),
    ("opens", "Unique opens", "orange"),
    ("replies", "Unique replies", "aqua"),
]


# --- date / week helpers ------------------------------------------------
def week_start(d):
    return d - timedelta(days=d.weekday())


def week_label(ws):
    we = ws + timedelta(days=6)
    if ws.month == we.month:
        return f"{ws.strftime('%b %-d')}–{we.strftime('%-d')}"
    return f"{ws.strftime('%b %-d')}–{we.strftime('%b %-d')}"


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


# --- load data ------------------------------------------------------------
def load_instantly():
    raw = json.loads((DATA_DIR / "instantly_raw.json").read_text())
    campaigns = []
    total_weekly = defaultdict(lambda: defaultdict(int))
    for camp in raw["campaigns"]:
        weekly = defaultdict(lambda: defaultdict(int))
        for rec in camp["daily"]:
            d = date.fromisoformat(rec["date"])
            wk = week_start(d).isoformat()
            weekly[wk]["sent"] += rec.get("sent", 0)
            weekly[wk]["opens"] += rec.get("unique_opened", 0)
            weekly[wk]["replies"] += rec.get("unique_replies", 0)
            weekly[wk]["clicks"] += rec.get("unique_clicks", 0)
            weekly[wk]["opportunities"] += rec.get("opportunities", 0)
        for wk, m in weekly.items():
            for k, v in m.items():
                total_weekly[wk][k] += v
        if weekly:
            campaigns.append({"id": camp["id"], "name": camp["name"], "status": camp["status"], "weekly": weekly})
    return raw["fetched_at"], campaigns, total_weekly


def load_kakiyo():
    path = DATA_DIR / "kakiyo_snapshots.jsonl"
    if not path.exists():
        return []
    snaps = [json.loads(line) for line in path.read_text().splitlines() if line.strip()]
    snaps.sort(key=lambda s: s["date"])
    return snaps


# --- chart rendering (self-contained inline SVG, no JS libs) --------------
def rounded_top_path(x, y, w, h, r):
    if h <= 0:
        return ""
    r = min(r, w / 2, h)
    if r <= 0:
        return f"M{x},{y+h} L{x},{y} L{x+w},{y} L{x+w},{y+h} Z"
    return (
        f"M{x},{y+h} L{x},{y+r} Q{x},{y} {x+r},{y} "
        f"L{x+w-r},{y} Q{x+w},{y} {x+w},{y+r} L{x+w},{y+h} Z"
    )


def bar_chart(weeks, series, height=260, width=760):
    """weeks: list of (label, metrics_dict). series: list of (metric_key, label, color_name)."""
    if not weeks:
        return "<p class='empty'>No data yet.</p>"
    pad_l, pad_r, pad_t, pad_b = 44, 12, 16, 32
    plot_w = width - pad_l - pad_r
    plot_h = height - pad_t - pad_b
    max_val = 1
    for _, m in weeks:
        for key, _, _ in series:
            max_val = max(max_val, m.get(key, 0))
    max_val = max_val * 1.15

    def y_of(v):
        return pad_t + plot_h - (v / max_val * plot_h)

    ticks = 4
    grid = []
    for i in range(ticks + 1):
        v = max_val / ticks * i
        y = y_of(v)
        grid.append(
            f"<line x1='{pad_l}' y1='{y:.1f}' x2='{width-pad_r}' y2='{y:.1f}' class='gridline'/>"
            f"<text x='{pad_l-8}' y='{y+4:.1f}' class='axis-label' text-anchor='end'>{round(v)}</text>"
        )

    group_w = plot_w / len(weeks)
    bar_gap = 2
    n_series = len(series)
    bars_area = group_w * 0.72
    bar_w = max(4, (bars_area - bar_gap * (n_series - 1)) / n_series)

    bars = []
    xlabels = []
    for wi, (label, metrics) in enumerate(weeks):
        group_x = pad_l + wi * group_w + (group_w - (bar_w * n_series + bar_gap * (n_series - 1))) / 2
        for si, (key, slabel, color) in enumerate(series):
            v = metrics.get(key, 0)
            x = group_x + si * (bar_w + bar_gap)
            y = y_of(v)
            h = pad_t + plot_h - y
            path = rounded_top_path(x, y, bar_w, h, 4)
            title = f"{label} — {slabel}: {v:,}"
            if path:
                bars.append(
                    f"<path d='{path}' fill='var(--series-{color})' class='bar'>"
                    f"<title>{escape(title)}</title></path>"
                )
        xlabels.append(
            f"<text x='{group_x + (bar_w*n_series + bar_gap*(n_series-1))/2:.1f}' "
            f"y='{height-8}' class='axis-label' text-anchor='middle'>{escape(label)}</text>"
        )

    baseline = f"<line x1='{pad_l}' y1='{pad_t+plot_h}' x2='{width-pad_r}' y2='{pad_t+plot_h}' class='baseline'/>"

    legend = "".join(
        f"<span class='legend-item'><i style='background:var(--series-{color})'></i>{escape(slabel)}</span>"
        for _, slabel, color in series
    )

    return (
        f"<div class='chart-wrap'>"
        f"<svg viewBox='0 0 {width} {height}' class='chart' role='img' aria-label='Weekly activity by metric'>"
        f"{''.join(grid)}{baseline}{''.join(bars)}{''.join(xlabels)}"
        f"</svg>"
        f"<div class='legend'>{legend}</div>"
        f"</div>"
    )


# --- section builders -------------------------------------------------------
def instantly_section(campaigns, total_weekly):
    all_weeks = sorted(total_weekly.keys())
    if not all_weeks:
        return "<p class='empty'>No Instantly activity in the loaded date range.</p>", ""

    today = date.today()
    current_week_key = week_start(today).isoformat()
    chart_weeks = [(week_label(date.fromisoformat(wk)), total_weekly[wk]) for wk in all_weeks]

    chart = bar_chart(chart_weeks, INSTANTLY_METRICS)

    last_wk = all_weeks[-1]
    prev_wk = all_weeks[-2] if len(all_weeks) > 1 else None
    in_progress = last_wk == current_week_key and (today - date.fromisoformat(last_wk)).days < 6
    cur_m = total_weekly[last_wk]
    prev_m = total_weekly.get(prev_wk, {}) if prev_wk else {}

    tiles = []
    for key, label, color in INSTANTLY_METRICS:
        cur_v = cur_m.get(key, 0)
        prev_v = prev_m.get(key, 0)
        sub = fmt_delta(cur_v, prev_v) if prev_wk else "<span class='delta flat'>no prior week yet</span>"
        tiles.append(
            f"<div class='tile'><div class='tile-label'>{escape(label)}</div>"
            f"<div class='tile-value'>{cur_v:,}</div>"
            f"<div class='tile-sub'>{sub} vs prior week</div></div>"
        )
    note = (
        f"<p class='note'>Week of {escape(week_label(date.fromisoformat(last_wk)))} is still in progress "
        f"— totals will grow before it's comparable to a full week.</p>"
        if in_progress else ""
    )
    headline = f"<div class='tiles'>{''.join(tiles)}</div>{note}"

    shown_weeks = all_weeks[-6:]
    thead = "".join(f"<th>{escape(week_label(date.fromisoformat(wk)))}</th>" for wk in shown_weeks)
    camp_rows = []
    for camp in campaigns:
        cells = []
        for wk in shown_weeks:
            m = camp["weekly"].get(wk, {})
            cells.append(f"<td>{m.get('sent',0)} sent / {m.get('opens',0)} opens / {m.get('replies',0)} replies</td>")
        status_label = {1: "Active", 2: "Paused", 0: "Draft", 3: "Completed"}.get(camp["status"], str(camp["status"]))
        camp_rows.append(
            f"<tr><td class='rowhead'>{escape(camp['name'])}<span class='pill'>{status_label}</span></td>"
            f"{''.join(cells)}</tr>"
        )

    table = (
        f"<div class='table-wrap'><table><thead><tr><th>Campaign</th>{thead}</tr></thead>"
        f"<tbody>{''.join(camp_rows)}</tbody></table></div>"
    )

    return headline + chart, table


def kakiyo_section(snaps):
    if not snaps:
        return "<p class='empty'>No Kakiyo snapshots recorded yet.</p>", ""

    latest = snaps[-1]
    prior = snaps[-2] if len(snaps) > 1 else None

    def totals(snap):
        agg = defaultdict(int)
        for c in snap["campaigns"]:
            for k in ("prospects", "invitationsSent", "invitationsAccepted", "messagesSent", "prospectsAnswers", "qualified"):
                agg[k] += c.get(k, 0)
        return agg

    cur_t = totals(latest)
    prev_t = totals(prior) if prior else None

    fields = [
        ("prospects", "Total prospects"),
        ("invitationsSent", "Invitations sent"),
        ("invitationsAccepted", "Invitations accepted"),
        ("messagesSent", "Messages sent"),
        ("prospectsAnswers", "Replies"),
        ("qualified", "Qualified"),
    ]
    tiles = []
    for key, label in fields:
        cur_v = cur_t[key]
        if prev_t is not None:
            sub = f"{fmt_delta(cur_v, prev_t[key])} since {escape(prior['date'])}"
        else:
            sub = "<span class='delta flat'>first snapshot — no comparison yet</span>"
        tiles.append(
            f"<div class='tile'><div class='tile-label'>{escape(label)}</div>"
            f"<div class='tile-value'>{cur_v:,}</div><div class='tile-sub'>{sub}</div></div>"
        )
    headline = f"<div class='tiles'>{''.join(tiles)}</div>"
    if prior is None:
        headline += (
            "<p class='note'>Kakiyo's API only exposes running totals, not a historical daily feed. "
            "This dashboard snapshots those totals on every refresh and diffs consecutive snapshots to "
            "build a week-over-week trend — run the refresh again in about a week to get your first "
            "week-over-week comparison.</p>"
        )

    thead_cols = "".join(f"<th>{label}</th>" for _, label in fields)
    body_rows = []
    prev_row = None
    for snap in snaps:
        t = totals(snap)
        cells = []
        for key, _ in fields:
            v = t[key]
            if prev_row is not None:
                d = v - prev_row[key]
                sign = "+" if d >= 0 else ""
                cells.append(f"<td>{v:,} <span class='mut'>({sign}{d:,})</span></td>")
            else:
                cells.append(f"<td>{v:,}</td>")
        body_rows.append(f"<tr><td class='rowhead'>{escape(snap['date'])}</td>{''.join(cells)}</tr>")
        prev_row = t
    table = (
        f"<div class='table-wrap'><table><thead><tr><th>Snapshot date</th>{thead_cols}</tr></thead>"
        f"<tbody>{''.join(body_rows)}</tbody></table></div>"
    )
    return headline, table


CSS_TEMPLATE = """
:root { color-scheme: light; }
* { box-sizing: border-box; }
body {
  margin: 0; font-family: system-ui, -apple-system, "Segoe UI", sans-serif;
  background: var(--page); color: var(--ink-1);
}
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
.wrap { max-width: 1040px; margin: 0 auto; padding: 32px 20px 80px; }
h1 { font-size: 1.6rem; margin: 0 0 4px; }
.sub { color: var(--ink-2); margin: 0 0 32px; font-size: 0.95rem; }
h2 { font-size: 1.15rem; margin: 0 0 4px; display:flex; align-items:center; gap:8px; }
h2 .dot { width:10px; height:10px; border-radius:50%; display:inline-block; }
section { background: var(--surface); border: 1px solid var(--border); border-radius: 12px;
  padding: 24px; margin-bottom: 24px; }
.tiles { display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); gap: 14px; margin: 16px 0; }
.tile { padding: 14px 16px; border: 1px solid var(--border); border-radius: 10px; }
.tile-label { font-size: 0.8rem; color: var(--ink-mut); margin-bottom: 6px; }
.tile-value { font-size: 1.6rem; font-variant-numeric: tabular-nums; }
.tile-sub { font-size: 0.78rem; color: var(--ink-2); margin-top: 4px; }
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
.table-wrap { overflow-x: auto; margin-top: 16px; }
table { border-collapse: collapse; width: 100%; font-size: 0.82rem; }
th, td { text-align: left; padding: 8px 10px; border-bottom: 1px solid var(--border); white-space: nowrap; }
th { color: var(--ink-mut); font-weight: 600; font-size: 0.75rem; text-transform: uppercase; letter-spacing: .02em; }
.rowhead { font-weight: 600; }
.pill { display: inline-block; margin-left: 8px; font-size: 0.68rem; font-weight: 500; color: var(--ink-mut);
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
    fetched_at, campaigns, total_weekly = load_instantly()
    kakiyo_snaps = load_kakiyo()

    instantly_head, instantly_table = instantly_section(campaigns, total_weekly)
    kakiyo_head, kakiyo_table = kakiyo_section(kakiyo_snaps)

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
  <p class="sub">Week-over-week activity across Kakiyo and Instantly campaigns. Data fetched {escape(fetched_at)}.</p>

  <section>
    <h2><span class="dot" style="background:var(--series-blue)"></span>Instantly</h2>
    {instantly_head}
    {instantly_table}
  </section>

  <section>
    <h2><span class="dot" style="background:var(--series-orange)"></span>Kakiyo</h2>
    {kakiyo_head}
    {kakiyo_table}
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
