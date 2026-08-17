import asyncio
import logging
from datetime import datetime, timedelta, timezone
from telethon import TelegramClient, events
from sqlalchemy import select

from app.db import SourceChannel, Mapping, FilterSetting
from app.services import (
    process_text, is_duplicate, mark_processed, log_event, history,
    render_template, in_schedule
)

log = logging.getLogger(__name__)

class ChannelEngine:
    def __init__(self, settings, db, bot):
        self.settings = settings
        self.db = db
        self.bot = bot
        self.client = None

    async def start(self):
        if not self.settings.api_id or not self.settings.api_hash:
            log.warning("API_ID/API_HASH missing; source monitor disabled.")
            return

        self.client = TelegramClient(
            self.settings.telegram_session,
            self.settings.api_id,
            self.settings.api_hash
        )
        await self.client.start(bot_token=self.settings.bot_token)

        @self.client.on(events.NewMessage)
        async def handler(event):
            await self.handle_event(event)

        log.info("Telethon source monitor started")
        await self.client.run_until_disconnected()

    async def handle_event(self, event):
        message = event.message
        if not message or not message.raw_text:
            return

        source_chat_id = event.chat_id
        async with self.db.session() as session:
            source = (await session.execute(
                select(SourceChannel).where(SourceChannel.chat_id == source_chat_id)
            )).scalar_one_or_none()
            if not source or not source.enabled or source.paused:
                return

            text, reason = await process_text(session, source.id, message.raw_text)
            if not text:
                await log_event(session, "POST_SKIPPED", f"{source_chat_id}:{message.id} {reason}")
                mappings = (await session.execute(select(Mapping).where(Mapping.source_id == source.id))).scalars().all()
                for m in mappings:
                    destination = m.destination_chat_id
                    if destination:
                        await history(session, source_chat_id, message.id, destination, "skipped", reason)
                await session.commit()
                return

            if await is_duplicate(session, source_chat_id, message.id, text):
                await log_event(session, "DUPLICATE_DETECTED", f"{source_chat_id}:{message.id}")
                await session.commit()
                return

            mappings = (await session.execute(
                select(Mapping).where(Mapping.source_id == source.id, Mapping.enabled == True, Mapping.paused == False)
            )).scalars().all()
            config = (await session.execute(select(__import__("app.db", fromlist=["BotConfig"]).BotConfig).where(__import__("app.db", fromlist=["BotConfig"]).BotConfig.id == 1))).scalar_one()
            mappings = list(mappings)

            if not mappings:
                await log_event(session, "NO_MAPPING", f"source={source_chat_id}")
                await session.commit()
                return

            await mark_processed(session, source_chat_id, message.id, text)

            for mapping in mappings:
                destination = mapping.destination_chat_id or config.my_channel_id
                if not destination:
                    await log_event(session, "DESTINATION_MISSING", f"mapping={mapping.id}", "ERROR")
                    continue
                final_text = render_template(mapping.template, text)
                if not in_schedule(mapping, self.settings.timezone):
                    from app.db import QueueItem
                    session.add(QueueItem(
                        source_chat_id=source_chat_id,
                        source_message_id=message.id,
                        destination_chat_id=destination,
                        text=final_text,
                        not_before=datetime.now(timezone.utc) + timedelta(hours=1),
                    ))
                    await history(session, source_chat_id, message.id, destination, "queued", "outside_schedule")
                    continue
                if mapping.delay_seconds:
                    await asyncio.sleep(mapping.delay_seconds)
                await self.publish_with_retry(session, source_chat_id, message.id, destination, final_text, mapping)
            await session.commit()

    async def publish_with_retry(self, session, source_chat_id, source_message_id, destination, text, mapping):
        attempts = max(1, mapping.retry_count)
        last_error = None
        for attempt in range(attempts):
            try:
                target = self.settings.test_channel_id if self.settings.test_mode and self.settings.test_channel_id else destination
                sent = await self.bot.send_message(target, text)
                await history(session, source_chat_id, source_message_id, destination, "published", destination_message_id=sent.message_id)
                await log_event(session, "POST_PUBLISHED", f"{source_chat_id}:{source_message_id}->{destination}")
                return
            except Exception as exc:
                last_error = str(exc)
                await asyncio.sleep(mapping.retry_delay)
        await history(session, source_chat_id, source_message_id, destination, "error", last_error)
        await log_event(session, "POST_ERROR", last_error, "ERROR")
