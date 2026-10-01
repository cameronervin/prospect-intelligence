"""Feature router contract tests."""

from dataclasses import replace
from datetime import UTC, datetime
from typing import Any, cast
from uuid import UUID

import jwt
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.bootstrap.exception_handlers import register_exception_handlers
from app.features.authentication.public import (
    AuthenticationService,
    InMemoryUserRepository,
    JwtTokenService,
    build_authenticated_user,
)
from app.features.prospect_intelligence.api.router import build_router
from app.features.prospect_intelligence.contracts.models import (
    AnalysisOutput,
    FitVerdict,
    OutreachDraft,
    ProspectBrief,
    ProspectRun,
    RecommendedNextStep,
    ReviewAction,
    RunError,
    RunStatus,
    SourceCoverage,
    SourceCoverageStatus,
)
from app.features.prospect_intelligence.contracts.workflow import review_tool_call_id
from app.features.prospect_intelligence.domain.progress import SourceCalled, StepStarted
from app.features.prospect_intelligence.repositories.memory import (
    InMemoryAccountRepository,
    InMemoryPreferenceRepository,
    InMemoryRunRepository,
    InMemorySendReceiptRepository,
)
from app.features.prospect_intelligence.services.runs import ProspectRunService
from tests.deterministic_pipeline import DeterministicProspectPipeline
from tests.fakes import auth_context, authentication_user, synthetic_prospect_sources

NOW = datetime(2026, 9, 29, 12, tzinfo=UTC)
TEST_USER = authentication_user()
JWT_SECRET = "test-signing-secret-that-is-at-least-thirty-two-bytes"


def _test_authentication() -> AuthenticationService:
    return AuthenticationService(
        users=InMemoryUserRepository((TEST_USER,)),
        tokens=JwtTokenService(JWT_SECRET),
    )


def _test_user_dependency():
    return _test_authentication().login(TEST_USER.email, "prospect-demo").user


def test_runs_expose_sanitized_specialist_steps_for_polling() -> None:
    api, service, _ = api_with_service()
    run = service.create_run(auth_context(rep_id="rep-demo"), "acme-foods")
    service.start_run(run.id)
    service.progress.record(run.id, StepStarted("external-research", NOW))
    service.progress.record(
        run.id, SourceCalled("external-research", "search_sec", ok=False, at=NOW)
    )

    body = api.get(
        f"/api/v1/prospect-runs/{run.id}",
        headers={"X-Tenant-Id": "tenant-demo", "X-Rep-Id": "rep-demo"},
    ).json()

    assert body["stage"] == "External research running"
    assert [step["key"] for step in body["steps"]] == [
        "account-context",
        "external-research",
        "lane-analyst",
        "outreach-drafter:1",
        "quality-reviewer:1",
        "review",
    ]
    research = body["steps"][1]
    assert research["status"] == "running"
    assert research["started_at"] == NOW.isoformat().replace("+00:00", "Z")
    assert research["activity"] == [
        {
            "at": NOW.isoformat().replace("+00:00", "Z"),
            "source": "SEC EDGAR filings",
            "outcome": "unavailable",
        }
    ]


def api_with_service() -> tuple[TestClient, ProspectRunService, InMemoryRunRepository]:
    runs = InMemoryRunRepository()
    service = ProspectRunService(
        accounts=InMemoryAccountRepository.seeded(),
        runs=runs,
        receipts=InMemorySendReceiptRepository(),
        preferences=InMemoryPreferenceRepository(),
        clock=lambda: datetime(2026, 9, 29, 12, tzinfo=UTC),
    )
    app = FastAPI()
    register_exception_handlers(app)
    auth = _test_authentication()
    token = auth.login(TEST_USER.email, "prospect-demo").access_token
    app.include_router(build_router(service, lambda: None, build_authenticated_user(auth)))
    return TestClient(app, headers={"Authorization": f"Bearer {token}"}), service, runs


def client() -> TestClient:
    api, _, _ = api_with_service()
    return api


def test_missing_bearer_returns_typed_401_challenge() -> None:
    api, _, _ = api_with_service()
    del api.headers["authorization"]

    response = api.get("/api/v1/accounts")

    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"
    assert response.json()["error"]["code"] == "unauthorized"


