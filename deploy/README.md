# Deployment foundation

The Compose stack is a cloud-neutral runtime contract for PostgreSQL, a migration job, the FastAPI backend, and the Next.js frontend. Both application images run as UID/GID `10001`, drop Linux capabilities, use read-only filesystems under Compose, and expose health checks.

```sh
cp deploy/envs/.env.local.example deploy/envs/.env.local
make docker-config
make docker-up
```

For live reload in containers, `make docker-dev-up` applies `compose.dev.yml` to the same
`langchain-takehome` project. The backend runs one reload-enabled Uvicorn application process from a
read-only source mount. The frontend uses its non-root development image with baked dependencies,
read-only source/configuration mounts, and a tmpfs-backed `.next` directory. No host dependency,
secret, test-result, or build-artifact directories are mounted. The development image links Next's
generated `next-env.d.ts` into that tmpfs so Next.js can refresh it without making the application
filesystem writable.

Return to the immutable production-style images with:

```sh
make docker-prod-restore
```

The restore command keeps the named PostgreSQL volume and recreates application services without
the development mounts or reload commands.

The application now provides authenticated sessions, persisted tenant membership, and actor-scoped
account assignments. Production delivery must still add a managed identity integration and secrets,
TLS, centralized redacted logs, immutable image references, scaling policy, and a reviewed database
migration/rollback strategy, plus an authorization review for the deployment's tenant model. Do not
expose LangSmith or model-provider credentials to the browser.
