# Vanguard Wire - Architecture & Context

This document outlines the entire technical stack, deployment infrastructure, and automation pipeline for **The Vanguard Wire** project. It is designed to provide complete context for future AI assistants or developers working on this codebase.

## 1. System Overview
The Vanguard Wire is a fully autonomous, AI-powered progressive news wire and cultural watchdog. It scrapes RSS feeds and X (via Apify), uses Google's Gemini to rewrite the content into a specific editorial persona (enforced via strict JSON schemas), sends a draft to a human editor via Telegram for 1-click approval, and automatically publishes approved articles to a live website. 

The architecture is stateful, storing drafts in a local SQLite database for reliability and enabling automated background retry mechanisms.

## 2. Tech Stack
*   **Frontend:** Astro (Static Site Generator)
*   **Styling:** Pure CSS (Vibrant dark mode, glassmorphism)
*   **Backend / AI Engine:** Python 3, Flask, Google GenAI SDK (Gemini 3.6 Flash)
*   **State Management:** SQLite (`vanguard.db`)
*   **Hosting (Frontend):** Cloudflare Pages (`thevanguardwire.com`)
*   **Hosting (Backend):** DigitalOcean Ubuntu VPS (`api.thevanguardwire.com`)

## 3. The Automation Pipeline (End-to-End)

### A. Ingestion (`engine/ingest.py`)
*   **Trigger:** Runs hourly via a system cron job on the DigitalOcean VPS.
*   **Process:** 
    1. Scrapes progressive RSS feeds and X (Twitter) accounts defined in `engine/feeds.json`. (Twitter data is fetched via the Apify RealTime scraper API).
    2. Sends the article to Gemini with a highly specific system prompt (`engine/rubric.md`) instructing it to adopt an irreverent, sarcastic, vigilant watchdog persona.
    3. Gemini evaluates the article's relevance (0-100 score). If `>= 65`, it formats a headline, framing lead, blockquote, kicker, category, and Tip CTA, enforcing output in strict JSON format (`DraftResponse` Pydantic model).
    4. The draft is persisted to a local SQLite database (`vanguard.db`) which returns a unique `draft_id`.
    5. The script sends the draft to the human editor via the Telegram Bot API with inline buttons attached to the `draft_id`.

### B. Approval Webhook (`engine/webhook.py`)
*   **Trigger:** The human editor taps "🟢 Approve" in Telegram or forwards an older message to the bot to recover it.
*   **Process:**
    1. Telegram sends a POST request to `api.thevanguardwire.com/webhook/<BOT_TOKEN>`.
    2. The Flask server (running as a `systemd` service) receives the payload, extracts the `draft_id` from the callback, and queries the SQLite database for the draft data.
    3. If the user forwards an old message without a callback button, the bot uses regex to parse the text, creates a new database entry, and replies with fresh approval buttons (Historical Draft Recovery).
    4. The bot calls the Unsplash API to fetch a relevant hero image. If the API fails, the article proceeds gracefully with a fallback placeholder.
    5. It constructs an Astro-compatible Markdown file with YAML frontmatter.
    6. **GitHub API:** It uses the `PyGithub` library to push a brand new commit containing the markdown file directly to the `BertNgomsi/vanguard-wire` repository. It includes a retry loop to elegantly handle `409 Conflict` errors when multiple editors approve simultaneously.

### C. Background Optimization (`engine/retry_images.py`)
*   **Trigger:** Runs every 2 hours via a system cron job on the DigitalOcean VPS.
*   **Process:** 
    1. Queries `vanguard.db` for articles marked "published" that do not have an Unsplash image attached.
    2. Attempts to fetch an image again. If successful, pulls the live Markdown file from GitHub, updates the frontmatter, and pushes a new commit to restore the image.

### D. Deployment (Cloudflare Pages)
*   **Trigger:** Cloudflare detects the new commit pushed to the `main` branch by the webhook or retry script.
*   **Process:** 
    1. Cloudflare runs `npm run build`.
    2. The Astro site is statically generated into the `dist` folder.
    3. The updated site goes live at `thevanguardwire.com` within ~60 seconds.

## 4. Server Infrastructure (DigitalOcean)
*   **IP Address:** `167.71.165.130`
*   **Reverse Proxy:** Nginx listens on port 80 and forwards traffic to the Flask app on port 5001.
*   **HTTPS:** Handled automatically by Cloudflare's proxy (Orange Cloud) for the `api.thevanguardwire.com` A-record.
*   **Service:** The webhook is managed by systemd (`vanguard-webhook.service`).
*   **Logs:** Can be viewed via `journalctl -u vanguard-webhook -n 50 --no-pager`.

## 5. Environment Variables (`.env`)
The engine requires the following keys, located in `/root/vanguard-wire/engine/.env` on the VPS:
*   `GEMINI_API_KEY`
*   `TELEGRAM_BOT_TOKEN`
*   `TELEGRAM_CHAT_ID`
*   `GITHUB_TOKEN` (Must have write permissions to push commits to the repo)
*   `APIFY_API_TOKEN` (For X/Twitter scraping)
*   `UNSPLASH_ACCESS_KEY` (For image sourcing)
