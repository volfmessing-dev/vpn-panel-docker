from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    database_url: str = "postgresql+psycopg://bypass_manager:change-me@postgres:5432/bypass_manager"
    backend_cors_origins: str = "http://localhost:3000,http://127.0.0.1:3000"
    ssh_key_path: str = "/run/secrets/ssh/id_ed25519"
    bypass_cidrs: str = ""
    bypass_domains_path: str = "/data/bypass-domains.txt"

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    @property
    def cors_origins(self) -> list[str]:
        return [origin.strip() for origin in self.backend_cors_origins.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
