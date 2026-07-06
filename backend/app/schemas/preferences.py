from pydantic import BaseModel, ConfigDict


class UserPreferencesResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    memory_enabled: bool


class UserPreferencesUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    memory_enabled: bool
