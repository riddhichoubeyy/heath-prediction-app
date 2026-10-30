
import os
import requests
from dotenv import load_dotenv

load_dotenv()

api_key = os.getenv("GEMINI_API_KEY", "").strip()
model = "gemini-3.1-flash-lite"

url = "https://generativelanguage.googleapis.com/v1beta/interactions"

payload = {
    "model": model,
    "input": "Reply with just: Gemini is working",
    "store": False
}

try:
    print("Testing model:", model)

    response = requests.post(
        url,
        headers={
            "x-goog-api-key": api_key,
            "Content-Type": "application/json"
        },
        json=payload,
        timeout=45
    )

    print("HTTP status:", response.status_code)
    print("Response:", response.text[:1000])

except requests.exceptions.Timeout:
    print("ERROR: Request timed out for", model)

except requests.exceptions.RequestException as error:
    print("CONNECTION ERROR:", type(error).__name__)
