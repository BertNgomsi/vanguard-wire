import os
import sys
import glob
import re
import time

sys.path.append(os.path.join(os.path.dirname(__file__), 'engine'))
from retry_images import get_brave_image

def replace_all():
    files = glob.glob('src/content/blog/*.md')
    print(f"Found {len(files)} articles to process.")
    for filepath in files:
        with open(filepath, 'r') as f:
            content = f.read()
        
        title_match = re.search(r'^title:\s+"?([^"\n]+)"?', content, re.MULTILINE)
        if not title_match:
            continue
        headline = title_match.group(1)
        
        category_match = re.search(r'^category:\s+"?([^"\n]+)"?', content, re.MULTILINE)
        category = category_match.group(1) if category_match else "News"
        
        print(f"Replacing image for: {headline}")
        hotlink_url, credit_name, _ = get_brave_image(headline, category)
        
        if hotlink_url:
            print(f" -> Success: {hotlink_url}")
            content = re.sub(r'^unsplashImage:.*?\n', f'unsplashImage: {hotlink_url}\n', content, flags=re.MULTILINE)
            content = re.sub(r'^imageCreditName:.*?\n', '', content, flags=re.MULTILINE)
            content = re.sub(r'^imageCreditUsername:.*?\n', '', content, flags=re.MULTILINE)
            content = re.sub(r'^unsplashImage: (.*?)\n', f'unsplashImage: \\1\nimageCreditName: "{credit_name}"\nimageCreditUsername: ""\n', content, flags=re.MULTILINE)
            
            with open(filepath, 'w') as f:
                f.write(content)
        else:
            print(f" -> Failed to find image.")
            
        time.sleep(2)

if __name__ == '__main__':
    replace_all()
