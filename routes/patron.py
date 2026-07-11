import uuid

from fastapi import APIRouter, Depends, File, Form, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from core.file import get_file, is_over_max_file_size, upload_file
from core.log import logger
from core.responses import (
    BadRequest,
    Forbidden,
    InternalServerError,
    NoContent,
    NotFound,
    Ok,
    Unauthorized,
    common_response,
)
from core.security import check_permissions, get_current_user
from models import get_db_sync
from models.User import MANAGEMENT_PARTICIPANT, User
from repository import patron as patronRepo
from schemas.auth import AuthorizationStatusEnum
from schemas.common import (
    BadRequestResponse,
    ForbiddenResponse,
    InternalServerErrorResponse,
    NotFoundResponse,
    UnauthorizedResponse,
)
from schemas.patron import (
    PatronListResponse,
    PatronResponseItem,
    PatronTier,
    patron_list_response_from_models,
    patron_response_item_from_model,
)
from settings import MAX_FILE_SIZE_MB

router = APIRouter(prefix="/patron", tags=["Patron"])

PATRON_IMAGE_CONTENT_TYPES = {
    "image/png": ".png",
    "image/jpeg": ".jpg",
    "image/svg+xml": ".svg",
}


def _authorize_management_user(current_user: User | None):
    auth_status = check_permissions(current_user, MANAGEMENT_PARTICIPANT)
    if auth_status == AuthorizationStatusEnum.UNAUTHORIZED:
        return common_response(Unauthorized(message="Unauthorized"))
    if auth_status == AuthorizationStatusEnum.FORBIDDEN:
        return common_response(Forbidden())
    return None


async def _upload_patron_image(image: UploadFile | None) -> str | None:
    if image is None:
        return None
    if image.content_type not in PATRON_IMAGE_CONTENT_TYPES:
        raise ValueError("Image must be png, jpeg, or svg")
    if is_over_max_file_size(upload_file=image):
        raise ValueError(f"File size exceeds the maximum limit ({MAX_FILE_SIZE_MB} mb)")

    suffix = PATRON_IMAGE_CONTENT_TYPES[image.content_type]
    path = f"patron/{uuid.uuid4()}{suffix}"
    return await upload_file(upload_file=image, path=path)


@router.get(
    "/",
    responses={
        "200": {"model": PatronListResponse},
        "500": {"model": InternalServerErrorResponse},
    },
)
def get_patrons(db: Session = Depends(get_db_sync)):
    try:
        patrons = patronRepo.get_patrons(db=db)
        data = patron_list_response_from_models(patrons)
        return common_response(Ok(data=data.model_dump()))
    except Exception as e:
        logger.error(f"Error fetching patrons: {e}")
        return common_response(InternalServerError(error=str(e)))


@router.post(
    "/",
    responses={
        "200": {"model": PatronResponseItem},
        "400": {"model": BadRequestResponse},
        "401": {"model": UnauthorizedResponse},
        "403": {"model": ForbiddenResponse},
        "500": {"model": InternalServerErrorResponse},
    },
)
async def create_patron(
    name: str = Form(...),
    tier: PatronTier = Form(...),
    image: UploadFile | None = File(None),
    db: Session = Depends(get_db_sync),
    current_user: User | None = Depends(get_current_user),
):
    unauthorized_response = _authorize_management_user(current_user)
    if unauthorized_response is not None:
        return unauthorized_response

    try:
        image_path = await _upload_patron_image(image)
        patron = patronRepo.insert_patron(
            db=db,
            name=name,
            tier=tier.value,
            image=image_path,
        )
        data = patron_response_item_from_model(patron)
        return common_response(Ok(data=data.model_dump()))
    except ValueError as e:
        return common_response(BadRequest(message=str(e)))
    except Exception as e:
        logger.error(f"Error creating patron: {e}")
        return common_response(InternalServerError(error=str(e)))


