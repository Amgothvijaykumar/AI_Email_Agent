from datetime import datetime
from langchain_core.tools import tool
from read_emails import search_emails, get_email_details
from gmail_service import create_gmail_service


def _get_service():
    """Retrieve Gmail API client instance."""
    return create_gmail_service()


@tool
def search_gmail(query: str) -> str:
    """
    Search Gmail using standard Gmail query filters (e.g. from:indeed, is:unread, subject:job).
    Returns matched email metadata (Message ID, Sender, Subject, Date).
    """
    service, messages = search_emails(query, max_results=10)
    if not messages:
        return f"No emails found matching: '{query}'"

    results = []
    for message in messages:
        msg_id = message["id"]
        email = get_email_details(service, msg_id)
        preview = " ".join(email.get("body", "").split())[:250]
        results.append(
            f"Message ID: {msg_id}\n"
            f"Sender: {email.get('sender')}\n"
            f"Subject: {email.get('subject')}\n"
            f"Date: {email.get('date')}\n"
            f"Preview: {preview}..."
        )

    return f"Found {len(results)} email(s) for '{query}':\n\n" + "\n\n---\n\n".join(results)


@tool
def read_gmail_email(message_id: str) -> str:
    """Read the complete body and headers of an email by its exact Message ID."""
    service = _get_service()
    try:
        email = get_email_details(service, message_id)
    except Exception as e:
        return f"Failed to fetch email '{message_id}': {e}"

    if not email:
        return f"Email not found with ID: {message_id}"

    return (
        f"Message ID: {email['id']}\n"
        f"From: {email['sender']}\n"
        f"Subject: {email['subject']}\n"
        f"Date: {email['date']}\n\n"
        f"Body:\n{email.get('body', '[Empty body]')}"
    )


@tool
def mark_email_as_read(message_id: str) -> str:
    """Mark an email as read by removing the UNREAD label."""
    service = _get_service()
    try:
        service.users().messages().modify(
            userId="me",
            id=message_id,
            body={"removeLabelIds": ["UNREAD"]},
        ).execute()
        return f"✓ Email {message_id} marked as read."
    except Exception as e:
        return f"Failed to mark as read: {e}"


@tool
def mark_email_as_unread(message_id: str) -> str:
    """Mark an email as unread by adding the UNREAD label."""
    service = _get_service()
    try:
        service.users().messages().modify(
            userId="me",
            id=message_id,
            body={"addLabelIds": ["UNREAD"]},
        ).execute()
        return f"✓ Email {message_id} marked as unread."
    except Exception as e:
        return f"Failed to mark as unread: {e}"


@tool
def star_email(message_id: str) -> str:
    """Star an email by adding the STARRED label."""
    service = _get_service()
    try:
        service.users().messages().modify(
            userId="me",
            id=message_id,
            body={"addLabelIds": ["STARRED"]},
        ).execute()
        return f"✓ Email {message_id} starred."
    except Exception as e:
        return f"Failed to star email: {e}"


@tool
def unstar_email(message_id: str) -> str:
    """Remove star from an email."""
    service = _get_service()
    try:
        service.users().messages().modify(
            userId="me",
            id=message_id,
            body={"removeLabelIds": ["STARRED"]},
        ).execute()
        return f"✓ Star removed from email {message_id}."
    except Exception as e:
        return f"Failed to unstar email: {e}"


@tool
def archive_email(message_id: str) -> str:
    """Archive an email by removing it from INBOX."""
    service = _get_service()
    try:
        service.users().messages().modify(
            userId="me",
            id=message_id,
            body={"removeLabelIds": ["INBOX"]},
        ).execute()
        return f"✓ Email {message_id} archived."
    except Exception as e:
        return f"Failed to archive email: {e}"


