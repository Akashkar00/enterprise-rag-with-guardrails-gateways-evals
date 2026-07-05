import os
import requests
from dotenv import load_dotenv

load_dotenv()
PORTKEY_API_KEY = os.getenv("PORTKEY_API_KEY")

url = "https://api.portkey.ai/v1/configs"
headers = {
    "x-portkey-api-key": PORTKEY_API_KEY,
    "Content-Type": "application/json"
}
data = {
    "workspace_id": "default", # Might not be needed
    "name": "Auto-generated Cache Config",
    "config": {
        "cache": {"mode": "semantic"}
    }
}

response = requests.post(url, headers=headers, json=data)
print("Status Code:", response.status_code)
print("Response:", response.text)
