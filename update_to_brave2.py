import os

brave_func = '''def get_brave_image(headline, category):
    """Uses Gemini to generate a search query, searches Brave Image Search, and picks image."""
    BRAVE_API_KEY = os.getenv("BRAVE_API_KEY")
    if not BRAVE_API_KEY or not client:
        return None, "", ""
    try:
        prompt = f"Extract the main subject, person, or event from this headline to search for a news photo. Return ONLY a 1-4 word search query (e.g., 'Jasmine Crockett' or 'Capitol Building').\\nHeadline: {headline}\\nCategory: {category}"
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
        search_res = requests.get(search_url, headers=headers, params={"q": search_query, "safesearch": "moderate", "count": 10})
        
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

        vision_prompt = "You are an editorial assistant. Review these image URLs. Select the most relevant, high-quality, or impactful image for a news story. Return ONLY the integer index (0-4) of the winning image."
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
    
    # Just find the bounds manually
    start_idx = content.find('def get_google_image')
    end_idx = content.find('        return None, "", ""\n', start_idx)
    if start_idx != -1 and end_idx != -1:
        end_idx += len('        return None, "", ""\n')
        content = content[:start_idx] + brave_func + "\n" + content[end_idx:]
    
    # Replace calls
    content = content.replace('get_google_image(', 'get_brave_image(')
    
    with open(filename, 'w') as f:
        f.write(content)

replace_func('/Users/bngomsi/Documents/NewBiz/vanguard-wire/engine/webhook.py')
replace_func('/Users/bngomsi/Documents/NewBiz/vanguard-wire/engine/retry_images.py')
print("Done")
