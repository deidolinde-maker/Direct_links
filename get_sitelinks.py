"""Read URL addresses from Yandex Direct sitelink sets."""

from __future__ import annotations

import json
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


SITELINKS_API_URL = "https://api.direct.yandex.com/json/v501/sitelinks"
PAGE_LIMIT = 10_000


def request_sitelinks_page(
    token: str,
    login: str,
    sitelink_ids: list[int],
    offset: int,
) -> tuple[list[dict], int | None]:
    payload = {
        "method": "get",
        "params": {
            "SelectionCriteria": {"Ids": sitelink_ids},
            "FieldNames": ["Id"],
            "SitelinkFieldNames": ["Href"],
            "Page": {"Limit": PAGE_LIMIT, "Offset": offset},
        },
    }
    request = Request(
        SITELINKS_API_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {token}",
            "Client-Login": login,
            "Accept-Language": "ru",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urlopen(request, timeout=60) as response:
            body = response.read().decode("utf-8")
    except HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Yandex Direct sitelinks HTTP {exc.code}: {body}") from exc
    except URLError as exc:
        raise RuntimeError(f"Yandex Direct sitelinks network error: {exc.reason}") from exc

    result = json.loads(body)
    if "error" in result:
        raise RuntimeError(f"Yandex Direct sitelinks API error: {json.dumps(result['error'], ensure_ascii=False)}")
    direct_result = result.get("result", {})
    return direct_result.get("SitelinksSets", []), direct_result.get("LimitedBy")


def load_sitelinks(token: str, login: str, sitelink_ids: list[int]) -> list[dict]:
    if not sitelink_ids:
        return []
    result: list[dict] = []
    offset = 0
    while True:
        page, limited_by = request_sitelinks_page(token, login, sitelink_ids, offset)
        result.extend(page)
        if not page or len(page) < PAGE_LIMIT or limited_by is None:
            return result
        offset = int(limited_by)
