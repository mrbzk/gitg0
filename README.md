# Outreach Activity Dashboard

A week-over-week activity dashboard for the Kakiyo and Instantly outreach campaigns.
It's a static HTML file ([`dashboard.html`](./dashboard.html)) built from data snapshots
committed to this repo — no server, no hosting, no external API keys required. You
refresh it from inside a Claude session (this one or a new one) using the connected
Kakiyo and Instantly MCP tools.

Open `dashboard.html` in a browser to view it.

## How it works

- **Instantly** exposes a real daily analytics feed
  (`get_daily_campaign_analytics`), so `data/instantly_raw.json` holds true daily
  history and the dashboard aggregates it into Mon–Sun weeks on every regenerate.
- **Kakiyo**'s API only exposes running totals per campaign (no historical
  time series). To get a week-over-week trend anyway, `data/kakiyo_snapshots.jsonl`
  is an append-only log — every refresh appends one row with the current cumulative
  totals, and the dashboard diffs consecutive rows to show what changed. The first
  refresh has nothing to compare against; the second (about a week later) produces
  the first real week-over-week number, and it keeps improving from there.

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
   {"date": "YYYY-MM-DD", "campaigns": [{"id": "...", "name": "...", "status": "active", "prospects": 0, "invitationsSent": 0, "invitationsAccepted": 0, "messagesSent": 0, "prospectsAnswers": 0, "qualified": 0, "closed": 0}]}
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
