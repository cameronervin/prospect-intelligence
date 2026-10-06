# Deployment foundation

The Compose stack runs PostgreSQL, a migration job, FastAPI, and Next.js. Both application images run
as UID/GID `10001`, drop Linux capabilities, use read-only filesystems, and expose health checks.

```sh
cp deploy/envs/.env.local.example deploy/envs/.env.local
# Set TAKEHOME_JWT_SIGNING_SECRET and OPENAI_API_KEY in .env.local.
make docker-config
make docker-up
make seed-demo-data
```

Open `http://localhost:3000/login` and use `alex.morgan@example.test` / `prospect-demo`.

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

The application provides demo sessions, persisted membership, and actor-scoped account assignments.
It also implements opt-in online-quality delivery. Production delivery must replace the demo issuer
with managed identity and add managed secrets, TLS, centralized redacted logs, immutable image
references, scaling policy, and a reviewed migration and rollback process. Private source systems,
outbound sending, and CRM writes also remain deferred. Do not expose LangSmith or model-provider
credentials to the browser.
