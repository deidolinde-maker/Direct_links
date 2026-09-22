"""Read-only probe for Yandex Direct campaigns.

The script intentionally does not contain credentials and does not modify
Yandex Direct data. Credentials are read from environment variables used by
Jenkins:
  YANDEX_DIRECT_LOGIN
  YANDEX_DIRECT_TOKEN
"""

from __future__ import annotations

import json
import os
import sys
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


API_URL = "https://api.direct.yandex.com/json/v5/campaigns"
PAGE_LIMIT = 1000


def required_env(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise RuntimeError(f"Required environment variable is missing: {name}")
    return value


def request_page(token: str, login: str, offset: int) -> dict:
    payload = {
        "method": "get",
        "params": {
            "SelectionCriteria": {},
            "FieldNames": [
                "Id",
                "Name",
                "Type",
                "State",
                "Status",
                "StatusPayment",
                "StatusClarification",
            ],
            "Page": {"Limit": PAGE_LIMIT, "Offset": offset},
        },
    }

    headers = {
        "Authorization": f"Bearer {token}",
        "Accept-Language": "ru",
        "Content-Type": "application/json",
    }
    if login:
        headers["Client-Login"] = login

    request = Request(
        API_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers=headers,
        method="POST",
    )

    try:
        with urlopen(request, timeout=30) as response:
            body = response.read().decode("utf-8")
    except HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Yandex Direct HTTP {exc.code}: {body}") from exc
    except URLError as exc:
        raise RuntimeError(f"Yandex Direct network error: {exc.reason}") from exc

    try:
        result = json.loads(body)
    except json.JSONDecodeError as exc:
        raise RuntimeError("Yandex Direct returned invalid JSON") from exc

    if "error" in result:
        raise RuntimeError(f"Yandex Direct API error: {json.dumps(result['error'], ensure_ascii=False)}")
    if "result" not in result:
        raise RuntimeError("Yandex Direct response has no result field")
    return result["result"]


def load_campaigns(token: str, login: str) -> list[dict]:
    campaigns: list[dict] = []
    offset = 0

    while True:
        result = request_page(token, login, offset)
        page = result.get("Campaigns", [])
        campaigns.extend(page)

        limited_by = result.get("LimitedBy")
        if not page or len(page) < PAGE_LIMIT or limited_by is None:
            break
        offset = int(limited_by)

    return campaigns


def main() -> int:
    try:
        token = required_env("YANDEX_DIRECT_TOKEN")
        login = required_env("YANDEX_DIRECT_LOGIN")
        campaigns = load_campaigns(token, login)
    except RuntimeError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    print(f"Campaigns received: {len(campaigns)}")
    for campaign in campaigns:
        print(
            f"{campaign.get('Id')}\t"
            f"{campaign.get('Name', '')}\t"
            f"{campaign.get('Type', '')}\t"
            f"{campaign.get('State', '')}\t"
            f"{campaign.get('Status', '')}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
