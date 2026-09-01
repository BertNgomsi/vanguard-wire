import os
import json
import re
from datetime import datetime, timedelta
import requests
import threading
import time
from zoneinfo import ZoneInfo
from google import genai
from flask import Flask, request, jsonify
from dotenv import load_dotenv

import db
import base64

dotenv_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env")
load_dotenv(dotenv_path)

app = Flask(__name__)
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
UNSPLASH_ACCESS_KEY = os.getenv("UNSPLASH_ACCESS_KEY")

client = None
if GEMINI_API_KEY:
    client = genai.Client(api_key=GEMINI_API_KEY)

db.init_db()

def create_markdown_post(headline, framing, quote, kicker, source_name, source_url, category, pub_date=None, tip_cta="", unsplash_img=None, image_credit_name="", image_credit_username=""):
    """Generates an Astro-compatible Markdown file and pushes it to GitHub via API with retries."""
    if not GITHUB_TOKEN:
        print("ERROR: GITHUB_TOKEN is missing. Cannot push to GitHub.")
        return None
        
    slug = re.sub(r'[^a-z0-9]+', '-', headline.lower()).strip('-')
    timestamp = pub_date if pub_date else datetime.now(ZoneInfo("America/New_York")).isoformat()
    filename = f"{slug}.md"
    
    unsplash_yaml = ""
    if unsplash_img:
        if unsplash_img.startswith("../../assets/"):
            unsplash_yaml = f'\nheroImage: "{unsplash_img}"'
            if image_credit_name:
                unsplash_yaml += f'\nimageCreditName: "{image_credit_name}"'
        else:
            unsplash_yaml = f'\nunsplashImage: "{unsplash_img}"\nimageCreditName: "{image_credit_name}"\nimageCreditUsername: "{image_credit_username}"'
    else:
        import random
        image_num = random.randint(1, 5)
        unsplash_yaml = f'\nheroImage: "../../assets/blog-placeholder-{image_num}.jpg"'
    
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

