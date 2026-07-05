import os
import json
import requests
from dotenv import load_dotenv

load_dotenv()
PORTKEY_API_KEY = os.getenv("PORTKEY_API_KEY")
url = "https://api.portkey.ai/v1/configs"
headers = {
    "x-portkey-api-key": PORTKEY_API_KEY,
    "Content-Type": "application/json"
}

def create_config(name, config_dict):
    data = {"name": name, "config": config_dict}
    resp = requests.post(url, headers=headers, json=data)
    if resp.status_code == 200:
        slug = resp.json().get("slug")
        print(f"Created {name}: {slug}")
        return slug
    else:
        print(f"Failed to create {name}: {resp.text}")
        return None

retry_slug = create_config("Auto Retry Config", {
    "retry": {"attempts": 3, "on_status_codes": [429, 500, 502, 503, 504]}
})

timeout_slug = create_config("Auto Timeout Config", {
    "request_timeout": 10000
})

fallback_slug = create_config("Auto Fallback Config", {
    "strategy": {"mode": "fallback", "on_status_codes": [429, 503]},
    "targets": [
        {"override_params": {"model": "@rag/llama-3.3-70b-versatile"}},
        {"override_params": {"model": "@fallback-rag/llama-3.1-8b-instant"}}
    ]
})

cache_slug = create_config("Auto Cache Config", {
    "cache": {"mode": "semantic"}
})

if retry_slug and timeout_slug and fallback_slug and cache_slug:
    print("All configs created successfully! Patching notebook...")
    
    file_path = "notebooks/02_llm_gateway_copy2.ipynb"
    with open(file_path, "r") as f:
        nb = json.load(f)

    for cell in nb.get("cells", []):
        if cell.get("cell_type") == "code":
            source = "".join(cell.get("source", []))
            
            if "portkey_retry = Portkey(api_key=PORTKEY_API_KEY, config=retry_config)" in source:
                new_source = source.replace(
                    "portkey_retry = Portkey(api_key=PORTKEY_API_KEY, config=retry_config)",
                    f"portkey_retry = Portkey(api_key=PORTKEY_API_KEY, config='{retry_slug}')"
                )
                cell["source"] = [line + "\n" if not line.endswith("\n") else line for line in new_source.splitlines()]
                
            elif "portkey_timeout = Portkey(api_key=PORTKEY_API_KEY, config=timeout_config)" in source:
                new_source = source.replace(
                    "portkey_timeout = Portkey(api_key=PORTKEY_API_KEY, config=timeout_config)",
                    f"portkey_timeout = Portkey(api_key=PORTKEY_API_KEY, config='{timeout_slug}')"
                )
                cell["source"] = [line + "\n" if not line.endswith("\n") else line for line in new_source.splitlines()]
                
            elif "portkey_fallback = Portkey(api_key=PORTKEY_API_KEY, config=fallback_config)" in source:
                new_source = source.replace(
                    "portkey_fallback = Portkey(api_key=PORTKEY_API_KEY, config=fallback_config)",
                    f"portkey_fallback = Portkey(api_key=PORTKEY_API_KEY, config='{fallback_slug}')"
                )
                cell["source"] = [line + "\n" if not line.endswith("\n") else line for line in new_source.splitlines()]
                
            elif "portkey_cached = Portkey(api_key=PORTKEY_API_KEY, config=cache_config)" in source:
                new_source = source.replace(
                    "portkey_cached = Portkey(api_key=PORTKEY_API_KEY, config=cache_config)",
                    f"portkey_cached = Portkey(api_key=PORTKEY_API_KEY, config='{cache_slug}')"
                )
                cell["source"] = [line + "\n" if not line.endswith("\n") else line for line in new_source.splitlines()]

    with open(file_path, "w") as f:
        json.dump(nb, f, indent=1)
        
    print("Notebook patched successfully!")

