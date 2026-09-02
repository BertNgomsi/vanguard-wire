import os
import sys
import re
import json
import base64
import time
import requests
from dotenv import load_dotenv

dotenv_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env")
load_dotenv(dotenv_path)

from webhook import get_brave_image

GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")

def backfill_all_placeholders():
    print("Starting backfill of placeholder images...")
    headers = {
        "Authorization": f"Bearer {GITHUB_TOKEN}",
        "Accept": "application/vnd.github.v3+json",
        "User-Agent": "Mozilla/5.0"
    }
    
    # 1. List all markdown files in src/content/blog
    url = "https://api.github.com/repos/BertNgomsi/vanguard-wire/contents/src/content/blog"
    res = requests.get(url, headers=headers)
    if res.status_code != 200:
        print(f"Failed to list repo files: {res.status_code}")
        return
        
    files = res.json()
    count_updated = 0
    
    for f in files:
        if not f['name'].endswith('.md'):
            continue
        if f['name'] in ['first-post.md', 'second-post.md', 'third-post.md', 'markdown-style-guide.md', 'test-publish-now.md']:
            continue # Skip demo / doc posts
            
        # Get content
        f_res = requests.get(f['url'], headers=headers)
        if f_res.status_code != 200:
            continue
            
        file_data = f_res.json()
        sha = file_data['sha']
        raw = base64.b64decode(file_data['content']).decode('utf-8', errors='ignore')
        
        # Check if it has a placeholder image or lacks an unsplashImage
        has_placeholder = 'blog-placeholder' in raw
        has_custom_image = 'unsplashImage:' in raw and ('upload.wikimedia.org' in raw or 'images.unsplash.com' in raw or 'http' in raw.split('unsplashImage:')[1].split('\n')[0])
        
        if has_placeholder or not has_custom_image:
            title_m = re.search(r'title:\s*\"(.*)\"', raw)
            category_m = re.search(r'category:\s*\"(.*)\"', raw)
            
            title = title_m.group(1).strip() if title_m else f['name']
            category = category_m.group(1).strip() if category_m else 'News'
            
            print(f"\n[Backfilling] {f['name']}: {title}")
            img_url, credit_name, credit_user = get_brave_image(title, category)
            
            if img_url and img_url.startswith('http'):
                # Replace frontmatter
                new_raw = re.sub(r'heroImage: .*?\n', '', raw)
                new_raw = re.sub(r'unsplashImage: .*?\n', '', new_raw)
                new_raw = re.sub(r'imageCreditName: .*?\n', '', new_raw)
                new_raw = re.sub(r'imageCreditUsername: .*?\n', '', new_raw)
                
                image_yaml = f'\nunsplashImage: "{img_url}"\nimageCreditName: "{credit_name}"\nimageCreditUsername: "{credit_user}"\n---'
                new_raw = new_raw.replace('\n---', image_yaml, 1)
                
                encoded = base64.b64encode(new_raw.encode('utf-8')).decode('utf-8')
                payload = {
                    "message": f"Auto-backfill: Add real image for {title}",
                    "content": encoded,
                    "sha": sha
                }
                
                put_res = requests.put(f['url'], headers=headers, json=payload)
                if put_res.status_code in [200, 201]:
                    print(f"  ✅ Successfully updated {f['name']}")
                    count_updated += 1
                else:
                    print(f"  ❌ Failed to update {f['name']}: {put_res.status_code}")
            else:
                print(f"  ⚠️ No valid image found from Brave.")
                
            time.sleep(3) # Prevent rate limits
            
    print(f"\nFinished image backfill. Total updated: {count_updated}")

if __name__ == "__main__":
    backfill_all_placeholders()
