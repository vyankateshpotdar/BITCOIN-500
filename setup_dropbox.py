"""Authorize the bot to upload Blogger charts to Dropbox and obtain a refresh token."""

from getpass import getpass
from urllib.parse import urlencode
import webbrowser

import requests


SCOPES = "account_info.read files.metadata.read files.content.write sharing.write"


def main():
    app_key = input("Dropbox app key: ").strip()
    app_secret = getpass("Dropbox app secret (input hidden): ").strip()
    if not app_key or not app_secret:
        raise SystemExit("Both Dropbox app key and secret are required.")

    authorize_url = "https://www.dropbox.com/oauth2/authorize?" + urlencode({
        "client_id": app_key,
        "response_type": "code",
        "token_access_type": "offline",
        "scope": SCOPES,
    })
    webbrowser.open(authorize_url)
    print("\nApprove the BITCOIN 500 app in Dropbox. Copy the authorization code shown afterward.")
    code = input("Dropbox authorization code: ").strip()
    response = requests.post(
        "https://api.dropbox.com/oauth2/token",
        data={
            "code": code,
            "grant_type": "authorization_code",
            "client_id": app_key,
            "client_secret": app_secret,
        },
        timeout=20,
    )
    response.raise_for_status()
    tokens = response.json()
    refresh_token = tokens.get("refresh_token")
    if not refresh_token:
        raise SystemExit("Dropbox returned no refresh token. Re-run authorization and approve offline access.")

    print("\nAdd these values to Koyeb Secrets (keep them private):")
    print(f"DROPBOX_APP_KEY={app_key}")
    print(f"DROPBOX_APP_SECRET={app_secret}")
    print(f"DROPBOX_REFRESH_TOKEN={refresh_token}")
    print("\nThe bot needs these Dropbox app scopes:")
    print(SCOPES)


if __name__ == "__main__":
    main()
