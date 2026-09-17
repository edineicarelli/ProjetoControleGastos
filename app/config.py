import os
from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Optional

class Settings(BaseSettings):
    TELEGRAM_BOT_TOKEN: str = "SEU_TELEGRAM_BOT_TOKEN_AQUI"
    GEMINI_API_KEY: str = "SUA_GEMINI_API_KEY_AQUI"
    DATABASE_URL: str = "sqlite:///./finance_control.db"
    HOST: str = "0.0.0.0"
    PORT: int = 8085
    BASE_URL: str = "http://localhost:8085"
    DEFAULT_CURRENCY: str = "R$"
    DEFAULT_TIMEZONE: str = "America/Sao_Paulo"
    
    # Uploads directory
    UPLOAD_DIR: str = "./uploads"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )

settings = Settings()

# Ensure uploads dir exists
os.makedirs(settings.UPLOAD_DIR, exist_ok=True)
os.makedirs(os.path.join(settings.UPLOAD_DIR, "audio"), exist_ok=True)
os.makedirs(os.path.join(settings.UPLOAD_DIR, "receipts"), exist_ok=True)
os.makedirs(os.path.join(settings.UPLOAD_DIR, "exports"), exist_ok=True)

# Ensure sqlite data directory exists if configured
if settings.DATABASE_URL.startswith("sqlite:///"):
    db_path = settings.DATABASE_URL.replace("sqlite:///", "")
    db_dir = os.path.dirname(db_path)
    if db_dir:
        os.makedirs(db_dir, exist_ok=True)

