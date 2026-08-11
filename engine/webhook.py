import os
import json
import re
from datetime import datetime
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

client = None
if GEMINI_API_KEY:
    client = genai.Client(api_key=GEMINI_API_KEY)

# Astro content directory
ASTRO_CONTENT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'src', 'content', 'blog'))

def create_markdown_post(headline, framing, quote, source_name, source_url, category):
    """Generates an Astro-compatible Markdown file for the approved post."""
    if not os.path.exists(ASTRO_CONTENT_DIR):
        os.makedirs(ASTRO_CONTENT_DIR, exist_ok=True)
        
    slug = re.sub(r'[^a-z0-9]+', '-', headline.lower()).strip('-')
    timestamp = datetime.now().isoformat()
    
    filename = f"{slug}.md"
    filepath = os.path.join(ASTRO_CONTENT_DIR, filename)
    
    # Astro Frontmatter
    md_content = f"""---
title: "{headline}"
pubDate: {timestamp}
category: "{category}"
source: "{source_name}"
sourceUrl: "{source_url}"
---

{framing}

> {quote}
> 
> — [{source_name}]({source_url})
"""
    
    with open(filepath, 'w') as f:
        f.write(md_content)
    
    print(f"Created new post: {filepath}")
    return filepath

@app.route(f'/webhook/{TELEGRAM_BOT_TOKEN}', methods=['POST'])
def telegram_webhook():
    """Listens for inline keyboard button presses from Telegram."""
    update = request.json
    
    if 'callback_query' in update:
        query = update['callback_query']
        data = query.get('data', '')
        message = query.get('message', {})
        text = message.get('text', '')
        
        # Format of callback data: "approve|http://source.url" or "reject|http://..."
        if data.startswith('approve|'):
            source_url = data.split('|', 1)[1]
            print(f"Approved article from: {source_url}")
            
            # Very basic extraction from the Telegram message text
            # In a production app, you might store the draft JSON in a DB 
            # and look it up by an ID rather than parsing the Telegram text.
            try:
                category = re.search(r'Category: \[(.*?)\]', text).group(1)
                headline = re.search(r'Headline: (.*?)\n', text).group(1)
                framing = re.search(r'Framing: (.*?)\n\n', text, re.DOTALL).group(1)
                quote_raw = re.search(r'Quote: "(.*?)" — (.*)', text, re.DOTALL)
                quote = quote_raw.group(1)
                source_name = quote_raw.group(2)
                
                create_markdown_post(headline, framing, quote, source_name, source_url, category)
                
                # Acknowledge the callback so the button stops loading
                # Also we could edit the original message to remove the buttons
                return jsonify({"ok": True})
            except Exception as e:
                print(f"Error parsing approved message: {e}")
                
        elif data.startswith('reject|'):
            print("Article rejected.")
            return jsonify({"ok": True})

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
