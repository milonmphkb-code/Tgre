import logging
from aiogram import Bot, Dispatcher, Router, F
from aiogram.filters import Command
from aiogram.types import Message
from sqlalchemy import select, delete

from app.db import (
    Admin, BotConfig, SourceChannel, Mapping, FilterSetting,
    Keyword, Replacement, GroupSetting, AppLog
)
from app.services import get_stats

log = logging.getLogger(__name__)

class AdminBot:
    def __init__(self, settings, db, ai_engine):
        self.settings = settings
        self.db = db
        self.ai_engine = ai_engine
        self.bot = Bot(settings.bot_token)
        self.dp = Dispatcher()
        self.router = Router()
        self.dp.include_router(self.router)
        self._routes()
        self._inline_routes()

    def authorized(self, message: Message) -> bool:
        return bool(message.from_user and message.from_user.id in self.settings.admin_ids)

    async def reply_auth(self, message):
        if not self.authorized(message):
            await message.answer("Unauthorized.")
            return False
        return True

    def _routes(self):
        r = self.router

        @r.message(Command("start"))
        async def start(message: Message):
            if not await self.reply_auth(message): return
            await message.answer("🤖 Bot online. /help দিয়ে commands দেখুন.")

        @r.message(Command("help"))
        async def help_cmd(message: Message):
            if not await self.reply_auth(message): return
            await message.answer(
                "/panel\n/status\n/setmychannel <chat_id>\n/addsource <chat_id> [name]\n"
                "/removesource <chat_id>\n/sources\n/addmapping <source_id> <destination_chat_id>\n"
                "/mappings\n/deletemapping <mapping_id>\n/setdelay <source_id> <seconds>\n"
                "/setfilter <source_id> username|phone|email|telegram_link|user_id on|off\n"
                "/addblacklist <source_id> <keyword>\n/addwhitelist <source_id> <keyword>\n"
                "/addreplace <source_id> <old> => <new>\n/settemplate <source_id> <template>\n"
                "/addgroup <chat_id>\n/groupon <chat_id>\n/groupoff <chat_id>\n/setprompt <chat_id> <prompt>\n"
                "/stats\n/logs\n/backup"
            )

        @r.message(Command("status"))
        async def status(message: Message):
            if not await self.reply_auth(message): return
            async with self.db.session() as s:
                c = (await s.execute(select(BotConfig).where(BotConfig.id == 1))).scalar_one()
                sources = len((await s.execute(select(SourceChannel))).scalars().all())
                groups = len((await s.execute(select(GroupSetting))).scalars().all())
            await message.answer(f"ONLINE\nMy Channel: {c.my_channel_id}\nSources: {sources}\nAI Groups: {groups}")

        @r.message(Command("setmychannel"))
        async def setmychannel(message: Message):
            if not await self.reply_auth(message): return
            parts = message.text.split(maxsplit=1)
            if len(parts) != 2:
                await message.answer("Usage: /setmychannel <chat_id>"); return
            async with self.db.session() as s:
                c = (await s.execute(select(BotConfig).where(BotConfig.id == 1))).scalar_one()
                c.my_channel_id = int(parts[1])
                await s.commit()
            await message.answer("My Channel saved.")

        @r.message(Command("addsource"))
        async def addsource(message: Message):
            if not await self.reply_auth(message): return
            p = message.text.split(maxsplit=2)
            if len(p) < 2:
                await message.answer("Usage: /addsource <chat_id> [name]"); return
            cid, name = int(p[1]), p[2] if len(p) > 2 else str(p[1])
            async with self.db.session() as s:
                source = (await s.execute(select(SourceChannel).where(SourceChannel.chat_id == cid))).scalar_one_or_none()
                if not source:
                    source = SourceChannel(chat_id=cid, name=name)
                    s.add(source)
                    await s.flush()
                    s.add(FilterSetting(source_id=source.id))
                await s.commit()
            await message.answer(f"Source added: {cid}")

        @r.message(Command("removesource"))
        async def removesource(message: Message):
            if not await self.reply_auth(message): return
            p = message.text.split()
            if len(p) != 2:
                await message.answer("Usage: /removesource <chat_id>"); return
            async with self.db.session() as s:
                source = (await s.execute(select(SourceChannel).where(SourceChannel.chat_id == int(p[1])))).scalar_one_or_none()
                if not source:
                    await message.answer("Not found."); return
                await s.delete(source)
                await s.commit()
            await message.answer("Source removed.")

        @r.message(Command("sources"))
        async def sources(message: Message):
            if not await self.reply_auth(message): return
            async with self.db.session() as s:
                rows = (await s.execute(select(SourceChannel))).scalars().all()
            await message.answer("\n".join(f"{x.id}: {x.chat_id} | {x.name} | {'ON' if x.enabled else 'OFF'}" for x in rows) or "No sources.")

        @r.message(Command("addmapping"))
        async def addmapping(message: Message):
            if not await self.reply_auth(message): return
            p = message.text.split()
            if len(p) != 3:
                await message.answer("Usage: /addmapping <source_id> <destination_chat_id>"); return
            async with self.db.session() as s:
                source = (await s.execute(select(SourceChannel).where(SourceChannel.id == int(p[1])))).scalar_one_or_none()
                if not source:
                    await message.answer("Source ID not found."); return
                s.add(Mapping(source_id=source.id, destination_chat_id=int(p[2])))
                await s.commit()
            await message.answer("Mapping added.")

        @r.message(Command("mappings"))
        async def mappings(message: Message):
            if not await self.reply_auth(message): return
            async with self.db.session() as s:
                rows = (await s.execute(select(Mapping))).scalars().all()
            await message.answer("\n".join(f"{x.id}: source={x.source_id} -> {x.destination_chat_id} | {'ON' if x.enabled else 'OFF'}" for x in rows) or "No mappings.")

        @r.message(Command("deletemapping"))
        async def deletemapping(message: Message):
            if not await self.reply_auth(message): return
            p = message.text.split()
            if len(p) != 2: await message.answer("Usage: /deletemapping <mapping_id>"); return
            async with self.db.session() as s:
                m = await s.get(Mapping, int(p[1]))
                if not m: await message.answer("Not found."); return
                await s.delete(m); await s.commit()
            await message.answer("Mapping deleted.")

        @r.message(Command("setdelay"))
        async def setdelay(message: Message):
            if not await self.reply_auth(message): return
            p = message.text.split()
            if len(p) != 3: await message.answer("Usage: /setdelay <source_id> <seconds>"); return
            async with self.db.session() as s:
                rows = (await s.execute(select(Mapping).where(Mapping.source_id == int(p[1])))).scalars().all()
                for m in rows: m.delay_seconds = max(0, int(p[2]))
                await s.commit()
            await message.answer("Delay updated for source mappings.")

        @r.message(Command("setfilter"))
        async def setfilter(message: Message):
            if not await self.reply_auth(message): return
            p = message.text.split()
            if len(p) != 4: await message.answer("Usage: /setfilter <source_id> <field> on|off"); return
            field, value = p[2], p[3].lower() == "on"
            allowed = {"username","phone","email","telegram_link","user_id"}
            if field not in allowed: await message.answer("Invalid filter."); return
            async with self.db.session() as s:
                fs = (await s.execute(select(FilterSetting).where(FilterSetting.source_id == int(p[1])))).scalar_one_or_none()
                if not fs: await message.answer("Source filter not initialized."); return
                setattr(fs, field, value)
                await s.commit()
            await message.answer("Filter updated.")

        @r.message(Command("addblacklist"))
        async def addblacklist(message: Message):
            await self._keyword(message, "black")

        @r.message(Command("addwhitelist"))
        async def addwhitelist(message: Message):
            await self._keyword(message, "white")

        @r.message(Command("addreplace"))
        async def addreplace(message: Message):
            if not await self.reply_auth(message): return
            raw = message.text.split(maxsplit=2)
            if len(raw) != 3 or "=>" not in raw[2]:
                await message.answer("Usage: /addreplace <source_id> <old> => <new>"); return
            old, new = [x.strip() for x in raw[2].split("=>", 1)]
            async with self.db.session() as s:
                s.add(Replacement(source_id=int(raw[1]), old_text=old, new_text=new))
                await s.commit()
            await message.answer("Replacement added.")

        @r.message(Command("settemplate"))
        async def settemplate(message: Message):
            if not await self.reply_auth(message): return
            raw = message.text.split(maxsplit=2)
            if len(raw) != 3: await message.answer("Usage: /settemplate <source_id> <template>"); return
            async with self.db.session() as s:
                rows = (await s.execute(select(Mapping).where(Mapping.source_id == int(raw[1])))).scalars().all()
                for m in rows: m.template = raw[2]
                await s.commit()
            await message.answer("Template updated.")

        @r.message(Command("addgroup"))
        async def addgroup(message: Message):
            if not await self.reply_auth(message): return
            p = message.text.split()
            if len(p) != 2: await message.answer("Usage: /addgroup <chat_id>"); return
            async with self.db.session() as s:
                g = (await s.execute(select(GroupSetting).where(GroupSetting.chat_id == int(p[1])))).scalar_one_or_none()
                if not g: s.add(GroupSetting(chat_id=int(p[1])))
                await s.commit()
            await message.answer("AI group added.")

        @r.message(Command("groupon"))
        async def groupon(message: Message):
            await self._group_toggle(message, True)

        @r.message(Command("groupoff"))
        async def groupoff(message: Message):
            await self._group_toggle(message, False)

        @r.message(Command("setprompt"))
        async def setprompt(message: Message):
            if not await self.reply_auth(message): return
            p = message.text.split(maxsplit=2)
            if len(p) != 3: await message.answer("Usage: /setprompt <chat_id> <prompt>"); return
            async with self.db.session() as s:
                g = (await s.execute(select(GroupSetting).where(GroupSetting.chat_id == int(p[1])))).scalar_one_or_none()
                if not g: await message.answer("Group not found."); return
                g.prompt = p[2]
                await s.commit()
            await message.answer("Prompt updated.")

        @r.message(Command("stats"))
        async def stats(message: Message):
            if not await self.reply_auth(message): return
            async with self.db.session() as s:
                x = await get_stats(s)
            await message.answer("\n".join(f"{k}: {v}" for k,v in x.items()))

        @r.message(Command("logs"))
        async def logs(message: Message):
            if not await self.reply_auth(message): return
            async with self.db.session() as s:
                rows = (await s.execute(select(AppLog).order_by(AppLog.id.desc()).limit(15))).scalars().all()
            await message.answer("\n".join(f"{x.created_at} | {x.level} | {x.event} | {x.details[:100]}" for x in rows) or "No logs.")

        @r.message(Command("backup"))
        async def backup(message: Message):
            if not await self.reply_auth(message): return
            await message.answer("Use the included backup script: `python -m app.backup`")

    async def _keyword(self, message: Message, kind: str):
        if not await self.reply_auth(message): return
        p = message.text.split(maxsplit=2)
        if len(p) != 3: await message.answer(f"Usage: /add{kind}list <source_id> <keyword>"); return
        async with self.db.session() as s:
            s.add(Keyword(source_id=int(p[1]), word=p[2], kind=kind))
            await s.commit()
        await message.answer(f"{kind}list keyword added.")

    async def _group_toggle(self, message: Message, enabled: bool):
        if not await self.reply_auth(message): return
        p = message.text.split()
        if len(p) != 2: await message.answer("Usage: /groupon <chat_id>"); return
        async with self.db.session() as s:
            g = (await s.execute(select(GroupSetting).where(GroupSetting.chat_id == int(p[1])))).scalar_one_or_none()
            if not g: await message.answer("Group not found."); return
            g.enabled = enabled
            await s.commit()
        await message.answer("Group AI " + ("ON" if enabled else "OFF"))

    async def run(self):
        await self.dp.start_polling(self.bot, handle_signals=True)


    def _inline_routes(self):
        from aiogram.types import CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
        from sqlalchemy import select, update, delete
        from app.db import SourceChannel, Mapping, GroupSetting, FilterSetting, Keyword, Replacement, BotConfig

        def kb(rows):
            return InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text=t, callback_data=c) for t, c in row]
                for row in rows
            ])

        async def menu(call):
            await call.message.edit_text(
                "🤖 ADMIN CONTROL PANEL\n\nসব সেটিংস Bot-এর ভিতর থেকেই Handle করুন।",
                reply_markup=kb([
                    [("📡 Channel Settings", "menu:channel"), ("🤖 AI Groups", "menu:ai")],
                    [("📝 Post Settings", "menu:post"), ("🛡️ Filters", "menu:filter")],
                    [("⏱️ Delay / Schedule", "menu:schedule"), ("📋 Queue", "menu:queue")],
                    [("📊 Statistics", "menu:stats"), ("📝 Logs", "menu:logs")],
                    [("👮 Admins", "menu:admins"), ("💾 Backup", "menu:backup")],
                    [("❤️ Health", "menu:health"), ("⚙️ Bot Control", "menu:control")],
                ])
            )

        @self.router.message(Command("panel"))
        async def panel(message: Message):
            if not await self.reply_auth(message): return
            await message.answer(
                "🤖 ADMIN CONTROL PANEL",
                reply_markup=kb([
                    [("📡 Channel Settings", "menu:channel"), ("🤖 AI Groups", "menu:ai")],
                    [("📝 Post Settings", "menu:post"), ("🛡️ Filters", "menu:filter")],
                    [("⏱️ Delay / Schedule", "menu:schedule"), ("📋 Queue", "menu:queue")],
                    [("📊 Statistics", "menu:stats"), ("📝 Logs", "menu:logs")],
                    [("👮 Admins", "menu:admins"), ("💾 Backup", "menu:backup")],
                    [("❤️ Health", "menu:health"), ("⚙️ Bot Control", "menu:control")],
                ])
            )

        @self.router.callback_query(F.data.startswith("menu:"))
        async def menus(call: CallbackQuery):
            if not call.from_user or call.from_user.id not in self.settings.admin_ids:
                await call.answer("Unauthorized", show_alert=True); return
            section = call.data.split(":",1)[1]
            if section == "channel":
                text = "📡 CHANNEL SETTINGS"
                buttons = [
                    [("🏠 My Channel", "ch:my"), ("➕ Add Source", "ch:add")],
                    [("📋 Sources", "ch:list"), ("🔗 Mappings", "ch:maps")],
                    [("🔄 Source ON/OFF", "ch:toggle"), ("⏸️ Pause/Resume", "ch:pause")],
                ]
            elif section == "ai":
                text = "🤖 AI GROUP SETTINGS"
                buttons = [
                    [("📋 Groups", "ai:list"), ("➕ Add Group", "ai:add")],
                    [("🟢 AI ON", "ai:on"), ("🔴 AI OFF", "ai:off")],
                    [("💬 Reply Mode", "ai:mode"), ("🧠 Prompt", "ai:prompt")],
                    [("🎨 Style / Length", "ai:style"), ("🧾 Context", "ai:context")],
                    [("👋 Welcome", "ai:welcome")],
                ]
            elif section == "post":
                text = "📝 POST SETTINGS"
                buttons = [
                    [("📝 Template", "post:template"), ("🧹 Cleaner", "post:clean")],
                    [("✏️ Replacement", "post:replace"), ("🔍 Preview/Test", "post:test")],
                ]
            elif section == "filter":
                text = "🛡️ FILTER & PRIVACY"
                buttons = [
                    [("👤 Personal Data", "filter:personal")],
                    [("✅ Whitelist", "filter:white"), ("🚫 Blacklist", "filter:black")],
                    [("🔗 Telegram Link", "filter:link"), ("📞 Phone/Email", "filter:contact")],
                ]
            elif section == "schedule":
                text = "⏱️ DELAY / SCHEDULE"
                buttons = [
                    [("⚡ Instant", "sch:instant"), ("⏱️ Set Delay", "sch:delay")],
                    [("📅 Schedule ON/OFF", "sch:onoff"), ("🕐 Time Window", "sch:window")],
                ]
            elif section == "queue":
                text = "📋 QUEUE CONTROL"
                buttons = [
                    [("📊 Queue Status", "queue:status")],
                    [("⏸️ Pause", "queue:pause"), ("▶️ Resume", "queue:resume")],
                    [("🗑️ Clear", "queue:clear")],
                ]
            elif section == "stats":
                async with self.db.session() as db:
                    x = await get_stats(db)
                text = "📊 STATISTICS\n\n" + "\n".join(f"• {k}: {v}" for k,v in x.items())
                buttons = []
            elif section == "logs":
                async with self.db.session() as db:
                    rows = (await db.execute(select(AppLog).order_by(AppLog.id.desc()).limit(10))).scalars().all()
                text = "📝 RECENT LOGS\n\n" + ("\n".join(f"{x.event}: {x.details[:80]}" for x in rows) or "No logs.")
                buttons = []
            elif section == "admins":
                async with self.db.session() as db:
                    rows = (await db.execute(select(Admin))).scalars().all()
                text = "👮 ADMINS\n\n" + ("\n".join(f"{x.user_id} — {x.role}" for x in rows) or "No database admins.")
                buttons = [[("➕ Add Admin", "admin:add"), ("➖ Remove Admin", "admin:remove")]]
            elif section == "backup":
                text = "💾 BACKUP & RESTORE"
                buttons = [[("💾 Create Backup", "backup:create"), ("♻️ Restore Info", "backup:restore")]]
            elif section == "health":
                text = "❤️ HEALTH\n\n🟢 Bot process: Online\n🟢 Database: Initialized\n🟢 Admin panel: Online"
                buttons = []
            else:
                text = "⚙️ BOT CONTROL"
                buttons = [
                    [("🟢 Status", "control:status"), ("🧪 Test Mode", "control:test")],
                    [("🔔 Notifications", "control:notify")],
                ]
            buttons.append([("⬅️ Main Menu", "back:main")])
            await call.message.edit_text(text, reply_markup=kb(buttons))
            await call.answer()

        @self.router.callback_query(F.data == "back:main")
        async def back(call: CallbackQuery):
            if call.from_user.id not in self.settings.admin_ids:
                await call.answer("Unauthorized", show_alert=True); return
            await menu(call)
            await call.answer()

        @self.router.callback_query(F.data == "ch:my")
        async def my_channel(call: CallbackQuery):
            async with self.db.session() as db:
                c = (await db.execute(select(BotConfig).where(BotConfig.id == 1))).scalar_one()
            await call.message.edit_text(
                f"🏠 MY CHANNEL\n\nCurrent: {c.my_channel_id or 'Not set'}\n\n"
                "Change করতে command ব্যবহার করুন:\n/setmychannel <chat_id>",
                reply_markup=kb([[("⬅️ Channel Settings", "menu:channel")]])
            )
            await call.answer()

        @self.router.callback_query(F.data == "ch:list")
        async def source_list(call: CallbackQuery):
            async with self.db.session() as db:
                rows = (await db.execute(select(SourceChannel))).scalars().all()
            text = "📋 SOURCE CHANNELS\n\n" + (
                "\n".join(f"#{x.id} | {x.chat_id} | {x.name} | {'ON' if x.enabled else 'OFF'} | {'PAUSED' if x.paused else 'RUN'}" for x in rows)
                or "No sources"
            )
            await call.message.edit_text(text, reply_markup=kb([[("➕ Add Source", "ch:add"), ("⬅️ Back", "menu:channel")]]))
            await call.answer()

        @self.router.callback_query(F.data == "ch:maps")
        async def maps(call: CallbackQuery):
            async with self.db.session() as db:
                rows = (await db.execute(select(Mapping))).scalars().all()
            text = "🔗 SOURCE → DESTINATION\n\n" + (
                "\n".join(f"#{x.id} | source={x.source_id} → {x.destination_chat_id} | {'ON' if x.enabled else 'OFF'}" for x in rows)
                or "No mappings"
            )
            await call.message.edit_text(text, reply_markup=kb([[("➕ Add Mapping", "ch:addmap"), ("⬅️ Back", "menu:channel")]]))
            await call.answer()

        @self.router.callback_query(F.data == "ai:list")
        async def ai_list(call: CallbackQuery):
            async with self.db.session() as db:
                rows = (await db.execute(select(GroupSetting))).scalars().all()
            text = "🤖 AI GROUPS\n\n" + (
                "\n".join(f"{x.chat_id} | {'ON' if x.enabled else 'OFF'} | {x.reply_mode} | {x.style}/{x.length}" for x in rows)
                or "No AI groups"
            )
            await call.message.edit_text(text, reply_markup=kb([[("➕ Add Group", "ai:add"), ("⬅️ Back", "menu:ai")]]))
            await call.answer()

        @self.router.callback_query(F.data == "queue:status")
        async def queue_status(call: CallbackQuery):
            from app.db import QueueItem
            async with self.db.session() as db:
                rows = (await db.execute(select(QueueItem).where(QueueItem.status == "pending"))).scalars().all()
            await call.message.edit_text(
                f"📋 QUEUE STATUS\n\nPending: {len(rows)}",
                reply_markup=kb([[("⏸️ Pause", "queue:pause"), ("▶️ Resume", "queue:resume")],
                                 [("🗑️ Clear", "queue:clear")], [("⬅️ Back", "menu:queue")]])
            )
            await call.answer()

        @self.router.callback_query(F.data == "queue:clear")
        async def queue_clear(call: CallbackQuery):
            from app.db import QueueItem
            async with self.db.session() as db:
                rows = (await db.execute(select(QueueItem).where(QueueItem.status == "pending"))).scalars().all()
                for x in rows: x.status = "cleared"
                await db.commit()
            await call.answer("Queue cleared", show_alert=True)
            await call.message.edit_text("📋 Queue cleared.", reply_markup=kb([[("⬅️ Back", "menu:queue")]]))

        @self.router.callback_query(F.data.startswith("ai:"))
        async def ai_actions(call: CallbackQuery):
            action = call.data.split(":",1)[1]
            if action in {"add","on","off","mode","prompt","style","context","welcome"}:
                await call.answer(
                    "এই setting-এর জন্য group ID/message input প্রয়োজন। "
                    "বর্তমানে command দিয়ে value দিন: /addgroup, /groupon, /groupoff, /setprompt",
                    show_alert=True
                )
            else:
                await call.answer()

        @self.router.callback_query(F.data.startswith("ch:"))
        async def channel_actions(call: CallbackQuery):
            action = call.data.split(":",1)[1]
            if action in {"add","addmap","toggle","pause"}:
                await call.answer("এই action-এর জন্য Channel ID/Source ID input প্রয়োজন। Command ব্যবহার করুন।", show_alert=True)
            else:
                await call.answer()

        @self.router.callback_query(F.data.startswith(("post:","filter:","sch:","admin:","backup:","control:")))
        async def generic_actions(call: CallbackQuery):
            await call.answer(
                "এই operation-এর input value প্রয়োজন। বিস্তারিত command /help-এ আছে।",
                show_alert=True
            )
