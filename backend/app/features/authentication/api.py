"""Authentication HTTP boundary and bearer dependency."""

from collections.abc import Callable
from typing import Annotated

import structlog
from fastapi import APIRouter, Depends, HTTPException, Response, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.platform.api.errors import ErrorResponse

from .contracts import SessionUser, UserRole
from .schemas import LoginRequest, SessionResponse, SessionUserResponse, TokenResponse
from .services.auth import AuthenticationError, AuthenticationService

_BEARER = HTTPBearer(auto_error=False)
AuthenticatedUser = Callable[..., SessionUser]
_NO_CACHE_HEADERS = {
    "Cache-Control": "no-store, max-age=0",
    "Pragma": "no-cache",
}
logger = structlog.get_logger(__name__)


def session_user_response(user: SessionUser) -> SessionUserResponse:
    return SessionUserResponse(
        subject=user.auth.subject,
        email=user.email,
        display_name=user.display_name,
        tenant_id=user.auth.tenant_id,
        rep_id=user.auth.rep_id,
        roles=[role.value for role in sorted(user.auth.roles, key=lambda item: item.value)],
    )


def build_authenticated_user(service: AuthenticationService) -> AuthenticatedUser:
    def authenticated_user(
        credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_BEARER)],
    ) -> SessionUser:
        if credentials is None or credentials.scheme.casefold() != "bearer":
            logger.warning(
                "authentication_failed",
                operation="verify",
                reason="missing_credentials",
            )
            raise _unauthorized()
        try:
            return service.verify(credentials.credentials)
        except AuthenticationError as error:
            logger.warning(
                "authentication_failed",
                operation="verify",
                reason="invalid_token",
            )
            raise _unauthorized() from error

    return authenticated_user


def require_sales_rep(user: SessionUser) -> SessionUser:
    try:
        user.auth.require(UserRole.SALES_REP)
    except PermissionError as error:
        logger.warning(
            "authorization_failed",
            operation="require_sales_rep",
            reason="missing_role",
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="The authenticated user is not permitted to use this application.",
            headers=_NO_CACHE_HEADERS,
        ) from error
    return user


def build_router(
    service: AuthenticationService, authenticated_user: AuthenticatedUser
) -> APIRouter:
    router = APIRouter(
        prefix="/api/v1/auth",
        tags=["authentication"],
        responses={401: {"model": ErrorResponse}, 403: {"model": ErrorResponse}},
    )

    @router.post("/token", response_model=TokenResponse)
    def login(request: LoginRequest, response: Response) -> TokenResponse:
        _disable_caching(response)
        try:
            session = service.login(str(request.email), request.password)
        except AuthenticationError as error:
            logger.warning(
                "authentication_failed",
                operation="login",
                reason="invalid_credentials",
            )
            raise _unauthorized("Email or password is incorrect.") from error
        logger.info("authentication_succeeded", operation="login")
        return TokenResponse(
            access_token=session.access_token,
            user=session_user_response(session.user),
            expires_at=session.expires_at,
            absolute_expires_at=session.absolute_expires_at,
        )

    @router.post("/refresh", response_model=TokenResponse)
    def refresh(
        response: Response,
        credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_BEARER)],
    ) -> TokenResponse:
        _disable_caching(response)
        if credentials is None or credentials.scheme.casefold() != "bearer":
            logger.warning(
                "authentication_failed",
                operation="refresh",
                reason="missing_credentials",
            )
            raise _unauthorized()
        try:
            session = service.refresh(credentials.credentials)
        except AuthenticationError as error:
            logger.warning(
                "authentication_failed",
                operation="refresh",
                reason="invalid_token",
            )
            raise _unauthorized("The session has expired. Sign in again.") from error
        logger.info("authentication_succeeded", operation="refresh")
        return TokenResponse(
            access_token=session.access_token,
            user=session_user_response(session.user),
            expires_at=session.expires_at,
            absolute_expires_at=session.absolute_expires_at,
        )

    @router.get("/me", response_model=SessionResponse)
    def me(
        response: Response,
        user: Annotated[SessionUser, Depends(authenticated_user)],
    ) -> SessionResponse:
        _disable_caching(response)
        return SessionResponse(user=session_user_response(user))

    return router


def _disable_caching(response: Response) -> None:
    response.headers.update(_NO_CACHE_HEADERS)


def _unauthorized(message: str = "A valid bearer token is required.") -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=message,
        headers={"WWW-Authenticate": "Bearer", **_NO_CACHE_HEADERS},
    )
