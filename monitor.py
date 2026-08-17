"""
Source channel monitor.

Uses a Telethon *user* client to listen for new messages in source channels
(a bot account cannot receive updates from a channel it isn't a member/admin of,
so a logged-in user session is used purely for reading).

Posting to the destination channel is done through the official python-telegram-bot
Bot instance, which must be added as admin in the destination channel.
"""
import asyncio
import logging

from telethon import TelegramClient, events

import config
import database as db
import filters

logger = logging.getLogger("monitor")


class ChannelMonitor:
    def __init__(self, bot):
        """bot: telegram.Bot instance used to post into destination channels."""
        self.bot = bot
        self.client = TelegramClient(config.SESSION_NAME, config.API_ID, config.API_HASH)

    async def start(self):
        await self.client.start()
        await self._sync_sources()
        self.client.add_event_handler(self._on_new_message, events.NewMessage())
        logger.info("Channel monitor started, listening for new posts.")
        db.add_log("INFO", "Monitor started and listening to source channels.")

    async def stop(self):
        await self.client.disconnect()

    async def _sync_sources(self):
        """Resolve any source with missing channel_id (newly added by URL)."""
        for source in db.list_sources():
            if source["channel_id"] is None:
                try:
                    entity = await self.client.get_entity(source["channel_url"])
                    db.update_source_channel_info(
                        source["id"], entity.id, getattr(entity, "title", str(entity.id))
                    )
                    logger.info(f"Resolved source #{source['id']} -> {entity.id}")
                except Exception as e:
                    logger.error(f"Could not resolve source {source['channel_url']}: {e}")
                    db.add_log("ERROR", f"Could not resolve source {source['channel_url']}: {e}")

    async def resolve_source(self, source_id: int):
        """Called right after a new source is added via the admin panel."""
        source = db.get_source(source_id)
        try:
            entity = await self.client.get_entity(source["channel_url"])
            db.update_source_channel_info(
                source_id, entity.id, getattr(entity, "title", str(entity.id))
            )
            return True, getattr(entity, "title", str(entity.id))
        except Exception as e:
            return False, str(e)

    async def resolve_destination_channel(self, channel_ref: str):
        """Resolve + register a destination channel from a url/username, using the bot."""
        chat = await self.bot.get_chat(channel_ref)
        return chat.id, chat.title

    async def _on_new_message(self, event):
        if db.get_state("paused") == "1":
            return

        chat_id = event.chat_id
        source = db.get_source_by_channel_id(chat_id)
        if not source or not source["is_active"]:
            return

        message = event.message

        # Text-only: ignore anything with media
        if message.media is not None:
            db.record_post(source["id"], message.id, "-", None, "skipped")
            return

        raw_text = message.message or ""
        if not raw_text.strip():
            return

        if db.was_already_processed(source["id"], message.id):
            return

        if not source["destination_id"]:
            db.add_log("ERROR", f"Source #{source['id']} has no destination set, skipping post.")
            return

        try:
            await self._process_and_post(source, message.id, raw_text)
        except Exception as e:
            logger.exception("Error processing message")
            db.record_post(source["id"], message.id, "-", None, "failed")
            db.add_log("ERROR", f"Post failed. Source: {source['channel_name']} Reason: {e}")
            await self._notify_admins(f"⚠️ Post failed from source #{source['id']}: {e}")

    async def _process_and_post(self, source, message_id, raw_text):
        final_text = filters.process_text(raw_text, source)

        import json
        keywords = json.loads(source["keywords"] or "[]")
        if not filters.passes_keyword_filter(final_text, source["keyword_mode"], keywords):
            db.record_post(source["id"], message_id, "-", None, "filtered")
            db.add_log("INFO", f"Post filtered by keyword rule. Source #{source['id']}")
            return

        chash = filters.content_hash(final_text)
        if db.is_duplicate(chash):
            db.record_post(source["id"], message_id, chash, None, "duplicate")
            db.add_log("INFO", f"Duplicate detected, skipped. Source #{source['id']}")
            return

        delay = source["delay_seconds"] or 0

        async def do_post():
            if delay:
                await asyncio.sleep(delay)
            destination = db.get_destination(source["destination_id"])
            if not destination:
                db.add_log("ERROR", f"Destination missing for source #{source['id']}")
                return
            sent = await self.bot.send_message(chat_id=destination["channel_id"], text=final_text)
            db.record_post(source["id"], message_id, chash, sent.message_id, "posted")
            db.add_log(
                "INFO",
                f"Posted successfully. Source #{source['id']} -> Destination #{destination['id']}",
            )

        asyncio.create_task(do_post())

    async def _notify_admins(self, text: str):
        for admin_id in config.ADMIN_IDS:
            try:
                await self.bot.send_message(chat_id=admin_id, text=text)
            except Exception:
                pass
