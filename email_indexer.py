"""
email_indexer.py
================
Builds and incrementally updates the email embedding index.

Uses Gemini text-embedding-004 (768-dim vectors) to embed
each email's sender + subject + body into a vector for
semantic search.

Usage:
    python email_indexer.py

The index is saved to email_embeddings.json with metadata:
    {
        "embedding_model": "text-embedding-004",
        "dimensions": 768,
        "emails": [ { ...email + embedding... } ]
    }
"""

import os
import json
import time
import base64

from bs4 import BeautifulSoup
from dotenv import load_dotenv

from gmail_service import create_gmail_service
from gemini_client import _get_api_keys
from langchain_google_genai import GoogleGenerativeAIEmbeddings

# Load .env
load_dotenv()


# ============================================================
# Configuration
# ============================================================

STORAGE_FILE = "email_embeddings.json"

# Confirmed working embedding model (3072-dim vectors)
EMBEDDING_MODEL = "models/gemini-embedding-001"

EMBEDDING_DIMENSIONS = 3072

# Delay between embedding requests (seconds) — avoids per-minute rate limits
EMBED_DELAY_SECONDS = 2.0

# Max retries per email on 429 quota errors
MAX_RETRIES = 3

# Save progress every N emails (so quota hits don't lose all work)
SAVE_EVERY = 10


# ============================================================
# HTML cleaner
# ============================================================

def clean_email_html(html: str) -> str:
    """Strip HTML tags and return readable plain text."""
    if not html:
        return ""

    soup = BeautifulSoup(html, "html.parser")

    for tag in soup(["script", "style", "head", "meta", "link"]):
        tag.decompose()

    text = soup.get_text(separator=" ")

    return " ".join(text.split())


# ============================================================
# Gmail body decoder
# ============================================================

def decode_body(data: str) -> str:
    """Decode Gmail Base64URL-encoded email body."""
    if not data:
        return ""

    try:
        return base64.urlsafe_b64decode(
            data.encode("UTF-8")
        ).decode("UTF-8", errors="ignore")

    except Exception:
        return ""


def extract_body(payload: dict) -> str:
    """
    Recursively extract the best available body from
    a Gmail message payload.
    """
    body = ""

    body_data = payload.get("body", {}).get("data")
    if body_data:
        body += decode_body(body_data)

    for part in payload.get("parts", []):
        body += extract_body(part)

    return body


# ============================================================
# Gmail email fetcher
# ============================================================

def get_emails(service, max_results: int = 50) -> list[dict]:
    """
    Fetch Gmail emails from INBOX.

    Args:
        service: Gmail API service object
        max_results: Maximum number of emails to fetch

    Returns:
        List of email dicts: id, sender, subject, date, body
    """
    response = service.users().messages().list(
        userId="me",
        labelIds=["INBOX"],
        maxResults=max_results,
    ).execute()

    messages = response.get("messages", [])

    emails = []

    for message in messages:
        msg = service.users().messages().get(
            userId="me",
            id=message["id"],
            format="full",
        ).execute()

        payload = msg.get("payload", {})
        headers = payload.get("headers", [])

        email = {
            "id": message["id"],
            "sender": "",
            "subject": "",
            "date": "",
            "body": "",
        }

        for header in headers:
            name = header["name"].lower()
            value = header["value"]

            if name == "from":
                email["sender"] = value
            elif name == "subject":
                email["subject"] = value
            elif name == "date":
                email["date"] = value

        raw_body = extract_body(payload)
        email["body"] = clean_email_html(raw_body)

        emails.append(email)

    return emails


# ============================================================
# Load existing index
# ============================================================

def load_index() -> tuple[dict, list[dict]]:
    """
    Load existing email index from disk.

    Returns:
        Tuple of (metadata_dict, list_of_email_records)
    """
    if not os.path.exists(STORAGE_FILE):
        return {}, []

    try:
        with open(STORAGE_FILE, "r", encoding="utf-8") as file:
            data = json.load(file)

        # New format: dict with metadata + emails list
        if isinstance(data, dict):
            metadata = {
                k: v for k, v in data.items()
                if k != "emails"
            }
            records = data.get("emails", [])
            return metadata, records

        # Old format: plain list (no metadata)
        else:
            print(
                "⚠️  Old index format detected (no metadata).\n"
                "   Re-indexing is recommended to ensure model consistency.\n"
                "   Delete email_embeddings.json and re-run to start fresh."
            )
            return {}, data

    except json.JSONDecodeError:
        print("⚠️  Existing index is corrupt. Starting fresh.")
        return {}, []


# ============================================================
# Save index
# ============================================================

def save_index(metadata: dict, records: list[dict]) -> None:
    """
    Save the email index atomically (write to temp, then rename).

    Args:
        metadata: Index metadata (model name, dimensions, etc.)
        records: List of email records with embeddings
    """
    data = {
        **metadata,
        "emails": records,
    }

    temp_file = STORAGE_FILE + ".tmp"

    with open(temp_file, "w", encoding="utf-8") as file:
        json.dump(data, file, indent=2, ensure_ascii=False)

    os.replace(temp_file, STORAGE_FILE)


