# Direct links

Read-only probe for checking access to Yandex Direct and receiving campaign IDs.

The probe is not the final URL availability autotest. It currently checks the
first two read-only steps:

```text
Jenkins credentials → /campaigns → CampaignId → /ads → Href
```

## Jenkins environment

Configure these credentials as environment variables:

- `YANDEX_DIRECT_LOGIN`
- `YANDEX_DIRECT_TOKEN`

Do not commit their values to the repository or print them in logs.

## Run locally or in Jenkins

```powershell
python get_campaigns.py
```

`get_campaigns.py` sends a read-only `POST` request to
`https://api.direct.yandex.com/json/v5/campaigns`, handles pagination, and
prints campaign ID, name, type, state, and status.

`get_ads.py` repeats the campaign lookup and sends read-only `POST` requests to
`https://api.direct.yandex.com/json/v5/ads`, then prints ad IDs and `Href` URLs.
Campaign IDs are sent in batches and all `/ads` pages are read. The API quota
itself is not bypassed; pagination only prevents truncating the result set.

`get_campaign_urls.py` probes one campaign by ID. The Jenkins parameter
`DIRECT_CAMPAIGN_ID` defaults to `109848388`; the script first reads the
campaign type and then requests the matching `Href` field for its ads.

`get_campaigns.py --without-client-login` performs the same read-only campaign
request without the `Client-Login` header. This checks the account associated
with the OAuth token rather than one selected client account.
