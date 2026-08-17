from aiogram import Router, F
from aiogram.types import Message
from sqlalchemy import select
from app.db import GroupSetting, GroupMessage

class GroupBot:
    def __init__(self, dp, db, ai_engine):
        self.db = db
        self.ai_engine = ai_engine
        self.router = Router()
        dp.include_router(self.router)
        self.register()

    def register(self):
        @self.router.message(F.text)
        async def on_message(message: Message):
            if not message.chat or message.chat.type not in {"group", "supergroup"}:
                return
            if not message.from_user or message.from_user.is_bot:
                return

            async with self.db.session() as s:
                gs = (await s.execute(
                    select(GroupSetting).where(GroupSetting.chat_id == message.chat.id)
                )).scalar_one_or_none()
                if not gs or not gs.enabled:
                    return

                text = message.text or ""
                mode = gs.reply_mode
                mentioned = message.entities and any(
                    getattr(e, "type", "") == "mention" for e in message.entities
                )
                is_reply_to_bot = bool(
                    message.reply_to_message and message.reply_to_message.from_user
                    and message.reply_to_message.from_user.is_bot
                )
                is_command = text.startswith("/ask")
                question = text.endswith("?") or text.startswith(("what ", "why ", "how ", "কি ", "কেন ", "কীভাবে "))

                should = (
                    mode == "always"
                    or (mode == "question_only" and question)
                    or (mode == "mention_only" and mentioned)
                    or (mode == "reply_to_bot" and is_reply_to_bot)
                    or (mode == "ask_command" and is_command)
                )
                if not should:
                    return

                clean = text[4:].strip() if is_command else text
                s.add(GroupMessage(chat_id=message.chat.id, user_id=message.from_user.id, text=clean))
                await s.commit()

            answer = await self.ai_engine.answer(message.chat.id, clean)
            if answer:
                await message.reply(answer)
