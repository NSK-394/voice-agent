import os
from dataclasses import dataclass
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

@dataclass
class Settings:
    VAPI_API_KEY: str
    VAPI_PHONE_NUMBER_ID: str
    VAPI_ASSISTANT_ID: str
    VAPI_WEBHOOK_SECRET: str  # empty string = signature check skipped (dev mode)
    OPENAI_API_KEY: str
    CONTEXT_DEV_API_KEY: str
    GOOGLE_SHEETS_ID: str
    GOOGLE_SERVICE_ACCOUNT_JSON: str
    HOST: str
    PORT: int
    DB_PATH: Path

_settings: Settings | None = None

def get_settings() -> Settings:
    global _settings
    if _settings is not None:
        return _settings

    required = [
        "VAPI_API_KEY",
        "VAPI_PHONE_NUMBER_ID",
        "VAPI_ASSISTANT_ID",
        "OPENAI_API_KEY",
        "CONTEXT_DEV_API_KEY",
        "GOOGLE_SHEETS_ID",
        "GOOGLE_SERVICE_ACCOUNT_JSON",
    ]
    missing = [k for k in required if not os.environ.get(k)]
    if missing:
        raise RuntimeError(f"Missing required env vars: {', '.join(missing)}")

    _settings = Settings(
        VAPI_API_KEY=os.environ["VAPI_API_KEY"],
        VAPI_PHONE_NUMBER_ID=os.environ["VAPI_PHONE_NUMBER_ID"],
        VAPI_ASSISTANT_ID=os.environ["VAPI_ASSISTANT_ID"],
        VAPI_WEBHOOK_SECRET=os.environ.get("VAPI_WEBHOOK_SECRET", ""),
        OPENAI_API_KEY=os.environ["OPENAI_API_KEY"],
        CONTEXT_DEV_API_KEY=os.environ["CONTEXT_DEV_API_KEY"],
        GOOGLE_SHEETS_ID=os.environ["GOOGLE_SHEETS_ID"],
        GOOGLE_SERVICE_ACCOUNT_JSON=os.environ["GOOGLE_SERVICE_ACCOUNT_JSON"],
        HOST=os.environ.get("HOST", "0.0.0.0"),
        PORT=int(os.environ.get("PORT", "8000")),
        DB_PATH=Path(__file__).resolve().parent / "data" / "voice.db",
    )
    return _settings
