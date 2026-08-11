import base64
import re

from bs4 import BeautifulSoup

from gmail_service import create_gmail_service


def decode_body(data):
    """Decode Gmail Base64URL encoded data."""

    if not data:
        return ""

    try:
        padding = "=" * (-len(data) % 4)

        return base64.urlsafe_b64decode(
            data + padding
        ).decode(
            "utf-8",
            errors="replace"
        )

    except Exception:
        return ""


def clean_html(html):
    """Convert HTML email into readable text."""

    soup = BeautifulSoup(
        html,
        "html.parser"
    )

    # Remove unnecessary HTML
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
    text = soup.get_text(
        separator="\n"
    )

    # Clean individual lines
    lines = []

    for line in text.splitlines():

        line = line.strip()

        if line:
            lines.append(line)

    text = "\n".join(lines)

    # Remove excessive blank lines
    text = re.sub(
        r"\n{3,}",
        "\n\n",
        text
    )

    return text.strip()


def extract_body(payload):
    """
    Extract the best available email body.

    Priority:
    1. text/plain
    2. text/html
    3. nested MIME parts
    """

    mime_type = payload.get(
        "mimeType",
        ""
    )

    body_data = payload.get(
        "body",
        {}
    ).get(
        "data"
    )

    # Direct plain-text body
    if mime_type == "text/plain" and body_data:

        return decode_body(
            body_data
        )

    # Direct HTML body
    if mime_type == "text/html" and body_data:

        html = decode_body(
            body_data
        )

        return clean_html(
            html
        )

    parts = payload.get(
        "parts",
        []
    )

    plain_text = ""
    html_text = ""

    for part in parts:

        part_type = part.get(
            "mimeType",
            ""
        )

        part_data = part.get(
            "body",
            {}
        ).get(
            "data"
        )

        # Plain text
        if part_type == "text/plain" and part_data:

            plain_text = decode_body(
                part_data
            )

        # HTML
        elif part_type == "text/html" and part_data:

            html_text = clean_html(
                decode_body(
                    part_data
                )
            )

        # Nested MIME structure
        elif part.get("parts"):

            nested_body = extract_body(
                part
            )

            if nested_body:

                if not plain_text:
                    plain_text = nested_body

    # Prefer plain text
    if plain_text.strip():

        return plain_text.strip()

    # Otherwise use cleaned HTML
    if html_text.strip():

        return html_text.strip()

    return ""


def get_header(headers, name):
    """Get a specific email header."""

    for header in headers:

        if header.get(
            "name",
            ""
        ).lower() == name.lower():

            return header.get(
                "value",
                ""
            )

    return ""


def get_latest_emails(max_results=5):
    """
    Get the latest Gmail messages.

    Returns:
        service: Gmail API service
        messages: list of Gmail message IDs
    """

    service = create_gmail_service()

    results = service.users().messages().list(
        userId="me",
        maxResults=max_results
    ).execute()

    messages = results.get(
        "messages",
        []
    )

    return service, messages


def format_local_date(raw_date: str) -> str:
    """Convert raw RFC 2822 email date to a readable local timezone string."""
    if not raw_date:
        return ""
    import email.utils
    try:
        dt = email.utils.parsedate_to_datetime(raw_date)
        local_dt = dt.astimezone()
        return local_dt.strftime("%a, %d %b %Y, %I:%M %p %Z")
    except Exception:
        return raw_date


def get_email_details(
    service,
    message_id
):
    """
    Retrieve complete information about one email.

    Returns:
        Dictionary containing:
        id, sender, subject, date, raw_date, body
    """

    message = service.users().messages().get(
        userId="me",
        id=message_id,
        format="full"
    ).execute()

    payload = message.get("payload", {})
    headers = payload.get("headers", [])
    raw_date = get_header(headers, "Date")

    email_data = {
        "id": message_id,
        "sender": get_header(headers, "From"),
        "subject": get_header(headers, "Subject"),
        "date": format_local_date(raw_date),
        "raw_date": raw_date,
        "body": extract_body(payload)
    }

    return email_data


# Test the email reader directly
if __name__ == "__main__":

    service, messages = get_latest_emails(
        max_results=5
    )

    print(
        f"Found {len(messages)} emails\n"
    )

    for index, message in enumerate(
        messages,
        start=1
    ):

        email = get_email_details(
            service,
            message["id"]
        )

        print("=" * 60)

        print(
            f"EMAIL {index}"
        )

        print(
            "Sender:",
            email["sender"]
        )

        print(
            "Subject:",
            email["subject"]
        )

        print(
            "Date:",
            email["date"]
        )

        print("\nBody:")

        if email["body"]:

            print(
                email["body"][:1000]
            )

        else:

            print(
                "[No readable body found]"
            )

        print()

        

def search_emails(query, max_results=10):
    """
    Search Gmail using Gmail's search syntax.

    Examples:
        from:indeed
        subject:job
        is:unread
        newer_than:7d
    """

    service = create_gmail_service()

    results = service.users().messages().list(
        userId="me",
        q=query,
        maxResults=max_results
    ).execute()

    messages = results.get(
        "messages",
        []
    )

    return service, messages