"""Read-only probe for ad URLs in Yandex Direct campaigns."""

from __future__ import annotations

import json
import sys
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from get_campaigns import load_campaigns, required_env


ADS_API_URL = "https://api.direct.yandex.com/json/v5/ads"
CAMPAIGN_BATCH_SIZE = 10


def request_ads_page(token: str, login: str, campaign_ids: list[int], offset: int) -> tuple[list[dict], int | None]:
    payload = {
        "method": "get",
        "params": {
            "SelectionCriteria": {"CampaignIds": campaign_ids},
            "FieldNames": ["Id", "CampaignId", "AdGroupId", "State", "Status"],
            "TextAdFieldNames": ["Href"],
            "Page": {"Limit": 1000, "Offset": offset},
        },
    }
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept-Language": "ru",
        "Content-Type": "application/json",
        "Client-Login": login,
    }
    request = Request(
        ADS_API_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers=headers,
        method="POST",
    )

    try:
        with urlopen(request, timeout=30) as response:
            body = response.read().decode("utf-8")
    except HTTPError as exc:
        error_body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Yandex Direct HTTP {exc.code}: {error_body}") from exc
    except URLError as exc:
        raise RuntimeError(f"Yandex Direct network error: {exc.reason}") from exc

    try:
        result = json.loads(body)
    except json.JSONDecodeError as exc:
        raise RuntimeError("Yandex Direct returned invalid JSON") from exc

    if "error" in result:
        raise RuntimeError(f"Yandex Direct API error: {json.dumps(result['error'], ensure_ascii=False)}")
    direct_result = result.get("result", {})
    return direct_result.get("Ads", []), direct_result.get("LimitedBy")


def load_ads(token: str, login: str, campaign_ids: list[int]) -> list[dict]:
    ads: list[dict] = []
    for start in range(0, len(campaign_ids), CAMPAIGN_BATCH_SIZE):
        batch = campaign_ids[start : start + CAMPAIGN_BATCH_SIZE]
        offset = 0
        while True:
            page, limited_by = request_ads_page(token, login, batch, offset)
            ads.extend(page)
            if not page or len(page) < 1000 or limited_by is None:
                break
            offset = int(limited_by)
    return ads


def main() -> int:
    try:
        token = required_env("YANDEX_DIRECT_TOKEN")
        login = required_env("YANDEX_DIRECT_LOGIN")
        campaigns = load_campaigns(token, login)
        campaign_ids = [int(item["Id"]) for item in campaigns if item.get("Id") is not None]
        ads = load_ads(token, login, campaign_ids)
    except (RuntimeError, KeyError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    print(f"Campaigns received: {len(campaign_ids)}")
    print(f"Ads received: {len(ads)}")
    for ad in ads:
        nested = ad.get("TextAd") or ad.get("TextImageAd") or ad.get("ResponsiveAd") or {}
        href = nested.get("Href") or ad.get("Href") or ""
        print(
            f"{ad.get('Id')}\t"
            f"campaign={ad.get('CampaignId')}\t"
            f"ad_group={ad.get('AdGroupId')}\t"
            f"state={ad.get('State')}\t"
            f"status={ad.get('Status')}\t"
            f"href={href}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
