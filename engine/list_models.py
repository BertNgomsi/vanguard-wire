import os
import requests
from dotenv import load_dotenv

dotenv_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env")
load_dotenv(dotenv_path)
api_key = os.getenv("GEMINI_API_KEY")

url = f"https://generativelanguage.googleapis.com/v1beta/models?key={api_key}"
r = requests.get(url)
models = r.json().get('models', [])
for m in models:
    if 'generateContent' in m.get('supportedGenerationMethods', []):
        print(m['name'])
