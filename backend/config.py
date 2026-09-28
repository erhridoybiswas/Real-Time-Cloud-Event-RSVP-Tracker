"""Application configuration loaded from environment variables."""
import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")


class Config:
    """Runtime configuration. Values are read from env with safe dev defaults."""

    # --- security ---
    SECRET_KEY: str = os.getenv("SECRET_KEY", "dev-secret-change-me")
    JWT_SECRET: str = os.getenv("JWT_SECRET", "dev-jwt-secret-change-me")
    JWT_ALGORITHM: str = "HS256"
    JWT_EXP_MINUTES: int = int(os.getenv("JWT_EXP_MINUTES", "120"))

    # --- database ---
    DATABASE_PATH: str = os.getenv("DATABASE_PATH", str(BASE_DIR / "data" / "app.db"))

    # --- http ---
    CORS_ORIGINS: str = os.getenv("CORS_ORIGINS", "*")
    RATE_LIMIT_PER_MINUTE: int = int(os.getenv("RATE_LIMIT_PER_MINUTE", "240"))

    # --- bootstrap ---
    BOOTSTRAP_KEY: str = os.getenv("BOOTSTRAP_KEY", "bootstrap-dev-key")

    # --- frontend ---
    FRONTEND_DIR: str = str(BASE_DIR / "frontend")