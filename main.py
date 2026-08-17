"""
Entry point. Boots the database, the admin Telegram bot, and the source
channel monitor together in one asyncio event loop.

On restart: sources/settings are reloaded from the database automatically
(database.py is the single source of truth), and duplicate-post protection
prevents old posts from being reposted again.
"""
import asyncio
import logging
import signal

import config
import database as db
import bot as botmodule
from monitor import ChannelMonitor

logger = logging.getLogger("main")


async def run():
    config.validate_config()
    db.init_db()
    db.add_log("INFO", "Bot starting up.")

    application = botmodule.build_application()
    monitor = ChannelMonitor(application.bot)
    botmodule.monitor = monitor  # make monitor reachable from command handlers

    await application.initialize()
    await application.start()
    await application.updater.start_polling()

    try:
        await monitor.start()
    except Exception as e:
        logger.error(f"Monitor failed to start (check API_ID/API_HASH/session login): {e}")
        db.add_log("ERROR", f"Monitor failed to start: {e}")

    logger.info("Bot is fully running. Press Ctrl+C to stop.")

    stop_event = asyncio.Event()

    def _stop(*_):
        stop_event.set()

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, _stop)
        except NotImplementedError:
            pass  # Windows

    await stop_event.wait()

    logger.info("Shutting down...")
    await monitor.stop()
    await application.updater.stop()
    await application.stop()
    await application.shutdown()


if __name__ == "__main__":
    asyncio.run(run())
