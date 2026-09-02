import os
import sys
import time
import re
import json
import base64
import requests
from datetime import datetime
from zoneinfo import ZoneInfo
from dotenv import load_dotenv

# Load environment
dotenv_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env")
load_dotenv(dotenv_path)

import db
from webhook import get_brave_image, create_markdown_post

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

def run_queue_worker():
    print(f"[{datetime.now().isoformat()}] Starting Queue Worker...")
    db.init_db()
    
    now = datetime.now(ZoneInfo("America/New_York"))
    now_iso = now.isoformat()
    
    due_drafts = db.get_due_queued_drafts(now_iso)
    print(f"Found {len(due_drafts)} queued drafts due for release.")
    
    if not due_drafts:
        return
        
    for draft in due_drafts:
        draft_id = draft['id']
        headline = draft['headline']
        category = draft['category']
        scheduled_slot = draft.get('scheduled_slot', '')
        print(f"\nProcessing Draft ID {draft_id}: {headline}")
        print(f"  Scheduled Slot: {scheduled_slot}")
        
        # 1. Fetch image if missing
        unsplash_img = draft.get('unsplash_img')
        credit_name = draft.get('image_credit_name')
        credit_username = draft.get('image_credit_username')
        
        if not unsplash_img:
            print("  Fetching Brave Image...")
            unsplash_img, credit_name, credit_username = get_brave_image(headline, category)
            if unsplash_img:
                db.update_draft_image(draft_id, unsplash_img, credit_name, credit_username)
                
        # 2. Update status to published
        db.update_draft_status(draft_id, 'published')
        
        # 3. Create Markdown Post with pubDate=now (current actual time of release)
        file_path = create_markdown_post(
            headline, draft['framing_lead'], draft['blockquote'], draft.get('kicker', ''),
            draft['source_name'], draft['source_url'], category,
            None, draft['tip_cta'], unsplash_img, credit_name, credit_username
        )
        
        # 4. Send Telegram live publication notification
        if file_path:
            slug = re.sub(r'[^a-z0-9]+', '-', headline.lower()).strip('-')
            live_url = f"https://thevanguardwire.com/blog/{slug}/"
            pub_notif = (
                f"🚀 <b>Article Published Live!</b>\n\n"
                f"📰 <b>{headline}</b>\n"
                f"📁 <i>{category}</i>\n\n"
                f"🔗 <a href=\"{live_url}\">Read on Vanguard Wire</a>"
            )
            requests.post(f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage", json={
                "chat_id": TELEGRAM_CHAT_ID,
                "text": pub_notif,
                "parse_mode": "HTML",
                "disable_web_page_preview": False
            })
            print(f"  ✅ Published & notified: {live_url}")
        else:
            print(f"  ❌ Failed to publish draft {draft_id} to GitHub.")
            
        # 5. Cooldown to prevent GitHub 409 collisions and Brave rate limits
        time.sleep(2.5)

if __name__ == "__main__":
    run_queue_worker()
