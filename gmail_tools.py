"""
gmail_tools.py
==============
Gmail LangChain tools for the AI Gmail Agent.

All tools use the Gmail API via read_emails.py / gmail_service.py.

CRITICAL RULE:
    message_id must ALWAYS be the exact Gmail message ID
    returned by search_gmail. Never use subject, sender,
    or any natural language text as a message_id.

Tools:
    search_gmail              - Search Gmail by query/operators
    read_gmail_email          - Read a specific email by ID
    mark_email_as_read        - Mark email as read (remove UNREAD label)
    mark_email_as_unread      - Mark email as unread (add UNREAD label)
    star_email                - Star an email
    unstar_email              - Remove star from an email
    archive_email             - Archive (remove from INBOX)
    delete_email              - Request deletion (returns confirmation)
    confirm_delete_email      - Actually deletes (called after user confirms)
    get_inbox_overview        - Return inbox summary stats
"""

from langchain_core.tools import tool
from read_emails import search_emails, get_email_details


# ============================================================
# Helper: get Gmail service cleanly
# ============================================================

def _get_service():
    """Return a Gmail API service object."""
    from gmail_service import create_gmail_service
    return create_gmail_service()


# ============================================================
# Tool 1: Search Gmail
# ============================================================

@tool
def search_gmail(query: str) -> str:
    """
    Search the user's Gmail account using Gmail search operators.

    Use this for:
    - Finding emails by sender:    from:indeed
    - Finding unread emails:       is:unread
    - Finding by subject:          subject:"job offer"
    - Finding by date:             after:2024/01/01
    - Finding starred emails:      is:starred
    - Finding emails with files:   has:attachment
    - Combining filters:           from:indeed is:unread

    Returns email metadata (ID, sender, subject, date) for up to 10 emails.
    Use the Message ID from these results to read or modify specific emails.

    IMPORTANT: Do NOT call this tool multiple times with slightly
    different queries. Make ONE well-formed query.
    """
    service, messages = search_emails(query, max_results=10)

    if not messages:
        return f"No emails found matching: '{query}'"

    results = []

    for message in messages:
        message_id = message["id"]
        email = get_email_details(service, message_id)

        # Return metadata only (not full body) for speed
        body_preview = ""
        if email.get("body"):
            body_preview = " ".join(
                email["body"].split()
            )[:300]
            if len(email["body"]) > 300:
                body_preview += "..."

        results.append(
            f"Message ID: {message_id}\n"
            f"Sender: {email['sender']}\n"
            f"Subject: {email['subject']}\n"
            f"Date: {email['date']}\n"
            f"Preview: {body_preview}"
        )

    header = f"Found {len(results)} email(s) for '{query}':\n"
    return header + "\n\n--- EMAIL ---\n\n".join(results)


# ============================================================
# Tool 2: Read a specific email
# ============================================================

@tool
def read_gmail_email(message_id: str) -> str:
    """
    Read the full content of a specific Gmail email.

    CRITICAL:
    - message_id must be the EXACT Gmail Message ID returned by search_gmail
    - Never use the email subject, sender name, or keywords as message_id
    - Always call search_gmail first to get the correct Message ID

    Example correct usage:
        search_gmail(query="from:Adobe subject:hackathon")
        → returns Message ID: 19fe5f834c141592
        read_gmail_email(message_id="19fe5f834c141592")

    Example WRONG usage (never do this):
        read_gmail_email(message_id="Adobe hackathon email")
    """
    service = _get_service()

    try:
        email = get_email_details(service, message_id)
    except Exception as e:
        return (
            f"Could not read email with ID '{message_id}': {e}\n"
            "Use search_gmail first to obtain the correct Message ID."
        )

    if not email:
        return (
            f"Email not found with ID: {message_id}\n"
            "Use search_gmail first to obtain the correct Message ID."
        )

    body = email.get("body", "[No readable body found]")

    return (
        f"Message ID: {email['id']}\n\n"
        f"Sender: {email['sender']}\n\n"
        f"Subject: {email['subject']}\n\n"
        f"Date: {email['date']}\n\n"
        f"Body:\n{body}"
    )


# ============================================================
# Tool 3: Mark as read
# ============================================================

@tool
def mark_email_as_read(message_id: str) -> str:
    """
    Mark a specific Gmail email as read (removes the UNREAD label).

    CRITICAL: message_id must be the exact Gmail Message ID
    returned by search_gmail. Never use subject or sender as ID.

    This action is reversible (can be marked unread again).
    Only perform when the user explicitly requests it.
    """
    service = _get_service()

    try:
        service.users().messages().modify(
            userId="me",
            id=message_id,
            body={"removeLabelIds": ["UNREAD"]},
        ).execute()
    except Exception as e:
        return f"Failed to mark email as read: {e}"

    return f"✓ Email {message_id} has been marked as read."


