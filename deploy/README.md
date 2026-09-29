# Deployment foundation

The Compose stack is a cloud-neutral runtime contract for PostgreSQL, a migration job, the FastAPI backend, and the Next.js frontend. Both application images run as UID/GID `10001`, drop Linux capabilities, use read-only filesystems under Compose, and expose health checks.

```sh
cp deploy/envs/.env.local.example deploy/envs/.env.local
make docker-config
make docker-up
```

Production delivery must add managed secrets, TLS, authentication, tenant isolation, centralized redacted logs, immutable image references, scaling policy, and a reviewed database migration/rollback strategy. Do not expose LangSmith or model-provider credentials to the browser.

