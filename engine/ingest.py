import os
import time
import json
import feedparser
import requests
from google import genai
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

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

SYSTEM_PROMPT = """
You are the senior political editor for a rapid-response Black progressive news wire and cultural watchdog. Your tone is irreverent, sarcastic, vigilant, combative, and cynical. Analyze the input article and perform the following actions:
1. RELEVANCE SCORE (0-100): Evaluate impact based on anti-Black political movements, civil rights battles, systemic hypocrisy, media bias, and Black culture. Reject if score < 65.
2. HEADLINE: Draft a high-impact, active-voice, combative headline (4-8 words).
3. FRAMING LEAD: Write a concise 30-50 word sarcastic or vigilant contextual paragraph explaining why this story matters to Black readers.
4. PRIMARY BLOCKQUOTE: Extract the most crucial 75-120 word verbatim quote from the source text.
5. CATEGORY: Assign 1 primary category from the following exactly:
  - "Anti-Black Racism & Extremism Watchdog"
  - "Civil Rights, Voting & Legal Tracker"
  - "Systemic Policy & Dogwhistle Watchdog"
  - "Anti-Black / Conservative Hypocrisy Tracker"
  - "Black Pop Culture & Sports Media Slant"
  - "The Watercooler / The Front Porch"
6. TIP CTA: Generate a custom, emotional 10-15 word call-to-action for a donation Tip Jar, based specifically on the article's topic. (e.g. "Help us keep exposing corporate greed. Chip in $5")
Output STRICT JSON exactly like this:
{
  "relevance_score": 85,
  "headline": "Example Headline",
  "framing_lead": "Example lead...",
  "blockquote": "Exact quote from text...",
  "category": "Civil Rights, Voting & Legal Tracker",
  "tip_cta": "Help us keep holding them accountable. Chip in $5."
}
"""

def fetch_feeds():
    """Fetch and parse RSS feeds."""
    entries = []
    for feed in RSS_FEEDS:
        try:
            print(f"Fetching {feed['name']}...")
            parsed = feedparser.parse(feed["url"])
            # Get latest 3 entries for testing
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
        response = client.models.generate_content(model='gemini-3.6-flash', contents=prompt)
        text_resp = response.text
        # Strip markdown code blocks if present
        if text_resp.startswith("```json"):
            text_resp = text_resp[7:-3]
        elif text_resp.startswith("```"):
            text_resp = text_resp[3:-3]
            
        data = json.loads(text_resp.strip())
        data['source_url'] = article['link']
        data['source_name'] = article['source']
        return data
    except Exception as e:
        print(f"Error calling Gemini: {e}")
        return None

def send_to_telegram(draft):
    """Send the formatted draft to Telegram for approval."""
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print("Skipping Telegram. Bot token or chat ID not set.")
        return

    text = f"🚨 DRAFT POST [Score: {draft.get('relevance_score', '?')}]\n"
    text += f"Category: [{draft.get('category', '?')}]\n"
    text += f"Headline: {draft.get('headline', '?')}\n\n"
    text += f"Framing: {draft.get('framing_lead', '?')}\n\n"
    text += f"Quote: \"{draft.get('blockquote', '?')}\" — {draft.get('source_name', '?')}\n"
    text += f"Tip CTA: {draft.get('tip_cta', '?')}\n"
    text += f"URL: {draft.get('source_url', '')}"

    # Inline keyboard for 1-click approval
    reply_markup = {
        "inline_keyboard": [
            [{"text": "🟢 Approve & Queue", "callback_data": "approve_queue"}, {"text": "🚨 Publish NOW", "callback_data": "approve_now"}],
            [{"text": "🔴 Reject", "callback_data": "reject"}],
            [{"text": "✏️ Edit Headline", "callback_data": "edit_headline"}, {"text": "✏️ Edit Framing", "callback_data": "edit_framing"}]
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
    articles = fetch_feeds()
    
    scanned_count = len(articles)
    selected_count = 0
    
    for article in articles:
        print(f"Processing: {article['title']}")
        draft = synthesize_content(article)
        
        if draft and draft.get('relevance_score', 0) >= 65:
            print(f"-> Selected: Score {draft['relevance_score']}")
            send_to_telegram(draft)
            selected_count += 1
            # Sleep briefly to avoid rate limits
            time.sleep(2)
        else:
            print("-> Rejected or low relevance.")
            
    send_summary_to_telegram(scanned_count, selected_count)

if __name__ == "__main__":
    main()
