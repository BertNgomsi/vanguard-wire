# Vanguard Wire - Architecture & Context

This document outlines the entire technical stack, deployment infrastructure, and automation pipeline for **The Vanguard Wire** project. It is designed to provide complete context for future AI assistants or developers working on this codebase.

## 1. System Overview
The Vanguard Wire is a fully autonomous, AI-powered progressive news wire and cultural watchdog. It scrapes RSS feeds, uses Google's Gemini to rewrite the content into a specific editorial persona, sends a draft to a human editor via Telegram for 1-click approval, and automatically publishes approved articles to a live website.

## 2. Tech Stack
*   **Frontend:** Astro (Static Site Generator)
*   **Styling:** Pure CSS (Vibrant dark mode, glassmorphism)
*   **Backend / AI Engine:** Python 3, Flask, Google GenAI SDK (Gemini 3.6 Flash)
*   **Hosting (Frontend):** Cloudflare Pages (`thevanguardwire.com`)
*   **Hosting (Backend):** DigitalOcean Ubuntu VPS (`api.thevanguardwire.com`)

## 3. The Automation Pipeline (End-to-End)

### A. Ingestion (`engine/ingest.py`)
*   **Trigger:** Runs hourly on the DigitalOcean server via a Linux `cron` job.
*   **Process:** 
    1. Scrapes progressive RSS feeds defined in `engine/feeds.json`.
    2. Sends the article to Gemini with a highly specific system prompt (instructing it to adopt an irreverent, sarcastic, vigilant watchdog persona).
    3. Gemini evaluates the article's relevance (0-100 score). If `>= 65`, it formats a headline, framing lead, and quote.
    4. The script sends the draft to the human editor via the Telegram Bot API.
*   **Crucial Implementation Detail:** Due to Telegram's strict 64-byte limit on `callback_data` for inline buttons, the `source_url` is appended to the visible message text, and the button's payload is kept simply as `"approve"` or `"reject"`.

### B. Approval Webhook (`engine/webhook.py`)
*   **Trigger:** The human editor taps "🟢 Approve" in Telegram.
*   **Process:**
    1. Telegram sends a POST request to `api.thevanguardwire.com/webhook/<BOT_TOKEN>`.
    2. The Flask server (running as a `systemd` service) receives the payload.
    3. It parses the original message text using Regex to extract the Headline, Framing, Quote, Category, and URL.
    4. It constructs an Astro-compatible Markdown file with YAML frontmatter.
    5. **GitHub API:** Instead of writing to the local filesystem, it uses the `PyGithub` / requests library to push a brand new commit containing the markdown file directly to the `BertNgomsi/vanguard-wire` repository on GitHub.

### C. Deployment (Cloudflare Pages)
*   **Trigger:** Cloudflare detects the new commit pushed to the `main` branch by the webhook.
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
*   `GITHUB_TOKEN` (Must have write permissions to push commits to the repo).
