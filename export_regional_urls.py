"""Export campaign URLs with regions where ads were shown during the period."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import sys
import time
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from direct_logins import required_logins
from get_campaigns import required_env


REPORTS_URL = "https://api.direct.yandex.com/json/v501/reports"


def request_report(token: str, login: str, date_range: str) -> tuple[int, str, dict[str, str]]:
    payload = {
        "params": {
            "SelectionCriteria": {},
            "FieldNames": [
                "CampaignId",
                "AdId",
                "CampaignUrlPath",
                "LocationOfPresenceId",
                "LocationOfPresenceName",
                "Impressions",
            ],
            "ReportName": f"export_regional_urls_{dt.datetime.now(dt.timezone.utc):%Y%m%d%H%M%S}",
            "ReportType": "AD_PERFORMANCE_REPORT",
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
        raise RuntimeError(f"Yandex Direct regional report network error: {exc.reason}") from exc


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--date-range", choices=("LAST_7_DAYS", "LAST_30_DAYS"), default="LAST_7_DAYS")
    parser.add_argument("--output", default=os.getenv("REGIONAL_URLS_FILE", "regional_urls.json"))
    args = parser.parse_args()

    try:
        token = required_env("YANDEX_DIRECT_TOKEN")
        logins = required_logins()
        rows: list[dict[str, str]] = []
        for login in logins:
            for attempt in range(1, 6):
                status, body, headers = request_report(token, login, args.date_range)
                if status == 200:
                    lines = [line for line in body.splitlines() if line.strip()]
                    if lines and lines[0].startswith("CampaignId"):
                        lines = lines[1:]
                    for line in lines:
                        columns = line.split("\t")
                        if len(columns) < 6:
                            continue
                        campaign_id, ad_id, url, region_id, region_name, impressions = columns[:6]
                        if not url.strip() or not region_name.strip():
                            continue
                        rows.append(
                            {
                                "login": login,
                                "campaign_id": campaign_id,
                                "ad_id": ad_id,
                                "url": url,
                                "region_id": region_id,
                                "region_name": region_name,
                                "impressions": impressions,
                            }
                        )
                    break
                if status in (201, 202):
                    if attempt == 5:
                        raise RuntimeError("Regional report is still not ready after 5 attempts")
                    time.sleep(int(headers.get("retryIn", "60")))
                    continue
                raise RuntimeError(f"Regional report returned HTTP {status}: {body}")

        output = Path(args.output)
        output.write_text(
            json.dumps(
                {
                    "date_range": args.date_range,
                    "rows": rows,
                    "unique_urls": len({row["url"] for row in rows}),
                    "unique_url_regions": len({(row["url"], row["region_id"]) for row in rows}),
                },
                ensure_ascii=False,
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        print(f"Client logins processed: {len(logins)}")
        print(f"Regional rows: {len(rows)}")
        print(f"Unique URLs: {len({row['url'] for row in rows})}")
        print(f"Unique URL-region pairs: {len({(row['url'], row['region_id']) for row in rows})}")
        print(f"Regional URLs file: {output}")
        return 0
    except (RuntimeError, KeyError, ValueError, json.JSONDecodeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
