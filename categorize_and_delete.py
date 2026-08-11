from datetime import datetime
from dotenv import load_dotenv
from langchain_core.messages import HumanMessage, SystemMessage
from read_emails import search_emails, get_email_details
from gmail_service import create_gmail_service
from gmail_tools import execute_batch_delete_emails
from gemini_client import invoke_with_fallback, extract_text

load_dotenv()

CATEGORIES = ["Jobs", "Finance", "Promotions", "Social", "Security", "Personal", "Important", "Other"]
CATEGORY_ICONS = {
    "Jobs": "💼", "Finance": "💰", "Promotions": "🛍️", "Social": "👥",
    "Security": "🔒", "Personal": "💌", "Important": "⭐", "Other": "📧"
}


def categorize_email(sender: str, subject: str, body: str) -> tuple[str, str]:
    """Classify email into category and provide a one-sentence rationale."""
    prompt = f"Categorize into ONE of: {', '.join(CATEGORIES)}\n\nFrom: {sender}\nSubject: {subject}\nBody: {body[:400]}\n\nFormat:\nCategory: <Category>\nReason: <One sentence>"
    try:
        response = invoke_with_fallback([
            SystemMessage(content="You are an email classifier. Output only the requested format."),
            HumanMessage(content=prompt)
        ])
        lines = extract_text(response).strip().splitlines()
        category = "Other"
        reason = ""
        for line in lines:
            if line.startswith("Category:"):
                raw = line.replace("Category:", "").strip()
                for c in CATEGORIES:
                    if c.lower() in raw.lower():
                        category = c
                        break
            elif line.startswith("Reason:"):
                reason = line.replace("Reason:", "").strip()
        return category, reason
    except Exception as e:
        return "Other", str(e)


def fetch_todays_emails(service, max_results: int = 30) -> list[dict]:
    """Retrieve emails received since midnight today in local time."""
    today_midnight = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    query = f"after:{int(today_midnight.timestamp())}"
    _, messages = search_emails(query, max_results=max_results)
    return [get_email_details(service, msg["id"]) for msg in messages]


def main():
    service = create_gmail_service()
    print("Fetching today's emails...")
    emails = fetch_todays_emails(service, max_results=30)
    if not emails:
        print("No emails found from today.")
        return

    print(f"Analyzing {len(emails)} emails with Gemini...\n")
    categorized = {cat: [] for cat in CATEGORIES}

    for i, email in enumerate(emails, 1):
        cat, reason = categorize_email(email.get("sender", ""), email.get("subject", ""), email.get("body", ""))
        email["_category"] = cat
        email["_reason"] = reason
        categorized[cat].append(email)
        print(f"[{i}/{len(emails)}] {email.get('subject', '')[:50]} -> {CATEGORY_ICONS.get(cat, '')} {cat}")

    print("\n" + "=" * 50)
    numbered = []
    for cat in CATEGORIES:
        items = categorized[cat]
        if not items:
            continue
        print(f"\n{CATEGORY_ICONS.get(cat, '')} {cat.upper()} ({len(items)})")
        for item in items:
            idx = len(numbered) + 1
            numbered.append(item)
            print(f"  [{idx}] {item.get('subject', '')[:50]} | From: {item.get('sender', '').split('<')[0].strip()}")

    print("\nEnter email numbers to delete (e.g. 1,3,5) or category name (e.g. Promotions).")
    choice = input("Choice (or 'q' to quit): ").strip()
    if choice.lower() in ["q", "quit", ""]:
        print("No emails deleted.")
        return

    to_delete_ids = []
    for part in choice.split(","):
        p = part.strip()
        matched = [c for c in CATEGORIES if c.lower() == p.lower()]
        if matched:
            to_delete_ids.extend([e["id"] for e in categorized[matched[0]]])
        else:
            try:
                n = int(p) - 1
                if 0 <= n < len(numbered):
                    to_delete_ids.append(numbered[n]["id"])
            except ValueError:
                pass

    to_delete_ids = list(set(to_delete_ids))
    if not to_delete_ids:
        print("No matching emails selected.")
        return

    confirm = input(f"\nMove {len(to_delete_ids)} email(s) to Trash? (yes/no): ").strip().lower()
    if confirm == "yes":
        res = execute_batch_delete_emails(service, to_delete_ids)
        print(res)
    else:
        print("Cancelled.")


if __name__ == "__main__":
    main()
