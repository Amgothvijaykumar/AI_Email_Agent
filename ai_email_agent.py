from gmail_service import create_gmail_service
from read_emails import get_latest_emails, get_email_details
from email_ai import analyze_email


def run_email_agent(max_results=5):

    # Get Gmail connection and latest emails
    service, messages = get_latest_emails(max_results)

    print(f"Found {len(messages)} emails\n")

    for index, message in enumerate(messages, start=1):

        # Get complete email details
        email = get_email_details(
            service,
            message["id"]
        )

        print("=" * 70)
        print(f"EMAIL {index}")
        print("=" * 70)

        print("Sender:", email["sender"])
        print("Subject:", email["subject"])

        # Analyze email using Gemini
        analysis = analyze_email(
            sender=email["sender"],
            subject=email["subject"],
            body=email["body"]
        )

        print("\nAI ANALYSIS:")
        print(analysis)

        print()


if __name__ == "__main__":
    run_email_agent(max_results=5)