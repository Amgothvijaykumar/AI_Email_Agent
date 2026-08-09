from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]


def create_gmail_service():
    creds = Credentials.from_authorized_user_file(
        "token.json",
        SCOPES
    )

    service = build(
        "gmail",
        "v1",
        credentials=creds
    )

    return service


if __name__ == "__main__":
    service = create_gmail_service()

    profile = service.users().getProfile(userId="me").execute()

    print("Gmail connection successful!")
    print("Connected account:", profile["emailAddress"])