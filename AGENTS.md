# Project Context & Mission

**The Vanguard Wire** is a Black progressive news aggregation platform. 
Our mission is to "plead our own cause," combat misinformation, and address critical information gaps (such as systemic racism, economic justice, voting rights, and health disparities) that mainstream media often overlooks. 

**Brand Voice & Tone:**
- **Compelling & Hard-hitting:** The writing should be uncompromising, direct, and authoritative.
- **Progressive & Independent:** We stand on the frontlines of truth, centering voices that challenge the status quo and demand equity.
- **Solidarity through Aggregation:** Our strategy is to break down silos, amplify independent Black publishers, and sustain the progressive media ecosystem.

**Key Themes:**
- The crisis of information (rollback of DEI, widespread disinformation).
- Speaking truth to power (holding institutions accountable, mobilizing for social justice).
- Preserving history, celebrating culture, and humanizing the Black experience.

## Editorial Taxonomy & Curation Pillars
We classify all ingested news into 6 precise categories:
1. **Anti-Black Racism & Extremism Watchdog:** Tracking viral microaggressions, racist comments, white nationalist rhetoric, and Fox News/Newsmax dogwhistles.
2. **Civil Rights, Voting & Legal Tracker:** Voter suppression bills, redlining lawsuits, SCOTUS DEI decisions, DOJ investigations.
3. **Systemic Policy & Dogwhistle Watchdog:** Anti-DEI laws, CRT panics, school board battles, criminal justice policy.
4. **Anti-Black / Conservative Hypocrisy Tracker:** Grifters, anti-Black political figures, and corporate fake DEI promises.
5. **Black Pop Culture & Sports Media Slant:** Black cinema/TV, sports activism, HBCU culture, viral Black Twitter/TikTok moments.
6. **The Watercooler / The Front Porch:** Community discussion, venting, news tips, and informal debate.

## System Architecture & Publishing Pipeline
- **Target Feeds:** `engine/feeds.json` stores 80+ curated RSS feeds, APIs, and Nitter Twitter scrapers covering progressive watchdog sites, Black media, and conservative targets.
- **Ingestion & AI (`engine/ingest.py`):** Automatically polls feeds, passing articles to Gemini Pro API for relevance scoring (must be >65), assigning one of the 6 taxonomy categories, extracting a 75-120 word primary quote, and writing a 30-50 word framing lead using an **"irreverent, sarcastic, vigilant, combative, and cynical"** tone.
- **Human-in-the-Loop Approval:** Valid drafts are sent to the founder's smartphone via Telegram with an interactive [Approve] / [Reject] button.
- **Webhook Listener (`engine/webhook.py`):** A Flask server (running on port 5001, exposed via ngrok) listens for Telegram callback queries. Upon approval, it formats the draft as an Astro Markdown (`.md`) file with frontmatter.
- **Automated Deployment:** The webhook uses the GitHub API (`GITHUB_TOKEN`) to commit the `.md` file directly to `src/content/blog/`. This push instantly triggers a Cloudflare Pages static site build, taking the post live within 30 seconds.

---

## Development

When starting the dev server, use background mode:

```
astro dev --background
```

Manage the background server with `astro dev stop`, `astro dev status`, and `astro dev logs`.

## Documentation

Full documentation: https://docs.astro.build

Consult these guides before working on related tasks:

