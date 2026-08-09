from read_emails import search_emails, get_email_details


query = "subject:job"

service, messages = search_emails(
    query,
    max_results=10
)

print(f"Search query: {query}")
print(f"Found {len(messages)} emails\n")

for index, message in enumerate(messages, start=1):

    email = get_email_details(
        service,
        message["id"]
    )

    print("=" * 70)
    print(f"EMAIL {index}")
    print("=" * 70)

    print("Sender:", email["sender"])
    print("Subject:", email["subject"])
    print("Date:", email["date"])

    print("\nBody:")
    
    if email["body"]:
        print(email["body"][:1000])
    else:
        print("[No readable body found]")

    print()