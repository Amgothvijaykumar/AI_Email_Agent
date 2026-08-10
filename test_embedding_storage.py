import os
import json
import requests
import numpy as np
import base64

from bs4 import BeautifulSoup
from gmail_service import create_gmail_service


# ==========================================
# Configuration
# ==========================================

API_KEY = os.getenv("OPENROUTER_API_KEY")

if not API_KEY:
    raise ValueError("OPENROUTER_API_KEY is not set")

EMBEDDING_URL = "https://openrouter.ai/api/v1/embeddings"

MODEL = "nvidia/nemotron-3-embed-1b:free"

STORAGE_FILE = "email_embeddings.json"

HEADERS = {
    "Authorization": f"Bearer {API_KEY}",
    "Content-Type": "application/json",
}


# ==========================================
# Generate embedding
# ==========================================

def get_embedding(text):

    data = {
        "model": MODEL,
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
# Clean HTML
# ==========================================

def clean_email_html(html):

    if not html:
        return ""

    soup = BeautifulSoup(
        html,
        "html.parser"
    )

    for tag in soup(
        ["script", "style", "head"]
    ):
        tag.decompose()

    text = soup.get_text(
        separator=" "
    )

    text = " ".join(
        text.split()
    )

    return text


# ==========================================
# Decode Gmail body
# ==========================================

def decode_body(data):

    if not data:
        return ""

    try:

        return base64.urlsafe_b64decode(
            data.encode("UTF-8")
        ).decode(
            "UTF-8",
            errors="ignore"
        )

    except Exception:

        return ""


# ==========================================
# Extract email body
# ==========================================

def extract_body(payload):

    body = ""

    if payload.get(
        "body",
        {}
    ).get("data"):

        body += decode_body(
            payload["body"]["data"]
        )

    for part in payload.get(
        "parts",
        []
    ):

        body += extract_body(part)

    return body


# ==========================================
# Get Gmail emails
# ==========================================

def get_emails(
    service,
    max_results=10
):

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

        for header in headers:

            name = header["name"]
            value = header["value"]

            if name.lower() == "from":

                email_data["sender"] = value

            elif name.lower() == "subject":

                email_data["subject"] = value

            elif name.lower() == "date":

                email_data["date"] = value

        raw_body = extract_body(
            payload
        )

        email_data["body"] = clean_email_html(
            raw_body
        )

        emails.append(
            email_data
        )

    return emails


# ==========================================
# Create text for embedding
# ==========================================

def create_email_text(email):

    return f"""
Sender: {email['sender']}

Subject: {email['subject']}

Body:
{email['body'][:5000]}
""".strip()


# ==========================================
# Save embeddings
# ==========================================

def save_embeddings(records):

    with open(
        STORAGE_FILE,
        "w",
        encoding="utf-8"
    ) as file:

        json.dump(
            records,
            file,
            indent=2,
            ensure_ascii=False
        )


# ==========================================
# Load embeddings
# ==========================================

def load_embeddings():

    if not os.path.exists(
        STORAGE_FILE
    ):

        return []

    with open(
        STORAGE_FILE,
        "r",
        encoding="utf-8"
    ) as file:

        return json.load(file)


# ==========================================
# Main
# ==========================================

service = create_gmail_service()

print("Fetching emails...")

emails = get_emails(
    service,
    max_results=10
)

print(
    f"Found {len(emails)} emails\n"
)


records = []


# ==========================================
# Generate and store embeddings
# ==========================================

for email in emails:

    print(
        "Embedding:",
        email["subject"]
    )

    email_text = create_email_text(
        email
    )

    embedding = get_embedding(
        email_text
    )

    record = {
        "id": email["id"],
        "sender": email["sender"],
        "subject": email["subject"],
        "date": email["date"],
        "body": email["body"][:5000],
        "embedding": embedding
    }

    records.append(record)


# ==========================================
# Save
# ==========================================

save_embeddings(records)

print(
    f"\nSaved {len(records)} embeddings"
)

print(
    f"File: {STORAGE_FILE}"
)


# ==========================================
# Verify storage
# ==========================================

loaded = load_embeddings()

print(
    f"Loaded {len(loaded)} embeddings"
)

if loaded:

    print(
        "\nFirst stored email:"
    )

    print(
        "Subject:",
        loaded[0]["subject"]
    )

    print(
        "Sender:",
        loaded[0]["sender"]
    )

    print(
        "Vector dimensions:",
        len(loaded[0]["embedding"])
    )