# ============================================================
# Tool 4: Mark as unread
# ============================================================

@tool
def mark_email_as_unread(message_id: str) -> str:
    """
    Mark a specific Gmail email as unread (adds the UNREAD label).

    CRITICAL: message_id must be the exact Gmail Message ID
    returned by search_gmail.

    Only perform when the user explicitly requests it.
    """
    service = _get_service()

    try:
        service.users().messages().modify(
            userId="me",
            id=message_id,
            body={"addLabelIds": ["UNREAD"]},
        ).execute()
    except Exception as e:
        return f"Failed to mark email as unread: {e}"

    return f"✓ Email {message_id} has been marked as unread."


# ============================================================
# Tool 5: Star email
# ============================================================

@tool
def star_email(message_id: str) -> str:
    """
    Star a specific Gmail email (adds the STARRED label).

    CRITICAL: message_id must be the exact Gmail Message ID
    returned by search_gmail.
    """
    service = _get_service()

    try:
        service.users().messages().modify(
            userId="me",
            id=message_id,
            body={"addLabelIds": ["STARRED"]},
        ).execute()
    except Exception as e:
        return f"Failed to star email: {e}"

    return f"✓ Email {message_id} has been starred."


# ============================================================
# Tool 6: Unstar email
# ============================================================

@tool
def unstar_email(message_id: str) -> str:
    """
    Remove the star from a specific Gmail email.

    CRITICAL: message_id must be the exact Gmail Message ID
    returned by search_gmail.
    """
    service = _get_service()

    try:
        service.users().messages().modify(
            userId="me",
            id=message_id,
            body={"removeLabelIds": ["STARRED"]},
        ).execute()
    except Exception as e:
        return f"Failed to unstar email: {e}"

    return f"✓ Star removed from email {message_id}."


# ============================================================
# Tool 7: Archive email
# ============================================================

@tool
def archive_email(message_id: str) -> str:
    """
    Archive a specific Gmail email (removes it from INBOX,
    but keeps it in All Mail). This is reversible.

    CRITICAL: message_id must be the exact Gmail Message ID
    returned by search_gmail.
    """
    service = _get_service()

    try:
        service.users().messages().modify(
            userId="me",
            id=message_id,
            body={"removeLabelIds": ["INBOX"]},
        ).execute()
    except Exception as e:
        return f"Failed to archive email: {e}"

    return f"✓ Email {message_id} has been archived (removed from Inbox)."


# ============================================================
# Tool 8: Delete email (returns confirmation request)
# ============================================================

@tool
def delete_email(message_id: str) -> str:
    """
    Request deletion of a specific Gmail email.

    IMPORTANT: This tool does NOT immediately delete the email.
    It returns a confirmation request that Python will present
    to the user before any actual deletion occurs.

    Deletion is PERMANENT and IRREVERSIBLE. Always confirm first.

    CRITICAL: message_id must be the exact Gmail Message ID
    returned by search_gmail.
    """
    service = _get_service()

    # Fetch email details for the confirmation message
    try:
        email = get_email_details(service, message_id)
    except Exception as e:
        return f"Could not find email with ID '{message_id}': {e}"

    if not email:
        return f"Email not found with ID: {message_id}"

    return (
        f"DELETE_CONFIRMATION_REQUIRED\n"
        f"Message ID: {message_id}\n"
        f"Subject: {email['subject']}\n"
        f"Sender: {email['sender']}\n"
        f"Date: {email['date']}\n"
        f"\n⚠️  This will move the email to Gmail Trash (recoverable for 30 days).\n"
        f"Reply 'yes' to confirm deletion or 'no' to cancel."
    )


# ============================================================
# Tool 8b: Batch delete emails (safe — confirmation required)
# ============================================================

@tool
def batch_delete_emails(message_ids: list[str]) -> str:
    """
    Request deletion of multiple emails at once (e.g. all promotional emails,
    all newsletters, all emails from a specific sender).

    IMPORTANT: This tool does NOT immediately delete the emails.
    It gathers their details and returns a confirmation request that Python/UI
    presents to the user before any actual deletion occurs.

    Args:
        message_ids: List of exact Gmail Message IDs returned by search_gmail
                     (e.g. ["19fef5058304439a", "19fef2eb4088ef50"])
    """
    if not message_ids:
        return "No message IDs provided to delete."

    service = _get_service()
    email_summaries = []

    for mid in message_ids:
        try:
            email = get_email_details(service, mid)
            if email and email.get("subject"):
                email_summaries.append(f"• [{mid}] {email['subject']} (From: {email['sender']})")
        except Exception:
            email_summaries.append(f"• [{mid}] (Message details unavailable)")

    summary_text = "\n".join(email_summaries)

    return (
        f"BATCH_DELETE_CONFIRMATION_REQUIRED\n"
        f"Count: {len(message_ids)} email(s)\n"
        f"IDs: {','.join(message_ids)}\n\n"
        f"Emails to delete:\n{summary_text}\n\n"
        f"⚠️  This will move all {len(message_ids)} email(s) to Gmail Trash (recoverable for 30 days).\n"
        f"Reply 'yes' to confirm deletion or 'no' to cancel."
    )


