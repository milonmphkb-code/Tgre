"""
Central configuration loader.
Reads everything from environment variables (.env file).
"""
import os
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN", "")
API_ID = int(os.getenv("API_ID", "0"))
API_HASH = os.getenv("API_HASH", "")
DATABASE_PATH = os.getenv("DATABASE_PATH", "bot_database.db")
SESSION_NAME = os.getenv("SESSION_NAME", "repost_userbot")

ADMIN_IDS = set(
    int(x.strip()) for x in os.getenv("ADMIN_IDS", "").split(",") if x.strip()
)

# Default delay in seconds if a source has no custom delay set
DEFAULT_DELAY_SECONDS = 0

# Media types the bot ignores by default (text-only bot)
IGNORED_MEDIA = {"photo", "video", "audio", "voice", "document", "sticker", "gif", "animation"}


def is_admin(user_id: int) -> bool:
    return user_id in ADMIN_IDS


def validate_config():
    missing = []
    if not BOT_TOKEN:
        missing.append("BOT_TOKEN")
    if not API_ID:
        missing.append("API_ID")
    if not API_HASH:
        missing.append("API_HASH")
    if not ADMIN_IDS:
        missing.append("ADMIN_IDS")
    if missing:
        raise RuntimeError(
            f"Missing required .env settings: {', '.join(missing)}. "
            f"Copy .env.example to .env and fill it in."
        )
