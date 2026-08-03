# Outreach Activity Dashboard

A week-over-week activity dashboard for the Kakiyo and Instantly outreach campaigns.
It's a static HTML file ([`dashboard.html`](./dashboard.html)) built from data snapshots
committed to this repo — no server, no hosting, no external API keys required. You
refresh it from inside a Claude session (this one or a new one) using the connected
Kakiyo and Instantly MCP tools.

Open `dashboard.html` in a browser to view it. A single **Compare periods**
control sits at the very top of the page — pick any two custom date ranges,
or a preset (this week vs last week, this month vs last month, last 7/30 days
vs the previous 7/30) — and it drives *everything* below it: the
cross-platform **Overview** table, and each platform's own **Selected
period** table inside its **Instantly** / **Kakiyo** tab. There's no
per-section picker; one selection updates all three at once, live,
client-side (the full merged daily dataset is embedded once in the HTML).
Below that, each tab still has its **Funnel** (a waterfall chart of that
platform's pipeline stages, always all-time — not affected by the picker),
**Weekly totals**, **Monthly totals**, and **Daily activity**. Every section
heading has a small (i) info bubble — hover on desktop, tap on mobile —
explaining what it shows.

### Funnels

Each tab's Funnel section is a cumulative, all-time waterfall — not tied to
the period picker or the week/month tables — built from `data/funnel.json`:

- **Kakiyo**: Connections sent → Connections accepted → Contacts replied →
  Contacts qualified → Sales (`closed`).
- **Instantly**: Total unique contacts → Emails sent → Emails replied (split
  positive / negative / unknown, from Instantly's interest-status labels —
  "unknown" is a reply nobody has triaged yet, not counted as negative) →
  Sales (`total_closed`). Emails sent can run *higher* than total
  unique contacts — that's expected, since each contact gets multiple steps
  in a sequence — so this is a waterfall (bars sized to their own value),
  not a strictly-narrowing funnel.

Every bar shows its **% of the top-of-funnel total** and its **% retained
from the previous stage**. "Sales" on both funnels currently reads the
platform's own Closed/Won status — a firmer, definitive source for that
number is still pending.

### Active conversations (Kakiyo)

A live KPI in the Kakiyo tab, separate from the funnel and not tied to the
period picker: the count of prospects who've replied or been qualified
*and* whose most recent message is within the last 3 days — i.e. people
worth following up with right now. Built from `list_campaign_prospects`
(`hasResponded: true`, status Replied or Qualified, `lastMessage` inside the
window). Stored in `data/funnel.json`'s `kakiyo.active_conversations` field
alongside `active_conversations_window_days` and `active_conversations_fetched_at`.

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
     "kakiyo": {"connections_sent": 0, "connections_accepted": 0, "contacts_replied": 0, "contacts_qualified": 0, "conversions": 0, "source": "kakiyo-mcp:list_campaigns + get_analytics_overview (all campaigns, all-time)", "active_conversations": 0, "active_conversations_window_days": 3, "active_conversations_fetched_at": "<ISO timestamp>", "active_conversations_source": "kakiyo-mcp:list_campaign_prospects(hasResponded=true), counting prospects with status Replied or Qualified whose lastMessage falls inside the window"}
   }
   ```
   `active_conversations` comes from `list_campaign_prospects` per Kakiyo campaign with
   `hasResponded: true` (paginate with `cursor` if a page fills up), counting prospects
   with `status` 4 (replied) or 5 (qualified) whose `lastMessage` timestamp is within
   the last 3 days of now.

4. **Regenerate the HTML**:
   ```
   python3 scripts/generate_dashboard.py
   ```

5. Commit and push the updated `data/` files and `dashboard.html`.

### Automated refresh

A daily Claude Routine ("Kakiyo daily snapshot", `0 0 * * *` UTC) already
handles steps 2–5 for Kakiyo's snapshot log, funnel numbers, and active
conversations — it's bound to this session (not a fresh one each time)
because this org can't currently grant MCP connector access to
routine-spawned fresh sessions. Instantly's data (step 1) isn't automated
yet; ask Claude to set that up too if you want the whole pipeline unattended.

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
