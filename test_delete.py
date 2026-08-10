"""
test_delete.py
==============
Test the delete email flow safely.

This script:
1. Searches for an email by your query
2. Shows you the matching email details
3. Asks for confirmation before deleting
4. Deletes ONLY after you type 'yes'

Run:
    source avkve/bin/activate
    python test_delete.py

The email goes to Gmail Trash (not permanently deleted).
You can recover it from Trash within 30 days.
"""

from read_emails import search_emails, get_email_details
from gmail_service import create_gmail_service
from gmail_tools import execute_delete_email


print("=" * 60)
print("  Delete Email Test")
print("=" * 60)
print()
print("This moves an email to Trash. Recoverable within 30 days.")
print()

# Step 1: Search
query = input("Search query (e.g. 'subject:testing from:vijay'): ").strip()
if not query:
    query = "subject:testing"

print(f"\nSearching for: '{query}'...")
service, messages = search_emails(query, max_results=5)

if not messages:
    print("No emails found. Try a different query.")
    exit(0)

print(f"\nFound {len(messages)} email(s):\n")

# Step 2: Show results
for i, msg in enumerate(messages, start=1):
    email = get_email_details(service, msg["id"])
    print(f"{i}. Message ID: {msg['id']}")
    print(f"   Subject : {email['subject']}")
    print(f"   Sender  : {email['sender']}")
    print(f"   Date    : {email['date']}")
    print()

# Step 3: Pick which one to delete
if len(messages) == 1:
    chosen = messages[0]
    print(f"Only one result found. Using: {chosen['id']}")
else:
    num = input("Enter the number of the email to delete (or 'q' to quit): ").strip()
    if num.lower() == 'q':
        print("Cancelled.")
        exit(0)
    try:
        idx = int(num) - 1
        chosen = messages[idx]
    except (ValueError, IndexError):
        print("Invalid selection. Exiting.")
        exit(1)

# Step 4: Confirm
email = get_email_details(service, chosen["id"])
print()
print("=" * 60)
print("  DELETION CONFIRMATION")
print("=" * 60)
print(f"Message ID : {chosen['id']}")
print(f"Subject    : {email['subject']}")
print(f"Sender     : {email['sender']}")
print(f"Date       : {email['date']}")
print()
print("⚠️  This will move the email to Trash.")
print("   You can recover it from Gmail Trash within 30 days.")
print()

confirm = input("Type 'yes' to delete, anything else to cancel: ").strip().lower()

if confirm == "yes":
    result = execute_delete_email(service, chosen["id"])
    print(f"\n{result}")
    print("\nCheck Gmail Trash to verify or recover the email.")
else:
    print("\nCancelled. No emails were deleted.")
