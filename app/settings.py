from pathlib import Path
import re
from typing import Annotated, Dict, List
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import AfterValidator, BaseModel, Field, field_validator, validator


def is_valid_name(value: str):
    if re.fullmatch(r"^[a-zA-Z0-9-]+", value) is None:
        raise ValueError("Name should only contain alphanumeric characters and dashes (-)")
    return value


class StepSettings(BaseModel):
    name: Annotated[str, AfterValidator(is_valid_name)]
    template: str = Field(default="step")
    args: dict[str, str] = {}


class UpgradePathSettings(BaseModel):
    steps: List[StepSettings]
    manifest_dir: Path
    job_env: Dict[str, str] = {}
    job_secret_env: Dict[str, str] = {}

    @field_validator("steps", mode="before")
    def validate_steps(cls, steps: dict) -> List[StepSettings]:
        keys = list(steps.keys())
        keys.sort()
        return [StepSettings(**steps[key]) for key in keys]


class S3Settings(BaseModel):
    bucket: str
    access_key: str
    secret_key: str
    endpoint: str


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="ODOO_UPGRADER_", env_nested_delimiter="__")

    concurrent_jobs_limit: int = Field(default=1)
    job_namespace: str
    upgrade_paths: Dict[str, UpgradePathSettings]
    job_env: Dict[str, str] = {}
    job_secret_env: Dict[str, str] = {}
    job_domain: str

    s3: S3Settings

    def get_upgrade_path(self, key) -> UpgradePathSettings:
        if key not in self.upgrade_paths:
            raise NotImplementedError("Upgrade path `%s` not found" % key)
        return self.upgrade_paths[key]
    
    def upgrade_path_exists(self, key, raise_exception=True):
        exists = key in self.upgrade_paths
        if raise_exception and not exists:
            raise NotImplementedError("Upgrade path `%s` not found" % key)
        return exists

settings = Settings()
