# Outreach Activity Dashboard

A week-over-week activity dashboard for the Kakiyo and Instantly outreach campaigns.
It's a static HTML file ([`dashboard.html`](./dashboard.html)) built from data snapshots
committed to this repo — no server, no hosting, no external API keys required. You
refresh it from inside a Claude session (this one or a new one) using the connected
Kakiyo and Instantly MCP tools.

Open `dashboard.html` in a browser to view it. Layout is modeled on the team's
outreach tracking spreadsheet: a cross-platform **this-week-vs-prior-week**
summary and an interactive **Compare date ranges** tool up top, then an
**Instantly** / **Kakiyo** tab switcher for the platform-specific detail —
each tab has its own **Weekly totals**, **Monthly totals**, and **Daily
activity**, plus Instantly's per-campaign breakdown and Kakiyo's raw snapshot
history.

The full merged daily dataset (every day Instantly has activity for, plus
Kakiyo's day-to-day snapshot deltas) is embedded directly in the HTML, so
**Compare date ranges** runs entirely client-side — pick any two custom date
ranges (or a preset: this week vs last week, this month vs last month, last
7/30 days vs the previous 7/30) and it recomputes Sends, Opens, Open Rate,
Interested, Connections Sent/Accepted, and # Completing Goal for both ranges
with a live delta, no server or rebuild required.

## How it works

- **Instantly** exposes a real daily analytics feed
  (`get_daily_campaign_analytics`), so `data/instantly_raw.json` holds true daily
  history and the dashboard aggregates it into Mon–Sun weeks and calendar months
  on every regenerate.
- **Kakiyo**'s API only exposes running totals per campaign (no historical
  time series). To get a week-over-week trend anyway, `data/kakiyo_snapshots.jsonl`
  is an append-only log — every refresh appends one row with the current cumulative
  totals (`invitationsSent`, `invitationsAccepted`, `qualified`, etc.), and the
  dashboard diffs consecutive rows to get each period's real change. The
  `2026-07-30` baseline row was seeded from the team's existing tracking
  spreadsheet (Kakiyo's API had no way to look back further); every row after
  that is pulled live and tagged `"source": "kakiyo-mcp"`. Weeks/months before
  a snapshot existed show `0` for Kakiyo columns — that means "not tracked yet,"
  not "no activity."

`scripts/generate_dashboard.py` reads both data files and renders `dashboard.html`.
It's dependency-free (Python 3 standard library only).

## Refreshing the data

Ask Claude (in this repo) to "refresh the activity dashboard." It should:

1. **Pull Instantly data** — call `list_campaigns` to get current campaign IDs/names/
   status, then `get_daily_campaign_analytics` per campaign (or for all campaigns) over
   a wide date range (e.g. last 90 days). Overwrite `data/instantly_raw.json` with:
   ```json
   {
     "fetched_at": "<ISO timestamp>",
     "date_range": { "start": "...", "end": "..." },
     "campaigns": [
       { "id": "...", "name": "...", "status": 1, "daily": [ { "date": "YYYY-MM-DD", "sent": 0, "contacted": 0, "opened": 0, "unique_opened": 0, "replies": 0, "unique_replies": 0, "clicks": 0, "unique_clicks": 0, "opportunities": 0 } ] }
     ]
   }
   ```
   Skip campaigns with no send activity (unlaunched drafts).

2. **Pull Kakiyo data** — call `list_campaigns` (or `get_campaign_stats` per
   campaign) and **append** one line to `data/kakiyo_snapshots.jsonl` (don't
   overwrite — if a snapshot for today's date already exists, replace that line
   instead of duplicating it):
   ```json
   {"date": "YYYY-MM-DD", "source": "kakiyo-mcp", "campaigns": [{"id": "...", "name": "...", "status": "active", "prospects": 0, "invitationsSent": 0, "invitationsAccepted": 0, "messagesSent": 0, "prospectsAnswers": 0, "qualified": 0, "closed": 0}]}
   ```

3. **Regenerate the HTML**:
   ```
   python3 scripts/generate_dashboard.py
   ```

4. Commit and push the updated `data/` files and `dashboard.html`.

For a running trend, refresh roughly once a week (a Claude Routine/cron trigger works
well for this — ask Claude to set one up if you want it automatic).

## Files

```
data/
  instantly_raw.json      # latest Instantly daily analytics pull (overwritten each refresh)
  kakiyo_snapshots.jsonl   # append-only Kakiyo cumulative-totals log, one JSON line per refresh
scripts/
  generate_dashboard.py   # renders dashboard.html from the two data files above
dashboard.html             # generated output — open this in a browser
```
