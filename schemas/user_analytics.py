from typing import List

from pydantic import BaseModel, RootModel


class LocationRef(BaseModel):
    id: int
    name: str


class UserAnalyticsByCityItem(BaseModel):
    city: LocationRef
    count: int


class UserAnalyticsByStateItem(BaseModel):
    state: LocationRef
    count: int


class UserAnalyticsByCountryItem(BaseModel):
    country: LocationRef
    count: int


class UserAnalyticsByCityResponse(RootModel[List[UserAnalyticsByCityItem]]):
    pass


class UserAnalyticsByStateResponse(RootModel[List[UserAnalyticsByStateItem]]):
    pass


class UserAnalyticsByCountryResponse(RootModel[List[UserAnalyticsByCountryItem]]):
    pass
