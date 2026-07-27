from pydantic import BaseModel, ConfigDict, model_validator


class UserPreferencesResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    memory_enabled: bool
    external_model_consent: bool
    privacy_version: str


class UserPreferencesUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    memory_enabled: bool | None = None
    external_model_consent: bool | None = None

    @model_validator(mode="after")
    def require_at_least_one_change(self) -> "UserPreferencesUpdate":
        if self.memory_enabled is None and self.external_model_consent is None:
            raise ValueError("at least one preference must be provided")
        return self
