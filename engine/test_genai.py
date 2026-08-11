import os
from google import genai
from dotenv import load_dotenv

load_dotenv()
client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))

try:
    response = client.models.generate_content(model='gemini-2.5-pro', contents="say hi")
    print("gemini-2.5-pro works:", response.text)
except Exception as e:
    print("gemini-2.5-pro failed:", e)
    
try:
    response = client.models.generate_content(model='gemini-3.1-pro', contents="say hi")
    print("gemini-3.1-pro works:", response.text)
except Exception as e:
    print("gemini-3.1-pro failed:", e)

