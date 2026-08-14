import os
import json
import re
from datetime import datetime, timedelta
import requests
from google import genai
from flask import Flask, request, jsonify
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
UNSPLASH_ACCESS_KEY = os.getenv("UNSPLASH_ACCESS_KEY")

client = None
if GEMINI_API_KEY:
    client = genai.Client(api_key=GEMINI_API_KEY)

import base64

def create_markdown_post(headline, framing, quote, source_name, source_url, category, pub_date=None, tip_cta="", unsplash_img=None, image_credit_name="", image_credit_username=""):
    """Generates an Astro-compatible Markdown file and pushes it to GitHub via API."""
    if not GITHUB_TOKEN:
        print("ERROR: GITHUB_TOKEN is missing. Cannot push to GitHub.")
        return None
        
    slug = re.sub(r'[^a-z0-9]+', '-', headline.lower()).strip('-')
    timestamp = pub_date if pub_date else datetime.now().isoformat()
    
    filename = f"{slug}.md"
    
    # Optional Unsplash data
    unsplash_yaml = ""
    if unsplash_img:
        unsplash_yaml = f'\nunsplashImage: "{unsplash_img}"\nimageCreditName: "{image_credit_name}"\nimageCreditUsername: "{image_credit_username}"'
    else:
        import random
        image_num = random.randint(1, 5)
        unsplash_yaml = f'\nheroImage: "../../assets/blog-placeholder-{image_num}.jpg"'
    
    # Astro Frontmatter
    md_content = f"""---
title: "{headline}"
pubDate: {timestamp}
category: "{category}"
source: "{source_name}"
sourceUrl: "{source_url}"
tipCta: "{tip_cta}"{unsplash_yaml}
---

{framing}

> {quote}
> 
> — [{source_name}]({source_url})
"""
    
    # Push to GitHub API
    repo_owner = "BertNgomsi"
    repo_name = "vanguard-wire"
    file_path = f"src/content/blog/{filename}"
    api_url = f"https://api.github.com/repos/{repo_owner}/{repo_name}/contents/{file_path}"
    
    headers = {
        "Authorization": f"Bearer {GITHUB_TOKEN}",
        "Accept": "application/vnd.github.v3+json"
    }
    
    encoded_content = base64.b64encode(md_content.encode('utf-8')).decode('utf-8')
    
    payload = {
        "message": f"Auto-publish approved article: {headline}",
        "content": encoded_content
    }
    
    response = requests.put(api_url, headers=headers, json=payload)
    
    if response.status_code in [200, 201]:
        print(f"Successfully pushed {filename} to GitHub!")
        return file_path
    else:
        print(f"Failed to push to GitHub. Status: {response.status_code}")
        print(response.json())
        return None

def get_next_queue_slot():
    """Calculates the next available publishing window."""
    state_file = 'queue_state.json'
    last_queued_str = None
    if os.path.exists(state_file):
        try:
            with open(state_file, 'r') as f:
                state = json.load(f)
                last_queued_str = state.get("last_queued_timestamp")
        except:
            pass
            
    now = datetime.now()
    
    if last_queued_str:
        try:
            last_queued = datetime.fromisoformat(last_queued_str)
        except ValueError:
            last_queued = now
    else:
        last_queued = now
        
    base_time = max(now, last_queued)
    
    # Define slots in HH:MM format
    slots = [(8, 30), (9, 30), (10, 30), (12, 0), (13, 30), (15, 0), (16, 30)]
    
    next_slot = None
    for hour, minute in slots:
        candidate = base_time.replace(hour=hour, minute=minute, second=0, microsecond=0)
        if candidate > base_time:
            next_slot = candidate
            break
            
    if not next_slot:
        next_day = base_time + timedelta(days=1)
        next_slot = next_day.replace(hour=slots[0][0], minute=slots[0][1], second=0, microsecond=0)

    # Skip weekends
    while next_slot.weekday() >= 5:
        next_slot += timedelta(days=1)
        next_slot = next_slot.replace(hour=slots[0][0], minute=slots[0][1], second=0, microsecond=0)

    # Avoid late Friday (after 2:00 PM) -> push to Monday
    if next_slot.weekday() == 4 and next_slot.hour >= 14:
        next_slot += timedelta(days=3)
        next_slot = next_slot.replace(hour=slots[0][0], minute=slots[0][1], second=0, microsecond=0)
        
    next_slot_iso = next_slot.isoformat()
    
    with open(state_file, 'w') as f:
        json.dump({"last_queued_timestamp": next_slot_iso}, f)
        
    return next_slot_iso
