"""Application settings loaded from the environment and `.env`."""

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Strongly-typed application configuration.

    Values come from environment variables first, then a local `.env` file.
    Unknown keys are ignored so the same `.env` can serve multiple services.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    DATABASE_URL: str = "postgresql+asyncpg://postgres:postgres@localhost:5442/eagleye"

    # RFC 7518 section 3.2 requires an HMAC key at least as long as the hash
    # output, so 32 bytes for SHA256. PyJWT only warns below that; we refuse to
    # start instead, so a weak signing key cannot reach production unnoticed.
    # 32 characters is always at least 32 bytes once UTF-8 encoded.
    JWT_SECRET: str = Field(default="change-me-in-production-min-32-bytes", min_length=32)
    JWT_ISSUER: str = "eagleye"
    JWT_AUDIENCE: str = "eagleye-admin"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60

    DEFAULT_ADMIN_EMAIL: str = "admin@example.com"
    DEFAULT_ADMIN_PASSWORD: str = "change-me"

    CORS_ORIGINS: str = "http://localhost:5173,http://localhost:3000"

    # Applied to every request by the slowapi middleware. Any `limits`
    # expression works ("10/second", "100/minute"); an empty value turns the
    # global throttle off for deployments that rate-limit at the gateway.
    RATE_LIMIT_DEFAULT: str = "10/second"

    # --- Eagleye: configuration files and storage ---------------------------
    CATALOG_PATH: str = "config/catalog.example.yaml"
    SITES_PATH: str = "config/sites.example.yaml"
    FRAMES_DIR: str = "data/frames"
    PUBLIC_BASE_URL: str = "http://localhost:3000"
    RETENTION_DAYS: int = Field(default=14, ge=1)
    RETENTION_QUIET_HOURS: int = Field(default=24, ge=1)

    # --- Claude ---------------------------------------------------------------
    ANTHROPIC_API_KEY: str = ""
    ANTHROPIC_MODEL: str = "claude-haiku-5-5"
    # Thinking counts against max_tokens; 20 images at medium effort need room.
    ANALYSIS_MAX_TOKENS: int = 8000
    # Per request; the SDK retries twice, so a stalled call costs at most ~3x this.
    ANALYSIS_TIMEOUT_SECONDS: float = 90.0
    ANALYSIS_CONCURRENCY: int = Field(default=8, ge=1)
    MAX_CAMERAS_PER_CALL: int = Field(default=20, ge=1)
    DAILY_BUDGET_USD: float = 25.0
    KEEPALIVE_ENABLED: bool = True
    KEEPALIVE_AFTER_MINUTES: int = Field(default=55, ge=1, le=59)
    # Haiku 5.5 list prices (prompts up to 100K tokens), per million tokens.
    PRICE_INPUT_PER_MTOK: float = 0.10
    PRICE_OUTPUT_PER_MTOK: float = 0.50
    PRICE_CACHE_READ_MULT: float = 0.1
    PRICE_CACHE_WRITE_1H_MULT: float = 2.0

    # --- Rounds and capture ---------------------------------------------------
    ROUND_INTERVAL_SECONDS: int = Field(default=120, ge=10)
    CAPTURE_FFMPEG_BIN: str = "ffmpeg"
    CAPTURE_TIMEOUT_SECONDS: float = 20.0
    CAPTURE_CONCURRENCY: int = Field(default=16, ge=1)
    FRAME_MAX_SIDE: int = Field(default=640, ge=64)

    # --- Change filter --------------------------------------------------------
    CHANGE_GRID_COLS: int = 16
    CHANGE_GRID_ROWS: int = 12
    CHANGE_CELL_THRESHOLD: float = 12.0
    CHANGE_MIN_CELLS: int = 2
    MAX_UNSENT_MINUTES: int = 60
    AUTOMASK_WINDOW: int = 30
    AUTOMASK_MIN_SAMPLES: int = 10
    AUTOMASK_RATIO: float = 0.8

    # --- Alerts and metrics ---------------------------------------------------
    ALERT_WEBHOOK_URLS: str = ""
    ALERT_WEBHOOK_SECRET: str = ""
    ALERT_COOLDOWN_MINUTES: int = 10
    METRICS_PORT: int = 9100

    @property
    def cors_origins_list(self) -> list[str]:
        """Parse the comma-separated CORS origins into a list."""
        return [origin.strip() for origin in self.CORS_ORIGINS.split(",") if origin.strip()]

    @property
    def alert_webhook_urls_list(self) -> list[str]:
        """Parse the comma-separated alert webhook URLs into a list."""
        return [url.strip() for url in self.ALERT_WEBHOOK_URLS.split(",") if url.strip()]


@lru_cache
def get_settings() -> Settings:
    """Return a cached `Settings` instance."""
    return Settings()
