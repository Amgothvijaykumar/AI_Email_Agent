import base64
import re
from bs4 import BeautifulSoup
from googleapiclient.discovery import build

from gmail_service import create_gmail_service


def decode_body(data):
    """Decode Gmail's base64url encoded email body."""
    if not data:
        return ""

    try:
        return base64.urlsafe_b64decode(data + "===" ).decode(
            "utf-8",
            errors="replace"
        )
    except Exception:
        return ""


def clean_html(html):
    """Convert HTML email into clean readable text."""

    soup = BeautifulSoup(html, "html.parser")

    # Remove elements that do not contain useful email content
    for tag in soup([
        "script",
        "style",
        "head",
        "meta",
        "link",
        "noscript",
        "svg"
    ]):
        tag.decompose()

    # Extract visible text
    text = soup.get_text(separator="\n")

    # Clean whitespace
    lines = []

    for line in text.splitlines():
        line = line.strip()

        if line:
            lines.append(line)

    text = "\n".join(lines)

    # Remove excessive blank lines
    text = re.sub(r"\n{3,}", "\n\n", text)

    # Remove very long tracking URLs
    text = re.sub(
        r"https?://\S+",
        "[LINK]",
        text
    )

    return text.strip()


def extract_body(payload):
    """
    Extract the best available email body.

    Priority:
    1. text/plain
    2. text/html
    3. recursively search multipart sections
    """

    mime_type = payload.get("mimeType", "")
    body_data = payload.get("body", {}).get("data")

    # Direct text/plain body
    if mime_type == "text/plain" and body_data:
        return decode_body(body_data)

    # Direct text/html body
    if mime_type == "text/html" and body_data:
        html = decode_body(body_data)
        return clean_html(html)

    # Multipart email
    parts = payload.get("parts", [])

    plain_text = ""
    html_text = ""

    for part in parts:

        part_type = part.get("mimeType", "")

        # Direct plain text
        if part_type == "text/plain":
            data = part.get("body", {}).get("data")

            if data:
                plain_text = decode_body(data)

        # Direct HTML
        elif part_type == "text/html":
            data = part.get("body", {}).get("data")

            if data:
                html_text = clean_html(decode_body(data))

        # Nested multipart
        elif part.get("parts"):
            nested_text = extract_body(part)

            if nested_text:
                if not plain_text:
                    plain_text = nested_text

    # Prefer plain text when available
    if plain_text.strip():
        return plain_text.strip()

    if html_text.strip():
        return html_text.strip()

    return ""


def get_header(headers, name):
    """Get a specific email header."""
    for header in headers:
        if header.get("name", "").lower() == name.lower():
            return header.get("value", "")

    return ""


def read_emails(max_results=5):

    service = create_gmail_service()

    results = service.users().messages().list(
        userId="me",
        maxResults=max_results
    ).execute()

    messages = results.get("messages", [])

    print(f"Found {len(messages)} emails")

    print("=" * 60)

    for message in messages:

        msg = service.users().messages().get(
            userId="me",
            id=message["id"],
            format="full"
        ).execute()

        payload = msg.get("payload", {})

        headers = payload.get("headers", [])

        sender = get_header(headers, "From")
        subject = get_header(headers, "Subject")
        date = get_header(headers, "Date")

        body = extract_body(payload)

        print("=" * 60)

        print(f"Sender: {sender}")
        print(f"Subject: {subject}")
        print(f"Date: {date}")

        print("\nBody:")

        if body:
            print(body)
        else:
            print("[No readable body found]")

        print()


if __name__ == "__main__":
    read_emails(5)