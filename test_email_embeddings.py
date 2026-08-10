import os
import requests
import numpy as np
import base64

from bs4 import BeautifulSoup
from gmail_service import create_gmail_service


# ==========================================
# OpenRouter configuration
# ==========================================

API_KEY = os.getenv("OPENROUTER_API_KEY")

if not API_KEY:
    raise ValueError("OPENROUTER_API_KEY is not set")

EMBEDDING_URL = "https://openrouter.ai/api/v1/embeddings"

HEADERS = {
    "Authorization": f"Bearer {API_KEY}",
    "Content-Type": "application/json",
}


# ==========================================
# Generate embedding
# ==========================================

def get_embedding(text):

    data = {
        "model": "nvidia/nemotron-3-embed-1b:free",
        "input": text,
        "encoding_format": "float",
    }

    response = requests.post(
        EMBEDDING_URL,
        headers=HEADERS,
        json=data,
        timeout=60,
    )

    response.raise_for_status()

    return response.json()["data"][0]["embedding"]


# ==========================================
# Clean HTML email
# ==========================================

def clean_email_html(html):
    """
    Convert HTML email content into clean readable text.
    """

    if not html:
        return ""

    soup = BeautifulSoup(
        html,
        "html.parser"
    )

    # Remove unwanted HTML sections
    for tag in soup(["script", "style", "head"]):
        tag.decompose()

    # Extract visible text
    text = soup.get_text(
        separator=" "
    )

    # Normalize whitespace
    text = " ".join(
        text.split()
    )

    return text


# ==========================================
# Cosine similarity
# ==========================================

def cosine_similarity(a, b):

    a = np.array(a)
    b = np.array(b)

    return np.dot(a, b) / (
        np.linalg.norm(a)
        * np.linalg.norm(b)
    )


# ==========================================
# Decode Gmail body
# ==========================================

def decode_body(data):

    if not data:
        return ""

    try:

        decoded = base64.urlsafe_b64decode(
            data.encode("UTF-8")
        ).decode(
            "UTF-8",
            errors="ignore"
        )

        return decoded

    except Exception:

        return ""


# ==========================================
# Extract email body recursively
# ==========================================

def extract_body(payload):

    body = ""

    # Check current part
    if payload.get("body", {}).get("data"):

        body += decode_body(
            payload["body"]["data"]
        )

    # Check nested parts
    for part in payload.get("parts", []):

        body += extract_body(part)

    return body


# ==========================================
# Get Gmail emails
# ==========================================

def get_emails(service, max_results=10):

    response = service.users().messages().list(
        userId="me",
        labelIds=["INBOX"],
        maxResults=max_results
    ).execute()

    messages = response.get(
        "messages",
        []
    )

    emails = []

    for message in messages:

        msg = service.users().messages().get(
            userId="me",
            id=message["id"],
            format="full"
        ).execute()

        payload = msg.get(
            "payload",
            {}
        )

        headers = payload.get(
            "headers",
            []
        )

        email_data = {
            "id": message["id"],
            "sender": "",
            "subject": "",
            "date": "",
            "body": ""
        }

        # ----------------------------------
        # Read headers
        # ----------------------------------

        for header in headers:

            name = header["name"]
            value = header["value"]

            if name.lower() == "from":

                email_data["sender"] = value

            elif name.lower() == "subject":

                email_data["subject"] = value

            elif name.lower() == "date":

                email_data["date"] = value

        # ----------------------------------
        # Extract raw body
        # ----------------------------------

        raw_body = extract_body(
            payload
        )

        # ----------------------------------
        # Clean HTML
        # ----------------------------------

        email_data["body"] = clean_email_html(
            raw_body
        )

        emails.append(
            email_data
        )

    return emails


# ==========================================
# Main
# ==========================================

service = create_gmail_service()

emails = get_emails(
    service,
    max_results=10
)

print(
    f"Found {len(emails)} emails\n"
)


# ==========================================
# Create email embeddings
# ==========================================

embedded_emails = []

for email in emails:

    # Combine important email information
    email_text = f"""
Sender: {email['sender']}

Subject: {email['subject']}

Body:
{email['body'][:5000]}
"""

    print(
        "Embedding:",
        email["subject"]
    )

    embedding = get_embedding(
        email_text
    )

    embedded_emails.append({

        "email": email,

        "embedding": embedding
    })


# ==========================================
# User query
# ==========================================

query = input(
    "\nWhat emails are you looking for?\n> "
)

print(
    "\nSearching semantically...\n"
)


# ==========================================
# Create query embedding
# ==========================================

query_embedding = get_embedding(
    query
)


# ==========================================
# Calculate similarity
# ==========================================

results = []

for item in embedded_emails:

    score = cosine_similarity(
        query_embedding,
        item["embedding"]
    )

    results.append({

        "email": item["email"],

        "score": score
    })


# ==========================================
# Sort results
# ==========================================

results.sort(
    key=lambda x: x["score"],
    reverse=True
)


# ==========================================
# Display results
# ==========================================

print(
    "=" * 70
)

print(
    "SEMANTIC SEARCH RESULTS"
)

print(
    "=" * 70
)


for i, result in enumerate(
    results,
    start=1
):

    email = result["email"]

    print(
        f"\n{i}. {email['subject']}"
    )

    print(
        f"   Sender: {email['sender']}"
    )

    print(
        f"   Date: {email['date']}"
    )

    print(
        f"   Similarity: {result['score']:.4f}"
    )

    # ----------------------------------
    # Body preview
    # ----------------------------------

    body = email["body"].strip()

    if body:

        preview = " ".join(
            body.split()
        )[:200]

        print(
            f"   Preview: {preview}..."
        )