from fastapi import APIRouter, Depends, Header, HTTPException, status
from shared_schemas import (
    AuthResponse,
    LoginRequest,
    LogoutResponse,
    RegistrationResponse,
    RegisterRequest,
    UserProfile,
    UserProfileUpdate,
)

from rag_api.dependencies import RequestAuthContext, get_local_auth_service, get_request_auth_context, verify_rag_api_key
from rag_api.services.auth import TokenValidationError
from rag_api.services.local_auth import LocalAuthError, LocalAuthService

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


@router.post("/register", response_model=RegistrationResponse, dependencies=[Depends(verify_rag_api_key)])
async def register(
    request: RegisterRequest,
    service: LocalAuthService = Depends(get_local_auth_service),
) -> RegistrationResponse:
    try:
        return service.register(request)
    except LocalAuthError as error:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(error)) from error


@router.post("/login", response_model=AuthResponse, dependencies=[Depends(verify_rag_api_key)])
async def login(
    request: LoginRequest,
    service: LocalAuthService = Depends(get_local_auth_service),
) -> AuthResponse:
    try:
        return service.login(request)
    except LocalAuthError as error:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(error)) from error


@router.get("/me", response_model=UserProfile)
async def me(
    auth_context: RequestAuthContext = Depends(get_request_auth_context),
    service: LocalAuthService = Depends(get_local_auth_service),
) -> UserProfile:
    if auth_context.user_context is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="No authenticated user session.")
    profile = service.profile_for_user_id(auth_context.user_context.user_id)
    if profile is not None:
        return profile
    return UserProfile(
        user_id=auth_context.user_context.user_id,
        email=auth_context.user_context.email,
        name=auth_context.user_context.email,
        tenant_id=auth_context.user_context.tenant_id,
        acl_tags=auth_context.user_context.acl_tags,
        groups=auth_context.user_context.groups,
        roles=auth_context.user_context.roles,
    )


@router.patch("/me", response_model=UserProfile)
async def update_me(
    request: UserProfileUpdate,
    auth_context: RequestAuthContext = Depends(get_request_auth_context),
    service: LocalAuthService = Depends(get_local_auth_service),
) -> UserProfile:
    if auth_context.user_context is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="No authenticated user session.")
    try:
        return service.update_profile(auth_context.user_context.user_id, request)
    except LocalAuthError as error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(error)) from error


@router.post("/logout", response_model=LogoutResponse)
async def logout(
    authorization: str | None = Header(default=None),
    _auth_context: RequestAuthContext = Depends(get_request_auth_context),
    service: LocalAuthService = Depends(get_local_auth_service),
) -> LogoutResponse:
    token = _bearer_token(authorization)
    if token:
        try:
            service.logout(token)
        except TokenValidationError as error:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(error)) from error
    return LogoutResponse(success=True)


def _bearer_token(authorization: str | None) -> str | None:
    if authorization and authorization.startswith("Bearer "):
        return authorization.split(" ", maxsplit=1)[1]
    return None

