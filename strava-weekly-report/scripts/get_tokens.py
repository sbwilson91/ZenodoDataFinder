#!/usr/bin/env python3
"""
Strava OAuth Setup — run this ONCE locally to get your refresh token.

Usage:
  1. Create a Strava API app at https://www.strava.com/settings/api
     - Set "Authorization Callback Domain" to: localhost
  2. pip install requests
  3. python scripts/get_tokens.py
  4. Follow the printed instructions
  5. Copy the output tokens into your GitHub repo secrets
"""

import os
import sys
import webbrowser
import urllib.parse
from http.server import HTTPServer, BaseHTTPRequestHandler
import requests

# ── Fill these in from https://www.strava.com/settings/api ──────────────────
CLIENT_ID     = input("Enter your Strava Client ID:     ").strip()
CLIENT_SECRET = input("Enter your Strava Client Secret: ").strip()

REDIRECT_URI  = "http://localhost:8765/callback"
SCOPES        = "read,activity:read_all"

auth_code = None

class OAuthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        global auth_code
        parsed = urllib.parse.urlparse(self.path)
        params = urllib.parse.parse_qs(parsed.query)

        if "code" in params:
            auth_code = params["code"][0]
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.end_headers()
            self.wfile.write(b"""
                <html><body style='font-family:monospace;background:#080b12;color:#22c55e;padding:40px'>
                <h2>&#10003; Authorised!</h2>
                <p>You can close this window and return to your terminal.</p>
                </body></html>
            """)
        elif "error" in params:
            self.send_response(400)
            self.end_headers()
            self.wfile.write(b"<html><body>Authorization failed.</body></html>")
        else:
            self.send_response(200)
            self.end_headers()

    def log_message(self, *args):
        pass  # suppress server logs


def main():
    auth_url = (
        f"https://www.strava.com/oauth/authorize"
        f"?client_id={CLIENT_ID}"
        f"&response_type=code"
        f"&redirect_uri={urllib.parse.quote(REDIRECT_URI)}"
        f"&approval_prompt=force"
        f"&scope={SCOPES}"
    )

    print("\n── Step 1: Opening Strava auth page in your browser ──────────────")
    print(f"\nIf it doesn't open automatically, visit:\n{auth_url}\n")
    webbrowser.open(auth_url)

    print("── Step 2: Waiting for redirect (localhost:8765)… ─────────────────")
    server = HTTPServer(("localhost", 8765), OAuthHandler)
    server.handle_request()  # handle one request then stop

    if not auth_code:
        print("\n✗ No auth code received. Did you authorise the app?")
        sys.exit(1)

    print(f"\n✓ Auth code received: {auth_code[:12]}…")

    # Exchange code for tokens
    print("\n── Step 3: Exchanging code for tokens… ────────────────────────────")
    resp = requests.post("https://www.strava.com/oauth/token", data={
        "client_id":     CLIENT_ID,
        "client_secret": CLIENT_SECRET,
        "code":          auth_code,
        "grant_type":    "authorization_code",
    })
    resp.raise_for_status()
    tokens = resp.json()

    print("\n" + "═"*60)
    print("  COPY THESE INTO YOUR GITHUB REPO SECRETS")
    print("  (Settings → Secrets and variables → Actions → New secret)")
    print("═"*60)
    print(f"\n  Secret name:   STRAVA_CLIENT_ID")
    print(f"  Secret value:  {CLIENT_ID}")
    print(f"\n  Secret name:   STRAVA_CLIENT_SECRET")
    print(f"  Secret value:  {CLIENT_SECRET}")
    print(f"\n  Secret name:   STRAVA_REFRESH_TOKEN")
    print(f"  Secret value:  {tokens['refresh_token']}")
    print("\n" + "═"*60)
    print(f"\n  Athlete: {tokens['athlete']['firstname']} {tokens['athlete']['lastname']}")
    print(f"  Access token expires: {tokens['expires_at']} (not needed — refresh token is what matters)")
    print("\n✓ Done! The GitHub Action will refresh the token automatically on each run.")


if __name__ == "__main__":
    main()
