# app/config/settings.py
import json
from typing import List, Union

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # MongoDB
    MONGODB_URI: str = "mongodb://localhost:27017"
    MONGODB_DB: str  = "oneofone"

    # API Keys
    SERPER_API_KEY: str = ""   # serper.dev — 2,500 free searches/month
    ODDS_API_KEY:   str = ""

    # App
    # List fields are typed as Union[List[str], str] (NOT plain List[str]) on
    # purpose: pydantic-settings 2.2+ json.loads()s every complex field from the
    # env BEFORE field validators run, so a plain value like ALLOWED_HOSTS=*
    # (or a comma-separated list) crashes boot with SettingsError. A Union
    # annotation makes the env source treat JSON-parse failure as non-fatal
    # (allow_parse_failure=True), so the raw string reaches parse_csv_lists
    # below, which handles both CSV and JSON-array forms.
    ALLOWED_ORIGINS: Union[List[str], str] = ["http://localhost:5173", "http://localhost:3000"]
    # Defaults to accepting any Host header so containerized/public deployments do
    # not fail every request with Starlette TrustedHostMiddleware 400s when the
    # platform injects its own domain/IP. Set this env var to a comma-separated
    # allowlist (for example: "api.example.com,localhost,127.0.0.1") to enforce
    # strict host validation in production.
    ALLOWED_HOSTS: Union[List[str], str] = ["*"]
    SECRET_KEY: str = "change-this-in-production"
    DEBUG: bool = False

    # Scheduler
    DAILY_PREDICTION_HOUR:   int = 6
    DAILY_PREDICTION_MINUTE: int = 0
    RESULT_RESOLUTION_HOUR:   int = 23
    RESULT_RESOLUTION_MINUTE: int = 0
    SCHEDULER_ADMIN_KEY: str = ""
    RENDER_APP_URL: str = ""

    # ML
    # Must match persisted artifacts in apps/api/models/ (currently v5.0.0).
    MODEL_VERSION:        str = "5.0.0"
    MIN_TRAINING_SAMPLES: int = 30
    CALIBRATION_METHOD:   str = "isotonic"
    # Best-effort real expected-goals lookup (Understat, free) at prediction
    # time; falls back to the heuristic when the source doesn't cover a fixture.
    ENABLE_XG_SCRAPING:   bool = True
    # Supported sports for the platform (single-source-of-truth). Union type for
    # the same reason as ALLOWED_HOSTS: a plain non-JSON env value (e.g.
    # SUPPORTED_SPORTS=soccer) would crash pydantic-settings' JSON decode.
    SUPPORTED_SPORTS: Union[list, str] = ["soccer"]

    # In-process cache caps
    SEARCH_CACHE_MAX_ENTRIES: int = 750

    # Platform report thresholds
    REPORT_ACCURACY_GOOD: float = 0.58
    REPORT_ACCURACY_NEEDS: float = 0.55
    REPORT_BRIER_GOOD: float = 0.42
    REPORT_BRIER_NEEDS: float = 0.50
    REPORT_RESOLUTION_GOOD: float = 0.50
    REPORT_LOW_CONFIDENCE: float = 0.55

    # Search budget (Serper.dev: 2,500/month free; cap at 2,400 for safety buffer)
    SERPAPI_MONTHLY_BUDGET: int = 2_400

    # Cache TTLs in seconds
    CACHE_TTL_SHORT:  int = 3_600
    CACHE_TTL_MEDIUM: int = 21_600
    CACHE_TTL_LONG:   int = 86_400

    # Rate limiting
    REQUESTS_PER_MINUTE:    int   = 30
    SCRAPING_DELAY_SECONDS: float = 1.5

    @field_validator("ALLOWED_ORIGINS", "ALLOWED_HOSTS", "SUPPORTED_SPORTS", mode="before")
    @classmethod
    def parse_csv_lists(cls, value):
        if isinstance(value, str):
            stripped = value.strip()
            # JSON array form, e.g. ALLOWED_HOSTS=["a.com","b.com"] or
            # SUPPORTED_SPORTS=["soccer"]
            if stripped.startswith("["):
                try:
                    parsed = json.loads(stripped)
                    if isinstance(parsed, list):
                        return [str(item).strip() for item in parsed]
                except (ValueError, TypeError):
                    pass  # malformed JSON array -> fall back to CSV split below
            # Comma-separated form, e.g. ALLOWED_HOSTS=*,a.com,b.com or
            # SUPPORTED_SPORTS=soccer
            return [item.strip() for item in value.split(",") if item.strip()]
        return value

    # extra="ignore" (not the pydantic default "forbid"): env vars that were
    # removed from this model — e.g. RAPID_API_KEY (deleted in the Sprint 4.4
    # cleanup) — may still be set in local shells, CI, or the Render env panel.
    # Rejecting unknown vars would crash the API at boot, so ignore them.
    model_config = SettingsConfigDict(
        env_file=".env",
        case_sensitive=True,
        extra="ignore",
    )


settings = Settings()