def get_unsplash_image(headline, category):
    """Uses Gemini to generate a search query, searches Unsplash, and uses Gemini to pick the best image."""
    if not UNSPLASH_ACCESS_KEY or not client:
        return None, "", ""
        
    try:
        # 1. Generate search query
        prompt = f"Extract the main subject or noun from this headline and category to search an image library. Return ONLY a 1-3 word search query.\nHeadline: {headline}\nCategory: {category}"
        query_response = client.models.generate_content(model='gemini-3.6-flash', contents=prompt)
        query = query_response.text.strip()
        print(f"Generated Unsplash Query: {query}")
        
        # 2. Search Unsplash
        headers = {"Authorization": f"Client-ID {UNSPLASH_ACCESS_KEY}"}
        search_url = f"https://api.unsplash.com/search/photos?query={query}&per_page=10"
        search_res = requests.get(search_url, headers=headers)
        
        if search_res.status_code != 200:
            print(f"Unsplash API Error: {search_res.status_code}")
            return None, "", ""
            
        results = search_res.json().get('results', [])
        if not results:
            print("No Unsplash results found.")
            return None, "", ""
            
        # 3. Use Gemini Vision to pick the best image
        image_urls = [r['urls']['regular'] for r in results[:5]]  # Send top 5 to Gemini
        vision_prompt = "You are an editorial assistant. Review these image URLs. Select the most comical, satirical, or entertaining image that relates to the subject. Return ONLY the integer index (0-4) of the winning image."
        vision_contents = [vision_prompt] + image_urls
        
        vision_response = client.models.generate_content(model='gemini-3.6-flash', contents=vision_contents)
        try:
            winner_idx = int(re.search(r'\d+', vision_response.text).group())
            if winner_idx < 0 or winner_idx >= len(results):
                winner_idx = 0
        except Exception:
            winner_idx = 0
            
        winner = results[winner_idx]
        print(f"Selected Unsplash Image ID: {winner['id']}")
        
        # 4. Trigger Unsplash Download Endpoint
        download_location = winner.get('links', {}).get('download_location')
        if download_location:
            requests.get(download_location, headers=headers)
            
        # 5. Extract Details for Hotlinking
        raw_url = winner['urls']['raw']
        hotlink_url = f"{raw_url}&w=1020&h=510&fit=crop"
        
        credit_name = winner['user']['name']
        credit_username = winner['user']['username']
        
        return hotlink_url, credit_name, credit_username
    except Exception as e:
        print(f"Error fetching Unsplash image: {e}")
        return None, "", ""

