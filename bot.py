"""
Admin-facing Telegram bot: commands + inline button panel.
Also owns the application lifecycle and starts the ChannelMonitor alongside it.
"""
import json
import logging

from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    ContextTypes,
)

import config
import database as db
from monitor import ChannelMonitor

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger("bot")

monitor: ChannelMonitor | None = None


def admin_only(func):
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
        user = update.effective_user
        if not user or not config.is_admin(user.id):
            if update.message:
                await update.message.reply_text("⛔ You are not authorized to use this bot.")
            return
        return await func(update, context)

    return wrapper


MAIN_MENU = InlineKeyboardMarkup(
    [
        [InlineKeyboardButton("➕ Add Source", callback_data="help_addsource"),
         InlineKeyboardButton("📋 Source List", callback_data="sources")],
        [InlineKeyboardButton("🎯 Destination", callback_data="help_setdestination"),
         InlineKeyboardButton("⚙️ Settings", callback_data="help_settings")],
        [InlineKeyboardButton("⏱ Delay", callback_data="help_delay"),
         InlineKeyboardButton("🔍 Filters", callback_data="help_filter")],
        [InlineKeyboardButton("▶️ Resume", callback_data="resume_all"),
         InlineKeyboardButton("⏸ Pause", callback_data="pause_all")],
        [InlineKeyboardButton("📊 Statistics", callback_data="stats"),
         InlineKeyboardButton("🧾 Logs", callback_data="logs")],
    ]
)


# ---------------- Basic commands ----------------

@admin_only
async def start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🤖 *Telegram Auto Repost Bot*\n\nUse the menu below or /help for all commands.",
        reply_markup=MAIN_MENU,
        parse_mode="Markdown",
    )


HELP_TEXT = """*Admin Commands*

*Sources*
/addsource <channel_url> — add a source channel
/removesource <source_id> — remove a source
/sources — list all sources with status

*Destination*
/setdestination <source_id> <dest_channel_url_or_@username> — set destination for a source

*Control*
/pause [source_id] — pause a source, or everything if no id
/resume [source_id] — resume a source, or everything if no id
/status — overall bot status

*Filtering & Editing*
/filter <source_id> <whitelist|blacklist|none> <kw1,kw2,...>
/pdfilter <source_id> <on|off> — personal data filter
/wordremove <source_id> <word1,word2,...>
/wordreplace <source_id> <old1=new1,old2=new2>
/lineremove <source_id> <text1,text2,...> — remove lines containing these
/footer <source_id> <text>
/hashtags <source_id> <#tag1 #tag2>
/delay <source_id> <seconds>

*Monitoring*
/stats — statistics
/logs — recent activity log
/settings <source_id> — show current settings for a source
"""


@admin_only
async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(HELP_TEXT, parse_mode="Markdown")


# ---------------- Source management ----------------

@admin_only
async def addsource_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Usage: /addsource https://t.me/channel_name")
        return
    url = context.args[0]
    source_id = db.add_source(url)
    ok, info = await monitor.resolve_source(source_id)
    if ok:
        await update.message.reply_text(f"✅ Source #{source_id} added: {info}")
        db.add_log("INFO", f"Source added: {url} (#{source_id})")
    else:
        await update.message.reply_text(
            f"⚠️ Source #{source_id} saved but could not be resolved yet: {info}\n"
            f"Make sure the reader account has access to this channel."
        )


@admin_only
async def removesource_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Usage: /removesource <source_id>")
        return
    source_id = int(context.args[0])
    db.remove_source(source_id)
    await update.message.reply_text(f"🗑 Source #{source_id} removed.")
    db.add_log("INFO", f"Source #{source_id} removed.")


@admin_only
async def sources_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await _send_sources_list(update.message)


async def _send_sources_list(message):
    sources = db.list_sources()
    if not sources:
        await message.reply_text("No sources added yet. Use /addsource <url>.")
        return
    lines = []
    for s in sources:
        status = "🟢 active" if s["is_active"] else "🔴 paused"
        dest = db.get_destination(s["destination_id"]) if s["destination_id"] else None
        dest_name = dest["channel_name"] if dest else "not set"
        lines.append(
            f"#{s['id']} — {s['channel_name'] or s['channel_url']}\n"
            f"   status: {status} | destination: {dest_name} | delay: {s['delay_seconds']}s"
        )
    await message.reply_text("\n\n".join(lines))


# ---------------- Destination ----------------

@admin_only
async def setdestination_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if len(context.args) < 2:
        await update.message.reply_text(
            "Usage: /setdestination <source_id> <dest_channel_url_or_@username>"
        )
        return
    source_id = int(context.args[0])
    channel_ref = context.args[1]
    try:
        channel_id, channel_name = await monitor.resolve_destination_channel(channel_ref)
    except Exception as e:
        await update.message.reply_text(
            f"⚠️ Couldn't resolve destination. Make sure the bot is an admin there.\n{e}"
        )
        return
    dest_id = db.add_destination(channel_id, channel_name)
    db.set_source_destination(source_id, dest_id)
    await update.message.reply_text(f"✅ Destination for source #{source_id} set to {channel_name}")
    db.add_log("INFO", f"Destination for source #{source_id} set to {channel_name}")


