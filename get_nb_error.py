import json

file_path = "notebooks/02_llm_gateway_copy2.ipynb"
with open(file_path, "r") as f:
    nb = json.load(f)

print("Checking cell outputs...")
for i, cell in enumerate(nb.get("cells", [])):
    if cell.get("cell_type") == "code":
        outputs = cell.get("outputs", [])
        for out in outputs:
            if out.get("output_type") == "error":
                print(f"Cell {i} Error:")
                print("".join(out.get("traceback", [])))
            elif out.get("name") == "stdout":
                text = "".join(out.get("text", []))
                if "ERROR" in text or "Exception" in text or "❌" in text:
                    print(f"Cell {i} stdout error:")
                    print(text[-500:])  # last 500 chars