@router.get(
    "/{patron_id}",
    responses={
        "200": {"model": PatronResponseItem},
        "401": {"model": UnauthorizedResponse},
        "403": {"model": ForbiddenResponse},
        "404": {"model": NotFoundResponse},
        "500": {"model": InternalServerErrorResponse},
    },
)
def get_patron(
    patron_id: str,
    db: Session = Depends(get_db_sync),
    current_user: User | None = Depends(get_current_user),
):
    unauthorized_response = _authorize_management_user(current_user)
    if unauthorized_response is not None:
        return unauthorized_response

    try:
        patron = patronRepo.get_patron_by_id(db=db, id=patron_id)
        if patron is None:
            return common_response(
                NotFound(message=f"patron with id = {patron_id} not found")
            )
        data = patron_response_item_from_model(patron)
        return common_response(Ok(data=data.model_dump()))
    except Exception as e:
        logger.error(f"Error fetching patron: {e}")
        return common_response(InternalServerError(error=str(e)))


@router.put(
    "/{patron_id}",
    responses={
        "200": {"model": PatronResponseItem},
        "400": {"model": BadRequestResponse},
        "401": {"model": UnauthorizedResponse},
        "403": {"model": ForbiddenResponse},
        "404": {"model": NotFoundResponse},
        "500": {"model": InternalServerErrorResponse},
    },
)
async def update_patron(
    patron_id: str,
    name: str = Form(...),
    tier: PatronTier = Form(...),
    image: UploadFile | None = File(None),
    db: Session = Depends(get_db_sync),
    current_user: User | None = Depends(get_current_user),
):
    unauthorized_response = _authorize_management_user(current_user)
    if unauthorized_response is not None:
        return unauthorized_response

    try:
        patron = patronRepo.get_patron_by_id(db=db, id=patron_id)
        if patron is None:
            return common_response(
                NotFound(message=f"patron with id = {patron_id} not found")
            )

        image_path = await _upload_patron_image(image)
        updated_patron = patronRepo.update_patron(
            db=db,
            patron=patron,
            name=name,
            tier=tier.value,
            image=image_path,
        )
        data = patron_response_item_from_model(updated_patron)
        return common_response(Ok(data=data.model_dump()))
    except ValueError as e:
        return common_response(BadRequest(message=str(e)))
    except Exception as e:
        logger.error(f"Error updating patron: {e}")
        return common_response(InternalServerError(error=str(e)))


@router.delete(
    "/{patron_id}",
    responses={
        "204": {"description": "No Content"},
        "401": {"model": UnauthorizedResponse},
        "403": {"model": ForbiddenResponse},
        "404": {"model": NotFoundResponse},
        "500": {"model": InternalServerErrorResponse},
    },
)
def delete_patron(
    patron_id: str,
    db: Session = Depends(get_db_sync),
    current_user: User | None = Depends(get_current_user),
):
    unauthorized_response = _authorize_management_user(current_user)
    if unauthorized_response is not None:
        return unauthorized_response

    try:
        patron = patronRepo.get_patron_by_id(db=db, id=patron_id)
        if patron is None:
            return common_response(
                NotFound(message=f"patron with id = {patron_id} not found")
            )
        patronRepo.delete_patron(db=db, patron=patron)
        return common_response(NoContent())
    except Exception as e:
        logger.error(f"Error deleting patron: {e}")
        return common_response(InternalServerError(error=str(e)))


@router.get(
    "/{patron_id}/image/",
    response_class=FileResponse,
    responses={
        "404": {"model": NotFoundResponse},
        "500": {"model": InternalServerErrorResponse},
    },
)
def get_patron_image(patron_id: str, db: Session = Depends(get_db_sync)):
    try:
        patron = patronRepo.get_patron_by_id(db=db, id=patron_id)
        if patron is None:
            return common_response(
                NotFound(message=f"patron with id = {patron_id} not found")
            )
        if patron.image is None:
            return common_response(NotFound(message="Patron image not found"))

        image = get_file(path=patron.image)
        if image is None:
            return common_response(NotFound(message="Patron image file not found"))
        return image
    except Exception as e:
        logger.error(f"Error fetching patron image: {e}")
        return common_response(InternalServerError(error=str(e)))
