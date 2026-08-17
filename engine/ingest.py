import os
import time
import json
import feedparser
import requests
from google import genai
from google.genai import types
from pydantic import BaseModel
from dotenv import load_dotenv

import db

# Load environment variables
load_dotenv()

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
APIFY_API_TOKEN = os.getenv("APIFY_API_TOKEN")

if not GEMINI_API_KEY:
    print("Warning: GEMINI_API_KEY is not set.")

# Configure Gemini Client
client = None
if GEMINI_API_KEY:
    client = genai.Client(api_key=GEMINI_API_KEY)

# Load curated feeds from feeds.json
FEEDS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "feeds.json")
try:
    with open(FEEDS_FILE, "r") as f:
        RSS_FEEDS = json.load(f)
except FileNotFoundError:
    print(f"Warning: {FEEDS_FILE} not found. No feeds loaded.")
    RSS_FEEDS = []

# Load external rubric
RUBRIC_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "rubric.md")
try:
    with open(RUBRIC_FILE, "r") as f:
        SYSTEM_PROMPT = f.read()
except FileNotFoundError:
    print(f"Warning: {RUBRIC_FILE} not found. Using default prompt.")
    SYSTEM_PROMPT = "Evaluate relevance and extract key information."

class DraftResponse(BaseModel):
    relevance_score: int
    headline: str
    framing_lead: str
    blockquote: str
    kicker: str
    category: str
    tip_cta: str

def fetch_feeds():
    """Fetch and parse RSS feeds and Apify data."""
    entries = []
    for feed in RSS_FEEDS:
        try:
            print(f"Fetching {feed['name']}...")
            if feed.get("type") == "Apify":
                if not APIFY_API_TOKEN:
                    print("Skipping Apify: APIFY_API_TOKEN not set.")
                    continue
                apify_url = f"https://api.apify.com/v2/acts/kaitoeasyapi~twitter-x-data-tweet-scraper-pay-per-result-cheapest/run-sync-get-dataset-items?token={APIFY_API_TOKEN}"
                payload = {
                    "maxItems": 3,
                    "queryType": "Latest",
                    "lang": "en",
                    "from": feed["from"]
                }
                res = requests.post(apify_url, json=payload, headers={'Content-Type': 'application/json'})
                res.raise_for_status()
                tweets = res.json()
                for tweet in tweets:
                    entries.append({
                        "title": f"Tweet by {feed['name']}",
                        "link": tweet.get("url", ""),
                        "description": tweet.get("text", ""),
                        "source": feed["name"]
                    })
            else:
                parsed = feedparser.parse(feed["url"])
                for entry in parsed.entries[:3]:
                    entries.append({
                        "title": entry.title,
                        "link": entry.link,
                        "description": entry.get("description", ""),
                        "source": feed["name"]
                    })
        except Exception as e:
            print(f"Error fetching {feed['name']}: {e}")
    return entries

def synthesize_content(article):
    """Pass article through Gemini Pro for synthesis."""
    if not client:
        print("Skipping AI synthesis: Gemini API key not found.")
        return None
        
    prompt = f"{SYSTEM_PROMPT}\n\nArticle Title: {article['title']}\nArticle Excerpt: {article['description']}\nSource: {article['source']}"
    
    try:
        response = client.models.generate_content(
            model='gemini-3.6-flash', 
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=DraftResponse,
            )
        )
        data = json.loads(response.text)
        data['source_url'] = article['link']
        data['source_name'] = article['source']
        return data
    except Exception as e:
        print(f"Error calling Gemini: {e}")
        return None

def send_to_telegram(draft, draft_id):
    """Send the formatted draft to Telegram for approval."""
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print("Skipping Telegram. Bot token or chat ID not set.")
        return

    text = f"🚨 DRAFT POST [Score: {draft.get('relevance_score', '?')}]\n"
    text += f"Category: [{draft.get('category', '?')}]\n"
    text += f"Headline: {draft.get('headline', '?')}\n\n"
    text += f"Framing: {draft.get('framing_lead', '?')}\n\n"
    text += f"Quote: \"{draft.get('blockquote', '?')}\" — {draft.get('source_name', '?')}\n"
    if draft.get('kicker'):
        text += f"Kicker: {draft.get('kicker')}\n"
    if draft.get('tip_cta'):
        text += f"Tip CTA: {draft.get('tip_cta')}\n"
    text += f"URL: {draft.get('source_url', '')}"

    # Inline keyboard for 1-click approval
    reply_markup = {
        "inline_keyboard": [
            [{"text": "🟢 Approve & Queue", "callback_data": f"approve_queue|{draft_id}"}, {"text": "🚨 Publish NOW", "callback_data": f"approve_now|{draft_id}"}],
            [{"text": "🔴 Reject", "callback_data": f"reject|{draft_id}"}],
            [{"text": "✏️ Edit Headline", "callback_data": f"edit_headline|{draft_id}"}, {"text": "✏️ Edit Framing", "callback_data": f"edit_framing|{draft_id}"}]
        ]
    }

    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": text,
        "reply_markup": json.dumps(reply_markup)
    }

    try:
        response = requests.post(url, json=payload)
        response.raise_for_status()
        print("Successfully sent draft to Telegram.")
    except Exception as e:
        print(f"Error sending to Telegram: {e}")

def send_summary_to_telegram(scanned, selected):
    """Send a final summary of the ingestion run to Telegram."""
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        return

    text = f"✅ *Hourly Ingestion Complete*\n\nScanned: {scanned} articles\nSelected: {selected} articles."
    
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": text,
        "parse_mode": "Markdown"
    }

    try:
        requests.post(url, json=payload)
    except Exception as e:
        print(f"Error sending summary to Telegram: {e}")

def main():
    print("Starting Antigravity Ingestion Cycle...")
    db.init_db()
    articles = fetch_feeds()
    
    scanned_count = len(articles)
    selected_count = 0
    
    for article in articles:
        print(f"Processing: {article['title']}")
        draft = synthesize_content(article)
        
        if draft and draft.get('relevance_score', 0) >= 65:
            print(f"-> Selected: Score {draft['relevance_score']}")
            draft_id = db.insert_draft(draft)
            send_to_telegram(draft, draft_id)
            selected_count += 1
            # Sleep briefly to avoid rate limits
            time.sleep(2)
        else:
            print("-> Rejected or low relevance.")
            
    send_summary_to_telegram(scanned_count, selected_count)

if __name__ == "__main__":
    main()
