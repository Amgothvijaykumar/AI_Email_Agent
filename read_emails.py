import base64
import email.utils
import re
from bs4 import BeautifulSoup
from gmail_service import create_gmail_service


def decode_body(data: str) -> str:
    """Decode Gmail Base64URL encoded data string."""
    if not data:
        return ""
    try:
        padding = "=" * (-len(data) % 4)
        return base64.urlsafe_b64decode(data + padding).decode("utf-8", errors="replace")
    except Exception:
        return ""


def clean_html(html: str) -> str:
    """Extract plain visible text from raw HTML email markup."""
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "head", "meta", "link", "noscript", "svg"]):
        tag.decompose()

    text = soup.get_text(separator="\n")
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    text = "\n".join(lines)
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def extract_body(payload: dict) -> str:
    """Extract email text from payload, prioritizing plain text over HTML."""
    mime_type = payload.get("mimeType", "")
    body_data = payload.get("body", {}).get("data")

    if mime_type == "text/plain" and body_data:
        return decode_body(body_data)

    if mime_type == "text/html" and body_data:
        return clean_html(decode_body(body_data))

    parts = payload.get("parts", [])
    plain_text = ""
    html_text = ""

    for part in parts:
        part_type = part.get("mimeType", "")
        part_data = part.get("body", {}).get("data")

        if part_type == "text/plain" and part_data:
            plain_text = decode_body(part_data)
        elif part_type == "text/html" and part_data:
            html_text = clean_html(decode_body(part_data))
        elif part.get("parts"):
            nested_body = extract_body(part)
            if nested_body and not plain_text:
                plain_text = nested_body

    if plain_text.strip():
        return plain_text.strip()
    if html_text.strip():
        return html_text.strip()
    return ""


def get_header(headers: list, name: str) -> str:
    """Get header value by case-insensitive name."""
    for header in headers:
        if header.get("name", "").lower() == name.lower():
            return header.get("value", "")
    return ""


def format_local_date(raw_date: str) -> str:
    """Convert raw email timestamp into a formatted local timezone string."""
    if not raw_date:
        return ""
    try:
        dt = email.utils.parsedate_to_datetime(raw_date)
        return dt.astimezone().strftime("%a, %d %b %Y, %I:%M %p %Z")
    except Exception:
        return raw_date


def get_email_details(service, message_id: str) -> dict:
    """Retrieve full details (sender, subject, date, body) for an email."""
    message = service.users().messages().get(
        userId="me",
        id=message_id,
        format="full"
    ).execute()

    payload = message.get("payload", {})
    headers = payload.get("headers", [])
    raw_date = get_header(headers, "Date")

    return {
        "id": message_id,
        "sender": get_header(headers, "From"),
        "subject": get_header(headers, "Subject"),
        "date": format_local_date(raw_date),
        "raw_date": raw_date,
        "body": extract_body(payload)
    }


def get_latest_emails(max_results: int = 5):
    """Fetch latest Gmail message references."""
    service = create_gmail_service()
    results = service.users().messages().list(
        userId="me",
        maxResults=max_results
    ).execute()
    return service, results.get("messages", [])


def search_emails(query: str, max_results: int = 10):
    """Search Gmail messages by query."""
    service = create_gmail_service()
    results = service.users().messages().list(
        userId="me",
        q=query,
        maxResults=max_results
    ).execute()
    return service, results.get("messages", [])