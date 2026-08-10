"""
categorize_and_delete.py
========================
Fetch today's emails, categorize them with Gemini,
let you choose which ones to delete, then confirm
before each deletion.

Flow:
    1. Fetch today's emails from Gmail
    2. Categorize each email using Gemini
    3. Display emails grouped by category
    4. You pick which emails/categories to delete
    5. Confirm each deletion individually
    6. Delete only after your 'yes'

Run:
    source avkve/bin/activate
    python categorize_and_delete.py

Emails go to Trash — recoverable within 30 days.
"""

import os
from datetime import datetime, timezone
from dotenv import load_dotenv

from read_emails import search_emails, get_email_details
from gmail_service import create_gmail_service
from gmail_tools import execute_delete_email
from gemini_client import invoke_with_fallback, extract_text

from langchain_core.messages import HumanMessage, SystemMessage

load_dotenv()


# ============================================================
# Categories
# ============================================================

CATEGORIES = [
    "Jobs",
    "Finance",
    "Promotions",
    "Social",
    "Security",
    "Personal",
    "Important",
    "Other",
]

CATEGORY_COLORS = {
    "Jobs":       "💼",
    "Finance":    "💰",
    "Promotions": "🛍️",
    "Social":     "👥",
    "Security":   "🔒",
    "Personal":   "💌",
    "Important":  "⭐",
    "Other":      "📧",
}


# ============================================================
# Categorize a single email with Gemini
# ============================================================

def categorize_email(sender: str, subject: str, body: str) -> tuple[str, str]:
    """
    Use Gemini to categorize an email.

    Returns:
        (category, reason) tuple
    """
    prompt = f"""Categorize this email into EXACTLY ONE of these categories:
Jobs, Finance, Promotions, Social, Security, Personal, Important, Other

Email:
From: {sender}
Subject: {subject}
Body preview: {body[:500]}

Reply in this EXACT format (no extra text):
Category: <one of the categories above>
Reason: <one short sentence>"""

    try:
        response = invoke_with_fallback([
            SystemMessage(content="You are an email categorizer. Be concise."),
            HumanMessage(content=prompt),
        ])

        text = extract_text(response)
        lines = text.strip().splitlines()

        category = "Other"
        reason = ""

        for line in lines:
            if line.startswith("Category:"):
                raw = line.replace("Category:", "").strip()
                # Match to known categories
                for cat in CATEGORIES:
                    if cat.lower() in raw.lower():
                        category = cat
                        break
            elif line.startswith("Reason:"):
                reason = line.replace("Reason:", "").strip()

        return category, reason

    except Exception as e:
        return "Other", f"(categorization failed: {e})"


# ============================================================
# Fetch today's emails
# ============================================================

def fetch_todays_emails(service, max_results: int = 30) -> list[dict]:
    """
    Fetch emails received today (using Gmail's newer_than:1d filter).
    """
    _, messages = search_emails("newer_than:1d", max_results=max_results)

    emails = []
    for msg in messages:
        email = get_email_details(service, msg["id"])
        emails.append(email)

    return emails


# ============================================================
# Main
# ============================================================

