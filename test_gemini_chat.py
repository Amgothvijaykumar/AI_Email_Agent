"""
test_gemini_chat.py
===================
Test Gemini LLM connection (no tools, no Gmail).

Automatically falls back through model chain if quota is hit:
  gemini-2.0-flash → gemini-1.5-flash → gemini-2.0-flash-lite → gemini-1.5-flash-8b

Run:
    source avkve/bin/activate
    python test_gemini_chat.py

Expected:
    A short response from Gemini confirming it's working.
"""

from gemini_client import invoke_with_fallback, LLM_MODELS
from langchain_core.messages import HumanMessage, SystemMessage


print("Testing Gemini chat connection...")
print(f"Model fallback chain: {' → '.join(LLM_MODELS)}")
print()

messages = [
    SystemMessage(content="You are a helpful assistant. Be very brief."),
    HumanMessage(content="Say exactly: 'Gemini is ready for the Gmail agent.'"),
]

response = invoke_with_fallback(messages)

# Gemini may return content as a plain string OR a list of dicts
content = response.content
if isinstance(content, list):
    text = "".join(
        item.get("text", "") if isinstance(item, dict) else str(item)
        for item in content
    )
else:
    text = str(content)

print("✓ Gemini response:")
print(text)
print()
model_used = response.response_metadata.get("model_name", "unknown")
print(f"Model used: {model_used}")