{kicker}
"""
    
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
    
    # Retry mechanism
    max_retries = 3
    for attempt in range(max_retries):
        response = requests.put(api_url, headers=headers, json=payload)
        if response.status_code in [200, 201]:
            print(f"Successfully pushed {filename} to GitHub!")
            return file_path
        elif response.status_code == 409: # Conflict
            print(f"GitHub Conflict (409) on attempt {attempt+1}. Retrying...")
            time.sleep(3)
        else:
            print(f"Failed to push to GitHub. Status: {response.status_code}")
            print(response.json())
            # Let it retry on other non-200 status codes as well in case of 5xx
            time.sleep(3)
            
    # Notify telegram on final failure
    requests.post(f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage", json={
        "chat_id": TELEGRAM_CHAT_ID,
        "text": f"❌ Failed to publish to GitHub after retries: {headline}"
    })
    return None


def process_approval_bg(action, draft, chat_id, message_id, query_id, draft_id):
    pub_date = None
    status_msg = "✅ [PUBLISHED NOW]"
    if action == 'approve_queue':
        pub_date = get_next_queue_slot()
        status_msg = f"✅ [QUEUED for {pub_date[:16].replace('T', ' ')}]"
    
    unsplash_img = draft.get('unsplash_img')
    credit_name = draft.get('image_credit_name')
    credit_username = draft.get('image_credit_username')
    
    if not unsplash_img:
        unsplash_img, credit_name, credit_username = get_brave_image(draft['headline'], draft['category'])
        if unsplash_img:
            db.update_draft_image(draft_id, unsplash_img, credit_name, credit_username)
    
    db.update_draft_status(draft_id, 'published')
    
    file_path = create_markdown_post(
        draft['headline'], draft['framing_lead'], draft['blockquote'], draft.get('kicker', ''),
        draft['source_name'], draft['source_url'], draft['category'],
        pub_date, draft['tip_cta'], unsplash_img, credit_name, credit_username
    )
    
    if chat_id and message_id:
        new_text = f"{status_msg}\n\n"
        new_text += f"Category: [{draft['category']}]\n"
        new_text += f"Headline: {draft['headline']}\n\n"
        new_text += f"Framing: {draft['framing_lead']}\n\n"
        new_text += f"Quote: \"{draft['blockquote']}\" — {draft['source_name']}\n"
        if draft.get('kicker'):
            new_text += f"Kicker: {draft['kicker']}\n"
        new_text += f"URL: {draft['source_url']}"
        requests.post(f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/editMessageText", json={
            "chat_id": chat_id, "message_id": message_id, "text": new_text
        })

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
            
    now = datetime.now(ZoneInfo("America/New_York"))
    if last_queued_str:
        try:
            last_queued = datetime.fromisoformat(last_queued_str)
            if last_queued.tzinfo is None:
                last_queued = last_queued.replace(tzinfo=ZoneInfo("America/New_York"))
        except ValueError:
            last_queued = now
    else:
        last_queued = now
        
    base_time = max(now, last_queued)
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

    while next_slot.weekday() >= 5:
        next_slot += timedelta(days=1)
        next_slot = next_slot.replace(hour=slots[0][0], minute=slots[0][1], second=0, microsecond=0)

    if next_slot.weekday() == 4 and next_slot.hour >= 14:
        next_slot += timedelta(days=3)
        next_slot = next_slot.replace(hour=slots[0][0], minute=slots[0][1], second=0, microsecond=0)
        
    next_slot_iso = next_slot.isoformat()
    with open(state_file, 'w') as f:
        json.dump({"last_queued_timestamp": next_slot_iso}, f)
        
    return next_slot_iso

def get_brave_image(headline, category):
    """Uses Gemini to generate a search query, searches Brave Image Search, and picks image."""
    BRAVE_API_KEY = os.getenv("BRAVE_API_KEY")
    if not BRAVE_API_KEY or not client:
        return None, "", ""
    try:
        prompt = f"Extract the specific main subject or person from this headline to search for a news photo. Include their full name or specific context to avoid ambiguity (e.g. 'Venus Williams' instead of just 'Venus'). Return ONLY a 1-4 word search query.\nHeadline: {headline}\nCategory: {category}"
        query_response = client.models.generate_content(model='gemini-3.6-flash', contents=prompt)
        query = query_response.text.strip()
        
        search_query = f"{query} site:wikimedia.org OR site:wikipedia.org OR site:flickr.com"
        print(f"Generated Brave Search Query: {search_query}")
        
        search_url = "https://api.search.brave.com/res/v1/images/search"
        headers = {
            "Accept": "application/json",
            "Accept-Encoding": "gzip",
            "X-Subscription-Token": BRAVE_API_KEY
        }
        search_res = requests.get(search_url, headers=headers, params={"q": search_query, "safesearch": "strict", "count": 10})
        
        if search_res.status_code != 200:
            print("Brave API failed:", search_res.text)
            return None, "", ""
            
        results = search_res.json().get('results', [])
        if not results:
            print("No Brave results")
            return None, "", ""
            
        image_urls = [r.get('properties', {}).get('url', '') for r in results[:5] if r.get('properties', {}).get('url')]
        if not image_urls:
            return None, "", ""

        vision_prompt = f"You are an editorial assistant. Review these 5 image URLs for a news article titled '{headline}'. Select the most relevant and high-quality image. If possible, pick one that is slightly comical, humorous, or highly impactful. Critically, ensure the image actually depicts the specific subject (e.g. do not select an image of the planet Venus if the article is about Venus Williams). Return ONLY the integer index (0-4) of the winning image." 
        vision_contents = [vision_prompt] + image_urls
        vision_response = client.models.generate_content(model='gemini-3.6-flash', contents=vision_contents)
        try:
            import re
            winner_idx = int(re.search(r'\d+', vision_response.text).group())
            if winner_idx < 0 or winner_idx >= len(image_urls):
                winner_idx = 0
        except:
            winner_idx = 0
            
        hotlink_url = image_urls[winner_idx]
        credit_name = "Web"
        for r in results:
            if r.get('properties', {}).get('url') == hotlink_url:
                source = r.get('source', '')
                credit_name = source.title() if source else "Web"
                break
        
        return hotlink_url, credit_name, ""
        
    except Exception as e:
        print(f"Error fetching Brave image: {e}")
        return None, "", ""


def handle_photo_replacement(message, headline, chat_id):
    try:
        photo = message['photo'][-1]
        file_id = photo['file_id']
        file_info_url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/getFile?file_id={file_id}"
        file_info = requests.get(file_info_url).json()
        if not file_info.get('ok'):
            return False
            
        file_path = file_info['result']['file_path']
        img_url = f"https://api.telegram.org/file/bot{TELEGRAM_BOT_TOKEN}/{file_path}"
        img_data = requests.get(img_url).content
        
        slug = re.sub(r'[^a-z0-9]+', '-', headline.lower()).strip('-')
        
        repo_owner = "BertNgomsi"
        repo_name = "vanguard-wire"
        asset_path = f"src/assets/{slug}.jpg"
        api_url_asset = f"https://api.github.com/repos/{repo_owner}/{repo_name}/contents/{asset_path}"
        headers = {"Authorization": f"Bearer {GITHUB_TOKEN}", "Accept": "application/vnd.github.v3+json"}
        
        encoded_image = base64.b64encode(img_data).decode('utf-8')
        
        res = requests.get(api_url_asset, headers=headers)
        payload_asset = {
            "message": f"Upload replaced image for {slug}",
            "content": encoded_image
        }
        if res.status_code == 200:
            payload_asset["sha"] = res.json()["sha"]
            
        res_asset = requests.put(api_url_asset, headers=headers, json=payload_asset)
        if res_asset.status_code not in [200, 201]:
            requests.post(f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage", json={
                "chat_id": chat_id, "text": f"❌ Failed to upload image to GitHub for {headline}"
            })
            return False
            
        local_img_path = f"../../assets/{slug}.jpg"
        
        conn = db.get_connection()
        c = conn.cursor()
        c.execute('SELECT id, status FROM drafts WHERE headline = ? ORDER BY id DESC LIMIT 1', (headline,))
        row = c.fetchone()
        if row:
            draft_id = row['id']
            db.update_draft_image(draft_id, local_img_path, "Uploaded via Telegram", "")
        conn.close()
            
        md_file_path = f"src/content/blog/{slug}.md"
        api_url_md = f"https://api.github.com/repos/{repo_owner}/{repo_name}/contents/{md_file_path}"
        res_md = requests.get(api_url_md, headers=headers)
        if res_md.status_code == 200:
            file_data = res_md.json()
            sha = file_data['sha']
            md_content = base64.b64decode(file_data['content']).decode('utf-8')
            
            md_content = re.sub(r'\nunsplashImage: ".*?"', '', md_content)
            md_content = re.sub(r'\nimageCreditName: ".*?"', '', md_content)
            md_content = re.sub(r'\nimageCreditUsername: ".*?"', '', md_content)
            
            if 'heroImage:' in md_content:
                md_content = re.sub(r'heroImage: ".*?"', f'heroImage: "{local_img_path}"\nimageCreditName: "Uploaded via Telegram"', md_content)
            else:
                md_content = md_content.replace('\n---\n', f'\nheroImage: "{local_img_path}"\nimageCreditName: "Uploaded via Telegram"\n---\n', 1)
                
            new_encoded = base64.b64encode(md_content.encode('utf-8')).decode('utf-8')
            put_res = requests.put(api_url_md, headers=headers, json={
                "message": f"Update image for {slug}",
                "content": new_encoded,
                "sha": sha
            })
            if put_res.status_code in [200, 201]:
                requests.post(f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage", json={
                    "chat_id": chat_id, "text": f"✅ Image successfully replaced for published post:\n{headline}"
                })
                return True
                
        requests.post(f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage", json={
            "chat_id": chat_id, "text": f"✅ Image uploaded and attached to Draft:\n{headline}"
        })
        return True
    except Exception as e:
        print(f"Error handling photo replacement: {e}")
        return False

@app.route(f'/webhook/{TELEGRAM_BOT_TOKEN}', methods=['POST'])

def telegram_webhook():
    update = request.json
    
    if 'callback_query' in update:
        query = update['callback_query']
        query_id = query.get('id')
        data = query.get('data', '')
        message = query.get('message', {})
        chat_id = message.get('chat', {}).get('id')
        message_id = message.get('message_id')
        
        try:
            parts = data.split('|')
            action = parts[0]
            draft_id = int(parts[1]) if len(parts) > 1 else None
            
            if action in ('approve_queue', 'approve_now') and draft_id:
                if query_id:
                    requests.post(f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/answerCallbackQuery", json={"callback_query_id": query_id, "text": "Processing... ⚙️"})
                    
                draft = db.get_draft(draft_id)
                if not draft:
                    requests.post(f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage", json={"chat_id": chat_id, "text": "❌ Error: Draft not found in DB."})
                    return jsonify({"ok": True})
                    
                if chat_id and message_id:
                    new_text = f"⏳ Processing and fetching image...\n\n"
                    new_text += f"Category: [{draft['category']}]\n"
                    new_text += f"Headline: {draft['headline']}\n"
                    requests.post(f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/editMessageText", json={
                        "chat_id": chat_id, "message_id": message_id, "text": new_text
                    })
                
                threading.Thread(target=process_approval_bg, args=(action, draft, chat_id, message_id, query_id, draft_id)).start()
                
            elif action == 'reject' and draft_id:
                db.update_draft_status(draft_id, 'rejected')
                if query_id:
                    requests.post(f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/answerCallbackQuery", json={"callback_query_id": query_id})
                if chat_id and message_id:
                    requests.post(f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/editMessageText", json={
                        "chat_id": chat_id, "message_id": message_id, "text": f"❌ [REJECTED]\n\nDraft ID: {draft_id}"
                    })
                    
            elif action.startswith('edit_') and draft_id:
                field = action.split('_')[1]
                if query_id:
                    requests.post(f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/answerCallbackQuery", json={"callback_query_id": query_id})
                if chat_id and message_id:
                    draft = db.get_draft(draft_id)
                    current_val = draft.get('headline') if field == 'headline' else draft.get('framing_lead')
                    prompt_text = f"✏️ Reply with the new {field}.\n\n[Action: edit_{field}]\n[Draft ID: {draft_id}]\n[Message ID: {message_id}]\n---\nCurrent: {current_val}"
                    requests.post(f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage", json={
                        "chat_id": chat_id, "text": prompt_text, "reply_markup": {"force_reply": True, "selective": True}
                    })
        except Exception as e:
            print(f"Error handling callback: {e}")
            
    elif 'message' in update:
        message = update['message']
        chat_id = message.get('chat', {}).get('id')
        text = message.get('text', '')
        

        # Handle Photos (Reply or Caption)
        if 'photo' in message:
            headline = ""
            if 'reply_to_message' in message:
                reply_text = message['reply_to_message'].get('text', '')
                headline_match = re.search(r'Headline: (.*?)\n', reply_text)
                if headline_match:
                    headline = headline_match.group(1).strip()
            
            if not headline and message.get('caption'):
                caption = message['caption']
                headline_match = re.search(r'Headline: (.*?)(?:\n|$)', caption)
                if headline_match:
                    headline = headline_match.group(1).strip()
                else:
                    headline = caption.strip()
                    
            if headline:
                requests.post(f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage", json={
                    "chat_id": chat_id, "text": f"🔄 Processing image replacement for:\n{headline}"
                })
                handle_photo_replacement(message, headline, chat_id)
                return jsonify({"ok": True})

        # Handle Forwarded messages for Historical Draft Recovery

        if 'forward_date' in message:
            try:
                clean_text = re.sub(r'^[✅❌].*?\n\n', '', text, flags=re.DOTALL).strip()
                clean_text = re.sub(r'^🚨.*?\]\n', '', clean_text).strip()
                category = re.search(r'Category: \[(.*?)\]', clean_text).group(1)
                headline = re.search(r'Headline: (.*?)\n', clean_text).group(1)
                framing = re.search(r'Framing: (.*?)\n\n', clean_text, re.DOTALL).group(1)
                
                quote_match = re.search(r'Quote: "(.*?)" — (.*?)\n', clean_text)
                quote = quote_match.group(1) if quote_match else ""
                source_name = quote_match.group(2) if quote_match else ""
                
                kicker_match = re.search(r'Kicker: (.*?)\n', clean_text)
                kicker = kicker_match.group(1) if kicker_match else ""
                
                tip_cta_match = re.search(r'Tip CTA: (.*?)\n', clean_text)
                tip_cta = tip_cta_match.group(1) if tip_cta_match else ""
                
                source_url = re.search(r'\nURL: (.*)$', clean_text).group(1).strip()
                
                draft = {
                    "category": category,
                    "headline": headline,
                    "framing_lead": framing,
                    "blockquote": quote,
                    "kicker": kicker,
                    "source_name": source_name,
                    "source_url": source_url,
                    "tip_cta": tip_cta,
                    "relevance_score": 99
                }
                
                draft_id = db.insert_draft(draft)
                
                new_text = f"🚨 RECOVERED DRAFT [Score: 99]\n"
                new_text += f"Category: [{category}]\n"
                new_text += f"Headline: {headline}\n\n"
                new_text += f"Framing: {framing}\n\n"
                new_text += f"Quote: \"{quote}\" — {source_name}\n"
                if kicker:
                    new_text += f"Kicker: {kicker}\n"
                if tip_cta:
                    new_text += f"Tip CTA: {tip_cta}\n"
                new_text += f"URL: {source_url}"
                
                reply_markup = {
                    "inline_keyboard": [
                        [{"text": "🟢 Approve & Queue", "callback_data": f"approve_queue|{draft_id}"}, {"text": "🚨 Publish NOW", "callback_data": f"approve_now|{draft_id}"}],
                        [{"text": "🔴 Reject", "callback_data": f"reject|{draft_id}"}],
                        [{"text": "✏️ Edit Headline", "callback_data": f"edit_headline|{draft_id}"}, {"text": "✏️ Edit Framing", "callback_data": f"edit_framing|{draft_id}"}]
                    ]
                }
                requests.post(f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage", json={
                    "chat_id": chat_id, "text": new_text, "reply_markup": json.dumps(reply_markup)
                })
            except Exception as e:
                print(f"Error parsing forwarded message: {e}")
                
        # Handle Edit Replies
        elif 'reply_to_message' in message:
            reply_text = message['reply_to_message'].get('text', '')
            if "[Action: edit_" in reply_text and "[Draft ID:" in reply_text:
                try:
                    field = re.search(r'\[Action: edit_(.*?)\]', reply_text).group(1)
                    draft_id = int(re.search(r'\[Draft ID: (\d+)\]', reply_text).group(1))
                    orig_msg_id = int(re.search(r'\[Message ID: (\d+)\]', reply_text).group(1))
                    
                    actual_field = 'headline' if field == 'headline' else 'framing_lead'
                    db.update_draft_field(draft_id, actual_field, text)
                    draft = db.get_draft(draft_id)
                    
                    new_draft_text = f"🚨 DRAFT POST [Score: {draft.get('relevance_score', '?')}]\n"
                    new_draft_text += f"Category: [{draft['category']}]\n"
                    new_draft_text += f"Headline: {draft['headline']}\n\n"
                    new_draft_text += f"Framing: {draft['framing_lead']}\n\n"
                    new_draft_text += f"Quote: \"{draft['blockquote']}\" — {draft['source_name']}\n"
                    if draft.get('kicker'):
                        new_draft_text += f"Kicker: {draft['kicker']}\n"
                    if draft.get('tip_cta'):
                        new_draft_text += f"Tip CTA: {draft['tip_cta']}\n"
                    new_draft_text += f"URL: {draft['source_url']}"
                    
                    reply_markup = {
                        "inline_keyboard": [
                            [{"text": "🟢 Approve & Queue", "callback_data": f"approve_queue|{draft_id}"}, {"text": "🚨 Publish NOW", "callback_data": f"approve_now|{draft_id}"}],
                            [{"text": "🔴 Reject", "callback_data": f"reject|{draft_id}"}],
                            [{"text": "✏️ Edit Headline", "callback_data": f"edit_headline|{draft_id}"}, {"text": "✏️ Edit Framing", "callback_data": f"edit_framing|{draft_id}"}]
                        ]
                    }
                    requests.post(f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/editMessageText", json={
                        "chat_id": chat_id, "message_id": orig_msg_id, "text": new_draft_text, "reply_markup": reply_markup
                    })
                    requests.post(f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/deleteMessage", json={
                        "chat_id": chat_id, "message_id": message['reply_to_message']['message_id']
                    })
                    requests.post(f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/deleteMessage", json={
                        "chat_id": chat_id, "message_id": message['message_id']
                    })
                except Exception as e:
                    print(f"Error handling edit reply: {e}")

    return jsonify({"ok": True})

def moderate_comment(comment_text, comment_id, node_id):
    if not client: return
    prompt = f"Evaluate the following comment for hate speech, severe toxicity, or slurs. Respond ONLY with a single JSON object containing 'score' (0.0 to 1.0, where 1.0 is highly toxic) and 'reason' (brief string).\n\nComment: {comment_text}"
    try:
        response = client.models.generate_content(model='gemini-3.6-flash', contents=prompt)
        text_resp = response.text
        if text_resp.startswith("```json"): text_resp = text_resp[7:-3]
        elif text_resp.startswith("```"): text_resp = text_resp[3:-3]
        data = json.loads(text_resp.strip())
        score = data.get('score', 0.0)
        
        if score > 0.75:
            delete_github_comment(node_id)
        elif score > 0.15:
            send_moderation_alert(comment_text, score, node_id)
    except Exception as e:
        pass

def delete_github_comment(node_id):
    if not GITHUB_TOKEN: return
    query = '''mutation($id: ID!) { deleteDiscussionComment(input: {id: $id}) { comment { id } } }'''
    headers = {"Authorization": f"Bearer {GITHUB_TOKEN}"}
    requests.post('https://api.github.com/graphql', json={'query': query, 'variables': {'id': node_id}}, headers=headers)

def send_moderation_alert(comment_text, score, node_id):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID: return
    text = f"⚠️ FLAGGED COMMENT [Toxicity: {score}]\n\n\"{comment_text}\""
    reply_markup = {"inline_keyboard": [[{"text": "🔴 Delete & Ban", "callback_data": f"mod_delete|{node_id}"}, {"text": "🟢 Approve", "callback_data": f"mod_approve|{node_id}"}]]}
    requests.post(f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage", json={"chat_id": TELEGRAM_CHAT_ID, "text": text, "reply_markup": json.dumps(reply_markup)})

@app.route('/webhook/github', methods=['POST'])
def github_webhook():
    event = request.headers.get('X-GitHub-Event')
    if event == 'discussion_comment':
        payload = request.json
        if payload.get('action') == 'created':
            comment = payload['comment']
            moderate_comment(comment['body'], comment['id'], comment['node_id'])
    return jsonify({"ok": True})

if __name__ == '__main__':
    print("Starting Telegram Webhook Server on port 5001...")
    app.run(port=5001)
