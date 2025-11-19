# app/config.py
from pydantic import Field
from pydantic_settings import BaseSettings
import pathlib
from dotenv import load_dotenv

# Charger explicitement le fichier .env
env_path = pathlib.Path(__file__).parent / ".env"
load_dotenv(env_path)

class Settings(BaseSettings):
    app_name: str = Field("Prospection System - Backend", env="APP_NAME")
    debug: bool = Field(False, env="DEBUG")
    host: str = Field("127.0.0.1", env="HOST")
    port: int = Field(8000, env="PORT")
    jwt_secret_key: str = Field(env="JWT_SECRET_KEY")
    jwt_algorithm: str = Field("HS256", env="JWT_ALGORITHM")
    jwt_expiration_hours: int = Field(24, env="JWT_EXPIRATION_HOURS")
    
    # Token d'administration pour les endpoints sensibles
    admin_token: str = Field(env="ADMIN_TOKEN")
    production: bool = Field(False, env="PRODUCTION")
    db_prod_url: str = Field(env="DB_PROD_URL")

    # Database
    db_host: str = Field("", env="DB_HOST")
    db_port: int = Field(5432, env="DB_PORT")
    db_name: str = Field("", env="DB_NAME")
    db_user: str = Field("", env="DB_USER")
    db_password: str = Field("", env="DB_PASSWORD")
    
    # Frontend URL pour les liens dans les emails
    frontend_url: str = Field("", env="FRONTEND_URL")

    # Unipile
    UNIPILE_DSN: str = Field("", env="UNIPILE_DSN")
    UNIPILE_API_KEY: str = Field("", env="UNIPILE_API_KEY")
    UNIPILE_ACCOUNT_ID: str = Field("", env="UNIPILE_ACCOUNT_ID")

    # OpenAI / LLM
    OPENAI_API_KEY: str = Field("", env="OPENAI_API_KEY")
    OPENAI_MODEL: str = Field("gpt-4", env="OPENAI_MODEL")

    # Anthropic
    ANTHROPIC_API_KEY: str = Field("", env="ANTHROPIC_API_KEY")
    ANTHROPIC_MODEL: str = Field("claude-3-opus-20240229", env="ANTHROPIC_MODEL")

    # Queue & Worker Configuration
    CUTOFF_DAYS: int = Field(30, env="CUTOFF_DAYS")
    MAX_CONNECTIONS_PER_DAY: int = Field(50, env="MAX_CONNECTIONS_PER_DAY")
    REQUIRE_AVATAR: bool = Field(True, env="REQUIRE_AVATAR")
    MAX_BATCH_SIZE: int = Field(10, env="MAX_BATCH_SIZE")

    # Worker intervals (seconds)
    SCAN_INTERVAL: int = Field(7200, env="SCAN_INTERVAL")  # 2h
    QUEUE_INTERVAL: int = Field(1800, env="QUEUE_INTERVAL")  # 30 min
    MESSAGE_INTERVAL: int = Field(1200, env="MESSAGE_INTERVAL")  # 20 min

    # Daily action limits (per action type)
    DAILY_LIMIT_FIRST_CONTACT: int = Field(50, env="DAILY_LIMIT_FIRST_CONTACT")
    DAILY_LIMIT_FOLLOWUP_A1: int = Field(30, env="DAILY_LIMIT_FOLLOWUP_A1")
    DAILY_LIMIT_FOLLOWUP_A2: int = Field(30, env="DAILY_LIMIT_FOLLOWUP_A2")
    DAILY_LIMIT_FOLLOWUP_A3: int = Field(30, env="DAILY_LIMIT_FOLLOWUP_A3")
    DAILY_LIMIT_FOLLOWUP_B: int = Field(20, env="DAILY_LIMIT_FOLLOWUP_B")
    DAILY_LIMIT_FOLLOWUP_C: int = Field(10, env="DAILY_LIMIT_FOLLOWUP_C")

    def get_daily_limit(self, action_type: str) -> int:
        """
        Get daily limit for an action type.

        Centralized mapping: action_type -> quota.
        """
        mapping = {
            'send_first_contact': self.DAILY_LIMIT_FIRST_CONTACT,
            'send_followup_a_1': self.DAILY_LIMIT_FOLLOWUP_A1,
            'send_followup_a_2': self.DAILY_LIMIT_FOLLOWUP_A2,
            'send_followup_a_3': self.DAILY_LIMIT_FOLLOWUP_A3,
            'send_followup_b': self.DAILY_LIMIT_FOLLOWUP_B,
            'send_followup_c': self.DAILY_LIMIT_FOLLOWUP_C,
        }
        return mapping.get(action_type, 50)

    class Config:
        env_file = pathlib.Path(__file__).parent / ".env"
        env_file_encoding = "utf-8"

settings = Settings()