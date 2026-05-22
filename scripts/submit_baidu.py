import os
import sys

import requests


PAGE_URL = os.environ.get("PAGE_URL", "https://www.et001.com/gameguide/freegametest.html").strip()
BAIDU_PUSH_ENDPOINT = os.environ.get("BAIDU_PUSH_ENDPOINT", "").strip()


def main():
    if not BAIDU_PUSH_ENDPOINT:
        print("BAIDU_PUSH_ENDPOINT is empty; skipped Baidu submit.")
        return

    response = requests.post(
        BAIDU_PUSH_ENDPOINT,
        data=(PAGE_URL + "\n").encode("utf-8"),
        headers={"Content-Type": "text/plain"},
        timeout=20,
    )
    print(f"Baidu response: {response.status_code} {response.text[:500]}")
    if response.status_code >= 400:
        sys.exit(1)


if __name__ == "__main__":
    main()
