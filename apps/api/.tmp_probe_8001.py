import urllib.error
import urllib.request

for port, path in ((8001, "/api/v1/auth/me"), (3000, "/")):
    try:
        urllib.request.urlopen(
            urllib.request.Request(f"http://127.0.0.1:{port}{path}"),
            timeout=3,
        )
        print(port, "up")
    except urllib.error.HTTPError as e:
        print(port, "HTTP", e.code)
    except Exception as e:
        print(port, "DOWN", type(e).__name__)
