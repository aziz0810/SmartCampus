from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import URL

ENV_FILE = Path(__file__).resolve().parents[2] / ".env"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=ENV_FILE, extra="ignore")

    db_host: str = "localhost"
    db_port: int = 5432
    app_db_name: str
    app_db_user: str
    app_db_password: str
    frontend_origin: str = "http://localhost:3000"
    visitor_session_ttl_hours: int = Field(default=24, gt=0, le=168)
    visitor_session_max_messages: int = Field(default=100, gt=0)
    visitor_memory_max_messages: int = Field(default=20, gt=0, le=100)
    visitor_message_max_length: int = Field(default=4000, gt=0, le=20000)

    # JWT
    jwt_secret_key: str = "CHANGE_ME_IN_DOT_ENV"
    jwt_access_token_ttl_minutes: int = Field(default=60 * 8, gt=0)  # 8 hours

    @property
    def database_url(self) -> URL:
        return URL.create(
            drivername="postgresql+psycopg",
            username=self.app_db_user,
            password=self.app_db_password,
            host=self.db_host,
            port=self.db_port,
            database=self.app_db_name,
        )


settings = Settings()