# ---------------- Pause / resume / status ----------------

@admin_only
async def pause_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if context.args:
        db.set_source_active(int(context.args[0]), False)
        await update.message.reply_text(f"⏸ Source #{context.args[0]} paused.")
    else:
        db.set_state("paused", "1")
        await update.message.reply_text("⏸ Bot paused globally. Use /resume to continue.")
    db.add_log("INFO", "Pause command executed.")


@admin_only
async def resume_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if context.args:
        db.set_source_active(int(context.args[0]), True)
        await update.message.reply_text(f"▶️ Source #{context.args[0]} resumed.")
    else:
        db.set_state("paused", "0")
        await update.message.reply_text("▶️ Bot resumed globally.")
    db.add_log("INFO", "Resume command executed.")


@admin_only
async def status_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    sources = db.list_sources()
    active = sum(1 for s in sources if s["is_active"])
    paused_globally = db.get_state("paused") == "1"
    text = (
        f"*Bot Status*\n"
        f"Global: {'⏸ paused' if paused_globally else '🟢 running'}\n"
        f"Total sources: {len(sources)}\n"
        f"Active sources: {active}\n"
    )
    await update.message.reply_text(text, parse_mode="Markdown")


# ---------------- Filters & text editing ----------------

@admin_only
async def filter_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if len(context.args) < 2:
        await update.message.reply_text(
            "Usage: /filter <source_id> <whitelist|blacklist|none> [kw1,kw2,...]"
        )
        return
    source_id = int(context.args[0])
    mode = context.args[1].lower()
    if mode not in {"whitelist", "blacklist", "none"}:
        await update.message.reply_text("Mode must be whitelist, blacklist, or none.")
        return
    keywords = []
    if len(context.args) > 2:
        keywords = [k.strip() for k in " ".join(context.args[2:]).split(",") if k.strip()]
    db.set_source_keyword_mode(source_id, mode)
    db.set_source_field_json(source_id, "keywords", keywords)
    await update.message.reply_text(f"✅ Filter for source #{source_id} set to {mode} {keywords}")


@admin_only
async def pdfilter_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if len(context.args) < 2 or context.args[1].lower() not in {"on", "off"}:
        await update.message.reply_text("Usage: /pdfilter <source_id> <on|off>")
        return
    source_id = int(context.args[0])
    enabled = context.args[1].lower() == "on"
    db.set_personal_data_filter(source_id, enabled)
    await update.message.reply_text(
        f"✅ Personal data filter for source #{source_id} turned {'ON' if enabled else 'OFF'}."
    )


@admin_only
async def wordremove_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if len(context.args) < 2:
        await update.message.reply_text("Usage: /wordremove <source_id> <word1,word2,...>")
        return
    source_id = int(context.args[0])
    words = [w.strip() for w in " ".join(context.args[1:]).split(",") if w.strip()]
    db.set_source_field_json(source_id, "word_remove", words)
    await update.message.reply_text(f"✅ Word-remove list updated for source #{source_id}: {words}")


@admin_only
async def wordreplace_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if len(context.args) < 2:
        await update.message.reply_text("Usage: /wordreplace <source_id> <old1=new1,old2=new2>")
        return
    source_id = int(context.args[0])
    pairs = " ".join(context.args[1:]).split(",")
    mapping = {}
    for pair in pairs:
        if "=" in pair:
            old, new = pair.split("=", 1)
            mapping[old.strip()] = new.strip()
    db.set_source_field_json(source_id, "word_replace", mapping)
    await update.message.reply_text(f"✅ Word-replace map updated for source #{source_id}: {mapping}")


@admin_only
async def lineremove_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if len(context.args) < 2:
        await update.message.reply_text("Usage: /lineremove <source_id> <text1,text2,...>")
        return
    source_id = int(context.args[0])
    substrings = [s.strip() for s in " ".join(context.args[1:]).split(",") if s.strip()]
    db.set_source_field_json(source_id, "line_remove", substrings)
    await update.message.reply_text(f"✅ Line-remove list updated for source #{source_id}: {substrings}")


@admin_only
async def footer_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if len(context.args) < 2:
        await update.message.reply_text("Usage: /footer <source_id> <text>")
        return
    source_id = int(context.args[0])
    text = " ".join(context.args[1:])
    db.set_source_footer(source_id, text)
    await update.message.reply_text(f"✅ Footer set for source #{source_id}.")


@admin_only
async def hashtags_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if len(context.args) < 2:
        await update.message.reply_text("Usage: /hashtags <source_id> <#tag1 #tag2>")
        return
    source_id = int(context.args[0])
    text = " ".join(context.args[1:])
    db.set_source_hashtags(source_id, text)
    await update.message.reply_text(f"✅ Hashtags set for source #{source_id}.")


@admin_only
async def delay_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if len(context.args) < 2:
        await update.message.reply_text("Usage: /delay <source_id> <seconds>")
        return
    source_id = int(context.args[0])
    seconds = int(context.args[1])
    db.set_source_delay(source_id, seconds)
    await update.message.reply_text(f"✅ Delay for source #{source_id} set to {seconds}s.")


