from gmail_tools import read_gmail_email


message_id = input(
    "Enter Gmail message ID: "
)

result = read_gmail_email.invoke(
    {
        "message_id": message_id
    }
)

print("\nEMAIL CONTENT")
print("=" * 70)
print(result)