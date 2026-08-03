# Outreach Activity Dashboard

A week-over-week activity dashboard for the Kakiyo and Instantly outreach campaigns.
It's a static HTML file ([`dashboard.html`](./dashboard.html)) built from data snapshots
committed to this repo — no server, no hosting, no external API keys required. You
refresh it from inside a Claude session (this one or a new one) using the connected
Kakiyo and Instantly MCP tools.

Open `dashboard.html` in a browser to view it. Up top is a cross-platform
**Combined metrics** summary (this week vs. prior week, both platforms
together), then an **Instantly** / **Kakiyo** tab switcher. Each tab is
scoped to just that platform: its own **This week vs. prior week** KPIs, its
own **Compare date ranges** tool, then **Funnel** (a waterfall chart of that
platform's pipeline stages), **Weekly totals**, **Monthly totals**, and
**Daily activity** — plus Kakiyo's raw snapshot history.

### Funnels

Each tab's Funnel section is a cumulative, all-time waterfall — not tied to
the week/month tables or the Compare tool — built from `data/funnel.json`:

- **Kakiyo**: Connections sent → Connections accepted → Contacts replied →
  Contacts qualified → Conversions (`closed`).
- **Instantly**: Total unique contacts → Emails sent → Emails replied (split
  positive / negative / unknown, from Instantly's interest-status labels —
  "unknown" is a reply nobody has triaged yet, not counted as negative) →
  Conversions (`total_closed`). Emails sent can run *higher* than total
  unique contacts — that's expected, since each contact gets multiple steps
  in a sequence — so this is a waterfall (bars sized to their own value),
  not a strictly-narrowing funnel.

Every bar shows its **% of the top-of-funnel total** and its **% retained
from the previous stage**.

The full merged daily dataset (every day Instantly has activity for, plus
Kakiyo's day-to-day snapshot deltas) is embedded directly in the HTML once, so
each tab's **Compare date ranges** tool runs entirely client-side, scoped to
that platform's own metrics — pick any two custom date ranges (or a preset:
this week vs last week, this month vs last month, last 7/30 days vs the
previous 7/30) and it recomputes with a live delta, no server or rebuild
required.

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

3. **Pull the funnel snapshot** — overwrite `data/funnel.json` with fresh
   cumulative, all-time totals for both platforms:
   - Kakiyo: `list_campaigns` for `invitationsSent`/`invitationsAccepted`/`closed`,
     `get_analytics_overview` for `totalAnswers`/`totalQualified`.
   - Instantly: `analytics_campaign_overview` (no date range = all-time) for
     `contacted_count` (total unique contacts), `emails_sent_count`, `reply_count_unique`,
     `total_interested` (positive replies), and `total_closed` (conversions). Negative
     replies come from `list_leads` with `filter: FILTER_LEAD_NOT_INTERESTED` (page
     through with `starting_after` and count the results — the response has no total
     count field). Unknown = `reply_count_unique - total_interested - <not-interested count>`.
   ```json
   {
     "fetched_at": "<ISO timestamp>",
     "instantly": {"total_unique_contacts": 0, "emails_sent": 0, "emails_replied": 0, "emails_replied_positive": 0, "emails_replied_negative": 0, "emails_replied_unknown": 0, "conversions": 0, "source": "instantly-mcp:analytics_campaign_overview (all campaigns, all-time)"},
     "kakiyo": {"connections_sent": 0, "connections_accepted": 0, "contacts_replied": 0, "contacts_qualified": 0, "conversions": 0, "source": "kakiyo-mcp:list_campaigns + get_analytics_overview (all campaigns, all-time)"}
   }
   ```

4. **Regenerate the HTML**:
   ```
   python3 scripts/generate_dashboard.py
   ```

5. Commit and push the updated `data/` files and `dashboard.html`.

For a running trend, refresh roughly once a week (a Claude Routine/cron trigger works
well for this — ask Claude to set one up if you want it automatic).

## Files

```
data/
  instantly_raw.json      # latest Instantly daily analytics pull (overwritten each refresh)
  kakiyo_snapshots.jsonl   # append-only Kakiyo cumulative-totals log, one JSON line per refresh
  funnel.json              # cumulative all-time funnel totals for both platforms (overwritten each refresh)
scripts/
  generate_dashboard.py   # renders dashboard.html from the two data files above
dashboard.html             # generated output — open this in a browser
```
