import os
from portkey_ai import Portkey
from dotenv import load_dotenv

load_dotenv()
PORTKEY_API_KEY = os.getenv("PORTKEY_API_KEY")

try:
    portkey = Portkey(api_key=PORTKEY_API_KEY, config="pc-enterp-edad02")
    r = portkey.chat.completions.create(
        messages=[{"role": "user", "content": "hello"}]
    )
    print("Success:", r)
except Exception as e:
    print("Error:", e)
