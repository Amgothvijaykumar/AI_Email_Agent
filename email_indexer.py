import os
import json
import time
import base64
from bs4 import BeautifulSoup
from dotenv import load_dotenv
from langchain_google_genai import GoogleGenerativeAIEmbeddings
from gmail_service import create_gmail_service
from gemini_client import _get_api_keys

load_dotenv()

STORAGE_FILE = "email_embeddings.json"
EMBEDDING_MODEL = "models/gemini-embedding-001"
EMBEDDING_DIMENSIONS = 3072
EMBED_DELAY_SECONDS = 2.0
MAX_RETRIES = 3
SAVE_EVERY = 10


def clean_email_html(html: str) -> str:
    """Extract plain readable text from HTML markup."""
    if not html:
        return ""
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "head", "meta", "link"]):
        tag.decompose()
    return " ".join(soup.get_text(separator=" ").split())


def decode_body(data: str) -> str:
    """Decode Base64URL-encoded email string."""
    if not data:
        return ""
    try:
        return base64.urlsafe_b64decode(data.encode("UTF-8")).decode("UTF-8", errors="ignore")
    except Exception:
        return ""


def extract_body(payload: dict) -> str:
    """Recursively extract body content from message payload."""
    body = ""
    body_data = payload.get("body", {}).get("data")
    if body_data:
        body += decode_body(body_data)
    for part in payload.get("parts", []):
        body += extract_body(part)
    return body


def get_emails(service, max_results: int = 50) -> list[dict]:
    """Fetch recent inbox messages with headers and body text."""
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
            val = header["value"]
            if name == "from":
                email["sender"] = val
            elif name == "subject":
                email["subject"] = val
            elif name == "date":
                email["date"] = val

        raw_body = extract_body(payload)
        email["body"] = clean_email_html(raw_body)
        emails.append(email)

    return emails


def load_index() -> tuple[dict, list[dict]]:
    """Load existing index and metadata from disk."""
    if not os.path.exists(STORAGE_FILE):
        return {}, []

    try:
        with open(STORAGE_FILE, "r", encoding="utf-8") as file:
            data = json.load(file)

        if isinstance(data, dict):
            metadata = {k: v for k, v in data.items() if k != "emails"}
            return metadata, data.get("emails", [])
        return {}, data
    except Exception:
        return {}, []


def save_index(metadata: dict, records: list[dict]) -> None:
    """Atomically save index metadata and records to disk."""
    data = {**metadata, "emails": records}
    temp_file = STORAGE_FILE + ".tmp"
    with open(temp_file, "w", encoding="utf-8") as file:
        json.dump(data, file, indent=2, ensure_ascii=False)
    os.replace(temp_file, STORAGE_FILE)


def build_email_text(email: dict) -> str:
    """Format email content for vector embedding generation."""
    return f"Sender: {email['sender']}\nSubject: {email['subject']}\nBody: {email['body'][:5000]}".strip()


def embed_text_with_fallback(text: str) -> list[float] | None:
    """Generate vector embedding with retry and key rotation on quota limits."""
    keys = _get_api_keys()

    for key in keys:
        for attempt in range(MAX_RETRIES):
            try:
                embeddings = GoogleGenerativeAIEmbeddings(
                    model=EMBEDDING_MODEL,
                    google_api_key=key,
                )
                return embeddings.embed_query(text)
            except Exception as e:
                error_str = str(e).lower()
                is_quota = any(w in error_str for w in ["429", "quota", "resource_exhausted"])
                if is_quota and attempt < MAX_RETRIES - 1:
                    time.sleep(2 ** (attempt + 1))
                    continue
                elif is_quota:
                    break
                raise
    return None


def update_index(service, max_results: int = 50) -> list[dict]:
    """Incrementally index new inbox emails into the vector database."""
    metadata, records = load_index()
    existing_ids = {record["id"] for record in records}

    current_model = metadata.get("embedding_model")
    if current_model and current_model != EMBEDDING_MODEL:
        raise ValueError(f"Embedding model mismatch: index={current_model}, current={EMBEDDING_MODEL}")

    emails = get_emails(service, max_results=max_results)
    new_emails = [email for email in emails if email["id"] not in existing_ids]

    if not new_emails:
        return records

    for index, email in enumerate(new_emails, start=1):
        if index > 1:
            time.sleep(EMBED_DELAY_SECONDS)

        embedding = embed_text_with_fallback(build_email_text(email))
        if embedding is None:
            continue

        records.append({
            "id": email["id"],
            "sender": email["sender"],
            "subject": email["subject"],
            "date": email["date"],
            "body": email["body"],
            "embedding": embedding,
        })

        if len(records) % SAVE_EVERY == 0:
            save_index({
                "embedding_model": EMBEDDING_MODEL,
                "dimensions": EMBEDDING_DIMENSIONS,
                "total": len(records),
            }, records)

    final_metadata = {
        "embedding_model": EMBEDDING_MODEL,
        "dimensions": EMBEDDING_DIMENSIONS,
        "total": len(records),
    }
    save_index(final_metadata, records)
    return records


if __name__ == "__main__":
    service = create_gmail_service()
    records = update_index(service, max_results=50)
    print(f"Index updated: {len(records)} total emails indexed.")