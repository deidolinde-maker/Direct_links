# Direct links

Read-only probe for checking access to Yandex Direct and receiving campaign IDs.

The probe is not the final URL availability autotest. It is the first step:

```text
Jenkins credentials → /campaigns → CampaignId
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

The script sends a read-only `POST` request to
`https://api.direct.yandex.com/json/v5/campaigns`, handles pagination, and
prints campaign ID, name, type, state, and status.
