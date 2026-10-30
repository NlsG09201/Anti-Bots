# Testing and quality checks

## Local commands

Install frontend dependencies with `npm --prefix frontend ci`. Then run:

| Command | Checks |
| --- | --- |
| `npm run test:backend` | Backend suite plus terminal and XML coverage reports |
| `npm run test:frontend` | URL routing unit tests and server-rendered component smoke tests |
| `npm test` | Both backend and frontend tests |
| `npm run lint` | ESLint over the frontend |
| `npm run typecheck` | TypeScript strict typecheck |
| `npm run build` | Optimized frontend production build |
| `npm run quality` | Tests, lint, typecheck, and production build |

Backend CI installs `requirements-dev.txt`, compiles Python, runs all tests (without stopping at the first failure), prints line coverage, and uploads `backend/coverage.xml` as a workflow artifact. The current measured baseline is 42% for `app/` (18,170 statements); this is reported without a fail-under threshold while coverage gaps are addressed.

Frontend CI runs the Node built-in test runner against compiled TypeScript utilities and server-rendered `PlatformBadge`/`StatCard` components, then ESLint, typecheck, and production build. This does not yet replace browser-level workflow, interaction, responsive, or accessibility testing.

Database API tests use isolated in-memory SQLite. The PostgreSQL Alembic baseline is documented as unreconciled in [DATABASE_MIGRATIONS.md](DATABASE_MIGRATIONS.md); CI does not apply those revisions to production or claim that PostgreSQL upgrades have been validated. Add migration integration tests after a supported baseline is established.
