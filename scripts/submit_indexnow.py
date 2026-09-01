import os
import sys
import urllib.parse

import requests


PAGE_URL = os.environ.get("PAGE_URL", "https://www.et001.com/gameguide/freegametest.html").strip()
INDEXNOW_KEY = os.environ.get("INDEXNOW_KEY", "").strip()
INDEXNOW_ENDPOINT = os.environ.get("INDEXNOW_ENDPOINT", "https://api.indexnow.org/indexnow").strip()


def main():
    if not INDEXNOW_KEY:
        print("INDEXNOW_KEY is empty; skipped IndexNow submit.")
        return

    parsed = urllib.parse.urlparse(PAGE_URL)
    if not parsed.scheme or not parsed.netloc:
        raise ValueError(f"Invalid PAGE_URL: {PAGE_URL}")

    payload = {
        "host": parsed.netloc,
        "key": INDEXNOW_KEY,
        "keyLocation": f"{parsed.scheme}://{parsed.netloc}/{INDEXNOW_KEY}.txt",
        "urlList": [PAGE_URL],
    }

    response = requests.post(INDEXNOW_ENDPOINT, json=payload, timeout=20)
    print(f"IndexNow response: {response.status_code} {response.text[:300]}")
    if response.status_code not in (200, 202):
        sys.exit(1)


if __name__ == "__main__":
    main()
