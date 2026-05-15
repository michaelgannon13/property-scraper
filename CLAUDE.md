# Revive Ireland — Claude Code Context

## What This Is
Irish derelict property register scraper. Scrapes 24 local councils nightly,
publishes to Supabase, powers revive-ireland.com.

## Key Dirs
- `derelict-scraper/` — Python scraper, parsers, geocoder, notifier
- `supabase/functions/` — Edge Functions for Supabase upsert/delete/cleanup
- `ADVISOR.md` — Business strategy context (read this for commercial questions)

## Business Advisor
For any commercial question (pricing, revenue, investors, partnerships), read
`ADVISOR.md` first — it contains the full business model and market context.
Then answer directly as a startup advisor who knows this product.

## Dev Branch
Always develop on `claude/check-branch-pointer-0Wo2f`, PR into main.

## Stack
- Python 3.12, SQLite, pdfplumber, pandas, requests
- Supabase (Postgres + Edge Functions)
- GitHub Actions nightly cron (1am UTC)
- Resend for email notifications
- Google Maps API for geocoding
