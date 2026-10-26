from functools import lru_cache
from typing import Literal

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        case_sensitive=False,
        extra="ignore",
        env_file=(".env", "../.env"),
        env_file_encoding="utf-8",
    )

    app_database_url: SecretStr | None = Field(default=None, validation_alias="APP_DATABASE_URL")
    erp_database_url: SecretStr | None = Field(default=None, validation_alias="ERP_DATABASE_URL")
    app_session_secret: SecretStr | None = Field(
        default=None, validation_alias="APP_SESSION_SECRET"
    )
    app_cookie_secure: bool = Field(default=True, validation_alias="APP_COOKIE_SECURE")
    app_cookie_samesite: Literal["lax", "strict", "none"] = Field(
        default="none", validation_alias="APP_COOKIE_SAMESITE"
    )
    app_session_hours: int = Field(default=12, ge=1, le=72, validation_alias="APP_SESSION_HOURS")

    @staticmethod
    def database_url(value: SecretStr | None) -> str | None:
        if value is None:
            return None
        url = value.get_secret_value()
        if url.startswith("postgres://"):
            return "postgresql+psycopg://" + url.removeprefix("postgres://")
        if url.startswith("postgresql://"):
            return "postgresql+psycopg://" + url.removeprefix("postgresql://")
        return url

    @property
    def app_sqlalchemy_url(self) -> str | None:
        return self.database_url(self.app_database_url)

    @property
    def erp_sqlalchemy_url(self) -> str | None:
        return self.database_url(self.erp_database_url)


@lru_cache
def get_settings() -> Settings:
    return Settings()
