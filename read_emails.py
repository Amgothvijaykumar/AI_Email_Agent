from gmail_service import create_gmail_service


def get_latest_emails(max_results=5):
    service = create_gmail_service()

    results = service.users().messages().list(
        userId="me",
        maxResults=max_results
    ).execute()

    messages = results.get("messages", [])

    print(f"Found {len(messages)} emails")

    return messages


if __name__ == "__main__":
    emails = get_latest_emails()

    for email in emails:
        print(email)