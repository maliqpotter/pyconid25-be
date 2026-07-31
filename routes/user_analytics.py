from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from core.log import logger
from core.responses import (
    Forbidden,
    InternalServerError,
    Ok,
    Unauthorized,
    common_response,
)
from core.security import check_permissions, get_current_user
from models import get_db_sync
from models.User import MANAGEMENT_PARTICIPANT, User
from repository import user_analytics as userAnalyticsRepo
from schemas.auth import AuthorizationStatusEnum
from schemas.common import (
    ForbiddenResponse,
    InternalServerErrorResponse,
    UnauthorizedResponse,
)
from schemas.user_analytics import (
    UserAnalyticsByCityResponse,
    UserAnalyticsByCountryResponse,
    UserAnalyticsByStateResponse,
)

router = APIRouter(prefix="/analitic/user", tags=["User Analytics"])


def _authorize_management_user(current_user: User | None):
    auth_status = check_permissions(current_user, MANAGEMENT_PARTICIPANT)
    if auth_status == AuthorizationStatusEnum.UNAUTHORIZED:
        return common_response(Unauthorized(message="Unauthorized"))
    if auth_status == AuthorizationStatusEnum.FORBIDDEN:
        return common_response(Forbidden())
    return None


@router.get(
    "/city/",
    responses={
        "200": {"model": UserAnalyticsByCityResponse},
        "401": {"model": UnauthorizedResponse},
        "403": {"model": ForbiddenResponse},
        "500": {"model": InternalServerErrorResponse},
    },
)
def get_user_analytics_by_city(
    db: Session = Depends(get_db_sync),
    current_user: User | None = Depends(get_current_user),
):
    unauthorized_response = _authorize_management_user(current_user)
    if unauthorized_response is not None:
        return unauthorized_response

    try:
        data = userAnalyticsRepo.get_registered_users_count_by_city(db=db)
        return common_response(
            Ok(data=UserAnalyticsByCityResponse.model_validate(data).model_dump())
        )
    except Exception as e:
        logger.error(f"Error fetching user analytics by city: {e}")
        return common_response(InternalServerError(error=str(e)))


@router.get(
    "/state/",
    responses={
        "200": {"model": UserAnalyticsByStateResponse},
        "401": {"model": UnauthorizedResponse},
        "403": {"model": ForbiddenResponse},
        "500": {"model": InternalServerErrorResponse},
    },
)
def get_user_analytics_by_state(
    db: Session = Depends(get_db_sync),
    current_user: User | None = Depends(get_current_user),
):
    unauthorized_response = _authorize_management_user(current_user)
    if unauthorized_response is not None:
        return unauthorized_response

    try:
        data = userAnalyticsRepo.get_registered_users_count_by_state(db=db)
        return common_response(
            Ok(data=UserAnalyticsByStateResponse.model_validate(data).model_dump())
        )
    except Exception as e:
        logger.error(f"Error fetching user analytics by state: {e}")
        return common_response(InternalServerError(error=str(e)))


@router.get(
    "/country/",
    responses={
        "200": {"model": UserAnalyticsByCountryResponse},
        "401": {"model": UnauthorizedResponse},
        "403": {"model": ForbiddenResponse},
        "500": {"model": InternalServerErrorResponse},
    },
)
def get_user_analytics_by_country(
    db: Session = Depends(get_db_sync),
    current_user: User | None = Depends(get_current_user),
):
    unauthorized_response = _authorize_management_user(current_user)
    if unauthorized_response is not None:
        return unauthorized_response

    try:
        data = userAnalyticsRepo.get_registered_users_count_by_country(db=db)
        return common_response(
            Ok(data=UserAnalyticsByCountryResponse.model_validate(data).model_dump())
        )
    except Exception as e:
        logger.error(f"Error fetching user analytics by country: {e}")
        return common_response(InternalServerError(error=str(e)))
