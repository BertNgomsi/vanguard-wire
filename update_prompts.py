import os
import re

brave_func = '''def get_brave_image(headline, category):
    """Uses Gemini to generate a search query, searches Brave Image Search, and picks image."""
    BRAVE_API_KEY = os.getenv("BRAVE_API_KEY")
    if not BRAVE_API_KEY or not client:
        return None, "", ""
    try:
        prompt = f"Extract the specific main subject or person from this headline to search for a news photo. Include their full name or specific context to avoid ambiguity (e.g. 'Venus Williams' instead of just 'Venus'). Return ONLY a 1-4 word search query.\\nHeadline: {headline}\\nCategory: {category}"
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
            winner_idx = int(re.search(r'\\d+', vision_response.text).group())
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
        return None, "", ""'''

def replace_func(filename):
    with open(filename, 'r') as f:
        content = f.read()
    
    # Just split by def get_brave_image and take the stuff before it, then split the rest by the end of the function
    parts = content.split('def get_brave_image(headline, category):')
    before = parts[0]
    
    # Find the end of the function. It ends at the first top-level def after it, or end of file
    after = ""
    if len(parts) > 1:
        rest = parts[1]
        next_def = rest.find('\\ndef ')
        if next_def != -1:
            after = rest[next_def:]
        else:
            # If no other def, it's end of file, but retry_images has no other defs! Wait, retry_images might have something at the end.
            # webhook.py has other defs. 
            pass
        if 'if __name__ ==' in rest:
            main_idx = rest.find('\\nif __name__ ==')
            if main_idx != -1 and (next_def == -1 or main_idx < next_def):
                after = rest[main_idx:]

    with open(filename, 'w') as f:
        f.write(before + brave_func + after)

replace_func('/Users/bngomsi/Documents/NewBiz/vanguard-wire/engine/webhook.py')
replace_func('/Users/bngomsi/Documents/NewBiz/vanguard-wire/engine/retry_images.py')
print("Updated API prompts")
