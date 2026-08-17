import sys
import os
from retry_images import get_unsplash_image

print("Testing get_unsplash_image...")
headline = "Supreme Court strikes down new voting rights map in Alabama"
category = "Civil Rights, Voting & Legal Tracker"
img_url, name, username = get_unsplash_image(headline, category)
print(f"URL: {img_url}")
print(f"Name: {name}")
print(f"Username: {username}")
