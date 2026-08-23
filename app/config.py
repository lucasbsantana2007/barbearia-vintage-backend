from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    database_url: str = "sqlite:///./barbearia.db"
    jwt_secret: str = "dev-secret-change-me"
    access_token_expire_minutes: int = 480
    n8n_webhook_url: str | None = None
    cors_origins: str = "http://localhost:5173"
    admin_email: str = "admin@barbeariavintage.com"
    admin_password: str = "admin123"

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    @property
    def cors_list(self) -> list[str]:
        return [x.strip() for x in self.cors_origins.split(",") if x.strip()]


settings = Settings()
