# web_app_service

Isolated web app service for the new chain.

## Scope
- Read-only APIs for A/B/C/D snapshot objects.
- Must call stock_processing_service ports/gateway facades.
- Must not directly access Postgres/Redis low-level clients.

## Constraints
- No `asyncpg`/`psycopg`/`sqlalchemy` usage.
- No raw SQL in this service.
- DTO-only responses.

## Run
```bash
uvicorn web_app_service.main:app --reload --port 8081
```
