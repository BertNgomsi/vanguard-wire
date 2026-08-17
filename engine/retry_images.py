import os
import requests
from google import genai
from dotenv import load_dotenv
import re
import base64
import db
import time

load_dotenv()
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
UNSPLASH_ACCESS_KEY = os.getenv("UNSPLASH_ACCESS_KEY")

client = None
if GEMINI_API_KEY:
    client = genai.Client(api_key=GEMINI_API_KEY)

def get_unsplash_image(headline, category):
    """Uses Gemini to generate a search query, searches Unsplash, and picks image."""
    if not UNSPLASH_ACCESS_KEY or not client:
        return None, "", ""
    try:
        prompt = f"Extract the main subject or noun from this headline and category to search an image library. Return ONLY a 1-3 word search query.\nHeadline: {headline}\nCategory: {category}"
        query_response = client.models.generate_content(model='gemini-3.6-flash', contents=prompt)
        query = query_response.text.strip()
        print(f"Generated Unsplash Query: {query}")
        
        headers = {"Authorization": f"Client-ID {UNSPLASH_ACCESS_KEY}"}
        search_url = f"https://api.unsplash.com/search/photos?query={query}&per_page=10"
        search_res = requests.get(search_url, headers=headers)
        if search_res.status_code != 200:
            return None, "", ""
            
        results = search_res.json().get('results', [])
        if not results:
            return None, "", ""
            
        image_urls = [r['urls']['regular'] for r in results[:5]]
        vision_prompt = "You are an editorial assistant. Review these image URLs. Select the most comical, satirical, or entertaining image that relates to the subject. Return ONLY the integer index (0-4) of the winning image."
        vision_contents = [vision_prompt] + image_urls
        vision_response = client.models.generate_content(model='gemini-3.6-flash', contents=vision_contents)
        try:
            winner_idx = int(re.search(r'\d+', vision_response.text).group())
            if winner_idx < 0 or winner_idx >= len(results):
                winner_idx = 0
        except:
            winner_idx = 0
            
        winner = results[winner_idx]
        download_location = winner.get('links', {}).get('download_location')
        if download_location:
            requests.get(download_location, headers=headers)
            
        raw_url = winner['urls']['raw']
        hotlink_url = f"{raw_url}&w=1020&h=510&fit=crop"
        credit_name = winner['user']['name']
        credit_username = winner['user']['username']
        return hotlink_url, credit_name, credit_username
    except Exception as e:
        print(f"Error fetching Unsplash image: {e}")
        return None, "", ""

def update_github_file(headline, unsplash_img, image_credit_name, image_credit_username):
    slug = re.sub(r'[^a-z0-9]+', '-', headline.lower()).strip('-')
    filename = f"{slug}.md"
    repo_owner = "BertNgomsi"
    repo_name = "vanguard-wire"
    file_path = f"src/content/blog/{filename}"
    api_url = f"https://api.github.com/repos/{repo_owner}/{repo_name}/contents/{file_path}"
    
    headers = {
        "Authorization": f"Bearer {GITHUB_TOKEN}",
        "Accept": "application/vnd.github.v3+json"
    }
    
    # 1. Get the current file content to find its SHA and text
    res = requests.get(api_url, headers=headers)
    if res.status_code != 200:
        print(f"Failed to fetch {filename} from GitHub.")
        return False
        
    file_info = res.json()
    sha = file_info['sha']
    content = base64.b64decode(file_info['content']).decode('utf-8')
    
    # 2. Update the frontmatter with image info
    # Replace placeholder heroImage if exists
    content = re.sub(r'heroImage: .*?\n', '', content)
    
    unsplash_yaml = f'\nunsplashImage: "{unsplash_img}"\nimageCreditName: "{image_credit_name}"\nimageCreditUsername: "{image_credit_username}"\n---'
    new_content = content.replace('\n---', unsplash_yaml, 1)
    
    # 3. Push update
    encoded_content = base64.b64encode(new_content.encode('utf-8')).decode('utf-8')
    payload = {
        "message": f"Auto-update: Add Unsplash image for {headline}",
        "content": encoded_content,
        "sha": sha
    }
    
    update_res = requests.put(api_url, headers=headers, json=payload)
    if update_res.status_code in [200, 201]:
        print(f"Successfully updated image for {filename}")
        return True
    else:
        print(f"Failed to update {filename}. Status: {update_res.status_code}")
        return False

def retry_images():
    print("Starting background retry for missing images...")
    db.init_db()
    drafts = db.get_published_drafts_without_images()
    
    for draft in drafts:
        print(f"Retrying image for: {draft['headline']}")
        unsplash_img, credit_name, credit_username = get_unsplash_image(draft['headline'], draft['category'])
        
        if unsplash_img:
            success = update_github_file(draft['headline'], unsplash_img, credit_name, credit_username)
            if success:
                db.update_draft_image(draft['id'], unsplash_img, credit_name, credit_username)
        
        time.sleep(5) # Prevent rate limits
        
if __name__ == "__main__":
    retry_images()