@app.route(f'/webhook/{TELEGRAM_BOT_TOKEN}', methods=['POST'])
def telegram_webhook():
    """Listens for inline keyboard button presses from Telegram."""
    update = request.json
    
    if 'callback_query' in update:
        query = update['callback_query']
        query_id = query.get('id')
        data = query.get('data', '')
        message = query.get('message', {})
        text = message.get('text', '')
        chat_id = message.get('chat', {}).get('id')
        message_id = message.get('message_id')
        
        # Format of callback data: "approve_queue", "approve_now", or "reject"
        if data in ('approve_queue', 'approve_now'):
            source_url = re.search(r'\nURL: (.*)$', text).group(1).strip()
            print(f"Approved article from: {source_url} (Action: {data})")
            
            # Very basic extraction from the Telegram message text
            # In a production app, you might store the draft JSON in a DB 
            # and look it up by an ID rather than parsing the Telegram text.
            try:
                category = re.search(r'Category: \[(.*?)\]', text).group(1)
                headline = re.search(r'Headline: (.*?)\n', text).group(1)
                framing = re.search(r'Framing: (.*?)\n\n', text, re.DOTALL).group(1)
                quote_raw = re.search(r'Quote: "(.*?)" — (.*?)\nTip CTA: (.*?)\nURL:', text, re.DOTALL)
                quote = quote_raw.group(1)
                source_name = quote_raw.group(2)
                tip_cta = quote_raw.group(3).strip() if len(quote_raw.groups()) > 2 else ""
                
                pub_date = None
                status_msg = "✅ [PUBLISHED NOW]"
                if data == 'approve_queue':
                    pub_date = get_next_queue_slot()
                    status_msg = f"✅ [QUEUED for {pub_date[:16].replace('T', ' ')}]"
                
                unsplash_img, credit_name, credit_username = get_unsplash_image(headline, category)
                
                create_markdown_post(headline, framing, quote, source_name, source_url, category, pub_date, tip_cta, unsplash_img, credit_name, credit_username)
                
                # Acknowledge the callback so the button stops loading
                if query_id:
                    requests.post(f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/answerCallbackQuery", json={"callback_query_id": query_id})
                
                if chat_id and message_id:
                    new_text = f"{status_msg}\n\n{text}"
                    requests.post(f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/editMessageText", json={
                        "chat_id": chat_id,
                        "message_id": message_id,
                        "text": new_text
                    })
                
                return jsonify({"ok": True})
            except Exception as e:
                print(f"Error parsing approved message: {e}")
                
        elif data == 'reject' or data.startswith('reject|'):
            print("Article rejected.")
            if query_id:
                requests.post(f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/answerCallbackQuery", json={"callback_query_id": query_id})
                
            if chat_id and message_id:
                new_text = f"❌ [REJECTED]\n\n{text}"
                requests.post(f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/editMessageText", json={
                    "chat_id": chat_id,
                    "message_id": message_id,
                    "text": new_text
                })
                
            return jsonify({"ok": True})
            
        elif data.startswith('edit_'):
            field = data.split('_')[1]
            if query_id:
                requests.post(f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/answerCallbackQuery", json={"callback_query_id": query_id})
                
            if chat_id and message_id:
                # Prompt the user for the new text
                prompt_text = f"✏️ Please reply to this message with the new {field}.\n\n[Action: edit_{field}]\n[Context ID: {message_id}]\n---\n{text}"
                requests.post(f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage", json={
                    "chat_id": chat_id,
                    "text": prompt_text,
                    "reply_markup": {"force_reply": True, "selective": True}
                })
            return jsonify({"ok": True})

    elif 'message' in update and 'reply_to_message' in update['message']:
        message = update['message']
        reply = message['reply_to_message']
        text = message.get('text', '')
        reply_text = reply.get('text', '')
        chat_id = message.get('chat', {}).get('id')
        
        # Check if this is a reply to an edit prompt
        if "[Action: edit_" in reply_text and "[Context ID:" in reply_text:
            try:
                field = re.search(r'\[Action: edit_(.*?)\]', reply_text).group(1)
                original_msg_id_match = re.search(r'\[Context ID: (\d+)\]', reply_text)
                if original_msg_id_match:
                    original_msg_id = int(original_msg_id_match.group(1))
                    
                    # Extract original draft text
                    original_draft = reply_text.split('---\n', 1)[1] if '---\n' in reply_text else ''
                    
                    # Perform replacement
                    new_draft = original_draft
                    if field == 'headline':
                        new_draft = re.sub(r'Headline: (.*?)\n', f'Headline: {text}\n', original_draft)
                    elif field == 'framing':
                        new_draft = re.sub(r'Framing: (.*?)\n\n', f'Framing: {text}\n\n', original_draft, flags=re.DOTALL)
                        
                    # Send updated text to Telegram
                    reply_markup = {
                        "inline_keyboard": [
                            [{"text": "🟢 Approve & Queue", "callback_data": "approve_queue"}, {"text": "🚨 Publish NOW", "callback_data": "approve_now"}],
                            [{"text": "🔴 Reject", "callback_data": "reject"}],
                            [{"text": "✏️ Edit Headline", "callback_data": "edit_headline"}, {"text": "✏️ Edit Framing", "callback_data": "edit_framing"}]
                        ]
                    }
                    requests.post(f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/editMessageText", json={
                        "chat_id": chat_id,
                        "message_id": original_msg_id,
                        "text": new_draft,
                        "reply_markup": reply_markup
                    })
                    
                    # Delete prompt and reply messages
                    requests.post(f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/deleteMessage", json={
                        "chat_id": chat_id,
                        "message_id": reply['message_id']
                    })
                    requests.post(f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/deleteMessage", json={
                        "chat_id": chat_id,
                        "message_id": message['message_id']
                    })
            except Exception as e:
                print(f"Error handling edit reply: {e}")

    return jsonify({"ok": True})

