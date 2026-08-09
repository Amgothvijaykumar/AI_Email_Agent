import os

from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.prompts import ChatPromptTemplate


# Get Gemini API key from environment variable
api_key = os.getenv("GEMINI_API_KEY")

if not api_key:
    raise ValueError(
        "GEMINI_API_KEY not found. "
        "Set it using: export GEMINI_API_KEY='your-key'"
    )


# Create Gemini model
llm = ChatGoogleGenerativeAI(
    model="gemini-3.5-flash",
    google_api_key=api_key,
    temperature=0
)


# Prompt for email analysis
prompt = ChatPromptTemplate.from_template("""
You are an AI email assistant.

Analyze the following email.

Email sender:
{sender}

Email subject:
{subject}

Email body:
{body}

Perform these tasks:

1. Classify the email into ONE category:
   - Jobs
   - Finance
   - Security
   - Promotions
   - Education
   - Important
   - Other

2. Give a short summary in 1-2 sentences.

3. Decide the priority:
   - High
   - Medium
   - Low

Return the result exactly in this format:

Category: <category>

Summary: <summary>

Priority: <priority>
""")


def analyze_email(sender, subject, body):
    response = llm.invoke(
        prompt.format_messages(
            sender=sender,
            subject=subject,
            body=body
        )
    )

    return response.content[0]["text"]