# Direct links

Read-only probe for checking access to Yandex Direct and receiving campaign IDs.

The probe is not the final URL availability autotest. It currently checks the
first two read-only steps:

```text
Jenkins credentials → /campaigns → CampaignId → /ads → Href
```

## Jenkins environment

Configure these credentials as environment variables:

- `YANDEX_DIRECT_LOGIN` — список Client-Login, по одному на строку (допустимы
  также разделители-запятые или пробелы)
- `YANDEX_DIRECT_TOKEN`

Один OAuth-токен используется для всех кабинетов, а `Client-Login` задаёт
кабинет, к которому относится конкретный запрос. Не коммитьте значения в
репозиторий и не выводите их в логи. Для локальной обратной совместимости
скрипт также принимает одиночный `YANDEX_DIRECT_LOGIN`.

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

Для экспериментальной выгрузки за последние 7 дней без объединения дублей:

```powershell
python export_all_urls.py --date-range LAST_7_DAYS --keep-duplicates
```

Период применяется к Reports API. `ads.get` возвращает доступные объявления
без отдельного фильтра по дате. Jenkins использует этот режим для текущей
проверочной выгрузки.

`get_campaign_urls.py` probes one campaign by ID. The Jenkins parameter
`DIRECT_CAMPAIGN_ID` defaults to `109848388`; the script first reads the
campaign type and then requests the matching `Href` field for its ads.

`get_campaigns.py --without-client-login` performs the same read-only campaign
request without the `Client-Login` header. This checks the account associated
with the OAuth token rather than one selected client account.

## План реализации автотеста

### 1. Выгрузка ссылок

Раз в неделю Jenkins получает ссылки из двух источников для каждого кабинета
из `YANDEX_DIRECT_LOGIN`:

1. `/json/v5/campaigns` и `/json/v5/ads` — URL объявлений только для
   активных кампаний и объявлений. Для кампании используются `State=ON`,
   `Status=ACCEPTED` и, если поле возвращено, `StatusPayment=ALLOWED`; для
   объявлений — `State=ON` и `Status=ACCEPTED`.
2. `/json/v501/reports` — `CampaignUrlPath` для кампаний, которые не
   возвращаются через `campaigns.get` или `ads.get` (например, кампании
   «Мастер кампаний»).

Для отчёта передаётся фильтр `Impressions > 0` за выбранный период без
ограничения списком ID из `campaigns.get`. Это важно для полноты: некоторые
типы кампаний могут отсутствовать в `campaigns.get`, но отдавать
`CampaignUrlPath` через Reports. Кампании без показов за период не попадают в
основной набор ссылок: это снижает риск добавления устаревших URL, но не
заменяет отдельную проверку полноты выгрузки.

Результаты сначала приводятся к URL целевой страницы: рекламные и аналитические
параметры (`utm_*`, `roistat`, `rs_stat`, идентификаторы кампании, объявления и
размещения) удаляются, а значимые параметры страницы, например `region` и `f`,
сохраняются. После этого ссылки объединяются по каноническому URL. Исходные
URL сохраняются в `source_urls`, чтобы можно было восстановить связь с рекламой.

Результирующий файл хранится в директории Jenkins и используется как входной
набор для ежедневной проверки. В выгрузку также попадают служебные данные:
дата обновления, ID кампании, источник и количество показов из Reports.

После выгрузки `build_check_file.py` создаёт `check_urls.json`: дубли страниц
объединяются, а для каждой страницы сохраняются источники, ID кампаний,
исходные URL и готовые региональные значения из параметра `region`. URL с
макросами вроде `{region_id}` не разворачиваются вручную. URL с кириллицей в
домене, пути или параметрах исключаются из scope проверки и отражаются в
статистике `excluded_cyrillic_rows` и `excluded_cyrillic_urls`.
Для `dom-provider.online` ссылки с параметрами `f` и `region` дополнительно
приводятся к региональному пути, например `/\<region\>`.

### 2. Ежедневная проверка

Автотест читает сохранённый файл и проверяет каждый URL. Для одного URL:

- HTTP 200 — доступен;
- HTTP 404, 502, таймаут или другая ошибка — недоступен;
- выполняется до трёх попыток;
- после третьей неудачи фиксируется ошибка с подробностями.

При первом обнаружении ошибки отправляется уведомление. При восстановлении
URL отправляется отдельное уведомление о восстановлении.

Расписание Jenkins настраивается отдельно: обновление ссылок — раз в неделю,
проверка доступности — ежедневно.

Для ручного запуска проверки:

```powershell
python build_check_file.py --input urls.json --output check_urls.json
python check_urls.py --input check_urls.json --output availability.json
```

`check_urls.py` выполняет HTTP GET с автоматическим переходом по редиректам.
HTTP 200 считается доступным, остальные статусы и сетевые ошибки — ошибкой.
По умолчанию используется 50 потоков, таймаут 15 секунд, одна первоначальная
попытка и три ретрая с паузой 0,2 секунды. Результат сохраняется с московским
временем, HTTP-кодом, текстом ошибки и числом попыток. Ошибка одного URL не
останавливает весь прогон, а промежуточный результат сохраняется каждые 500
URL. Jenkins даёт проверке до 120 минут.

После проверки `generate_allure.py` формирует Allure-результаты: отдельный тест
на каждый URL со статусом, HTTP-кодом, ошибкой, количеством попыток, регионом и
ID кампаний. Jenkins публикует каталог `allure-results` в Allure Report.

В Jenkins проверка выполняется через HTTP/HTTPS-прокси. Credential
`browser_proxy_creds` хранится как Secret Text в формате
`host:port:user:password` и передаётся скрипту через переменную
`BROWSER_PROXY_CREDS`. Секрет не выводится в лог и не записывается в отчёт.

В Jenkins параметр `RUN_MODE` запускает один из двух режимов:

- `EXPORT_AND_PREPARE` — обновление URL-файлов, используется раз в неделю;
- `CHECK_ONLY` — проверка сохранённого `check_urls.json`, используется ежедневно
  или вручную через `Build with Parameters`.
