from read_emails import get_latest_emails, get_email_details
from email_ai import analyze_email


def run_email_agent(max_results: int = 5):
    """Fetch and analyze recent emails."""
    service, messages = get_latest_emails(max_results)
    print(f"Analyzing {len(messages)} recent emails...\n")

    for index, message in enumerate(messages, start=1):
        email = get_email_details(service, message["id"])
        print(f"[{index}] {email.get('subject')} | From: {email.get('sender')}")
        analysis = analyze_email(
            sender=email.get("sender", ""),
            subject=email.get("subject", ""),
            body=email.get("body", "")
        )
        print(analysis)
        print("-" * 50)


if __name__ == "__main__":
    run_email_agent(max_results=5)