"""Route check for the set-password page. Not a browser session."""

import time
import urllib.request

time.sleep(5)
for path in ("/login", "/set-password"):
    url = "http://127.0.0.1:3000" + path
    try:
        with urllib.request.urlopen(url, timeout=20) as res:
            body = res.read().decode("utf-8", errors="replace")
            markers = [
                name
                for name, needle in (
                    ("heading", "Choose a password"),
                    ("testid", "set-password-new"),
                    ("signin", "Sign in"),
                    ("login-email", "login-email"),
                    ("chunk", "set-password/page"),
                )
                if needle in body
            ]
            print(path, res.status, "bytes", len(body), "markers", ",".join(markers) or "none")
    except Exception as exc:
        print(path, type(exc).__name__)
