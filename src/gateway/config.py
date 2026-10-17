from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="GATEWAY_", env_file=".env", extra="ignore")

    # OpenAI-compatible upstream. Ollama serves one at http://localhost:11434/v1.
    upstream_base_url: str = "http://localhost:11434/v1"
    upstream_api_key: str = ""
    upstream_timeout_s: float = 120.0

    # Comma-separated client keys. Milestone 2 moves these into Postgres.
    api_keys: str = "dev-key"

    redis_url: str = "redis://localhost:6379/0"
    database_url: str = "postgresql://gateway:gateway@localhost:5432/gateway"

    def key_set(self) -> set[str]:
        return {k.strip() for k in self.api_keys.split(",") if k.strip()}
