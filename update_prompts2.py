import os

def rewrite_file(filepath):
    with open(filepath, 'r') as f:
        content = f.read()

    # 1. Update the generation prompt
    old_prompt = """prompt = f"Extract the main subject, person, or event from this headline to search for a news photo. Return ONLY a 1-4 word search query (e.g., 'Jasmine Crockett' or 'Capitol Building').\\nHeadline: {headline}\\nCategory: {category}"""""
    new_prompt = """prompt = f"Extract the specific main subject or person from this headline to search for a news photo. Include their full name or specific context to avoid ambiguity (e.g. 'Venus Williams' instead of just 'Venus'). Return ONLY a 1-4 word search query.\\nHeadline: {headline}\\nCategory: {category}"""""
    content = content.replace(old_prompt, new_prompt)

    # 2. Update the vision prompt
    old_vision = """vision_prompt = "You are an editorial assistant. Review these image URLs. Select the most relevant, high-quality, or impactful image for a news story. Return ONLY the integer index (0-4) of the winning image." """
    new_vision = """vision_prompt = f"You are an editorial assistant. Review these 5 image URLs for a news article titled '{headline}'. Select the most relevant and high-quality image. If possible, pick one that is slightly comical, humorous, or highly impactful. Critically, ensure the image actually depicts the specific subject (e.g. do not select an image of the planet Venus if the article is about Venus Williams). Return ONLY the integer index (0-4) of the winning image." """
    content = content.replace('vision_prompt = "You are an editorial assistant. Review these image URLs. Select the most relevant, high-quality, or impactful image for a news story. Return ONLY the integer index (0-4) of the winning image."', new_vision)

    with open(filepath, 'w') as f:
        f.write(content)

rewrite_file('/Users/bngomsi/Documents/NewBiz/vanguard-wire/engine/webhook.py')
rewrite_file('/Users/bngomsi/Documents/NewBiz/vanguard-wire/engine/retry_images.py')
print("Prompts rewritten.")
