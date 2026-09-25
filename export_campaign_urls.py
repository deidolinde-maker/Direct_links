"""Export accessible Yandex Direct campaign URLs through Reports."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import sys
import time
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


REPORTS_URL = "https://api.direct.yandex.com/json/v501/reports"


def required_env(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise RuntimeError(f"Required environment variable is missing: {name}")
    return value


def request_report(token: str, login: str, date_range: str) -> tuple[int, str, dict[str, str]]:
    report_name = f"export_campaign_urls_{dt.datetime.now(dt.timezone.utc):%Y%m%d%H%M%S}"
    payload = {
        "params": {
            "SelectionCriteria": {},
            "FieldNames": [
                "CampaignId",
                "CampaignName",
                "CampaignType",
                "CampaignUrlPath",
                "Impressions",
            ],
            "ReportName": report_name,
            "ReportType": "CAMPAIGN_PERFORMANCE_REPORT",
            "DateRangeType": date_range,
            "Format": "TSV",
            "IncludeVAT": "NO",
        }
    }
    request = Request(
        REPORTS_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {token}",
            "Client-Login": login,
            "Accept-Language": "ru",
            "Content-Type": "application/json",
            "processingMode": "auto",
            "skipReportHeader": "true",
            "skipColumnHeader": "false",
            "skipReportSummary": "true",
        },
        method="POST",
    )
    try:
        with urlopen(request, timeout=60) as response:
            return response.status, response.read().decode("utf-8"), dict(response.headers)
    except HTTPError as exc:
        return exc.code, exc.read().decode("utf-8", errors="replace"), dict(exc.headers)
    except URLError as exc:
        raise RuntimeError(f"Yandex Direct network error: {exc.reason}") from exc


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--date-range",
        choices=("LAST_7_DAYS", "LAST_30_DAYS", "ALL_TIME"),
        default="LAST_30_DAYS",
        help="Period used to identify campaigns with available URLs",
    )
    args = parser.parse_args()
    try:
        token = required_env("YANDEX_DIRECT_TOKEN")
        login = required_env("YANDEX_DIRECT_LOGIN")
        for attempt in range(1, 6):
            status, body, headers = request_report(token, login, args.date_range)
            if status == 200:
                rows = [line for line in body.splitlines() if line.strip()]
                if rows and rows[0].startswith("CampaignId"):
                    rows = rows[1:]
                records = []
                unique_urls = set()
                for row in rows:
                    columns = row.split("\t")
                    if len(columns) < 5:
                        continue
                    campaign_id, name, campaign_type, url, impressions = columns[:5]
                    if not url.strip():
                        continue
                    record = {
                        "campaign_id": campaign_id,
                        "campaign_name": name,
                        "campaign_type": campaign_type,
                        "url": url,
                        "impressions": impressions,
                    }
                    records.append(record)
                    unique_urls.add(url)
                print(f"Campaign rows with URL: {len(records)}")
                print(f"Unique URLs: {len(unique_urls)}")
                print("campaign_id\tcampaign_name\tcampaign_type\turl\timpressions")
                for record in records:
                    print("\t".join(record.values()))
                return 0
            if status in (201, 202):
                retry_in = int(headers.get("retryIn", "60"))
                if attempt == 5:
                    raise RuntimeError("URL report is still not ready after 5 attempts")
                print(f"Report is not ready; retrying in {retry_in}s")
                time.sleep(retry_in)
                continue
            raise RuntimeError(f"Reports API returned HTTP {status}: {body}")
    except (RuntimeError, ValueError, json.JSONDecodeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
