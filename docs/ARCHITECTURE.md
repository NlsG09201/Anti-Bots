# Architecture and module boundaries

This repository uses a modular monolith. Keep provider integrations and API/web application processes in the existing deployment shape; split services only when operational evidence requires it.

## Backend

- `app/api`: HTTP and WebSocket adapters. Validate requests, authenticate, call application services, and serialize responses.
- `app/services`: use cases and orchestration. Coordinate domain rules with persistence and external providers.
- `app/domain`: provider-independent business rules and domain models. Keep Redis, SQLAlchemy sessions, FastAPI, and provider SDK calls out of this layer.
- `app/integrations`: provider-specific OAuth, API clients, webhook adapters, and protocol details. Keep one provider's wire format out of another provider's module.
- `app/infrastructure`: database, cache, queues, and other concrete implementations.
- `app/workers` and `app/events`: asynchronous execution and event transport.

Platform monitor health now has a small domain slice in `app/domain/platform_health`: health snapshots and the in-memory tracker calculations. Its registry, persistence, provider probes, audit loop, and alert delivery remain in `app/services/platform_health`, where infrastructure coordination belongs.

When extending a flow, keep provider parsing in its integration adapter; have services call that adapter and apply domain rules before persistence or side effects. Avoid adding repository interfaces that only wrap a single SQLAlchemy query. Move direct database work out of API handlers when changing the relevant feature, rather than doing a broad mechanical migration.

## Frontend

- `src/app`: route composition and page-level layouts.
- `src/components`: shared UI and feature components.
- `src/hooks`, `src/contexts`, and `src/stores`: reusable client behavior and state.
- `src/lib`: API client, runtime URL configuration, and shared utilities.
- `src/types`: shared client contracts.

Keep request construction in `src/lib/api.ts`; pages and components should call typed client methods rather than assemble URLs or duplicate authentication behavior. Keep local view state local and promote state only when multiple routes need to share it.

## Safe incremental changes

Preserve API contracts and existing provider boundaries. For structural changes, move one cohesive feature slice, update its imports in the same change, and run its focused tests plus relevant type/build checks. Do not introduce placeholder layers or duplicate DTOs solely to match a textbook architecture.
