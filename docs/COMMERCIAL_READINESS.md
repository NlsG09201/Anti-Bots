# Commercial readiness snapshot

Reviewed against repository code on 2026-10-31. “Implemented” means present in this checkout; it does not mean a live-provider certification, customer-scale validation, or deployment verification.

| Area | Status | Evidence / remaining work |
| --- | --- | --- |
| FastAPI and Spring services | PARTIALLY IMPLEMENTED | The README describes Spring as an optional progressive migration: it currently serves the assistant chat and tenant-scoped stream reads, while FastAPI owns the rest. The assistant route overlaps by design; it is not a full replacement. Spring production deployment is not enabled in `render.yaml`, and shared JWT/DB/Redis configuration must be operated consistently. |
| Tenant accounts and access | PARTIALLY IMPLEMENTED | Tenant, user, and stream records and role-aware auth exist. Verify tenant isolation across every customer-facing query and add end-to-end account/team lifecycle coverage before onboarding customers. |
| Twitch, Kick, YouTube Live | PARTIALLY IMPLEMENTED | Provider OAuth/API clients, routes, and monitoring paths exist. Per-account permissions, quotas, production credentials, and end-to-end provider verification remain external/operational requirements. Advertise only the features verified for each permission set. |
| TikTok LIVE | NOT IMPLEMENTED | `backend/app/integrations/tiktok/webcast.py` explicitly raises an unavailable error; there is no supported LIVE API access in this build. |
| AI assistance and usage records | PARTIALLY IMPLEMENTED | AI configuration, request controls, caching, and tenant-scoped usage records exist. No plan-entitlement enforcement or customer AI quota/billing integration exists. |
| Plans, subscription lifecycle, and payments | NOT IMPLEMENTED | No billing provider integration, paid plan catalog, entitlement enforcement, renewal, downgrade, cancellation, or payment reconciliation exists. No checkout or payment claims should be shown. |
| Customer legal/support materials | NOT IMPLEMENTED | No customer Terms of Service or Privacy Policy was found in the repository. Data retention/deletion guarantees, support commitments, and customer incident communications need product/legal approval. |
| Delivery and recovery | PARTIALLY IMPLEMENTED | CI, manual Render deploy, health checks, and a PostgreSQL backup/restore utility exist. A deployed staging environment, automated off-site backup schedule, alert receiver, and successful isolated restore drill are not verified. |
| Performance and capacity | NOT VERIFIED | No representative load test or measured tenant/event capacity was found in this review. Do not publish throughput or uptime claims. |

## Implemented directly in this review

The landing page previously listed TikTok LIVE under “Platform workflows in the product.” It now lists Twitch, Kick, and YouTube Live as integrations in this build and explicitly says TikTok LIVE monitoring is unavailable. This is not an assertion that each integration has passed production end-to-end certification.

## Deployment and cost dependencies

The checked-in Render blueprint currently declares a free API service and a starter worker; its database is supplied through `DATABASE_URL`, and Redis is external. `vercel.json` delegates the frontend to Vercel. The actual provider accounts, regions, resource use, and current invoices are not available here, so a total monthly bill or margin estimate would be fabricated.

For planning only, the providers' current public list prices are in USD before taxes and usage: Vercel Pro is $20/month and is the commercial plan (Hobby is restricted to non-commercial use); Render Pro workspace is $25/month plus per-service compute; Upstash Redis Pay-as-You-Go is $0.20 per 100,000 commands, with a $10/month fixed option; OpenAI charges by model and token usage. These are pricing references, not confirmed account plans or a complete deployment estimate. PostgreSQL cost, storage/egress, compute sizing, Redis volume, OpenAI model/rate, domain, email/support, and backups must be priced from real workload and selected plans before setting customer prices.

- [Vercel plans and commercial-use terms](https://vercel.com/docs/plans/hobby)
- [Render plans and compute pricing](https://render.com/pricing)
- [Upstash Redis pricing](https://upstash.com/pricing/redis)
- [OpenAI API pricing](https://developers.openai.com/api/docs/pricing)

## Minimum blockers before accepting paying customers

1. Implement real subscription/entitlement state and payment-provider webhooks only after choosing the provider and validating country, currency, tax, refund, and legal requirements.
2. Complete cross-tenant authorization coverage and security review for every customer-data route, plus account deletion and documented retention behavior.
3. Publish reviewed Terms of Service and Privacy Policy, supported-platform capability matrix, support path, and clear incident/data handling commitments.
4. Provision commercial production plans for frontend, API, database, Redis, and backups; configure staging, alert delivery, secret rotation, and customer-data retention.
5. Pass integration/E2E checks for each advertised platform capability, run a representative load test, and complete an isolated database restore drill.

Until these blockers are cleared, the application is a functional technical product with partial SaaS foundations, not a verified commercial SaaS service. Do not enable checkout or claim service-level guarantees.