@tool
def delete_email(message_id: str) -> str:
    """Request deletion of an email. Returns confirmation prompt with email metadata."""
    service = _get_service()
    try:
        email = get_email_details(service, message_id)
    except Exception as e:
        return f"Could not find email '{message_id}': {e}"

    if not email:
        return f"Email not found with ID: {message_id}"

    return (
        f"DELETE_CONFIRMATION_REQUIRED\n"
        f"Message ID: {message_id}\n"
        f"Subject: {email['subject']}\n"
        f"Sender: {email['sender']}\n"
        f"Date: {email['date']}\n\n"
        f"Confirm moving this email to Gmail Trash? (Reply 'yes' or 'no')"
    )


@tool
def batch_delete_emails(message_ids: list[str]) -> str:
    """Request bulk deletion of multiple emails. Returns summary confirmation prompt."""
    if not message_ids:
        return "No message IDs provided."

    service = _get_service()
    summaries = []

    for mid in message_ids:
        try:
            email = get_email_details(service, mid)
            if email and email.get("subject"):
                summaries.append(f"• [{mid}] {email['subject']} (From: {email.get('sender', '').split('<')[0].strip()})")
        except Exception:
            summaries.append(f"• [{mid}] (Details unavailable)")

    return (
        f"BATCH_DELETE_CONFIRMATION_REQUIRED\n"
        f"Count: {len(message_ids)} email(s)\n"
        f"IDs: {','.join(message_ids)}\n\n"
        f"Emails to delete:\n" + "\n".join(summaries) + "\n\n"
        f"Confirm moving all {len(message_ids)} email(s) to Gmail Trash? (Reply 'yes' or 'no')"
    )


def execute_delete_email(service, message_id: str) -> str:
    """Execute trash action on an email after confirmation."""
    try:
        service.users().messages().trash(userId="me", id=message_id).execute()
        return f"✓ Email {message_id} moved to Trash."
    except Exception as e:
        return f"Deletion failed: {e}"


def execute_batch_delete_emails(service, message_ids: list[str]) -> str:
    """Execute bulk trash action on a list of emails after confirmation."""
    if not message_ids:
        return "No emails specified."

    success = 0
    for mid in message_ids:
        try:
            service.users().messages().trash(userId="me", id=mid).execute()
            success += 1
        except Exception:
            pass

    return f"✓ Successfully moved {success} email(s) to Gmail Trash."


@tool
def get_inbox_overview() -> str:
    """Retrieve inbox overview including unread count, today's arrivals, and latest emails."""
    service = _get_service()
    try:
        profile = service.users().getProfile(userId="me").execute()
        unread_res = service.users().messages().list(
            userId="me", labelIds=["INBOX", "UNREAD"], maxResults=1
        ).execute()
        unread_est = unread_res.get("resultSizeEstimate", 0)

        today_midnight = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        today_res = service.users().messages().list(
            userId="me", labelIds=["INBOX"], q=f"after:{int(today_midnight.timestamp())}", maxResults=25
        ).execute()

        today_list = []
        for msg in today_res.get("messages", []):
            em = get_email_details(service, msg["id"])
            preview = em.get("body", "")[:180].replace("\n", " ").strip()
            today_list.append(f"• [{msg['id']}] {em['subject']}\n  From: {em['sender']}\n  Date: {em['date']}\n  Preview: {preview}")

        inbox_res = service.users().messages().list(
            userId="me", labelIds=["INBOX"], maxResults=10
        ).execute()

        latest_list = []
        for msg in inbox_res.get("messages", []):
            em = get_email_details(service, msg["id"])
            latest_list.append(f"• [{msg['id']}] {em['subject']}\n  From: {em['sender']}\n  Date: {em['date']}")

        today_section = f"📅 Today's Emails ({len(today_list)}):\n\n" + "\n\n".join(today_list) if today_list else "📅 No emails from today."

        return (
            f"📬 Inbox Overview\n"
            f"{'=' * 50}\n"
            f"Account: {profile.get('emailAddress', 'N/A')}\n"
            f"Estimated unread: {unread_est}\n\n"
            f"{today_section}\n\n"
            f"{'=' * 50}\n"
            f"Latest 10 inbox emails:\n\n" + "\n\n".join(latest_list)
        )
    except Exception as e:
        return f"Failed to get inbox overview: {e}"