# ============================================================
# Build embedding text
# ============================================================

def build_email_text(email: dict) -> str:
    """
    Build the text string to embed for an email.

    Combines sender + subject + body (truncated) for a
    rich semantic representation.
    """
    return (
        f"Sender: {email['sender']}\n"
        f"Subject: {email['subject']}\n"
        f"Body: {email['body'][:5000]}"
    ).strip()


# ============================================================
# Incremental index update
# ============================================================

def embed_text_with_fallback(text: str) -> list[float] | None:
    """
    Embed text using Gemini, with key fallback and retry on 429.

    Tries each API key in sequence on quota errors.
    Retries with exponential backoff within each key.

    Returns:
        Embedding vector, or None if all keys failed.
    """
    keys = _get_api_keys()

    for key_idx, key in enumerate(keys):
        for attempt in range(MAX_RETRIES):
            try:
                embeddings = GoogleGenerativeAIEmbeddings(
                    model=EMBEDDING_MODEL,
                    google_api_key=key,
                )
                return embeddings.embed_query(text)

            except Exception as e:
                error_str = str(e).lower()
                is_quota = any(word in error_str for word in [
                    "429", "quota", "resource_exhausted"
                ])

                if is_quota and attempt < MAX_RETRIES - 1:
                    wait = 2 ** (attempt + 1)  # 2s, 4s, 8s
                    print(f"  ⏳ Quota hit (key {key_idx+1}), retrying in {wait}s...")
                    time.sleep(wait)
                    continue
                elif is_quota:
                    # This key is exhausted — try next key
                    print(f"  ⚠️  Key {key_idx+1} exhausted, trying next key...")
                    break
                else:
                    # Non-quota error — don't retry
                    raise

    return None  # All keys exhausted


def update_index(
    service,
    max_results: int = 50,
) -> list[dict]:
    """
    Incrementally update the email embedding index.

    Only embeds emails that are not already in the index.
    Saves progress every SAVE_EVERY emails so quota hits
    don't lose all work.

    Args:
        service: Gmail API service object
        max_results: How many Gmail emails to check
    """
    print("Loading existing index...")
    metadata, records = load_index()

    existing_ids = {record["id"] for record in records}

    print(f"Already indexed: {len(existing_ids)} emails")

    # Validate model consistency
    current_model = metadata.get("embedding_model")
    if current_model and current_model != EMBEDDING_MODEL:
        print(
            f"\n⚠️  WARNING: Existing index uses '{current_model}' "
            f"but this run uses '{EMBEDDING_MODEL}'.\n"
            "   Mixing embedding models is not allowed.\n"
            "   Delete email_embeddings.json and re-run to rebuild cleanly.\n"
        )
        raise ValueError(
            f"Embedding model mismatch: index={current_model}, "
            f"current={EMBEDDING_MODEL}"
        )

    print("\nFetching emails from Gmail...")
    emails = get_emails(service, max_results=max_results)
    print(f"Found {len(emails)} Gmail emails")

    new_emails = [
        email for email in emails
        if email["id"] not in existing_ids
    ]

    print(f"New emails to embed: {len(new_emails)}")

    if not new_emails:
        print("\n✓ Index is already up to date.")
        return records

    print(f"\nUsing Gemini embedding model: {EMBEDDING_MODEL}")
    print(f"Rate limit: {EMBED_DELAY_SECONDS}s delay between requests")
    print()

    embedded_count = 0
    skipped_count = 0

    for index, email in enumerate(new_emails, start=1):
        print(f"Embedding {index}/{len(new_emails)}: {email['subject']}")

        text = build_email_text(email)

        # Rate limiting — pause between requests
        if index > 1:
            time.sleep(EMBED_DELAY_SECONDS)

        embedding = embed_text_with_fallback(text)

        if embedding is None:
            print(f"  ⚠️  Skipping — all API keys exhausted for this email")
            skipped_count += 1
            continue

        records.append({
            "id": email["id"],
            "sender": email["sender"],
            "subject": email["subject"],
            "date": email["date"],
            "body": email["body"],
            "embedding": embedding,
        })

        embedded_count += 1

        # Periodic save — don't lose progress if quota hits
        if embedded_count % SAVE_EVERY == 0:
            checkpoint_metadata = {
                "embedding_model": EMBEDDING_MODEL,
                "dimensions": EMBEDDING_DIMENSIONS,
                "total": len(records),
            }
            save_index(checkpoint_metadata, records)
            print(f"  💾 Checkpoint saved ({len(records)} total)")

    # Final save with metadata
    final_metadata = {
        "embedding_model": EMBEDDING_MODEL,
        "dimensions": EMBEDDING_DIMENSIONS,
        "total": len(records),
    }

    save_index(final_metadata, records)

    print(f"\n✓ Saved {len(records)} total email embeddings.")
    print(f"  Model: {EMBEDDING_MODEL} ({EMBEDDING_DIMENSIONS}-dim)")
    if skipped_count:
        print(f"  ⚠️  {skipped_count} emails skipped (quota). Run again later to embed them.")

    return records


# ============================================================
# Main
# ============================================================

if __name__ == "__main__":
    service = create_gmail_service()
    update_index(service, max_results=50)