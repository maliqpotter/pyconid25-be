from typing import List, Optional

from pydantic import BaseModel


class UserQrDetail(BaseModel):
    id: str
    username: Optional[str] = None
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    email: Optional[str] = None


class UserListResponse(BaseModel):
    results: List[UserQrDetail]
