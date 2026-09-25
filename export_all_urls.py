"""Export ad-level and campaign-level URLs and deduplicate them."""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

from export_campaign_urls import request_report
from direct_logins import required_logins
from get_ads import load_ads
from get_campaigns import load_campaigns, required_env


def is_valid_url(value: str) -> bool:
    parsed = urlparse(value.strip())
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


def write_urls_file(path: Path, url_rows: list[dict], stats: dict[str, int]) -> None:
    payload = {
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "stats": stats,
        "urls": [
            {
                "url": row["url"],
                "campaign_ids": sorted(row["campaign_ids"]),
                "sources": sorted(row["sources"]),
                "impressions": row["impressions"],
            }
            for row in url_rows
        ],
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = path.with_suffix(path.suffix + ".tmp")
    temporary_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary_path.replace(path)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--date-range",
        choices=("LAST_7_DAYS", "LAST_30_DAYS", "ALL_TIME"),
        default="LAST_30_DAYS",
    )
    parser.add_argument("--output", default=os.getenv("URLS_FILE", "urls.json"))
    parser.add_argument(
        "--keep-duplicates",
        action="store_true",
        help="Keep one output row for every valid URL occurrence instead of merging duplicates",
    )
    args = parser.parse_args()
    try:
        token = required_env("YANDEX_DIRECT_TOKEN")
        logins = required_logins()
        campaigns_count = 0
        ads_count = 0
        report_rows_count = 0
        filtered_rows_count = 0
        url_rows: list[dict] = []
        url_index: dict[str, dict] = {}
        ad_url_count = 0

        def add_url(url: str, campaign_id: str, source: str, impressions: str = "") -> None:
            row = {
                "url": url.strip(),
                "campaign_ids": [campaign_id] if campaign_id else [],
                "sources": [source],
                "impressions": impressions,
            }
            if args.keep_duplicates:
                url_rows.append(row)
                return
            existing = url_index.get(row["url"])
            if existing is None:
                url_index[row["url"]] = row
                url_rows.append(row)
                return
            existing["campaign_ids"] = sorted(set(existing["campaign_ids"]) | set(row["campaign_ids"]))
            existing["sources"] = sorted(set(existing["sources"]) | set(row["sources"]))
            if row["impressions"]:
                existing["impressions"] = row["impressions"]

        for login in logins:
            campaigns = load_campaigns(token, login)
            campaigns_count += len(campaigns)
            campaign_ids = [int(item["Id"]) for item in campaigns if item.get("Id") is not None]
            ads = load_ads(token, login, campaign_ids)
            ads_count += len(ads)

            for ad in ads:
                nested = ad.get("TextAd") or ad.get("TextImageAd") or ad.get("ResponsiveAd") or {}
                href = nested.get("Href") or ad.get("Href") or ""
                if not is_valid_url(href):
                    filtered_rows_count += 1
                    continue
                ad_url_count += 1
                add_url(href, str(ad.get("CampaignId", "")), "ad")

            for attempt in range(1, 6):
                status, body, headers = request_report(token, login, args.date_range)
                if status == 200:
                    lines = [line for line in body.splitlines() if line.strip()]
                    if lines and lines[0].startswith("CampaignId"):
                        lines = lines[1:]
                    for line in lines:
                        columns = line.split("\t")
                        if len(columns) < 5:
                            continue
                        report_rows_count += 1
                        campaign_id, _name, _kind, url, impressions = columns[:5]
                        if not is_valid_url(url):
                            filtered_rows_count += 1
                            continue
                        add_url(url, campaign_id, "campaign_report", impressions)
                    break
                if status in (201, 202):
                    import time
                    if attempt == 5:
                        raise RuntimeError("URL report is still not ready after 5 attempts")
                    time.sleep(int(headers.get("retryIn", "60")))
                    continue
                raise RuntimeError(f"Reports API returned HTTP {status}: {body}")

        print(f"Client logins processed: {len(logins)}")
        print(f"Campaigns received: {campaigns_count}")
        print(f"Ads received: {ads_count}")
        print(f"Ad URLs: {ad_url_count}")
        print(f"Campaign report rows: {report_rows_count}")
        stats = {
            "client_logins": len(logins),
            "campaigns": campaigns_count,
            "ads": ads_count,
            "ad_urls": ad_url_count,
            "campaign_report_rows": report_rows_count,
            "filtered_rows": filtered_rows_count,
            "url_rows": len(url_rows),
            "unique_urls": len({row["url"] for row in url_rows}),
            "date_range": args.date_range,
            "duplicates_kept": args.keep_duplicates,
        }
        output_path = Path(args.output)
        write_urls_file(output_path, url_rows, stats)

        print(f"Filtered invalid rows: {filtered_rows_count}")
        print(f"URL rows: {len(url_rows)}")
        print(f"Unique URLs: {len({row['url'] for row in url_rows})}")
        print(f"Duplicates kept: {args.keep_duplicates}")
        print(f"URLs file: {output_path}")
        print("campaign_ids\tsources\turl\timpressions")
        for row in url_rows:
            print(
                f"{','.join(row['campaign_ids'])}\t"
                f"{','.join(row['sources'])}\t{row['url']}\t{row['impressions']}"
            )
        return 0
    except (RuntimeError, KeyError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
