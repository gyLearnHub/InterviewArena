from pydantic import BaseModel, ConfigDict, Field


class AuthRequest(BaseModel):
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=6, max_length=128)


class UserPublic(BaseModel):
    id: int
    username: str
    display_name: str
    avatar_url: str | None = None

    model_config = ConfigDict(from_attributes=True)


class LoginResponse(BaseModel):
    id: int
    username: str
    display_name: str
    avatar_url: str | None = None


class UserProfileUpdate(BaseModel):
    display_name: str = Field(min_length=1, max_length=64)
