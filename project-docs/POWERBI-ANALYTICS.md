# Power BI Analytics Backend

## Endpoints

- `GET /api/v1/analytics/overview`
- `GET /api/v1/analytics/live-metrics`
- `GET /api/v1/analytics/suspicious-activity`
- `GET /api/v1/analytics/stream-analytics`
- `GET /api/v1/analytics/ai-analytics`
- `GET /api/v1/analytics/engagement-analytics`
- `GET /api/v1/analytics/attack-analytics`
- `GET /api/v1/analytics/powerbi/model`
- `GET /api/v1/analytics/powerbi/dax`
- `GET /api/v1/analytics/powerbi/metadata`
- `GET /api/v1/analytics/powerbi/datasets`
- `GET /api/v1/analytics/powerbi/datasets/{dataset_name}`
- `POST /api/v1/analytics/powerbi/sync`
- `GET /api/v1/analytics/exports/json`
- `GET /api/v1/analytics/exports/csv?dataset=streams`
- `GET /api/v1/analytics/exports/excel`
- `GET /api/v1/analytics/exports/powerbi-package`

## Datasets

- `platforms`
- `streamers`
- `streams`
- `viewers`
- `suspicious_viewers`
- `attacks`
- `follows`
- `engagement_metrics`
- `ai_predictions`
- `threat_scores`
- `chat_activity`
- `bot_profiles`

## Environment

- `ANALYTICS_DEFAULT_HOURS`
- `POWERBI_ENABLED`
- `POWERBI_TENANT_ID`
- `POWERBI_CLIENT_ID`
- `POWERBI_CLIENT_SECRET`
- `POWERBI_GROUP_ID`
- `POWERBI_DATASET_NAME`
- `POWERBI_MAX_ROWS_PER_TABLE`

## Power BI Service

`POST /api/v1/analytics/powerbi/sync` uses Azure AD client credentials and creates a Push dataset in the configured Power BI workspace if it does not exist. Then it pushes current dataset rows per table, capped by `POWERBI_MAX_ROWS_PER_TABLE`.

## Import Flow

1. Download `GET /api/v1/analytics/exports/powerbi-package`.
2. Import the CSV tables into Power BI Desktop.
3. Create relationships from `powerbi_model.json`.
4. Paste measures from `powerbi_measures.dax`.
5. Publish to Power BI Service or enable direct push sync with the Power BI environment variables.
