"""Read-only Reports probe for one Yandex Direct campaign."""

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


def request_report(token: str, login: str, campaign_id: int) -> tuple[int, str, dict[str, str]]:
    report_name = f"check_{campaign_id}_{dt.datetime.now(dt.timezone.utc):%Y%m%d%H%M%S}"
    payload = {
        "params": {
            "SelectionCriteria": {
                "Filter": [{
                    "Field": "CampaignId",
                    "Operator": "EQUALS",
                    "Values": [str(campaign_id)],
                }]
            },
            "FieldNames": ["CampaignId", "CampaignName", "CampaignType", "Impressions"],
            "ReportName": report_name,
            "ReportType": "CAMPAIGN_PERFORMANCE_REPORT",
            "DateRangeType": "LAST_30_DAYS",
            "Format": "TSV",
            "IncludeVAT": "NO",
        }
    }
    headers = {
        "Authorization": f"Bearer {token}",
        "Client-Login": login,
        "Accept-Language": "ru",
        "Content-Type": "application/json",
        "processingMode": "auto",
        "skipReportHeader": "true",
        "skipColumnHeader": "false",
        "skipReportSummary": "true",
    }
    request = Request(
        REPORTS_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers=headers,
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
    parser.add_argument("campaign_id", nargs="?", default="109848388")
    args = parser.parse_args()
    campaign_id = int(args.campaign_id)
    try:
        token = required_env("YANDEX_DIRECT_TOKEN")
        login = required_env("YANDEX_DIRECT_LOGIN")
        for attempt in range(1, 6):
            status, body, headers = request_report(token, login, campaign_id)
            print(f"Reports HTTP status: {status}")
            print(f"RequestId: {headers.get('RequestId', '')}")
            if status == 200:
                print(body or "REPORT_EMPTY")
                return 0
            if status in (201, 202):
                retry_in = int(headers.get("retryIn", "60"))
                if attempt == 5:
                    raise RuntimeError("Report is still not ready after 5 attempts")
                print(f"Report is not ready; retrying in {retry_in}s")
                time.sleep(retry_in)
                continue
            raise RuntimeError(f"Reports API returned HTTP {status}: {body}")
    except (RuntimeError, ValueError, json.JSONDecodeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
