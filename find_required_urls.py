"""Locate required landing-page domains in all accessible Direct objects."""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit

from direct_logins import required_logins
from export_campaign_urls import request_report
from get_ads import AD_FIELD_SPECS, load_ads
from get_campaigns import load_campaigns, required_env
from get_sitelinks import load_sitelinks


def read_domains(path: Path) -> set[str]:
    domains = set()
    for line in path.read_text(encoding="utf-8").splitlines():
        value = line.split("#", 1)[0].strip().lower()
        if value:
            domains.add(value.removeprefix("www."))
    if not domains:
        raise RuntimeError(f"No required domains found in {path}")
    return domains


def matches_domain(url: str, domains: set[str]) -> bool:
    host = urlsplit(url.strip()).hostname or ""
    host = host.lower().removeprefix("www.")
    return host in domains or any(host.endswith(f".{domain}") for domain in domains)


def nested_ad(ad: dict) -> dict:
    return next(
        (
            ad.get(name)
            for name in (
                "TextAd",
                "DynamicTextAd",
                "TextImageAd",
                "ResponsiveAd",
                "CpmBannerAdBuilderAd",
                "SmartAdBuilderAd",
                "MobileAppAd",
            )
            if ad.get(name)
        ),
        {},
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--domains-file", default="required_domains.txt")
    parser.add_argument("--date-range", choices=("LAST_7_DAYS", "LAST_30_DAYS", "ALL_TIME"), default="LAST_7_DAYS")
    parser.add_argument("--output", default="required_urls.json")
    args = parser.parse_args()

    try:
        token = required_env("YANDEX_DIRECT_TOKEN")
        logins = required_logins()
        domains = read_domains(Path(args.domains_file))
        matches: list[dict] = []
        seen: set[tuple[str, str, str, str]] = set()

        def add_match(url: str, source: str, login: str, campaign: dict, **extra: object) -> None:
            url = url.strip()
            if not url or not matches_domain(url, domains):
                return
            key = (login, source, str(extra.get("ad_id", extra.get("sitelink_set_id", ""))), url)
            if key in seen:
                return
            seen.add(key)
            matches.append(
                {
                    "url": url,
                    "source": source,
                    "login": login,
                    "campaign_id": str(campaign.get("Id", extra.get("campaign_id", ""))),
                    "campaign_name": campaign.get("Name", ""),
                    "campaign_type": campaign.get("Type", ""),
                    "campaign_state": campaign.get("State", ""),
                    "campaign_status": campaign.get("Status", ""),
                    "campaign_status_payment": campaign.get("StatusPayment", ""),
                    **extra,
                }
            )

        for login in logins:
            campaigns = load_campaigns(token, login)
            by_id = {int(item["Id"]): item for item in campaigns if item.get("Id") is not None}
            campaign_types = {campaign_id: item.get("Type", "TEXT_CAMPAIGN") for campaign_id, item in by_id.items()}
            ads = load_ads(token, login, list(by_id), campaign_types, active_only=False)
            sitelink_ids: set[int] = set()
            sitelink_campaign_ids: dict[int, set[int]] = {}
            for ad in ads:
                nested = nested_ad(ad)
                campaign = by_id.get(int(ad.get("CampaignId", 0)), {})
                href = nested.get("Href") or ad.get("Href") or ""
                add_match(
                    href,
                    "ad",
                    login,
                    campaign,
                    ad_id=str(ad.get("Id", "")),
                    ad_state=ad.get("State", ""),
                    ad_status=ad.get("Status", ""),
                )
                if nested.get("SitelinkSetId") is not None:
                    sitelink_id = int(nested["SitelinkSetId"])
                    sitelink_ids.add(sitelink_id)
                    sitelink_campaign_ids.setdefault(sitelink_id, set()).add(int(ad.get("CampaignId", 0)))

            for sitelink_set in load_sitelinks(token, login, sorted(sitelink_ids)):
                sitelink_id = int(sitelink_set.get("Id", 0))
                for sitelink in sitelink_set.get("Sitelinks", []):
                    for campaign_id in sitelink_campaign_ids.get(sitelink_id, set()):
                        add_match(
                            sitelink.get("Href", ""),
                            "sitelink",
                            login,
                            by_id.get(campaign_id, {}),
                            sitelink_set_id=str(sitelink_id),
                        )

            for attempt in range(1, 6):
                status, body, headers = request_report(token, login, args.date_range)
                if status == 200:
                    break
                if status in (201, 202) and attempt < 5:
                    time.sleep(int(headers.get("retryIn", "60")))
                    continue
                raise RuntimeError(f"Reports API returned HTTP {status}: {body}")
            lines = [line for line in body.splitlines() if line.strip()]
            if lines and lines[0].startswith("CampaignId"):
                lines = lines[1:]
            for line in lines:
                columns = line.split("\t")
                if len(columns) < 5:
                    continue
                campaign_id, name, kind, url, impressions = columns[:5]
                campaign = by_id.get(int(campaign_id), {"Id": campaign_id, "Name": name, "Type": kind})
                add_match(url, "campaign_report", login, campaign, impressions=impressions)

        payload = {
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "domains": sorted(domains),
            "date_range": args.date_range,
            "logins": len(logins),
            "matches": sorted(matches, key=lambda item: (item["url"], item["source"], item["login"])),
        }
        Path(args.output).write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"Logins processed: {len(logins)}")
        print(f"Required domains: {len(domains)}")
        print(f"Matches: {len(matches)}")
        print(f"Unique matched URLs: {len({item['url'] for item in matches})}")
        print(f"Output: {args.output}")
        for item in payload["matches"]:
            print(
                f"{item['source']}\t{item['url']}\t"
                f"campaign={item['campaign_id']}\t"
                f"campaign_state={item['campaign_state']}\t"
                f"campaign_status={item['campaign_status']}\t"
                f"ad_status={item.get('ad_status', '')}"
            )
        return 0
    except (RuntimeError, KeyError, ValueError, json.JSONDecodeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
