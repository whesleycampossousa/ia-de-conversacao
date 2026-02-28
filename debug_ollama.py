import ollama

model = "qwen3:8b"
print(f"Testing connectivity with {model}...")

try:
    response = ollama.chat(model=model, messages=[
        {'role': 'user', 'content': 'Hello, are you working? Respond with a single word.'}
    ])
    print("--- RESPONSE ---")
    print(f"Keys: {response.keys()}")
    content = response['message']['content']
    print(f"Content Length: {len(content)}")
    print("--- CONTENT ---")
    print(content)
except Exception as e:
    print(f"Error: {e}")
