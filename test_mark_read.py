from gmail_tools import mark_email_as_read

message_id = input("Enter Gmail message ID: ")

result = mark_email_as_read.invoke(
    {
        "message_id": message_id
    }
)

print("\nRESULT:")
print(result)