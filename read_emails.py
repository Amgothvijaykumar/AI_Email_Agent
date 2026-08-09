import base64

from gmail_service import create_gmail_service


def get_latest_emails(max_results=5):
    service = create_gmail_service()

    results = service.users().messages().list(
        userId="me",
        maxResults=max_results
    ).execute()

    messages = results.get("messages", [])

    return service, messages


def get_email_body(payload):
    """
    Extracts plain-text content from a Gmail message payload.
    """

    # Case 1: Email has a direct body
    body_data = payload.get("body", {}).get("data")

    if body_data:
        decoded_body = base64.urlsafe_b64decode(
            body_data
        ).decode("utf-8", errors="ignore")

        return decoded_body

    # Case 2: Email contains multiple parts
    parts = payload.get("parts", [])

    for part in parts:

        # Prefer plain text
        if part.get("mimeType") == "text/plain":

            part_data = part.get("body", {}).get("data")

            if part_data:
                decoded_body = base64.urlsafe_b64decode(
                    part_data
                ).decode("utf-8", errors="ignore")

                return decoded_body

        # Recursively check nested parts
        if part.get("parts"):
            body = get_email_body(part)

            if body:
                return body

    return ""


def get_email_details(service, message_id):

    message = service.users().messages().get(
        userId="me",
        id=message_id,
        format="full"
    ).execute()

    payload = message.get("payload", {})

    headers = payload.get("headers", [])

    email_data = {
        "id": message_id,
        "sender": None,
        "subject": None,
        "date": None,
        "body": ""
    }

    for header in headers:

        name = header["name"].lower()

        if name == "from":
            email_data["sender"] = header["value"]

        elif name == "subject":
            email_data["subject"] = header["value"]

        elif name == "date":
            email_data["date"] = header["value"]

    # Extract email body
    email_data["body"] = get_email_body(payload)

    return email_data


if __name__ == "__main__":

    service, emails = get_latest_emails()

    print(f"Found {len(emails)} emails\n")

    for email in emails:

        details = get_email_details(
            service,
            email["id"]
        )

        print("=" * 60)

        print("Sender:", details["sender"])
        print("Subject:", details["subject"])
        print("Date:", details["date"])

        print("\nBody:")
        print(details["body"][:1000])