"""
Google Drive OAuth2 setup — run ONCE to generate token.json.

Usage:
    python setup_drive.py

This opens a browser for Google OAuth2 authorization and saves token.json
in the same directory as the service account file (GOOGLE_SERVICE_ACCOUNT_FILE).
After this, the app uses the token automatically (auto-refreshed).

For production, prefer Service Account (set GOOGLE_SERVICE_ACCOUNT_FILE in .env).
"""
from pathlib import Path

SCOPES = ["https://www.googleapis.com/auth/drive.file"]


def _credentials_dir() -> Path:
    """Return the directory where credentials live (same as service account file)."""
    try:
        from config import settings
        sa = settings.google_service_account_file
        if sa:
            return Path(sa).parent
    except Exception:
        pass
    return Path(".")


def main():
    from google_auth_oauthlib.flow import InstalledAppFlow
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials

    creds_dir  = _credentials_dir()
    token_path = creds_dir / "token.json"
    oauth_creds_path = creds_dir / "credentials.json"

    creds = None
    if token_path.exists():
        creds = Credentials.from_authorized_user_file(str(token_path), SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            print("Refreshing expired token...")
            creds.refresh(Request())
        else:
            if not oauth_creds_path.exists():
                print(f"ERROR: credentials.json not found at {oauth_creds_path}")
                print("Download it from: Google Cloud Console → APIs & Services → Credentials")
                return

            flow = InstalledAppFlow.from_client_secrets_file(str(oauth_creds_path), SCOPES)
            creds = flow.run_local_server(port=0)

        token_path.write_text(creds.to_json())
        print(f"token.json saved → {token_path}")

    # Test connection
    from googleapiclient.discovery import build
    service = build("drive", "v3", credentials=creds)
    about   = service.about().get(fields="user").execute()
    print(f"✅ Connected as: {about['user']['emailAddress']}")
    print("You can now run the app — Drive is ready.")


if __name__ == "__main__":
    main()
