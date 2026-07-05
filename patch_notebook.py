import json

file_path = "notebooks/02_llm_gateway_copy2.ipynb"
with open(file_path, "r") as f:
    nb = json.load(f)

for cell in nb.get("cells", []):
    if cell.get("cell_type") == "code":
        source = cell.get("source", [])
        new_source = []
        skip = False
        for line in source:
            if 'load_balance_config = {' in line:
                skip = True
            if skip:
                if 'portkey_lb = Portkey' in line:
                    skip = False
                    new_source.append('# load_balance_config is now managed in Portkey Dashboard\n')
                    new_source.append('portkey_lb = Portkey(api_key=PORTKEY_API_KEY, config="pc-enterp-edad02")\n')
            else:
                new_source.append(line)
        cell["source"] = new_source

with open(file_path, "w") as f:
    json.dump(nb, f, indent=1)
    
print("Notebook patched successfully!")