def moderate_comment(comment_text, comment_id, node_id):
    """Passes the comment to Gemini for safety evaluation."""
    if not client:
        return
        
    prompt = f"Evaluate the following comment for hate speech, severe toxicity, or slurs. Respond ONLY with a single JSON object containing 'score' (0.0 to 1.0, where 1.0 is highly toxic) and 'reason' (brief string).\n\nComment: {comment_text}"
    
    try:
        response = client.models.generate_content(model='gemini-3.6-flash', contents=prompt)
        text_resp = response.text
        if text_resp.startswith("```json"):
            text_resp = text_resp[7:-3]
        elif text_resp.startswith("```"):
            text_resp = text_resp[3:-3]
            
        data = json.loads(text_resp.strip())
        score = data.get('score', 0.0)
        
        if score > 0.75:
            print(f"Comment {comment_id} failed moderation (Score: {score}). Deleting...")
            delete_github_comment(node_id)
        elif score > 0.15:
            print(f"Comment {comment_id} flagged for review (Score: {score}). Sending to Telegram...")
            send_moderation_alert(comment_text, score, node_id)
            
    except Exception as e:
        print(f"Moderation error: {e}")

def delete_github_comment(node_id):
    """Deletes a discussion comment via GitHub GraphQL API."""
    if not GITHUB_TOKEN:
        return
        
    query = '''
    mutation($id: ID!) {
      deleteDiscussionComment(input: {id: $id}) {
        comment { id }
      }
    }
    '''
    headers = {"Authorization": f"Bearer {GITHUB_TOKEN}"}
    requests.post('https://api.github.com/graphql', json={'query': query, 'variables': {'id': node_id}}, headers=headers)

def send_moderation_alert(comment_text, score, node_id):
    """Sends a flagged comment to Telegram for manual review."""
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        return
        
    text = f"⚠️ FLAGGED COMMENT [Toxicity: {score}]\n\n\"{comment_text}\""
    reply_markup = {
        "inline_keyboard": [[
            {"text": "🔴 Delete & Ban", "callback_data": f"mod_delete|{node_id}"},
            {"text": "🟢 Approve", "callback_data": f"mod_approve|{node_id}"}
        ]]
    }
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": text, "reply_markup": json.dumps(reply_markup)}
    requests.post(url, json=payload)

@app.route('/webhook/github', methods=['POST'])
def github_webhook():
    """Listens for new comments via GitHub Discussions webhook."""
    event = request.headers.get('X-GitHub-Event')
    if event == 'discussion_comment':
        payload = request.json
        if payload.get('action') == 'created':
            comment = payload['comment']
            comment_text = comment['body']
            comment_id = comment['id']
            node_id = comment['node_id']
            
            # Run moderation asynchronously or inline
            moderate_comment(comment_text, comment_id, node_id)
            
    return jsonify({"ok": True})

if __name__ == '__main__':
    print("Starting Telegram Webhook Server on port 5001...")
    print("Use ngrok to expose this port to the internet and set your Telegram webhook URL.")
    app.run(port=5001)