- [Adding pages, dynamic routes, or middleware](https://docs.astro.build/en/guides/routing/)
- [Working with Astro components](https://docs.astro.build/en/basics/astro-components/)
- [Using React, Vue, Svelte, or other framework components](https://docs.astro.build/en/guides/framework-components/)
- [Adding or managing content](https://docs.astro.build/en/guides/content-collections/)
- [Adding styles or using Tailwind](https://docs.astro.build/en/guides/styling/)
- [Supporting multiple languages](https://docs.astro.build/en/guides/internationalization/)

---

## Editorial Workflow & Automation Architecture

The project features a highly automated editorial pipeline designed for rapid "newsjacking" and hybrid scheduling, managed entirely via a Telegram Bot. Future agents should understand this architecture before modifying backend scripts.

### 1. Ingestion & AI Synthesis (`engine/ingest.py`)
- Curated RSS feeds are parsed and sent to Gemini Pro for synthesis.
- Gemini scores relevance (rejects < 65) and generates an active-voice headline, framing lead, and blockquote.
- Drafts are pushed to a Telegram chat as an alert.

### 2. Telegram Inline Editor
- The Telegram alert contains inline buttons for moderation and editing.
- Users can tap `[✏️ Edit Headline]` or `[✏️ Edit Framing]` to reply in Telegram and update the draft directly.

### 3. The Webhook & Auto-Queue System (`engine/webhook.py`)
- The webhook runs as a Flask app (managed by `systemd` on an Ubuntu production server on port 5001).
- **[🚨 Publish NOW]:** Instantly creates the Astro Markdown file with `pubDate = datetime.now()` and pushes it to GitHub via the REST API.
- **[🟢 Approve & Queue]:** Calculates the *next available publishing window* (e.g., 08:30, 09:30, 10:30, 12:00, 13:30, 15:00, 16:30 Eastern) based on the `last_queued_timestamp` stored in `engine/queue_state.json`. It skips weekends and Friday afternoons.
- This creates a completely hands-off scheduling system where editors are only the bottleneck for quality (approvals), while the Python backend handles deployment logistics.

### 4. Production Note
If `webhook.py` is modified, the production systemd service must be restarted (`systemctl restart vanguard-wire`) to pick up the new code. Do not attempt to run it manually (`python webhook.py`) in production, as systemd will lock the port.

## Backend Server & Webhook Architecture
The project includes a Python backend (located in `engine/`) that acts as an RSS scraper and Telegram webhook server.
- **Server:** Runs on an Ubuntu VPS.
- **Ingestion:** `ingest.py` is executed hourly via a GitHub Actions workflow (`.github/workflows/ingest.yml`). It scrapes RSS feeds, passes them to Gemini for summarization, and sends draft alerts to a Telegram chat with inline Approve/Reject buttons. At the end of every run, it sends a final status summary to Telegram, and the workflow is configured to send failure alerts if it crashes.
- **Webhook Service:** `webhook.py` runs as a systemd background service (`vanguard-webhook.service`) on port `5001`. It receives callback queries from Telegram.
- **Telegram UX Edge Cases:** Clicking Approve/Reject in Telegram sends an immediate `answerCallbackQuery` (to stop the button loading animation) and an `editMessageText` request to remove the buttons and mark the message as `✅ [APPROVED]` or `❌ [REJECTED]`. This prevents duplicate approvals.
- **GitHub Integration:** Approved articles are pushed directly to the `BertNgomsi/vanguard-wire` GitHub repository under `src/content/blog/` via the GitHub API.
- **Networking & SSL:** 
  - Nginx is configured as a reverse proxy, listening on `api.thevanguardwire.com` and forwarding to `127.0.0.1:5001`.
  - SSL is managed by Let's Encrypt / Certbot.
  - **Cloudflare Note:** When configuring or renewing Certbot certificates, the Cloudflare DNS record for `api.thevanguardwire.com` must be set to "DNS Only" (Grey Cloud). It can be set back to "Proxied" (Orange Cloud) afterward.
  - The Telegram webhook URL is registered as `https://api.thevanguardwire.com/webhook/<BOT_TOKEN>`.
- **Logs:** Webhook logs can be viewed via `journalctl -u vanguard-webhook -f` on the VPS. Note that Python buffers `print()` outputs in systemd, so they may be delayed unless the service is restarted or output is explicitly flushed.
## Telegram Bot Architecture & Workflow

The project uses a Telegram bot for approving and editing ingested news drafts before they are published to the Astro site.

**Stateless Design & Editing:**
- The bot is completely stateless and does not use a database to store drafts. 
- All data (Category, Headline, Framing, Quote) is parsed directly from the text of the Telegram message.
- Users can edit the "Headline" and "Framing" of a draft directly in Telegram. This is handled using Telegram's `ForceReply` feature: the bot replies asking for the new text and secretly embeds context (like `[Action: edit_headline]` and `[Context ID: <message_id>]`) in the prompt. When the user replies, the bot parses this context, uses regex to replace the specific field in the original message, updates the original message, and deletes the prompt/reply to keep the chat clean.

**Publishing & Queueing:**
- Drafts can be published via two methods:
  - **🚨 Publish NOW**: Immediately pushes the markdown file to GitHub with the current timestamp.
  - **🟢 Approve & Queue**: Schedules the article for a future publishing window.
- The queue uses predefined slots (e.g., 8:30, 9:30, 10:30, 12:00, 13:30, 15:00, 16:30) and avoids publishing on weekends or late Fridays (after 2:00 PM). The last used slot is tracked in `engine/queue_state.json`.

## Social Media & Distribution Strategy
The Vanguard Wire relies on automated social media distribution to amplify its journalism and push new posts immediately upon approval.
- **Target Platforms (Tier 1):** X (Twitter), LinkedIn Company Page, and Facebook Page. These platforms are optimized for news consumption, link sharing, and B2B/professional engagement.
- **Target Platforms (Tier 2):** Bluesky. We utilize domain verification (`@thevanguardwire.com`) to establish immediate trust and credibility among the growing independent news audience.
- **Platforms to Avoid for Link Automation:** Instagram (Feed) and TikTok/YouTube Shorts, as they do not support native clickable links in captions for simple text/link news drops.
- **Automation Pipeline:** The CMS/publishing engine (via RSS feed, webhooks, or native plugins) is connected to an automation tool (e.g., Zapier, Make, Buffer) to automatically format and push the article title, a short summary, and the URL to the target platforms immediately upon publication.
- **Social Brand Voice:** Authoritative, forward-looking, sharp, and reliable. The social copy emphasizes cutting through the noise and providing critical context.
