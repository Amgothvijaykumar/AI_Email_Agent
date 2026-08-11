from gemini_client import invoke_with_fallback, extract_text
from langchain_core.messages import HumanMessage, SystemMessage

SYSTEM_PROMPT = """Analyze the provided email and output in this exact format:
Category: <Jobs | Finance | Security | Promotions | Education | Important | Other>
Summary: <1-2 sentence summary>
Priority: <High | Medium | Low>"""


def analyze_email(sender: str, subject: str, body: str) -> str:
    """Classify category, priority, and summarize an email."""
    content = f"From: {sender}\nSubject: {subject}\nBody:\n{body[:1500]}"
    messages = [
        SystemMessage(content=SYSTEM_PROMPT),
        HumanMessage(content=content)
    ]
    response = invoke_with_fallback(messages)
    return extract_text(response)