from pydantic import BaseModel, ConfigDict, Field, field_validator


class AuthRequest(BaseModel):
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=6, max_length=128)

    @field_validator("password")
    @classmethod
    def password_must_not_be_blank(cls, value: str) -> str:
        if value.isspace():
            raise ValueError("password must not be blank")
        return value


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
