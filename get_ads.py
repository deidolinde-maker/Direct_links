"""Read-only probe for ad URLs in Yandex Direct campaigns."""

from __future__ import annotations

import json
import sys
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from get_campaigns import load_campaigns, required_env


ADS_API_URL = "https://api.direct.yandex.com/json/v5/ads"
CAMPAIGN_BATCH_SIZE = 10

AD_FIELD_SPECS = {
    "TEXT_CAMPAIGN": ("TextAdFieldNames", "TextAd"),
    "DYNAMIC_TEXT_CAMPAIGN": ("DynamicTextAdFieldNames", "DynamicTextAd"),
    "UNIFIED_CAMPAIGN": ("ResponsiveAdFieldNames", "ResponsiveAd"),
    "CPM_BANNER_CAMPAIGN": ("CpmBannerAdBuilderAdFieldNames", "CpmBannerAdBuilderAd"),
    "SMART_CAMPAIGN": ("SmartAdBuilderAdFieldNames", "SmartAdBuilderAd"),
    "MOBILE_APP_CAMPAIGN": ("MobileAppAdFieldNames", "MobileAppAd"),
}


def request_ads_page(
    token: str,
    login: str,
    campaign_ids: list[int],
    offset: int,
    field_name: str = "TextAdFieldNames",
) -> tuple[list[dict], int | None]:
    payload = {
        "method": "get",
        "params": {
            "SelectionCriteria": {"CampaignIds": campaign_ids},
            "FieldNames": ["Id", "CampaignId", "AdGroupId", "State", "Status"],
            field_name: ["Href"],
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


def load_ads(
    token: str,
    login: str,
    campaign_ids: list[int],
    campaign_types: dict[int, str] | None = None,
) -> list[dict]:
    ads: list[dict] = []
    grouped_ids: dict[str, list[int]] = {}
    for campaign_id in campaign_ids:
        campaign_type = (campaign_types or {}).get(campaign_id, "TEXT_CAMPAIGN")
        field_name = AD_FIELD_SPECS.get(campaign_type, ("TextAdFieldNames", "TextAd"))[0]
        grouped_ids.setdefault(field_name, []).append(campaign_id)

    for field_name, typed_campaign_ids in grouped_ids.items():
        for start in range(0, len(typed_campaign_ids), CAMPAIGN_BATCH_SIZE):
            batch = typed_campaign_ids[start : start + CAMPAIGN_BATCH_SIZE]
            offset = 0
            while True:
                page, limited_by = request_ads_page(token, login, batch, offset, field_name)
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
        active_campaigns = [
            item
            for item in campaigns
            if item.get("State") == "ON" and item.get("Status") == "ACCEPTED"
        ]
        campaign_types = {
            int(item["Id"]): item.get("Type", "TEXT_CAMPAIGN")
            for item in active_campaigns
            if item.get("Id") is not None
        }
        campaign_ids = list(campaign_types)
        ads = load_ads(token, login, campaign_ids, campaign_types)
    except (RuntimeError, KeyError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    print(f"Campaigns received: {len(campaigns)}")
    print(f"Active campaigns: {len(campaign_ids)}")
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
