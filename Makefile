.DEFAULT_GOAL := help
SHELL := /bin/sh

.PHONY: help setup dev verify test-e2e audit docker-config docker-up docker-down feature smoke-online-quality online-quality-plan online-quality-setup online-quality-simulate online-quality-teardown secret-scan cleanup

help:
	@echo "LangChain take-home development targets"
	@echo "  setup          Install backend and frontend dependencies"
	@echo "  dev            Start PostgreSQL, backend, and frontend for development"
	@echo "  verify         Run repository checks and tests"
	@echo "  test-e2e       Run Playwright browser tests"
	@echo "  audit          Audit production dependencies"
	@echo "  docker-config  Validate the Compose configuration"
	@echo "  docker-up      Build and start the container stack"
	@echo "  docker-down    Stop the container stack"
	@echo "  feature        Create a feature with NAME=<snake_case> [DRY_RUN=1]"
	@echo "  smoke-online-quality  Publish one credential-gated synthetic LangSmith event"
	@echo "  online-quality-plan      Preview CAM-43 LangSmith resources without credentials"
	@echo "  online-quality-setup     Reconcile CAM-43 resources with explicit execution"
	@echo "  online-quality-simulate  Publish the deterministic 12-session demo corpus"
	@echo "  online-quality-teardown  Delete owned resources while preserving project/traces"
	@echo "  secret-scan    Scan project files for likely credentials"
	@echo "  cleanup        Remove generated caches; CLEAN_VOLUMES=1 also removes local DB data"

setup:
	@sh scripts/setup.sh

dev:
	@sh scripts/dev.sh

verify:
	@sh scripts/verify.sh

test-e2e:
	@sh scripts/test-e2e.sh

audit:
	@sh scripts/audit.sh

docker-config:
	@sh scripts/docker.sh config

docker-up:
	@sh scripts/docker.sh up

docker-down:
	@sh scripts/docker.sh down

feature:
	@test -n "$(NAME)" || (echo "error: NAME=<snake_case> is required" >&2; exit 2)
	@cd backend && uv run python scripts/scaffold_feature.py "$(NAME)" $(if $(DRY_RUN),--dry-run,)

smoke-online-quality:
	@cd backend && uv run python scripts/smoke_online_quality.py --execute

online-quality-plan:
	@cd backend && uv run python scripts/online_quality_ops.py plan

online-quality-setup:
	@cd backend && uv run python scripts/online_quality_ops.py setup --execute

online-quality-simulate:
	@cd backend && uv run python scripts/online_quality_ops.py simulate --execute

online-quality-teardown:
	@cd backend && uv run python scripts/online_quality_ops.py teardown --execute

secret-scan:
	@sh scripts/secret-scan.sh

cleanup:
	@sh scripts/cleanup.sh
