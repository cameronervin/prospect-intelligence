# Prospect Intelligence

## Product overview

Prospect Intelligence helps a freight sales rep research an assigned shipper. It creates a sourced
brief and an outreach draft, then pauses for review. Approval records a simulated send. The MVP does
not contact prospects or write to a CRM.

## Core workflow

1. The sales rep signs in and selects an assigned shipper.
2. The agent gathers account, freight, carrier, and public-source data.
3. The agent creates a brief with source links and an outreach draft.
4. The sales rep approves, edits, or rejects the outreach draft.
5. An approval or valid edit creates a simulated send.

## Local quick start

Prerequisites:

- Python 3.12
- [uv](https://docs.astral.sh/uv/)
- Node.js `>=22.12.0` and npm 10
- Docker with Compose v2
- [ripgrep](https://github.com/BurntSushi/ripgrep)

Install the dependencies:

```sh
make setup
```

Create the backend environment file:

```sh
cp backend/.env.example backend/.env
```

Set these values in `backend/.env`:

- `TAKEHOME_JWT_SIGNING_SECRET`: at least 32 random bytes
- `OPENAI_API_KEY`: a valid OpenAI API key

Start PostgreSQL, FastAPI, and Next.js:

```sh
make dev
```

Open `http://localhost:3000/login` and sign in with:

- Email: `alex.morgan@example.test`
- Password: `prospect-demo`

See [local development](docs/development/setup.md) for Docker Compose and optional integrations.

## Credential-free verification

Run the repository checks:

```sh
make verify
```

The checks use synthetic data and test models. They do not call model providers or publish data to
LangSmith.

Run the browser tests separately:

```sh
make test-e2e
```

## Technology

- Python 3.12 and FastAPI
- LangGraph and Deep Agents
- PostgreSQL
- Next.js
- Offline evaluation and optional LangSmith reporting

## Documentation

- [Documentation index](docs/README.md)
- [System architecture](docs/architecture/system.md)
- [Evaluation](docs/evaluation/README.md)
- [MVP scope](docs/delivery/mvp-scoping.md)