def main():
    service = create_gmail_service()

    print()
    print("=" * 62)
    print("  Categorize & Delete — Today's Emails")
    print("=" * 62)
    print()

    # -------------------------------------------------------
    # Step 1: Fetch today's emails
    # -------------------------------------------------------
    print("📬 Fetching today's emails...")
    emails = fetch_todays_emails(service, max_results=30)

    if not emails:
        print("No emails found from today.")
        return

    print(f"Found {len(emails)} emails from today.\n")

    # -------------------------------------------------------
    # Step 2: Categorize with Gemini
    # -------------------------------------------------------
    print("🤖 Categorizing with Gemini (this may take a moment)...\n")

    categorized: dict[str, list[dict]] = {cat: [] for cat in CATEGORIES}

    for i, email in enumerate(emails, start=1):
        subject = email.get("subject", "(No Subject)")
        sender  = email.get("sender", "")
        body    = email.get("body", "")

        print(f"  [{i}/{len(emails)}] {subject[:55]}", end="", flush=True)

        category, reason = categorize_email(sender, subject, body)

        email["_category"] = category
        email["_reason"]   = reason
        categorized[category].append(email)

        icon = CATEGORY_COLORS.get(category, "📧")
        print(f" → {icon} {category}")

    # -------------------------------------------------------
    # Step 3: Display by category
    # -------------------------------------------------------
    print()
    print("=" * 62)
    print("  📂 EMAIL CATEGORIES")
    print("=" * 62)

    # Index each email for easy selection (number → email)
    numbered: list[dict] = []

    for category in CATEGORIES:
        emails_in_cat = categorized[category]
        if not emails_in_cat:
            continue

        icon = CATEGORY_COLORS.get(category, "📧")
        print(f"\n{icon} {category.upper()} ({len(emails_in_cat)} emails)")
        print("-" * 50)

        for email in emails_in_cat:
            n = len(numbered) + 1
            numbered.append(email)

            subject = email.get("subject", "(No Subject)")
            sender  = email.get("sender", "").split("<")[0].strip()
            date    = email.get("date", "")
            reason  = email.get("_reason", "")

            print(f"  [{n}] {subject[:50]}")
            print(f"       From: {sender[:40]}")
            print(f"       Date: {date[:40]}")
            if reason:
                print(f"       Why:  {reason[:60]}")
            print()

    if not numbered:
        print("No emails to display.")
        return

    # -------------------------------------------------------
    # Step 4: Let user pick which to delete
    # -------------------------------------------------------
    print("=" * 62)
    print("  🗑️  SELECT EMAILS TO DELETE")
    print("=" * 62)
    print()
    print("Enter numbers to delete (comma-separated), e.g.:  1,3,7")
    print("Or enter a category name to delete all in that category.")
    print("Examples:")
    print("  1,2,5          → delete emails 1, 2 and 5")
    print("  Promotions     → delete all Promotions emails")
    print("  Jobs,Other     → delete all Jobs and Other emails")
    print("  q              → quit without deleting anything")
    print()

    choice = input("Your choice: ").strip()

    if choice.lower() in ("q", "quit", "exit", ""):
        print("\nNo emails deleted. Goodbye!")
        return

    # Parse selection
    to_delete: list[dict] = []

    for part in choice.split(","):
        part = part.strip()

        # Category name
        matched_cat = None
        for cat in CATEGORIES:
            if cat.lower() == part.lower():
                matched_cat = cat
                break

        if matched_cat:
            to_delete.extend(categorized[matched_cat])
            print(f"  + Selected all {len(categorized[matched_cat])} {matched_cat} emails")
        else:
            # Try as number
            try:
                idx = int(part) - 1
                if 0 <= idx < len(numbered):
                    to_delete.append(numbered[idx])
                else:
                    print(f"  ⚠️  Number {part} is out of range (1–{len(numbered)})")
            except ValueError:
                print(f"  ⚠️  '{part}' is not a valid number or category name")

    # Deduplicate by message ID
    seen_ids = set()
    unique_to_delete = []
    for email in to_delete:
        if email["id"] not in seen_ids:
            seen_ids.add(email["id"])
            unique_to_delete.append(email)

    if not unique_to_delete:
        print("\nNothing selected to delete.")
        return

    # -------------------------------------------------------
    # Step 5: Confirm and delete each one
    # -------------------------------------------------------
    print()
    print("=" * 62)
    print(f"  ⚠️  CONFIRM DELETION ({len(unique_to_delete)} emails selected)")
    print("=" * 62)
    print()

    deleted = []
    skipped = []

    for email in unique_to_delete:
        subject  = email.get("subject", "(No Subject)")
        sender   = email.get("sender", "")
        date     = email.get("date", "")
        category = email.get("_category", "?")
        icon     = CATEGORY_COLORS.get(category, "📧")

        print(f"{icon} {subject}")
        print(f"   From     : {sender}")
        print(f"   Date     : {date}")
        print(f"   Category : {category}")
        print(f"   ID       : {email['id']}")
        print()

        confirm = input("   Delete this email? (yes / no / quit): ").strip().lower()
        print()

        if confirm == "yes":
            result = execute_delete_email(service, email["id"])
            print(f"   ✅ {result}\n")
            deleted.append(email)
        elif confirm in ("quit", "q"):
            print("   Stopping. Remaining emails were NOT deleted.\n")
            break
        else:
            print("   ⏭️  Skipped.\n")
            skipped.append(email)

    # -------------------------------------------------------
    # Step 6: Summary
    # -------------------------------------------------------
    print("=" * 62)
    print("  DONE")
    print("=" * 62)
    print(f"  ✅ Deleted : {len(deleted)} emails")
    print(f"  ⏭️  Skipped : {len(skipped)} emails")
    print()
    if deleted:
        print("  Deleted emails are in Gmail Trash.")
        print("  You can recover them within 30 days.")
    print()


if __name__ == "__main__":
    main()
