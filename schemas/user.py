from typing import List, Optional

from fastapi import Query
from pydantic import BaseModel


class UserQrDetail(BaseModel):
    id: str
    username: Optional[str] = None
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    email: Optional[str] = None


class UserQrQuery(BaseModel):
    page: Optional[int] = Query(1, description="Page Number")
    page_size: Optional[int] = Query(10, description="Page Size")
    search: Optional[str] = Query(
        None, description="Search users by name, username, or email"
    )
    all: Optional[bool] = Query(None, description="Return all users if true")


class UserListResponse(BaseModel):
    page: int
    page_size: int
    count: int
    page_count: int
    results: List[UserQrDetail]