# ============================================================
# NOT a LangChain tool — called directly by Python after
# user confirms deletion
# ============================================================

def execute_delete_email(service, message_id: str) -> str:
    """
    Actually delete an email by moving it to Trash. Call this ONLY after explicit
    user confirmation. This is NOT exposed as a Gemini tool.

    Args:
        service: Gmail API service
        message_id: Exact Gmail message ID

    Returns:
        Confirmation string
    """
    try:
        service.users().messages().trash(
            userId="me",
            id=message_id,
        ).execute()
        return f"✓ Email {message_id} has been moved to Trash."
    except Exception as e:
        return f"Deletion failed: {e}"


def execute_batch_delete_emails(service, message_ids: list[str]) -> str:
    """
    Move a list/bunch of emails to Trash at once. Call this ONLY after explicit
    user confirmation.

    Args:
        service: Gmail API service
        message_ids: List of Gmail message IDs

    Returns:
        Summary confirmation string
    """
    if not message_ids:
        return "No emails specified to delete."

    success_count = 0
    errors = []

    for mid in message_ids:
        try:
            service.users().messages().trash(userId="me", id=mid).execute()
            success_count += 1
        except Exception as e:
            errors.append(f"{mid}: {e}")

    result = f"✓ Successfully moved {success_count} email(s) to Gmail Trash."
    if errors:
        result += f" ({len(errors)} failed to trash)"
    return result


# ============================================================
# Tool 9: Inbox overview
# ============================================================

@tool
def get_inbox_overview() -> str:
    """
    Get a quick overview of the inbox: unread count, today's emails
    with previews, and the latest 10 inbox emails.

    Use this when the user asks for:
    - "Give me an inbox overview"
    - "Summarize my inbox"
    - "What's in my inbox?"
    - "Give me today's email digest"
    - "Categorize today's emails"
    - "What emails did I get today?"
    """
    service = _get_service()

    try:
        # Get account info
        profile = service.users().getProfile(userId="me").execute()

        unread_result = service.users().messages().list(
            userId="me",
            labelIds=["INBOX", "UNREAD"],
            maxResults=1,
        ).execute()
        unread_est = unread_result.get("resultSizeEstimate", 0)

        # ---- Today's emails (since midnight 00:00 local time) ----
        from datetime import datetime
        today_midnight = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        midnight_ts = int(today_midnight.timestamp())
        today_query = f"after:{midnight_ts}"

        today_result = service.users().messages().list(
            userId="me",
            labelIds=["INBOX"],
            q=today_query,
            maxResults=25,
        ).execute()

        today_messages = today_result.get("messages", [])
        today_list = []

        for msg in today_messages:
            email = get_email_details(service, msg["id"])
            preview = email.get("body", "")[:200].replace("\n", " ").strip()
            today_list.append(
                f"• [{msg['id']}] {email['subject']}\n"
                f"  From: {email['sender']}\n"
                f"  Date: {email['date']}\n"
                f"  Preview: {preview}"
            )

        # ---- Latest 10 inbox emails (for general context) ----
        inbox_result = service.users().messages().list(
            userId="me",
            labelIds=["INBOX"],
            maxResults=10,
        ).execute()

        latest_messages = inbox_result.get("messages", [])
        latest_list = []

        for msg in latest_messages:
            email = get_email_details(service, msg["id"])
            latest_list.append(
                f"• [{msg['id']}] {email['subject']}\n"
                f"  From: {email['sender']}\n"
                f"  Date: {email['date']}"
            )

        today_section = (
            f"📅 Today's Emails ({len(today_list)}):\n\n"
            + "\n\n".join(today_list)
            if today_list
            else "📅 No emails from today."
        )

        overview = (
            f"📬 Inbox Overview\n"
            f"{'=' * 50}\n"
            f"Account: {profile.get('emailAddress', 'N/A')}\n"
            f"Estimated unread: {unread_est}\n\n"
            f"{today_section}\n\n"
            f"{'=' * 50}\n"
            f"Latest 10 inbox emails:\n\n"
            + "\n\n".join(latest_list)
        )

        return overview

    except Exception as e:
        return f"Failed to get inbox overview: {e}"