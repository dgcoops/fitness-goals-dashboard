#!/usr/bin/env python3
"""One-off Withings authorisation. Run this on your own computer, not in GitHub.

  python3 scripts/withings_setup.py

It asks for your Withings app's client ID and secret, opens the Withings sign-in
page, catches the reply on this computer, and prints the two values to add as
GitHub secrets. Nothing is saved to disk. Standard library only.
"""
import getpass
import http.server
import json
import secrets
import sys
import urllib.parse
import urllib.request
import webbrowser

PORT = 8765
REDIRECT = f"http://localhost:{PORT}/callback"
TOKEN_URL = "https://wbsapi.withings.net/v2/oauth2"


def main():
    client_id = input("Withings client ID: ").strip()
    client_secret = getpass.getpass("Withings client secret (hidden): ").strip()
    if not client_id or not client_secret:
        sys.exit("Both values are needed.")
    state = secrets.token_urlsafe(16)
    url = "https://account.withings.com/oauth2_user/authorize2?" + urllib.parse.urlencode({
        "response_type": "code", "client_id": client_id, "scope": "user.metrics",
        "redirect_uri": REDIRECT, "state": state})
    result = {}

    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            q = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
            if q.get("state", [""])[0] != state or "code" not in q:
                self.send_response(400); self.end_headers()
                self.wfile.write(b"Unexpected reply. Close this tab and try again.")
                return
            # The code lasts 30 seconds, so swap it for tokens straight away.
            body = urllib.parse.urlencode({
                "action": "requesttoken", "grant_type": "authorization_code", "client_id": client_id,
                "client_secret": client_secret, "code": q["code"][0], "redirect_uri": REDIRECT}).encode()
            with urllib.request.urlopen(urllib.request.Request(TOKEN_URL, data=body), timeout=30) as r:
                result.update(json.load(r))
            ok = result.get("status") == 0
            self.send_response(200); self.end_headers()
            self.wfile.write(b"Done. You can close this tab and go back to the terminal." if ok
                             else b"Withings refused the request. See the terminal.")

        def log_message(self, *args):
            pass

    server = http.server.HTTPServer(("127.0.0.1", PORT), Handler)
    print("\nOpening the Withings sign-in page. Approve access, then come back here.")
    print("If it does not open, paste this into your browser:\n" + url + "\n")
    webbrowser.open(url)
    while not result:
        server.handle_request()

    if result.get("status") != 0:
        sys.exit(f"Withings returned status {result.get('status')}. Check the client ID, secret and callback URL.")
    print("Success. Add these two repository secrets in GitHub, then close this window:\n")
    print("WITHINGS_REFRESH_TOKEN =", result["body"]["refresh_token"])
    print("WITHINGS_TOKEN_KEY     =", secrets.token_urlsafe(32))
    print("\nAlso add WITHINGS_CLIENT_ID and WITHINGS_CLIENT_SECRET with the values you entered.")


if __name__ == "__main__":
    main()
