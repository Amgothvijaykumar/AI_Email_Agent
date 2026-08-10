import os

from dotenv import load_dotenv
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.prompts import ChatPromptTemplate

# Load .env if present
load_dotenv()

# Get Gemini API key (support both GEMINI_API_KEY and GEMINI_API_KEY_1)
api_key = (
    os.getenv("GEMINI_API_KEY_1") or
    os.getenv("GEMINI_API_KEY")
)

if not api_key:
    raise ValueError(
        "GEMINI_API_KEY_1 not found. "
        "Set it in your .env file. See .env.example."
    )


# Create Gemini model (gemini-2.0-flash supports tool calling)
llm = ChatGoogleGenerativeAI(
    model="gemini-2.0-flash",
    google_api_key=api_key,
    temperature=0,
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
            body=body,
        )
    )

    # Gemini returns response.content as a string
    return response.content