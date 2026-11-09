"""Authorize BITCOIN 500 to publish Blogger posts and show the required settings."""

import json
from pathlib import Path

import requests
from google_auth_oauthlib.flow import InstalledAppFlow


SCOPES = ["https://www.googleapis.com/auth/blogger"]
CLIENT_FILE = Path(__file__).with_name("client_secret.json")


def main():
    if not CLIENT_FILE.is_file():
        raise SystemExit(
            "Download an OAuth client JSON for a Desktop app from Google Cloud, "
            "save it next to this script as client_secret.json, then run again."
        )

    client_config = json.loads(CLIENT_FILE.read_text())
    app_config = client_config.get("installed")
    if not app_config:
        raise SystemExit("Use an OAuth client of type Desktop app; client_secret.json must contain 'installed'.")

    flow = InstalledAppFlow.from_client_secrets_file(str(CLIENT_FILE), SCOPES)
    credentials = flow.run_local_server(
        host="127.0.0.1",
        port=0,
        open_browser=True,
        access_type="offline",
        prompt="consent",
    )

    response = requests.get(
        "https://www.googleapis.com/blogger/v3/users/self/blogs",
        headers={"Authorization": f"Bearer {credentials.token}"},
        timeout=20,
    )
    response.raise_for_status()
    blogs = response.json().get("items", [])
    if not blogs:
        raise SystemExit("No Blogger blogs were found for the Google account you authorized.")

    print("\nAvailable Blogger blogs:")
    for index, blog in enumerate(blogs, 1):
        print(f"{index}. {blog.get('name', '(untitled)')} — {blog.get('url', '')}")

    while True:
        selection = input("Choose the blog number to receive BTC updates: ").strip()
        if selection.isdigit() and 1 <= int(selection) <= len(blogs):
            blog = blogs[int(selection) - 1]
            break
        print("Enter one of the listed numbers.")

    print("\nAdd these values in Koyeb Secrets / environment variables (keep them private):")
    print(f"BLOGGER_CLIENT_ID={app_config['client_id']}")
    print(f"BLOGGER_CLIENT_SECRET={app_config['client_secret']}")
    print(f"BLOGGER_REFRESH_TOKEN={credentials.refresh_token}")
    print(f"BLOGGER_BLOG_ID={blog['id']}")
    print("BLOGGER_ENABLED=true")


if __name__ == "__main__":
    main()
