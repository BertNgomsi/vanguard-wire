import os
import requests
from google import genai
from dotenv import load_dotenv
import re
import base64
import db
import time

dotenv_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env")
load_dotenv(dotenv_path)
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
UNSPLASH_ACCESS_KEY = os.getenv("UNSPLASH_ACCESS_KEY")

client = None
if GEMINI_API_KEY:
    client = genai.Client(api_key=GEMINI_API_KEY)

def get_brave_image(headline, category):
    """Uses Brave Image Search to pick an image."""
    BRAVE_API_KEY = os.getenv("BRAVE_API_KEY")
    if not BRAVE_API_KEY:
        return None, "", ""
    try:
        search_query = f"{headline} site:wikimedia.org OR site:wikipedia.org OR site:flickr.com"
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
            
        hotlink_url = results[0].get('properties', {}).get('url', '')
        if not hotlink_url:
            return None, "", ""

        source = results[0].get('source', '')
        credit_name = source.title() if source else "Web"
        
        return hotlink_url, credit_name, ""
        
    except Exception as e:
        print(f"Error fetching Brave image: {e}")
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
    content = re.sub(r"unsplashImage: .*?\n", "", content)
    content = re.sub(r"imageCreditName: .*?\n", "", content)
    content = re.sub(r"imageCreditUsername: .*?\n", "", content)

    content = re.sub(r"unsplashImage: .*?\n", "", content)
    content = re.sub(r"imageCreditName: .*?\n", "", content)
    content = re.sub(r"imageCreditUsername: .*?\n", "", content)

    
    # Remove existing unsplashImage keys if any
    content = re.sub(r'unsplashImage: .*?\n', '', content)
    content = re.sub(r'imageCreditName: .*?\n', '', content)
    content = re.sub(r'imageCreditUsername: .*?\n', '', content)
    
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
        print(f"[{draft['id']}] Fetching missing image...")
        unsplash_img, credit_name, credit_username = get_brave_image(draft['headline'], draft['category'])
        
        if unsplash_img:
            success = update_github_file(draft['headline'], unsplash_img, credit_name, credit_username)
            if success:
                db.update_draft_image(draft['id'], unsplash_img, credit_name, credit_username)
        
        time.sleep(5) # Prevent rate limits
        
if __name__ == "__main__":
    retry_images()
