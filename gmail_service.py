"""
gmail_service.py
================
Creates and returns an authenticated Gmail API service object.

The scope must match what was used during gmail_auth.py:
    https://www.googleapis.com/auth/gmail.modify

This scope allows:
- Reading emails
- Searching emails
- Marking read/unread
- Starring / archiving
- Deleting emails
- Managing labels

Do NOT change the scope without re-running gmail_auth.py.
"""

import os
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build


# Must match gmail_auth.py
SCOPES = ["https://www.googleapis.com/auth/gmail.modify"]

TOKEN_FILE = "token.json"


def create_gmail_service():
    """
    Create an authenticated Gmail API service.

    Automatically refreshes expired tokens using the refresh token
    stored in token.json.

    Returns:
        Gmail API service object

    Raises:
        FileNotFoundError: If token.json does not exist.
            Run gmail_auth.py first to authenticate.
        google.auth.exceptions.RefreshError: If token refresh fails.
            Run gmail_auth.py again to re-authenticate.
    """
    if not os.path.exists(TOKEN_FILE):
        raise FileNotFoundError(
            f"{TOKEN_FILE} not found.\n"
            "Run: python gmail_auth.py\n"
            "to authenticate with Gmail first."
        )

    creds = Credentials.from_authorized_user_file(
        TOKEN_FILE,
        SCOPES
    )

    # Refresh token if expired
    if creds.expired and creds.refresh_token:
        try:
            creds.refresh(Request())

            # Save the refreshed token
            with open(TOKEN_FILE, "w") as token_file:
                token_file.write(creds.to_json())

        except Exception as e:
            raise RuntimeError(
                f"Token refresh failed: {e}\n"
                "Run: python gmail_auth.py\n"
                "to re-authenticate."
            ) from e

    service = build(
        "gmail",
        "v1",
        credentials=creds
    )

    return service


# ============================================================
# Self-test
# ============================================================

if __name__ == "__main__":
    service = create_gmail_service()
    profile = service.users().getProfile(userId="me").execute()
    print("Gmail connection successful!")
    print("Connected account:", profile["emailAddress"])
    print("Scope: gmail.modify ✓")