from langchain_core.tools import tool

from read_emails import search_emails, get_email_details


@tool
def search_gmail(query: str) -> str:
    """
    Search the user's Gmail account.

    Use this tool when the user wants to find emails
    based on sender, subject, keywords, dates, or
    Gmail search filters.

    Returns email IDs that can be passed to
    read_gmail_email.
    """

    service, messages = search_emails(
        query,
        max_results=10
    )

    if not messages:
        return "No emails found."

    results = []

    for message in messages:

        message_id = message["id"]

        email = get_email_details(
            service,
            message_id
        )

        results.append(
            f"""
Email ID: {message_id}
Sender: {email["sender"]}
Subject: {email["subject"]}
Date: {email["date"]}
Body:
{email["body"][:1500]}
"""
        )

    return "\n\n--- EMAIL ---\n\n".join(results)



@tool
def read_gmail_email(message_id: str) -> str:
    """
    Read a specific Gmail email.

    IMPORTANT:
    The message_id must be the exact Gmail
    Email ID returned by search_gmail.

    Do NOT use the email subject, sender,
    or any other text as the message_id.
    """

    service, _ = search_emails(
        "in:anywhere",
        max_results=1
    )

    email = get_email_details(
        service,
        message_id
    )

    if not email:
        return (
            "Email not found. "
            "Use search_gmail first to obtain "
            "the correct Email ID."
        )

    return f"""
Email ID: {email["id"]}

Sender: {email["sender"]}

Subject: {email["subject"]}

Date: {email["date"]}

Body:
{email["body"]}
"""