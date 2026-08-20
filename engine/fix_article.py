import sys
import os
from retry_images import get_unsplash_image, update_github_file

headline = "THE AUDACITY: Cities Plan to Deter Homelessness With Heavier Policing and Empty Promises"
category = "Criminal Justice & Accountability Watchdog"
print(f"Fetching image for: {headline}")
unsplash_img, credit_name, credit_username = get_unsplash_image(headline, category)

if unsplash_img:
    print(f"Found image: {unsplash_img}")
    success = update_github_file(headline, unsplash_img, credit_name, credit_username)
    if success:
        print("Successfully updated GitHub!")
else:
    print("Failed to get image.")
