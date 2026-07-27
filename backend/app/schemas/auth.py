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


class RegisterRequest(AuthRequest):
    model_config = ConfigDict(extra="forbid")

    external_model_consent: bool = False


class UserPublic(BaseModel):
    id: int
    username: str
    display_name: str
    avatar_url: str | None = None
    external_model_consent: bool = False

    model_config = ConfigDict(from_attributes=True)


class LoginResponse(BaseModel):
    id: int
    username: str
    display_name: str
    avatar_url: str | None = None
    external_model_consent: bool = False


class UserProfileUpdate(BaseModel):
    display_name: str = Field(min_length=1, max_length=64)


class AccountDeleteRequest(BaseModel):
    password: str = Field(min_length=6, max_length=128)
    confirmation: str = Field(pattern="^DELETE$")
