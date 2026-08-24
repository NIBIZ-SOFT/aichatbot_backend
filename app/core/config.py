import os
from typing import List, Optional
from pydantic import AnyHttpUrl
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    PROJECT_NAME: str = "Enterprise AIaaS SaaS Platform"
    API_V1_STR: str = "/api/v1"
    SECRET_KEY: str = "super-secret-enterprise-encryption-key-change-in-prod-32bytes!"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24  # 1 day
    REFRESH_TOKEN_EXPIRE_MINUTES: int = 60 * 24 * 7  # 7 days
    
    # AES-256 GCM Key for tenant secret storage (Gemini keys, webhook secrets)
    AES_ENCRYPTION_KEY: str = "01234567890123456789012345678901"  # 32 chars

    # Database
    POSTGRES_SERVER: str = "localhost"
    POSTGRES_USER: str = "postgres"
    POSTGRES_PASSWORD: str = "postgres"
    POSTGRES_DB: str = "aiaas_db"
    POSTGRES_PORT: int = 5432
    DATABASE_URL: Optional[str] = None

    # Redis
    REDIS_HOST: str = "localhost"
    REDIS_PORT: int = 639
    REDIS_PASSWORD: Optional[str] = None
    REDIS_URL: Optional[str] = None

    # AI Provider Settings (OpenAI-compatible & Gemini)
    AI_BASE_URL: Optional[str] = "http://4bhgvnanm2jpfo73shwbhcsh.163.227.238.4.sslip.io/v1"
    AI_API_KEY: Optional[str] = "sk-gemini"
    AI_MODEL: str = "gemini-3.6-flash"

    # Google Gemini Default Fallback
    GEMINI_API_KEY: Optional[str] = None
    DEFAULT_GEMINI_MODEL: str = "gemini-3.6-flash"
    DEFAULT_EMBEDDING_MODEL: str = "text-embedding-004"

    # CORS
    BACKEND_CORS_ORIGINS: List[str] = ["*"]

    # Environment
    ENVIRONMENT: str = "development"
    DEBUG: bool = True
    FRONTEND_URL: str = "https://jobab.chat"

    model_config = {
        "env_file": ".env",
        "case_sensitive": True,
        "extra": "ignore"
    }

    def get_database_url(self) -> str:
        if self.DATABASE_URL:
            return self.DATABASE_URL
        return f"postgresql+asyncpg://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}@{self.POSTGRES_SERVER}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"

    def get_redis_url(self) -> str:
        if self.REDIS_URL:
            return self.REDIS_URL
        auth = f":{self.REDIS_PASSWORD}@" if self.REDIS_PASSWORD else ""
        return f"redis://{auth}{self.REDIS_HOST}:{self.REDIS_PORT}/0"

settings = Settings()
