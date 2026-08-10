"""
test_gemini_tools.py
====================
Test Gemini with Gmail tool binding and tool calling.

Run:
    python test_gemini_tools.py

Expected:
    Gemini should call search_gmail with an appropriate query.
    You will see the tool name and arguments it chose.
"""

from gemini_client import get_gemini_llm
from gmail_tools import search_gmail
from langchain_core.messages import HumanMessage, SystemMessage


print("Testing Gemini tool calling...")
print()

# Bind search tool to LLM
llm = get_gemini_llm()
llm_with_tools = llm.bind_tools([search_gmail])

messages = [
    SystemMessage(content=(
        "You are a Gmail assistant. "
        "Use the search_gmail tool to search Gmail. "
        "Use Gmail operators like from:, subject:, is:unread."
    )),
    HumanMessage(content="Find emails from Indeed"),
]

response = llm_with_tools.invoke(messages)

print(f"Has tool calls: {bool(response.tool_calls)}")
print()

if response.tool_calls:
    for call in response.tool_calls:
        print(f"Tool: {call['name']}")
        print(f"Arguments: {call['args']}")
        print()

    # Execute the first tool call
    first_call = response.tool_calls[0]
    if first_call["name"] == "search_gmail":
        print("Executing search_gmail...")
        result = search_gmail.invoke(first_call["args"])
        print()
        print("Result preview:")
        print(result[:800])
else:
    print("No tool calls made. Response:")
    print(response.content)
