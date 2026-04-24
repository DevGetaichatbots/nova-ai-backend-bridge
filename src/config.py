import os
from pydantic_settings import BaseSettings
from typing import Optional


class Settings(BaseSettings):
    SUPABASE_URL: str = ""
    SUPABASE_SERVICE_KEY: str = ""
    SUPABASE_DB_HOST: str = ""
    SUPABASE_DB_USER: str = "postgres"
    SUPABASE_DB_PASSWORD: str = ""
    SUPABASE_DB_NAME: str = "postgres"
    SUPABASE_DB_PORT: int = 5432
    DATABASE_URL: str = ""
    SUPABASE_POOLER_URL: str = ""
    
    AZURE_OPENAI_API_KEY: str = ""
    AZURE_OPENAI_ENDPOINT: str = ""
    AZURE_OPENAI_EMBEDDING_DEPLOYMENT: str = "text-embedding-3-small"
    AZURE_OPENAI_CHAT_DEPLOYMENT: str = "gpt-4.1"
    AZURE_OPENAI_PREDICTIVE_DEPLOYMENT: str = "gpt-4.1"
    AZURE_OPENAI_API_VERSION: str = "2025-04-01-preview"
    
    EMBEDDING_DIMENSION: int = 1536

    class Config:
        env_file = ".env"
        extra = "ignore"


settings = Settings()


def get_database_url() -> str:
    if settings.SUPABASE_POOLER_URL:
        return settings.SUPABASE_POOLER_URL
    if settings.DATABASE_URL:
        return settings.DATABASE_URL
    return f"postgresql://{settings.SUPABASE_DB_USER}:{settings.SUPABASE_DB_PASSWORD}@{settings.SUPABASE_DB_HOST}:{settings.SUPABASE_DB_PORT}/{settings.SUPABASE_DB_NAME}"
