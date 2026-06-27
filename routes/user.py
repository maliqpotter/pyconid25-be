from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from core.responses import (
    Forbidden,
    NotFound,
    Ok,
    Unauthorized,
    common_response,
)
from core.security import check_permissions, get_current_user
from models import get_db_sync
from models.User import MANAGEMENT_PARTICIPANT, User
from repository import user as userRepo
from schemas.auth import AuthorizationStatusEnum
from schemas.common import (
    ForbiddenResponse,
    InternalServerErrorResponse,
    NotFoundResponse,
)
from schemas.user import UserListResponse, UserQrDetail


router = APIRouter(prefix="/user", tags=["User"])


@router.get(
    "/qr/",
    responses={
        "200": {"model": UserListResponse},
        "403": {"model": ForbiddenResponse},
        "500": {"model": InternalServerErrorResponse},
    },
)
async def get_user_for_qr(
    db: Session = Depends(get_db_sync),
    current_user: User = Depends(get_current_user),
    search: str | None = Query(
        None, description="Search users by name, username, or email"
    ),
):
    auth_status = check_permissions(current_user, MANAGEMENT_PARTICIPANT)
    if auth_status == AuthorizationStatusEnum.UNAUTHORIZED:
        return common_response(Unauthorized(message="Unauthorized"))
    if auth_status == AuthorizationStatusEnum.FORBIDDEN:
        return common_response(
            Forbidden(custom_response="Forbidden: Insufficient permissions")
        )

    all_user = userRepo.get_all_user(db=db, search=search, all=False)
    return common_response(
        Ok(
            data=UserListResponse(
                results=[
                    UserQrDetail(
                        id=str(user.id),
                        username=user.username,
                        first_name=user.first_name,
                        last_name=user.last_name,
                        email=user.email,
                    )
                    for user in all_user
                ]
            ).model_dump()
        )
    )


@router.get(
    "/{user_id}/qr/",
    responses={
        "200": {"model": UserQrDetail},
        "403": {"model": ForbiddenResponse},
        "404": {"model": NotFoundResponse},
        "500": {"model": InternalServerErrorResponse},
    },
)
async def get_detail_user_for_qr(
    user_id: str,
    db: Session = Depends(get_db_sync),
    current_user: User = Depends(get_current_user),
):
    auth_status = check_permissions(current_user, MANAGEMENT_PARTICIPANT)
    if auth_status == AuthorizationStatusEnum.UNAUTHORIZED:
        return common_response(Unauthorized(message="Unauthorized"))
    if auth_status == AuthorizationStatusEnum.FORBIDDEN:
        return common_response(
            Forbidden(custom_response="Forbidden: Insufficient permissions")
        )

    user = userRepo.get_user_by_id(db=db, id=user_id)
    if not user:
        return common_response(NotFound(message="User not found"))

    return common_response(
        Ok(
            data=UserQrDetail(
                id=str(user.id),
                username=user.username,
                first_name=user.first_name,
                last_name=user.last_name,
                email=user.email,
            ).model_dump()
        )
    )
