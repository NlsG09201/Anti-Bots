# Power BI Analytics

The reproducible cloud, PostgreSQL warehouse, ETL, tenant-scoped credentials, Power Query transformations, DAX measures, report plan, publishing, and refresh workflow now live in [`business-intelligence/README.md`](../business-intelligence/README.md).

The FastAPI analytics endpoints are tenant-scoped and require an analyst, admin, or super-admin bearer token:

- `GET /api/v1/analytics/overview`
- `GET /api/v1/analytics/powerbi/model`
- `GET /api/v1/analytics/powerbi/datasets`
- `GET /api/v1/analytics/powerbi/datasets/{dataset_name}`
- `GET /api/v1/analytics/exports/json`
- `GET /api/v1/analytics/exports/csv?dataset=streams`
- `GET /api/v1/analytics/exports/excel`
- `GET /api/v1/analytics/exports/powerbi-package`
- `POST /api/v1/analytics/powerbi/sync`

Power BI push synchronization requires `POWERBI_ENABLED`, Microsoft tenant/client credentials, and `POWERBI_GROUP_ID`. The API creates a dataset scoped to the authenticated tenant and replaces push rows on refresh to prevent duplicate accumulation. Cloud resources, published PBIX reports, and external credentials must be provisioned and verified in their owner accounts before they can be reported as deployed.