# ---------------- Settings / stats / logs ----------------

@admin_only
async def settings_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Usage: /settings <source_id>")
        return
    source = db.get_source(int(context.args[0]))
    if not source:
        await update.message.reply_text("Source not found.")
        return
    dest = db.get_destination(source["destination_id"]) if source["destination_id"] else None
    text = (
        f"*Settings — source #{source['id']}*\n"
        f"Channel: {source['channel_name'] or source['channel_url']}\n"
        f"Active: {'yes' if source['is_active'] else 'no'}\n"
        f"Destination: {dest['channel_name'] if dest else 'not set'}\n"
        f"Delay: {source['delay_seconds']}s\n"
        f"Personal data filter: {'on' if source['personal_data_filter'] else 'off'}\n"
        f"Keyword mode: {source['keyword_mode']} {json.loads(source['keywords'])}\n"
        f"Word remove: {json.loads(source['word_remove'])}\n"
        f"Word replace: {json.loads(source['word_replace'])}\n"
        f"Line remove: {json.loads(source['line_remove'])}\n"
        f"Footer: {source['footer'] or '-'}\n"
        f"Hashtags: {source['hashtags'] or '-'}\n"
    )
    await update.message.reply_text(text, parse_mode="Markdown")


@admin_only
async def stats_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await _send_stats(update.message)


async def _send_stats(message):
    s = db.get_stats()
    text = (
        "*Statistics*\n"
        f"Total source channels: {s['total_sources']}\n"
        f"Total detected posts: {s['total_detected']}\n"
        f"Total reposted: {s['total_posted']}\n"
        f"Total skipped: {s['total_skipped']}\n"
        f"Total duplicate: {s['total_duplicate']}\n"
        f"Total filtered: {s['total_filtered']}\n"
        f"Total errors: {s['total_errors']}\n"
        f"Today's posts: {s['today_posts']}\n"
        f"Last 7 days: {s['week_posts']}\n"
    )
    await message.reply_text(text, parse_mode="Markdown")


@admin_only
async def logs_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await _send_logs(update.message)


async def _send_logs(message):
    logs = db.recent_logs(15)
    if not logs:
        await message.reply_text("No logs yet.")
        return
    import datetime
    lines = []
    for l in logs:
        ts = datetime.datetime.fromtimestamp(l["created_at"]).strftime("%Y-%m-%d %H:%M")
        lines.append(f"[{ts}] {l['level']}: {l['message']}")
    await message.reply_text("\n".join(lines))


# ---------------- Inline button callbacks ----------------

@admin_only
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data

    if data == "sources":
        await _send_sources_list(query.message)
    elif data == "stats":
        await _send_stats(query.message)
    elif data == "logs":
        await _send_logs(query.message)
    elif data == "pause_all":
        db.set_state("paused", "1")
        await query.message.reply_text("⏸ Bot paused globally.")
    elif data == "resume_all":
        db.set_state("paused", "0")
        await query.message.reply_text("▶️ Bot resumed globally.")
    elif data.startswith("help_"):
        topic = data.replace("help_", "")
        hints = {
            "addsource": "Send: /addsource https://t.me/channel_name",
            "setdestination": "Send: /setdestination <source_id> <dest_url_or_@username>",
            "settings": "Send: /settings <source_id>",
            "delay": "Send: /delay <source_id> <seconds>",
            "filter": "Send: /filter <source_id> <whitelist|blacklist|none> <kw1,kw2>",
        }
        await query.message.reply_text(hints.get(topic, "See /help for all commands."))


# ---------------- App wiring ----------------

def build_application() -> Application:
    application = Application.builder().token(config.BOT_TOKEN).build()

    application.add_handler(CommandHandler("start", start_cmd))
    application.add_handler(CommandHandler("help", help_cmd))
    application.add_handler(CommandHandler("addsource", addsource_cmd))
    application.add_handler(CommandHandler("removesource", removesource_cmd))
    application.add_handler(CommandHandler("sources", sources_cmd))
    application.add_handler(CommandHandler("setdestination", setdestination_cmd))
    application.add_handler(CommandHandler("pause", pause_cmd))
    application.add_handler(CommandHandler("resume", resume_cmd))
    application.add_handler(CommandHandler("status", status_cmd))
    application.add_handler(CommandHandler("filter", filter_cmd))
    application.add_handler(CommandHandler("pdfilter", pdfilter_cmd))
    application.add_handler(CommandHandler("wordremove", wordremove_cmd))
    application.add_handler(CommandHandler("wordreplace", wordreplace_cmd))
    application.add_handler(CommandHandler("lineremove", lineremove_cmd))
    application.add_handler(CommandHandler("footer", footer_cmd))
    application.add_handler(CommandHandler("hashtags", hashtags_cmd))
    application.add_handler(CommandHandler("delay", delay_cmd))
    application.add_handler(CommandHandler("settings", settings_cmd))
    application.add_handler(CommandHandler("stats", stats_cmd))
    application.add_handler(CommandHandler("logs", logs_cmd))
    application.add_handler(CallbackQueryHandler(button_handler))

    return application
