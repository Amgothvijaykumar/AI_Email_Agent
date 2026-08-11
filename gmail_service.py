import os
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build

SCOPES = ["https://www.googleapis.com/auth/gmail.modify"]
TOKEN_FILE = "token.json"


def create_gmail_service():
    """Authenticate and return the Gmail API client service."""
    if not os.path.exists(TOKEN_FILE):
        raise FileNotFoundError(
            f"{TOKEN_FILE} not found. Run 'python gmail_auth.py' to authenticate."
        )

    creds = Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)

    if creds.expired and creds.refresh_token:
        try:
            creds.refresh(Request())
            with open(TOKEN_FILE, "w") as token_file:
                token_file.write(creds.to_json())
        except Exception as e:
            raise RuntimeError(f"Token refresh failed: {e}. Run 'python gmail_auth.py'.") from e

    return build("gmail", "v1", credentials=creds)


if __name__ == "__main__":
    service = create_gmail_service()
    profile = service.users().getProfile(userId="me").execute()
    print("Connected account:", profile.get("emailAddress"))