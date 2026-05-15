# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Overview

This is John Zhou's personal website (`johnzhou.xyz`). It has two distinct parts:

1. **Static site** — `index.html` and `recipes.html` served directly at `johnzhou.xyz`
2. **Plants app** — a Flask web app in `plants/`, deployed separately at `plants.johnzhou.xyz`

There is no build step, no package manager, and no bundler for the static site. Edit HTML files directly.

## Running the Plants App

```bash
cd plants
cp .env.example .env   # fill in RESEND_API_KEY and ALERT_EMAIL
pip install -r requirements.txt
python app.py           # starts on PORT from .env, default 5001
```

The SQLite database (`plants.db`) is created automatically on first run via `init_db()`. The watering alert email runs as a cron job at 8:00 AM daily via APScheduler.

## Architecture

### Static site (`index.html`, `recipes.html`)
- No external CSS/JS files — all styles and scripts are inline within each HTML file.
- `index.html`: Retro 90s aesthetic (ivory `#FFFFF0` background, Times New Roman, hit counter, webring).
- `recipes.html`: Card-based layout with tab navigation (pink/rose palette, `--primary: #E85D75`). Adding a new recipe means adding a `<button class="recipe-tab">` to the nav and a corresponding `<article class="recipe-card">` to the main grid. The tab↔card pairing is done by `data-recipe` / `data-recipe-card` index attributes.
- `images/` holds the recipe photo JPGs referenced directly by filename.

### Plants app (`plants/`)
- **`app.py`**: Single-file Flask app. SQLite via the stdlib `sqlite3` module. Two tables: `plants` and `waterings`. All DB access goes through `get_db()` which sets `row_factory = sqlite3.Row` for dict-like access.
- **`templates/index.html`**: Jinja2 template. All CSS is inline. Plant cards are rendered server-side; modals (Add Plant, Water Plant) are shown/hidden client-side via `openModal()`/`closeModal()`.
- **Watering logic**: `app.py` computes `days_since`, `days_until`, `pct` (0–100 thirst percentage), and `overdue` in the `index` route and passes them to the template. Plants are sorted by `pct` descending (most thirsty first).
- **Email alerts**: Sent via the `resend` library. Configured with `RESEND_API_KEY` and `ALERT_EMAIL` env vars. If either is missing, the alert is skipped silently.

## Design Conventions

Both the recipes page and the plants app share the same Google Fonts stack: `Satisfy` (cursive) for display headings and `Poppins` for body text. Maintain this when adding new pages.

CSS custom properties (`:root` variables) define the color palette in each file — use those variables rather than hardcoded hex values when adding styles within those files.

Health status values in the plants app are an enum enforced at the DB level: `thriving`, `good`, `okay`, `struggling`, `bad`. These same strings drive CSS class names (`health-thriving`, etc.) in the template.
