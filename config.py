import os
from dataclasses import dataclass
from dotenv import load_dotenv

load_dotenv()

def _ints(value: str) -> set[int]:
    return {int(x.strip()) for x in value.split(",") if x.strip()}

@dataclass(frozen=True)
class Settings:
    bot_token: str
    admin_ids: set[int]
    api_id: int
    api_hash: str
    telegram_session: str
    database_url: str
    ai_api_key: str
    ai_api_url: str
    ai_model: str
    ai_provider: str
    timezone: str
    test_mode: bool
    test_channel_id: int | None
    default_retry_count: int
    default_retry_delay: int
    max_context_messages: int
    log_level: str

def load_settings() -> Settings:
    token = os.getenv("BOT_TOKEN", "").strip()
    if not token:
        raise RuntimeError("BOT_TOKEN is required")

    api_id_raw = os.getenv("API_ID", "0").strip()
    api_id = int(api_id_raw or 0)

    test_id = os.getenv("TEST_CHANNEL_ID", "").strip()
    return Settings(
        bot_token=token,
        admin_ids=_ints(os.getenv("ADMIN_IDS", "")),
        api_id=api_id,
        api_hash=os.getenv("API_HASH", "").strip(),
        telegram_session=os.getenv("TELEGRAM_SESSION", "source_monitor").strip(),
        database_url=os.getenv("DATABASE_URL", "sqlite+aiosqlite:///./data/bot.db"),
        ai_api_key=os.getenv("AI_API_KEY", "").strip(),
        ai_api_url=os.getenv("AI_API_URL", "https://api.openai.com/v1/chat/completions").strip(),
        ai_model=os.getenv("AI_MODEL", "gemini-3.6-flash").strip(),
        ai_provider=os.getenv("AI_PROVIDER", "gemini").strip().lower(),
        timezone=os.getenv("TIMEZONE", "Asia/Dhaka").strip(),
        test_mode=os.getenv("TEST_MODE", "false").lower() == "true",
        test_channel_id=int(test_id) if test_id else None,
        default_retry_count=int(os.getenv("DEFAULT_RETRY_COUNT", "3")),
        default_retry_delay=int(os.getenv("DEFAULT_RETRY_DELAY", "10")),
        max_context_messages=int(os.getenv("MAX_CONTEXT_MESSAGES", "8")),
        log_level=os.getenv("LOG_LEVEL", "INFO").upper(),
    )