def test_verified_identity_without_sales_rep_role_returns_403() -> None:
    api, _, _ = api_with_service()
    valid = _test_authentication().login(TEST_USER.email, "prospect-demo").access_token
    claims = jwt.decode(valid, options={"verify_signature": False})
    claims["roles"] = []
    token = jwt.encode(claims, JWT_SECRET, algorithm="HS256")

    response = api.get("/api/v1/accounts", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "forbidden"


def terminal_output(verdict: FitVerdict) -> AnalysisOutput:
    next_step = (
        RecommendedNextStep.NOT_A_FIT
        if verdict is FitVerdict.NO_FIT
        else RecommendedNextStep.NEEDS_MORE_DATA
    )
    return AnalysisOutput(
        verdict=verdict,
        brief=ProspectBrief(
            summary="Evidence does not support outreach.",
            markdown="Evidence does not support outreach.",
            recommended_next_step=next_step,
            recommendation="Do not send outreach.",
            lanes=(),
        ),
        outreach=None,
        source_coverage=(
            SourceCoverage(
                source="CRM",
                status=SourceCoverageStatus.COMPLETE,
            ),
        ),
    )


def test_accounts_ignore_browser_scope_headers_and_use_verified_token() -> None:
    response = client().get(
        "/api/v1/accounts",
        headers={"X-Tenant-Id": "tenant-other", "X-Rep-Id": "rep-other"},
    )
    assert response.status_code == 200
    assert response.json()["items"][0]["name"] == "Acme Foods"


def test_create_and_poll_run() -> None:
    api = client()
    headers = {"X-Tenant-Id": "tenant-demo", "X-Rep-Id": "rep-demo"}
    account_id = api.get("/api/v1/accounts", headers=headers).json()["items"][0]["id"]

    created = api.post(
        "/api/v1/prospect-runs",
        headers=headers,
        json={"account_id": account_id},
    )

    assert created.status_code == 202
    assert created.json()["status"] == "queued"
    assert created.json()["pending_review"] is None
    polled = api.get(f"/api/v1/prospect-runs/{created.json()['id']}", headers=headers)
    assert polled.status_code == 200
    assert polled.json()["id"] == created.json()["id"]


def test_awaiting_review_exposes_stable_review_contract() -> None:
    service = ProspectRunService(
        accounts=InMemoryAccountRepository.seeded(),
        runs=InMemoryRunRepository(),
        receipts=InMemorySendReceiptRepository(),
        preferences=InMemoryPreferenceRepository(),
        clock=lambda: datetime(2026, 9, 29, 12, tzinfo=UTC),
    )
    run = service.create_run(auth_context(rep_id="rep-demo"), "acme-foods")
    DeterministicProspectPipeline(service, synthetic_prospect_sources()).run(run.id)
    app = FastAPI()
    register_exception_handlers(app)
    app.include_router(build_router(service, lambda: None, _test_user_dependency))

    response = TestClient(app).get(
        f"/api/v1/prospect-runs/{run.id}",
        headers={"X-Tenant-Id": "tenant-demo", "X-Rep-Id": "rep-demo"},
    )

    assert response.status_code == 200
    assert response.json()["status"] == "awaiting_review"
    assert response.json()["pending_review"] == {
        "name": "send_outreach",
        "allowed_decisions": ["approve", "edit", "reject"],
        "tool_call_id": f"review-{run.id}",
    }
    assert "subject" not in response.json()["pending_review"]
    assert response.json()["outreach"]["subject"]


def test_fit_lanes_expose_lane_fit_score_components() -> None:
    api, service, _ = api_with_service()
    run = service.create_run(auth_context(rep_id="rep-demo"), "acme-foods")
    DeterministicProspectPipeline(service, synthetic_prospect_sources()).run(run.id)

    response = api.get(
        f"/api/v1/prospect-runs/{run.id}",
        headers={"X-Tenant-Id": "tenant-demo", "X-Rep-Id": "rep-demo"},
    )

    lanes = response.json()["brief"]["lanes"]
    assert lanes
    for lane in lanes:
        components = (lane["backhaul_fill"], lane["density"], lane["equipment_match"])
        assert all(0 <= value <= 1 for value in components)
        weighted = 0.5 * components[0] + 0.3 * components[1] + 0.2 * components[2]
        assert lane["fit_score"] == pytest.approx(weighted, abs=0.001)


def test_source_coverage_discloses_source_mode() -> None:
    api, service, _ = api_with_service()
    run = service.create_run(auth_context(rep_id="rep-demo"), "acme-foods")
    DeterministicProspectPipeline(service, synthetic_prospect_sources()).run(run.id)

    response = api.get(
        f"/api/v1/prospect-runs/{run.id}",
        headers={"X-Tenant-Id": "tenant-demo", "X-Rep-Id": "rep-demo"},
    )

    coverage = response.json()["source_coverage"]
    assert coverage
    assert {item["source"]: item["mode"] for item in coverage} == {
        "GenLogs fixture": "fixture",
        "Carrier network fixture": "fixture",
    }


def test_pending_review_is_null_for_non_review_lifecycle_states() -> None:
    api, service, runs = api_with_service()
    headers = {"X-Tenant-Id": "tenant-demo", "X-Rep-Id": "rep-demo"}
    run = service.create_run(auth_context(rep_id="rep-demo"), "acme-foods")

    assert (
        api.get(f"/api/v1/prospect-runs/{run.id}", headers=headers).json()["pending_review"] is None
    )

    service.start_run(run.id)
    assert (
        api.get(f"/api/v1/prospect-runs/{run.id}", headers=headers).json()["pending_review"] is None
    )

    DeterministicProspectPipeline(service, synthetic_prospect_sources()).run(run.id)
    service.review_run(
        run.id,
        ReviewAction.REJECT,
        tool_call_id=review_tool_call_id(run.id),
    )
    rejected = api.get(f"/api/v1/prospect-runs/{run.id}", headers=headers).json()
    assert rejected["status"] == "rejected"
    assert rejected["pending_review"] is None

    failed_run = service.create_run(auth_context(rep_id="rep-demo"), "acme-foods")
    runs.save(
        replace(
            failed_run,
            status=RunStatus.FAILED,
            stage="Run failed",
            error=RunError(
                code="execution_failed",
                message="The run could not be completed.",
                retryable=False,
            ),
        )
    )
    failed = api.get(f"/api/v1/prospect-runs/{failed_run.id}", headers=headers).json()
    assert failed["status"] == "failed"
    assert failed["pending_review"] is None
    assert failed["error"] == {
        "code": "execution_failed",
        "message": "The run could not be completed.",
        "retryable": False,
    }


@pytest.mark.parametrize("verdict", [FitVerdict.NO_FIT, FitVerdict.NEEDS_MORE_DATA])
def test_terminal_success_verdicts_are_completed_without_review(
    verdict: FitVerdict,
) -> None:
    api, service, _ = api_with_service()
    headers = {"X-Tenant-Id": "tenant-demo", "X-Rep-Id": "rep-demo"}
    run = service.create_run(auth_context(rep_id="rep-demo"), "acme-foods")
    service.start_run(run.id)
    service.submit_analysis(run.id, terminal_output(verdict))

    response = api.get(f"/api/v1/prospect-runs/{run.id}", headers=headers)

    assert response.status_code == 200
    assert response.json()["status"] == "completed"
    assert response.json()["verdict"] == verdict.value
    assert response.json()["pending_review"] is None


def test_tenant_header_cannot_override_token_scope() -> None:
    api = client()
    owner = {"X-Tenant-Id": "tenant-demo", "X-Rep-Id": "rep-demo"}
    account_id = api.get("/api/v1/accounts", headers=owner).json()["items"][0]["id"]
    created = api.post(
        "/api/v1/prospect-runs",
        headers=owner,
        json={"account_id": account_id},
    ).json()

    response = api.get(
        f"/api/v1/prospect-runs/{created['id']}",
        headers={"X-Tenant-Id": "tenant-other", "X-Rep-Id": "rep-demo"},
    )

    assert response.status_code == 200


def test_rep_header_cannot_override_token_scope() -> None:
    api = client()
    owner = {"X-Tenant-Id": "tenant-demo", "X-Rep-Id": "rep-owner"}
    created = api.post(
        "/api/v1/prospect-runs",
        headers=owner,
        json={"account_id": "acme-foods"},
    ).json()

    response = api.get(
        f"/api/v1/prospect-runs/{created['id']}",
        headers={"X-Tenant-Id": "tenant-demo", "X-Rep-Id": "rep-other"},
    )

    assert response.status_code == 200
    assert response.json()["id"] == created["id"]


def test_unknown_account_and_run_return_ownership_safe_not_found() -> None:
    api = client()
    headers = {"X-Tenant-Id": "tenant-demo", "X-Rep-Id": "rep-demo"}

    unknown_account = api.post(
        "/api/v1/prospect-runs",
        headers=headers,
        json={"account_id": "missing-account"},
    )
    unknown_run = api.get(
        "/api/v1/prospect-runs/00000000-0000-0000-0000-000000000001",
        headers=headers,
    )

    assert unknown_account.status_code == 404
    assert unknown_account.json()["error"]["message"] == "Account not found"
    assert "missing-account" not in unknown_account.text
    assert unknown_run.status_code == 404
    assert unknown_run.json()["error"]["message"] == "Run not found"
    assert "00000000" not in unknown_run.text


def test_malformed_run_id_returns_typed_validation_failure() -> None:
    response = client().get(
        "/api/v1/prospect-runs/not-a-uuid",
        headers={"X-Tenant-Id": "tenant-demo", "X-Rep-Id": "rep-demo"},
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"
    assert response.json()["error"]["issues"][0]["location"] == "path.run_id"
    assert "not-a-uuid" not in response.text


def test_malformed_payload_has_typed_failure_without_echoing_body() -> None:
    response = client().post(
        "/api/v1/prospect-runs",
        headers={
            "Content-Type": "application/json",
            "X-Tenant-Id": "tenant-demo",
            "X-Rep-Id": "rep-demo",
        },
        content='{"account_id": "secret-value"',
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"
    assert "secret-value" not in response.text


def test_extra_request_fields_are_rejected_without_echoing_values() -> None:
    response = client().post(
        "/api/v1/prospect-runs",
        headers={"X-Tenant-Id": "tenant-demo", "X-Rep-Id": "rep-demo"},
        json={"account_id": "acme-foods", "private_context": "secret-customer-value"},
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"
    assert response.json()["error"]["issues"][0]["location"] == "body.private_context"
    assert "secret-customer-value" not in response.text


def test_edit_review_requires_a_body_at_the_api_boundary() -> None:
    response = client().post(
        "/api/v1/prospect-runs/00000000-0000-0000-0000-000000000001/review",
        headers={"X-Tenant-Id": "tenant-demo", "X-Rep-Id": "rep-demo"},
        json={
            "decision": "edit",
            "subject": "Edited subject",
            "tool_call_id": review_tool_call_id(UUID("00000000-0000-0000-0000-000000000001")),
        },
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"


def test_review_is_retryable_when_durable_handler_is_unavailable() -> None:
    api = client()
    headers = {"X-Tenant-Id": "tenant-demo", "X-Rep-Id": "rep-demo"}
    created = api.post(
        "/api/v1/prospect-runs",
        headers=headers,
        json={"account_id": "acme-foods"},
    ).json()

    response = api.post(
        f"/api/v1/prospect-runs/{created['id']}/review",
        headers=headers,
        json={
            "decision": "approve",
            "tool_call_id": review_tool_call_id(UUID(created["id"])),
        },
    )

    assert response.status_code == 503
    assert response.json()["error"] == {
        "code": "service_unavailable",
        "message": "Prospect review is temporarily unavailable",
        "retryable": True,
        "issues": [],
    }


def test_review_rejects_a_noncanonical_token_as_a_conflict() -> None:
    service = ProspectRunService(
        accounts=InMemoryAccountRepository.seeded(),
        runs=InMemoryRunRepository(),
        receipts=InMemorySendReceiptRepository(),
        preferences=InMemoryPreferenceRepository(),
        clock=lambda: datetime(2026, 9, 29, 12, tzinfo=UTC),
    )
    run = service.create_run(auth_context(rep_id="rep-demo"), "acme-foods")
    DeterministicProspectPipeline(service, synthetic_prospect_sources()).run(run.id)

    async def review_handler(
        run_id: UUID,
        action: ReviewAction,
        *,
        tool_call_id: str,
        edited_outreach: OutreachDraft | None = None,
        auth: Any | None = None,
    ) -> ProspectRun:
        del auth
        return service.review_run(
            run_id,
            action,
            tool_call_id=tool_call_id,
            edited_outreach=edited_outreach,
        )

    app = FastAPI()
    register_exception_handlers(app)
    app.include_router(
        build_router(service, lambda: cast(Any, review_handler), _test_user_dependency)
    )

    response = TestClient(app).post(
        f"/api/v1/prospect-runs/{run.id}/review",
        headers={"X-Tenant-Id": "tenant-demo", "X-Rep-Id": "rep-demo"},
        json={"decision": "approve", "tool_call_id": "review-wrong-run"},
    )

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "conflict"
    assert service.get_run(run.id).status is RunStatus.AWAITING_REVIEW


@pytest.mark.parametrize(
    ("tenant_id", "rep_id", "subject"),
    [
        ("tenant-other", "rep-owner", "rep-owner"),
        ("tenant-demo", "rep-other", "rep-other"),
        ("tenant-demo", "rep-owner", "different-subject"),
    ],
)
def test_out_of_scope_review_returns_not_found_without_calling_handler(
    tenant_id: str,
    rep_id: str,
    subject: str,
) -> None:
    service = ProspectRunService(
        accounts=InMemoryAccountRepository.seeded(),
        runs=InMemoryRunRepository(),
        receipts=InMemorySendReceiptRepository(),
        preferences=InMemoryPreferenceRepository(),
        clock=lambda: datetime(2026, 9, 29, 12, tzinfo=UTC),
    )
    run = service.create_run(auth_context(rep_id="rep-owner"), "acme-foods")
    DeterministicProspectPipeline(service, synthetic_prospect_sources()).run(run.id)
    calls: list[UUID] = []

    async def review_handler(
        run_id: UUID,
        action: ReviewAction,
        *,
        tool_call_id: str,
        edited_outreach: OutreachDraft | None = None,
    ) -> ProspectRun:
        del action, tool_call_id, edited_outreach
        calls.append(run_id)
        return service.get_run(run_id)

    app = FastAPI()
    register_exception_handlers(app)
    requester = replace(TEST_USER, tenant_id=tenant_id, rep_id=rep_id, subject=subject)
    auth = AuthenticationService(
        users=InMemoryUserRepository((requester,)),
        tokens=JwtTokenService(JWT_SECRET),
    )
    app.include_router(
        build_router(service, lambda: cast(Any, review_handler), build_authenticated_user(auth))
    )
    token = auth.login(requester.email, "prospect-demo").access_token

    response = TestClient(app).post(
        f"/api/v1/prospect-runs/{run.id}/review",
        headers={
            "Authorization": f"Bearer {token}",
            "X-Tenant-Id": "tenant-demo",
            "X-Rep-Id": "rep-owner",
        },
        json={"decision": "approve", "tool_call_id": review_tool_call_id(run.id)},
    )

    assert response.status_code == 404
    assert response.json()["error"]["message"] == "Run not found"
    assert calls == []


def test_unsafe_edit_returns_sanitized_conflict_without_echoing_draft() -> None:
    service = ProspectRunService(
        accounts=InMemoryAccountRepository.seeded(),
        runs=InMemoryRunRepository(),
        receipts=InMemorySendReceiptRepository(),
        preferences=InMemoryPreferenceRepository(),
        clock=lambda: datetime(2026, 9, 29, 12, tzinfo=UTC),
    )
    run = service.create_run(auth_context(rep_id="rep-demo"), "acme-foods")
    DeterministicProspectPipeline(service, synthetic_prospect_sources()).run(run.id)

    class ReviewHandler:
        async def __call__(
            self,
            run_id: UUID,
            action: ReviewAction,
            *,
            tool_call_id: str,
            edited_outreach: OutreachDraft | None = None,
            auth: Any | None = None,
        ) -> ProspectRun:
            del auth
            return service.review_run(
                run_id,
                action,
                tool_call_id=tool_call_id,
                edited_outreach=edited_outreach,
            )

    app = FastAPI()
    register_exception_handlers(app)
    app.include_router(
        build_router(service, lambda: cast(Any, ReviewHandler()), _test_user_dependency)
    )

    response = TestClient(app).post(
        f"/api/v1/prospect-runs/{run.id}/review",
        headers={"X-Tenant-Id": "tenant-demo", "X-Rep-Id": "rep-demo"},
        json={
            "decision": "edit",
            "subject": "Private rate proposal",
            "body": "secret-customer-value and internal margin",
            "tool_call_id": review_tool_call_id(run.id),
        },
    )

    assert response.status_code == 409
    assert response.json()["error"] == {
        "code": "conflict",
        "message": "customer outreach contains internal-only information",
        "retryable": False,
        "issues": [],
    }
    assert "secret-customer-value" not in response.text


def test_unexpected_failure_returns_generic_error_without_internal_details() -> None:
    class ExplodingService:
        def get_scoped_run(
            self,
            run_id: UUID,
            tenant_id: str,
            rep_id: str,
        ) -> ProspectRun:
            del run_id, tenant_id, rep_id
            raise RuntimeError("database password and private prompt")

    app = FastAPI()
    register_exception_handlers(app)
    app.include_router(
        build_router(
            cast(ProspectRunService, ExplodingService()), lambda: None, _test_user_dependency
        )
    )

    response = TestClient(app, raise_server_exceptions=False).get(
        "/api/v1/prospect-runs/00000000-0000-0000-0000-000000000001",
        headers={"X-Tenant-Id": "tenant-demo", "X-Rep-Id": "rep-demo"},
    )

    assert response.status_code == 500
    assert response.json()["error"] == {
        "code": "internal_error",
        "message": "The request could not be completed.",
        "retryable": False,
        "issues": [],
    }
    assert "password" not in response.text
    assert "prompt" not in response.text


def test_review_route_uses_lifespan_provided_agent_review_handler() -> None:
    service = ProspectRunService(
        accounts=InMemoryAccountRepository.seeded(),
        runs=InMemoryRunRepository(),
        receipts=InMemorySendReceiptRepository(),
        preferences=InMemoryPreferenceRepository(),
        clock=lambda: datetime(2026, 9, 29, 12, tzinfo=UTC),
    )
    run = service.create_run(auth_context(rep_id="rep-demo"), "acme-foods")
    DeterministicProspectPipeline(service, synthetic_prospect_sources()).run(run.id)
    calls: list[ReviewAction] = []

    class ReviewHandler:
        async def __call__(
            self,
            run_id: UUID,
            action: ReviewAction,
            *,
            tool_call_id: str,
            edited_outreach: OutreachDraft | None = None,
            auth: Any | None = None,
        ) -> ProspectRun:
            del auth
            calls.append(action)
            return service.review_run(
                run_id,
                action,
                tool_call_id=tool_call_id,
                edited_outreach=edited_outreach,
            )

    app = FastAPI()
    register_exception_handlers(app)
    handler = ReviewHandler()
    app.include_router(build_router(service, lambda: cast(Any, handler), _test_user_dependency))

    response = TestClient(app).post(
        f"/api/v1/prospect-runs/{run.id}/review",
        headers={"X-Tenant-Id": "tenant-demo", "X-Rep-Id": "rep-demo"},
        json={"decision": "approve", "tool_call_id": review_tool_call_id(run.id)},
    )

    assert response.status_code == 200
    assert calls == [ReviewAction.APPROVE]
    assert response.json()["status"] == "completed"
    assert response.json()["pending_review"] is None


def test_openapi_declares_typed_error_response() -> None:
    schema = client().get("/openapi.json").json()
    validation_response = schema["paths"]["/api/v1/prospect-runs"]["post"]["responses"]["422"]

    assert validation_response["content"]["application/json"]["schema"]["$ref"].endswith(
        "/ErrorResponse"
    )
