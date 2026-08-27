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
from webhook import get_brave_image

# Load environment variables
dotenv_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env")
load_dotenv(dotenv_path)

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
    
    # 1. Fetch Standard RSS Feeds
    for feed in RSS_FEEDS:
        if feed.get("type") != "Apify":
            try:
                print(f"Fetching {feed['name']}...")
                parsed = feedparser.parse(feed["url"])
                for entry in parsed.entries[:5]: # Let's fetch 5 to give it more data for clustering
                    link = entry.link
                    if link and not db.is_url_processed(link):
                        db.mark_url_processed(link)
                        entries.append({
                            "title": entry.title,
                            "link": link,
                            "description": entry.get("description", ""),
                            "source": feed["name"]
                        })
            except Exception as e:
                print(f"Error fetching {feed['name']}: {e}")

    # 2. Batch Fetch Apify Feeds
    apify_feeds = [f for f in RSS_FEEDS if f.get("type") == "Apify"]
    if apify_feeds and APIFY_API_TOKEN:
        try:
            print(f"Batch fetching {len(apify_feeds)} Apify targets...")
            # Combine all handles into a single search query (e.g. from:user1 OR from:user2)
            handles = [f"from:{f['from']}" for f in apify_feeds if f.get('from')]
            search_query = " OR ".join(handles)
            
            apify_url = f"https://api.apify.com/v2/acts/kaitoeasyapi~twitter-x-data-tweet-scraper-pay-per-result-cheapest/run-sync-get-dataset-items?token={APIFY_API_TOKEN}"
            payload = {
                "searchTerms": [search_query],
                "maxItems": len(apify_feeds), # roughly 1 per user (reduced from 3 per user)
                "queryType": "Latest",
                "lang": "en"
            }
            res = requests.post(apify_url, json=payload, headers={'Content-Type': 'application/json'})
            res.raise_for_status()
            tweets = res.json()
            
            for tweet in tweets:
                link = tweet.get("url", "")
                
                # Match the tweet back to its original source name based on the handle in the URL
                matched_feed = None
                for f in apify_feeds:
                    if f.get('from') and f.get('from').lower() in link.lower():
                        matched_feed = f
                        break
                        
                source_name = matched_feed['name'] if matched_feed else "Twitter Scraper"
                
                if link and not db.is_url_processed(link):
                    db.mark_url_processed(link)
                    entries.append({
                        "title": f"Tweet by {source_name}",
                        "link": link,
                        "description": tweet.get("text", ""),
                        "source": source_name
                    })
        except Exception as e:
            print(f"Error in batch Apify fetch: {e}")
            print("Response text:", res.text if 'res' in locals() else "No response")
    elif apify_feeds and not APIFY_API_TOKEN:
        print("Skipping Apify: APIFY_API_TOKEN not set.")
        
    return entries

def synthesize_cluster(cluster):
    """Pass cluster of articles through Gemini Pro for synthesis."""
    if not client:
        print("Skipping AI synthesis: Gemini API key not found.")
        return None
        
    combined_sources = " & ".join(list(dict.fromkeys([a['source'] for a in cluster])))
    primary_url = cluster[0]['link']
    
    prompt = f"{SYSTEM_PROMPT}\n\nWe have a cluster of {len(cluster)} articles about the same story. Synthesize them into ONE unified post."
    if len(cluster) > 1:
        prompt += "\nIMPORTANT: Since there are multiple sources, extract a quote from EACH source and weave them together in narrative order in the `blockquote` field. Separate each quote with a double newline, and cite the source inline at the end of each quote, like this:\n\"First quote here.\" — Source 1\n\n\"Second quote here.\" — Source 2\nDo NOT use markdown blockquote symbols (>), just plain text."
    
    for i, a in enumerate(cluster):
        prompt += f"\n\nSource {i+1}: {a['source']}\nURL {i+1}: {a['link']}\nTitle: {a['title']}\nExcerpt: {a['description']}"
        
    try:
        response = client.models.generate_content(
            model='gemini-3.1-pro-preview', 
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=DraftResponse,
            )
        )
        data = json.loads(response.text)
        data['source_url'] = primary_url
        data['source_name'] = combined_sources
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

def cluster_articles(articles):
    if not articles:
        return []
    if len(articles) == 1:
        return [[articles[0]]]
        
    print(f"Clustering {len(articles)} new articles...")
    prompt = "You are an AI editor. Review the following news articles. Group them into clusters where the articles cover the exact same underlying event or story. Return a JSON array of arrays, where each inner array contains the integer indices of the articles in that cluster. If an article is unique, it should be in an array by itself."
    for i, a in enumerate(articles):
        prompt += f"\n\n[{i}] Source: {a['source']}\nTitle: {a['title']}\nDescription: {a['description']}"
        
    class ClusterResult(BaseModel):
        clusters: list[list[int]]
        
    try:
        response = client.models.generate_content(
            model='gemini-3.6-flash',
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=ClusterResult,
            )
        )
        data = json.loads(response.text)
        cluster_indices = data.get("clusters", [])
        
        clustered_articles = []
        for indices in cluster_indices:
            cluster = []
            for idx in indices:
                if 0 <= idx < len(articles):
                    cluster.append(articles[idx])
            if cluster:
                clustered_articles.append(cluster)
        return clustered_articles
    except Exception as e:
        print(f"Clustering failed: {e}. Falling back to individual processing.")
        return [[a] for a in articles]

def main():
    print("Starting Antigravity Ingestion Cycle...")
    db.init_db()
    new_articles = fetch_feeds()
    
    scanned_count = len(new_articles)
    selected_count = 0
    
    if not new_articles:
        print("No new articles found.")
        return
        
    clusters = cluster_articles(new_articles)
    
    for cluster in clusters:
        titles = " | ".join([a['title'] for a in cluster])
        print(f"Processing cluster of {len(cluster)} articles: {titles}")
        draft = synthesize_cluster(cluster)
        
        if draft and draft.get('relevance_score', 0) >= 65:
            print(f"-> Selected: Score {draft['relevance_score']}")
            
            # Fetch image and validate semantics
            unsplash_img, credit_name, credit_username = get_brave_image(draft['headline'], draft['category'])
            if unsplash_img and client:
                pass # Image validation removed to save quota and align with workflow
            
            draft_id = db.insert_draft(draft)
            
            # Save the pre-fetched image so webhook doesn't fetch it again
            if unsplash_img:
                db.update_draft_image(draft_id, unsplash_img, credit_name, credit_username)
                
            send_to_telegram(draft, draft_id)
            selected_count += 1
            # Sleep briefly to avoid rate limits
            time.sleep(2)
        else:
            print("-> Rejected or low relevance.")
            
    send_summary_to_telegram(scanned_count, selected_count)

if __name__ == "__main__":
    main()
