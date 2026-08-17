import asyncio
import logging
from app.config import load_settings
from app.logging_setup import setup_logging
from app.db import Database
from app.ai_engine import AIEngine
from app.admin_bot import AdminBot
from app.group_bot import GroupBot
from app.channel_engine import ChannelEngine

async def main():
    settings = load_settings()
    setup_logging(settings.log_level)
    log = logging.getLogger(__name__)

    db = Database(settings.database_url)
    await db.init()

    ai_engine = AIEngine(settings, db)
    admin = AdminBot(settings, db, ai_engine)
    GroupBot(admin.dp, db, ai_engine)

    channel_engine = ChannelEngine(settings, db, admin.bot)

    tasks = [asyncio.create_task(admin.run())]
    if settings.api_id and settings.api_hash:
        tasks.append(asyncio.create_task(channel_engine.start()))

    log.info("Application started")
    await asyncio.gather(*tasks)

if __name__ == "__main__":
    asyncio.run(main())
