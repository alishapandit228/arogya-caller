from urllib.parse import urlparse
from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    admin_api_token: SecretStr
    database_url: str = "sqlite:///./arogya.db"
    ollama_url: str = "http://127.0.0.1:11434"
    ollama_model: str = "qwen2.5:1.5b"
    trusted_origins: list[str] = Field(default_factory=list)

    @field_validator("admin_api_token")
    @classmethod
    def token_length(cls, value):
        if len(value.get_secret_value()) < 32:
            raise ValueError("Generate an admin token with at least 32 characters")
        return value

    @field_validator("ollama_url")
    @classmethod
    def local_model(cls, value):
        url = urlparse(value)
        if url.scheme != "http" or url.hostname not in {"127.0.0.1", "localhost", "::1"}:
            raise ValueError("Ollama must use local HTTP")
        if url.username or url.password or url.query or url.fragment or url.path not in {"", "/"}:
            raise ValueError("Invalid local Ollama URL")
        return value.rstrip("/")

    @field_validator("database_url")
    @classmethod
    def sqlite_only(cls, value):
        if not value.startswith("sqlite:///"):
            raise ValueError("Only SQLite is supported")
        return value

    @field_validator("trusted_origins")
    @classmethod
    def explicit_origins(cls, values):
        for value in values:
            url = urlparse(value)
            if "*" in value or url.scheme not in {"http", "https"} or not url.netloc or url.path or url.query or url.fragment or url.username:
                raise ValueError("Use explicit HTTP origins without paths or wildcards")
        return values
