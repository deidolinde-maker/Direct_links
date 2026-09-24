"""Read-only probe for URLs from one Yandex Direct campaign."""

from __future__ import annotations

import json
import argparse
import sys
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from get_campaigns import required_env


API_ROOTS = {
    "v5": "https://api.direct.yandex.com/json/v5",
    "v501": "https://api.direct.yandex.com/json/v501",
}


def post_json(api_root: str, path: str, token: str, login: str, payload: dict) -> dict:
    request = Request(
        f"{api_root}/{path}",
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
        with urlopen(request, timeout=30) as response:
            body = response.read().decode("utf-8")
    except HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Yandex Direct HTTP {exc.code}: {body}") from exc
    except URLError as exc:
        raise RuntimeError(f"Yandex Direct network error: {exc.reason}") from exc

    result = json.loads(body)
    if "error" in result:
        raise RuntimeError(json.dumps(result["error"], ensure_ascii=False))
    return result.get("result", {})


def campaign_info(api_root: str, token: str, login: str, campaign_id: int) -> dict:
    result = post_json(
        api_root,
        "campaigns",
        token,
        login,
        {
            "method": "get",
            "params": {
                "SelectionCriteria": {"Ids": [campaign_id]},
                "FieldNames": ["Id", "Name", "Type", "State", "Status"],
            },
        },
    )
    campaigns = result.get("Campaigns", [])
    if not campaigns:
        raise RuntimeError(f"Campaign {campaign_id} was not found for this login")
    return campaigns[0]


def ad_field_names(campaign_type: str) -> tuple[str, str]:
    mapping = {
        "TEXT_CAMPAIGN": ("TextAdFieldNames", "TextAd"),
        "DYNAMIC_TEXT_CAMPAIGN": ("DynamicTextAdFieldNames", "DynamicTextAd"),
        "UNIFIED_CAMPAIGN": ("ResponsiveAdFieldNames", "ResponsiveAd"),
        "CPM_BANNER_CAMPAIGN": ("CpmBannerAdBuilderAdFieldNames", "CpmBannerAdBuilderAd"),
    }
    try:
        return mapping[campaign_type]
    except KeyError as exc:
        raise RuntimeError(f"Unsupported campaign type for Href probe: {campaign_type}") from exc


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("campaign_id", nargs="?", default="109848388")
    parser.add_argument("--api-version", choices=API_ROOTS, default="v5")
    args = parser.parse_args()
    campaign_id = int(args.campaign_id)
    api_root = API_ROOTS[args.api_version]
    try:
        token = required_env("YANDEX_DIRECT_TOKEN")
        login = required_env("YANDEX_DIRECT_LOGIN")
        campaign = campaign_info(api_root, token, login, campaign_id)
        field_name, nested_name = ad_field_names(campaign["Type"])
        result = post_json(
            api_root,
            "ads",
            token,
            login,
            {
                "method": "get",
                "params": {
                    "SelectionCriteria": {"CampaignIds": [campaign_id]},
                    "FieldNames": ["Id", "CampaignId", "AdGroupId", "State", "Status"],
                    field_name: ["Href"],
                    "Page": {"Limit": 1000, "Offset": 0},
                },
            },
        )
    except (RuntimeError, ValueError, KeyError, json.JSONDecodeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    print(
        f"Campaign: {campaign['Id']}\t{campaign['Name']}\t"
        f"type={campaign['Type']}\tstate={campaign['State']}\tstatus={campaign['Status']}"
    )
    ads = result.get("Ads", [])
    print(f"Ads received: {len(ads)}")
    for ad in ads:
        href = (ad.get(nested_name) or {}).get("Href", "")
        print(
            f"{ad.get('Id')}\tad_group={ad.get('AdGroupId')}\t"
            f"state={ad.get('State')}\tstatus={ad.get('Status')}\thref={href}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
