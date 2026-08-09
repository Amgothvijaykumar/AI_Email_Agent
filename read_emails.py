from gmail_service import create_gmail_service


def get_latest_emails(max_results=5):
    service = create_gmail_service()

    results = service.users().messages().list(
        userId="me",
        maxResults=max_results
    ).execute()

    messages = results.get("messages", [])

    return service, messages


def get_email_details(service, message_id):
    message = service.users().messages().get(
        userId="me",
        id=message_id,
        format="full"
    ).execute()

    headers = message["payload"].get("headers", [])

    email_data = {
        "id": message_id,
        "sender": None,
        "subject": None,
        "date": None
    }

    for header in headers:
        name = header["name"].lower()

        if name == "from":
            email_data["sender"] = header["value"]

        elif name == "subject":
            email_data["subject"] = header["value"]

        elif name == "date":
            email_data["date"] = header["value"]

    return email_data


if __name__ == "__main__":
    service, emails = get_latest_emails()

    print(f"Found {len(emails)} emails\n")

    for email in emails:
        details = get_email_details(service, email["id"])

        print("----------")
        print("Sender:", details["sender"])
        print("Subject:", details["subject"])
        print("Date:", details["date"])